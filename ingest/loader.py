"""Load raw API responses into DuckDB.

We keep the ingestion dead simple: fetch departures, flatten a few useful
fields, and append them to a `raw.departures` table. dbt does the rest.
"""

from __future__ import annotations

import datetime as dt
import json
from typing import Any

import duckdb

from ingest.config import settings


def _connect() -> duckdb.DuckDBPyConnection:
    settings.duckdb_path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(settings.duckdb_path))


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
            raw              JSON
        );
        """
    )


def _parse_ts(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    # API returns ISO 8601 with timezone, e.g. 2024-01-01T12:00:00+01:00
    return dt.datetime.fromisoformat(value)


def load_departures(
    station_id: str,
    station_name: str,
    payload: dict[str, Any],
) -> int:
    """Flatten a departures payload and append rows. Returns row count."""
    rows = payload.get("departures", payload) if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        rows = []

    loaded_at = dt.datetime.now(dt.timezone.utc)
    records = []
    for d in rows:
        line = d.get("line") or {}
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
                json.dumps(d),
            )
        )

    with _connect() as con:
        _ensure_schema(con)
        if records:
            con.executemany(
                """
                INSERT INTO raw.departures VALUES
                (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                records,
            )
    return len(records)
