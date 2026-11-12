"""Artig HTTP-klient: ärlig User-Agent och max ett anrop per sekund per domän."""
from __future__ import annotations

import logging
import time
from typing import Callable
from urllib.parse import urlsplit

import httpx

USER_AGENT = "bostadsbevakning/0.1 (privat bevakning av lediga hyreslagenheter; max 1 anrop/s)"
log = logging.getLogger(__name__)


class PoliteClient:
    def __init__(
        self,
        min_interval: float = 1.1,
        timeout: float = 30.0,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.min_interval = min_interval
        self._client = client or httpx.Client(
            headers={"User-Agent": USER_AGENT, "Accept-Language": "sv-SE"},
            timeout=timeout,
            follow_redirects=True,
        )
        self._sleep = sleep
        self._clock = clock
        self._last: dict[str, float] = {}

    def _throttle(self, url: str) -> None:
        host = urlsplit(url).hostname or ""
        last = self._last.get(host)
        if last is not None:
            wait = self.min_interval - (self._clock() - last)
            if wait > 0:
                self._sleep(wait)
        self._last[host] = self._clock()

    def _request(self, method: str, url: str, **kw) -> httpx.Response:
        for attempt in (1, 2):
            self._throttle(url)
            try:
                resp = self._client.request(method, url, **kw)
                if resp.status_code < 500 or attempt == 2:
                    resp.raise_for_status()
                    return resp
                log.warning("%s %s gav %s, försöker igen", method, url, resp.status_code)
            except httpx.TransportError as e:
                if attempt == 2:
                    raise
                log.warning("%s %s misslyckades (%s), försöker igen", method, url, e)
            self._sleep(2.0)
        raise AssertionError("unreachable")

    def get_text(self, url: str) -> str:
        return self._request("GET", url).text

    def post_json(self, url: str, payload: dict) -> None:
        self._request("POST", url, json=payload)
