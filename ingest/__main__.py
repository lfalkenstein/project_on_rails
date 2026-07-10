"""CLI entry point.

Normal run (uses ingest_config.yml -> collects every configured station):
    python -m ingest

Override the API for one run:
    python -m ingest --api db

One-off single station (ignores the config list):
    python -m ingest --station "Berlin Hbf"

Preview what a station search resolves to (no data stored):
    python -m ingest --find "Alexanderplatz"
"""

from __future__ import annotations

import argparse

from ingest import station_cache
from ingest.client import TransportClient
from ingest.config import Station, settings
from ingest.loader import load_departures


def _resolve_station(client: TransportClient, search: str) -> tuple[str, str] | None:
    """Resolve a search term to (station_id, station_name), using the cache.

    On a cache hit we skip the /locations call entirely. On a miss we search,
    store the result, and return it. Returns None if nothing matched.
    """
    cached = station_cache.get(settings.api, search)
    if cached:
        return cached["id"], cached["name"]

    matches = client.search_stations(search, results=1)
    if not matches:
        return None
    station = matches[0]
    station_id, station_name = station["id"], station["name"]
    station_cache.put(settings.api, search, station_id, station_name)
    return station_id, station_name


def _run_station(client: TransportClient, search: str) -> None:
    resolved = _resolve_station(client, search)
    if resolved is None:
        print(f"  ! no station found for {search!r}, skipping")
        return
    station_id, station_name = resolved
    payload = client.departures(station_id, duration=settings.duration)
    count = load_departures(station_id, station_name, payload)
    print(f"  + {station_name} (id={station_id}): {count} new observation(s) stored")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch transit departures into DuckDB")
    parser.add_argument("--api", choices=["db", "bvg"], help="Override the API from config")
    parser.add_argument("--station", help="Collect a single station (ignores config list)")
    parser.add_argument("--find", help="Preview station search results, store nothing")
    parser.add_argument(
        "--refresh-stations",
        action="store_true",
        help="Clear the cached station ids and re-resolve them from the API",
    )
    args = parser.parse_args()

    if args.api:
        settings.api = args.api

    if args.refresh_stations:
        station_cache.clear()
        print("Cleared station id cache")

    with TransportClient() as client:
        if args.find:
            for s in client.search_stations(args.find, results=5):
                print(f"  {s['id']}  {s['name']}")
            return

        stations = [Station(search=args.station)] if args.station else settings.stations
        if not stations:
            raise SystemExit("No stations configured. Edit ingest_config.yml or pass --station.")

        print(f"[{settings.api}] collecting {len(stations)} station(s), window={settings.duration}min")
        failures = 0
        for st in stations:
            # Isolate each station: a transient upstream failure (already retried
            # in the client) for one station shouldn't abort collection for the
            # rest. We log it, count it, and keep going.
            try:
                _run_station(client, st.search)
            except Exception as exc:  # noqa: BLE001 - deliberately broad; keep the batch alive
                failures += 1
                print(f"  ! {st.search!r} failed: {exc}")

    print(f"Done -> {settings.duckdb_path}")
    if failures:
        # Non-zero exit so the scheduler log flags the run, but only after every
        # station has had its turn.
        raise SystemExit(f"{failures} of {len(stations)} station(s) failed")


if __name__ == "__main__":
    main()
