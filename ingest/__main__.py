"""CLI entry point:  python -m ingest --station "Berlin Hbf"

Searches for a station by name, pulls upcoming departures, and stores them
in DuckDB under raw.departures.
"""

from __future__ import annotations

import argparse

from ingest.client import TransportClient
from ingest.config import settings
from ingest.loader import load_departures


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch transit departures into DuckDB")
    parser.add_argument("--station", default="Berlin Hbf", help="Station name to search")
    parser.add_argument("--duration", type=int, default=60, help="Look-ahead window in minutes")
    args = parser.parse_args()

    with TransportClient() as client:
        matches = client.search_stations(args.station, results=1)
        if not matches:
            raise SystemExit(f"No station found for {args.station!r}")

        station = matches[0]
        station_id, station_name = station["id"], station["name"]
        print(f"[{settings.api}] Using station {station_name} (id={station_id})")

        payload = client.departures(station_id, duration=args.duration)
        count = load_departures(station_id, station_name, payload)

    print(f"Stored {count} departures in {settings.duckdb_path}")


if __name__ == "__main__":
    main()
