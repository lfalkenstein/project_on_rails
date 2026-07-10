"""Thin client for the transport.rest APIs (Deutsche Bahn / BVG).

Both APIs share the same interface, so a single client works for either one.
Docs: https://v6.db.transport.rest/api.html
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from ingest.config import settings

log = logging.getLogger(__name__)

# Upstream (BVG/DB) occasionally returns transient errors - rate limiting (429)
# or short-lived 5xx blips (502/503/504). These are worth retrying; other 4xx
# (e.g. a bad station id) are not, so we don't retry them.
RETRY_STATUS = frozenset({429, 500, 502, 503, 504})


class TransportClient:
    def __init__(
        self,
        base_url: str | None = None,
        timeout: float = 30.0,
        max_retries: int = 4,
        backoff_base: float = 1.0,
    ) -> None:
        self.base_url = (base_url or settings.base_url).rstrip("/")
        self.max_retries = max_retries
        self.backoff_base = backoff_base
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
        """GET with retry + exponential backoff for transient failures.

        Retries transient HTTP status codes (see RETRY_STATUS) and network-level
        errors (timeouts, connection resets). Permanent errors (e.g. 404) raise
        immediately. Backoff is exponential: backoff_base * 2**attempt seconds.
        """
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = self._client.get(path, params=params)
                if resp.status_code in RETRY_STATUS:
                    resp.raise_for_status()
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as exc:
                # Only retry the transient status codes; re-raise everything else.
                if exc.response.status_code not in RETRY_STATUS:
                    raise
                last_exc = exc
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                last_exc = exc

            if attempt < self.max_retries:
                delay = self.backoff_base * (2 ** attempt)
                log.warning(
                    "transient error on GET %s (attempt %d/%d): %s - retrying in %.1fs",
                    path, attempt + 1, self.max_retries, last_exc, delay,
                )
                time.sleep(delay)

        assert last_exc is not None
        raise last_exc

    def search_stations(self, query: str, results: int = 5) -> list[dict[str, Any]]:
        """Find stations by name.

        The /locations endpoint can also return addresses and POIs, which lack
        the id/name we need. We ask for stops only and defensively filter to
        entries that actually have both fields.
        """
        raw = self._get(
            "/locations",
            query=query,
            results=results,
            stops=True,
            addresses=False,
            poi=False,
        )
        return [loc for loc in raw if loc.get("id") and loc.get("name")]

    def departures(self, station_id: str, duration: int = 60) -> dict[str, Any]:
        """Departures for a station over the next `duration` minutes."""
        return self._get(f"/stops/{station_id}/departures", duration=duration)

    def arrivals(self, station_id: str, duration: int = 60) -> dict[str, Any]:
        """Arrivals for a station over the next `duration` minutes."""
        return self._get(f"/stops/{station_id}/arrivals", duration=duration)
