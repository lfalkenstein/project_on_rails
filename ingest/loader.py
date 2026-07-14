"""Load raw API responses into DuckDB.

raw.departures is an append-only history, but we avoid storing exact repeats:
each row carries a `content_hash` of its departure payload, and we only insert
observations whose hash isn't already present. So if a departure is fetched
again unchanged it's skipped, but if any field changed (e.g. the delay updated)
the new observation is kept. dbt does the final per-departure dedup.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import time
from typing import Any

import duckdb

from ingest.config import settings

log = logging.getLogger(__name__)

# DuckDB is single-writer: opening the file read-write fails while another
# process holds it (a dbt run, a dashboard read, DBeaver...). That contention is
# brief, so we retry with a short exponential backoff instead of dropping the
# batch. Total wait ~15s (0.5+1+2+4+8), which stays well under the 5-min poll
# cadence so a busy moment can't stall the schedule.
CONNECT_RETRIES = 5
CONNECT_BACKOFF = 0.5


def _connect() -> duckdb.DuckDBPyConnection:
    settings.duckdb_path.parent.mkdir(parents=True, exist_ok=True)
    last_exc: duckdb.IOException | None = None
    for attempt in range(CONNECT_RETRIES + 1):
        try:
            return duckdb.connect(str(settings.duckdb_path))
        except duckdb.IOException as exc:
            # Almost always transient lock contention; retry briefly. A genuine
            # IO problem (missing path, disk full) will still raise after the
            # attempts are exhausted.
            last_exc = exc
            if attempt < CONNECT_RETRIES:
                wait = CONNECT_BACKOFF * (2 ** attempt)
                log.warning(
                    "warehouse busy (attempt %d/%d): %s - retrying in %.1fs",
                    attempt + 1, CONNECT_RETRIES, exc, wait,
                )
                time.sleep(wait)
    assert last_exc is not None
    raise last_exc


def _ensure_schema(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("CREATE SCHEMA IF NOT EXISTS raw;")
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS raw.departures (
            loaded_at        TIMESTAMP,
            api              VARCHAR,
            station_id       VARCHAR,
            station_name     VARCHAR,
            trip_id          VARCHAR,
            line_name        VARCHAR,
            line_mode        VARCHAR,
            direction        VARCHAR,
            planned_when     TIMESTAMP,
            actual_when      TIMESTAMP,
            delay_seconds    BIGINT,
            platform         VARCHAR,
            raw              JSON,
            content_hash     VARCHAR
        );
        """
    )
    # Migrate older tables created before content_hash existed.
    con.execute("ALTER TABLE raw.departures ADD COLUMN IF NOT EXISTS content_hash VARCHAR;")


def _parse_ts(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    # API returns ISO 8601 with timezone, e.g. 2024-01-01T12:00:00+01:00
    return dt.datetime.fromisoformat(value)


# Fields that define a *meaningful* change for punctuality analysis. The hash
# is built only from these, so volatile noise (live GPS position, occupancy,
# free-text remarks) does NOT create a new "observation". The full payload is
# still stored in the `raw` column. Widen this list if you later care about
# more fields.
SIGNATURE_FIELDS = (
    "tripId",
    "plannedWhen",
    "when",
    "delay",
    "cancelled",
    "platform",
    "plannedPlatform",
    "direction",
)


def _content_hash(station_id: str, d: dict[str, Any]) -> str:
    """Stable fingerprint of one observation, built from the meaningful fields
    only (see SIGNATURE_FIELDS). Re-fetching a departure whose schedule/delay
    hasn't changed yields the same hash, so it is treated as a duplicate."""
    line = d.get("line") or {}
    signature = {f: d.get(f) for f in SIGNATURE_FIELDS}
    signature["station_id"] = station_id
    signature["line_name"] = line.get("name")
    signature["line_mode"] = line.get("mode")
    payload = json.dumps(signature, sort_keys=True, default=str)
    return hashlib.md5(payload.encode("utf-8")).hexdigest()


def load_departures(
    station_id: str,
    station_name: str,
    payload: dict[str, Any],
) -> int:
    """Flatten a departures payload and insert only new observations.

    Returns the number of rows actually inserted (exact duplicates skipped)."""
    rows = payload.get("departures", payload) if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        rows = []

    loaded_at = dt.datetime.now(dt.timezone.utc)
    records = []
    for d in rows:
        line = d.get("line") or {}
        raw_json = json.dumps(d)
        records.append(
            (
                loaded_at,
                settings.api,
                station_id,
                station_name,
                d.get("tripId"),
                line.get("name"),
                line.get("mode"),
                d.get("direction"),
                _parse_ts(d.get("plannedWhen")),
                _parse_ts(d.get("when")),
                d.get("delay"),
                d.get("platform"),
                raw_json,
                _content_hash(station_id, d),
            )
        )

    if not records:
        return 0

    with _connect() as con:
        _ensure_schema(con)

        # Stage the batch, then insert only rows whose content_hash is new.
        con.execute("CREATE OR REPLACE TEMP TABLE _incoming AS SELECT * FROM raw.departures WHERE 1=0;")
        con.executemany(
            "INSERT INTO _incoming VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            records,
        )

        before = con.execute("SELECT count(*) FROM raw.departures").fetchone()[0]
        con.execute(
            """
            INSERT INTO raw.departures
            SELECT i.* FROM (
                SELECT DISTINCT ON (content_hash) * FROM _incoming
            ) i
            WHERE NOT EXISTS (
                SELECT 1 FROM raw.departures r WHERE r.content_hash = i.content_hash
            );
            """
        )
        after = con.execute("SELECT count(*) FROM raw.departures").fetchone()[0]

    return after - before
