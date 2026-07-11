"""On-disk cache for resolved station IDs.

Resolving a search term (e.g. "Behaimstr.") to a station id via the /locations
endpoint is stable over time - the id doesn't change - but we were doing it on
every run, once per station. That's an extra API call (and an extra failure
surface, e.g. the 503 we hit) per station per cycle.

This cache stores the resolved {id, name} per (api, search) pair in a small JSON
file next to the warehouse, so subsequent runs skip the search entirely. Delete
the file (or use --refresh-stations) to force re-resolution.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ingest.config import settings

CACHE_PATH: Path = settings.duckdb_path.parent / "station_cache.json"


def _key(api: str, search: str) -> str:
    # ids differ per upstream API, so the api is part of the key.
    return f"{api}:{search}"


def _load() -> dict[str, Any]:
    if not CACHE_PATH.exists():
        return {}
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        # A corrupt cache should never break ingestion; just start fresh.
        return {}


def get(api: str, search: str) -> dict[str, str] | None:
    """Return the cached {'id', 'name'} for a search term, or None on a miss."""
    return _load().get(_key(api, search))


def put(api: str, search: str, station_id: str, station_name: str) -> None:
    """Persist a resolved station under (api, search)."""
    data = _load()
    data[_key(api, search)] = {"id": station_id, "name": station_name}
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def clear() -> None:
    """Drop the whole cache (used by --refresh-stations)."""
    CACHE_PATH.unlink(missing_ok=True)
