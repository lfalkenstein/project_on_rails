"""Ad-hoc DuckDB query helper.

Usage:
    python query.py "SELECT * FROM raw.departures LIMIT 10"
    python query.py                # no arg -> lists tables

Runs read-only so it won't block or corrupt the ingest process.
"""

from __future__ import annotations

import sys

import duckdb

DB_PATH = "data/warehouse.duckdb"

DEFAULT_SQL = """
SELECT table_schema, table_name
FROM information_schema.tables
ORDER BY 1, 2
"""


def main() -> None:
    sql = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SQL
    with duckdb.connect(DB_PATH, read_only=True) as con:
        con.sql(sql).show()


if __name__ == "__main__":
    main()
