"""Central configuration loaded from environment / .env."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    api: str
    base_url: str
    duckdb_path: Path

    @classmethod
    def load(cls) -> "Settings":
        api = os.getenv("TRANSPORT_API", "db").lower()
        if api == "bvg":
            base_url = os.getenv("BVG_API_BASE", "https://v6.bvg.transport.rest")
        else:
            base_url = os.getenv("DB_API_BASE", "https://v6.db.transport.rest")

        duckdb_path = PROJECT_ROOT / os.getenv("DUCKDB_PATH", "data/warehouse.duckdb")
        return cls(api=api, base_url=base_url.rstrip("/"), duckdb_path=duckdb_path)


settings = Settings.load()
