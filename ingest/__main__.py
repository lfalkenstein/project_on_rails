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

from ingest.client import TransportClient
from ingest.config import Station, settings
from ingest.loader import load_departures


def _run_station(client: TransportClient, search: str) -> None:
    matches = client.search_stations(search, results=1)
    if not matches:
        print(f"  ! no station found for {search!r}, skipping")
        return
    station = matches[0]
    station_id, station_name = station["id"], station["name"]
    payload = client.departures(station_id, duration=settings.duration)
    count = load_departures(station_id, station_name, payload)
    print(f"  + {station_name} (id={station_id}): stored {count} departures")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch transit departures into DuckDB")
    parser.add_argument("--api", choices=["db", "bvg"], help="Override the API from config")
    parser.add_argument("--station", help="Collect a single station (ignores config list)")
    parser.add_argument("--find", help="Preview station search results, store nothing")
    args = parser.parse_args()

    if args.api:
        settings.api = args.api

    with TransportClient() as client:
        if args.find:
            for s in client.search_stations(args.find, results=5):
                print(f"  {s['id']}  {s['name']}")
            return

        stations = [Station(search=args.station)] if args.station else settings.stations
        if not stations:
            raise SystemExit("No stations configured. Edit ingest_config.yml or pass --station.")

        print(f"[{settings.api}] collecting {len(stations)} station(s), window={settings.duration}min")
        for st in stations:
            _run_station(client, st.search)

    print(f"Done -> {settings.duckdb_path}")


if __name__ == "__main__":
    main()
