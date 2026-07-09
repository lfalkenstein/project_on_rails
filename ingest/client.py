"""Thin client for the transport.rest APIs (Deutsche Bahn / BVG).

Both APIs share the same interface, so a single client works for either one.
Docs: https://v6.db.transport.rest/api.html
"""

from __future__ import annotations

from typing import Any

import httpx

from ingest.config import settings


class TransportClient:
    def __init__(self, base_url: str | None = None, timeout: float = 30.0) -> None:
        self.base_url = (base_url or settings.base_url).rstrip("/")
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            headers={"User-Agent": "project-on-rails (learning project)"},
        )

    def __enter__(self) -> "TransportClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def _get(self, path: str, **params: Any) -> Any:
        resp = self._client.get(path, params=params)
        resp.raise_for_status()
        return resp.json()

    def search_stations(self, query: str, results: int = 5) -> list[dict[str, Any]]:
        """Find stations by name. Returns a list of location objects."""
        return self._get("/locations", query=query, results=results, stops=True)

    def departures(self, station_id: str, duration: int = 60) -> dict[str, Any]:
        """Departures for a station over the next `duration` minutes."""
        return self._get(f"/stops/{station_id}/departures", duration=duration)

    def arrivals(self, station_id: str, duration: int = 60) -> dict[str, Any]:
        """Arrivals for a station over the next `duration` minutes."""
        return self._get(f"/stops/{station_id}/arrivals", duration=duration)
