"""Central configuration.

Two layers:
  * .env            -> machine/secret-ish settings (paths, base URLs)
  * ingest_config.yml -> what to collect (api, stations, duration)

CLI flags override the YAML for one-off runs.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = PROJECT_ROOT / "ingest_config.yml"

API_BASE_URLS = {
    "db": os.getenv("DB_API_BASE", "https://v6.db.transport.rest"),
    "bvg": os.getenv("BVG_API_BASE", "https://v6.bvg.transport.rest"),
}


@dataclass(frozen=True)
class Station:
    search: str


@dataclass
class Settings:
    api: str
    duration: int
    stations: list[Station] = field(default_factory=list)
    duckdb_path: Path = PROJECT_ROOT / "data" / "warehouse.duckdb"

    @property
    def base_url(self) -> str:
        return API_BASE_URLS.get(self.api, API_BASE_URLS["db"]).rstrip("/")

    @classmethod
    def load(cls) -> "Settings":
        data: dict = {}
        if CONFIG_FILE.exists():
            data = yaml.safe_load(CONFIG_FILE.read_text(encoding="utf-8")) or {}

        api = str(data.get("api", os.getenv("TRANSPORT_API", "db"))).lower()
        duration = int(data.get("duration", 60))
        stations = [Station(search=s["search"]) for s in data.get("stations", [])]

        duckdb_path = PROJECT_ROOT / os.getenv("DUCKDB_PATH", "data/warehouse.duckdb")
        return cls(api=api, duration=duration, stations=stations, duckdb_path=duckdb_path)


settings = Settings.load()
