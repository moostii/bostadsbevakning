"""ÖrebroBostäder (ÖBO) – minasidor.obo.se/market/…

Sidan är en Angular-app som hämtar annonserna som JSON. Vi låter en headless
webbläsare besöka den publika sidan som en vanlig besökare och läser JSON-svaret
som sidan själv hämtar – vi anropar aldrig API:t direkt. Bilder/typsnitt blockeras
för att belasta sajten så lite som möjligt.
"""
from __future__ import annotations

import logging
import os
import re
import time
from contextlib import contextmanager
from datetime import datetime
from typing import Callable, Iterator
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

from ..http import USER_AGENT
from ..models import Listing

log = logging.getLogger(__name__)

SITE = "https://minasidor.obo.se"
# Marknader (URL-id -> namn). Senior-, student- och ungdomsbostäder har särskilda krav och ingår inte.
MARKETS = {
    "residential": "Bostad",
    "VJKbFxvkM99GGWCvwXyhWYCX": "Poängfritt – Snabbvalet",
}
PAGE_SIZE = 100
MAX_PAGES = 5
TZ = ZoneInfo("Europe/Stockholm")
BLOCKED_RESOURCES = {"image", "font", "media"}
_DATE_RE = re.compile(r"/Date\((-?\d+)")
_ROOMS_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*rum", re.I)


def _ms_date(value: str | None) -> str | None:
    if not value:
        return None
    m = _DATE_RE.search(value)
    if not m:
        return None
    return datetime.fromtimestamp(int(m.group(1)) / 1000, TZ).date().isoformat()


def _rooms(text: str | None) -> float | None:
    m = _ROOMS_RE.search(text or "")
    return float(m.group(1).replace(",", ".")) if m else None


def _area(location: dict) -> str | None:
    name = ((location.get("area") or {}).get("displayName") or "").strip()
    paths = [(p.get("displayName") or "").strip() for p in location.get("areaPath") or []]
    parts = [name] if name else []
    parts += [p for p in paths if p and p.casefold() not in {x.casefold() for x in parts}]
    return ", ".join(parts) or None


def parse_objects(data: dict, market: str) -> list[Listing]:
    if not isinstance(data, dict) or "items" not in data:
        raise ValueError("ÖBO: oväntat svar, saknar 'items' (API-ändring?)")
    out = []
    for it in data["items"]:
        address = re.sub(r"\s+", " ", it.get("displayName") or "").strip()
        size = it.get("size") or {}
        price = (it.get("pricing") or {}).get("price")
        number = it.get("number")
        out.append(Listing(
            id=f"obo:{number or it['id']}",
            source="obo",
            url=f"{SITE}/market/{market}/{it['id']}",
            address=address,
            area=_area(it.get("location") or {}),
            rooms=_rooms(size.get("roomsDisplayName")),
            size_m2=float(size["area"]) if size.get("area") is not None else None,
            rent_sek=int(round(price)) if price is not None else None,
            move_in=_ms_date((it.get("availability") or {}).get("availableFrom")),
            apply_by=None,  # finns bara i detaljvyn, fylls i av enrich()
            landlord="ÖBO",
            text=f"{address} {size.get('roomsDisplayName') or ''}\n{it.get('description') or ''}".strip(),
        ))
    return out


def parse_apply_by(detail: dict) -> str | None:
    return _ms_date((detail.get("application") or {}).get("openTo"))


def _is_list_response(url: str, market: str) -> bool:
    parts = urlsplit(url)
    return parts.path.endswith("/market/objects") and parse_qs(parts.query).get("type") == [market]


class OboSource:
    name = "obo"
    label = "ÖBO"
    is_aggregator = False
    search_url = f"{SITE}/market/residential"

    def __init__(self, markets: dict[str, str] | None = None, channel: str | None = None,
                 nav_interval: float = 1.2, timeout_ms: int = 45_000) -> None:
        self.markets = markets or MARKETS
        self.channel = os.environ.get("BEVAKNING_BROWSER_CHANNEL", "chrome") if channel is None else channel
        self.nav_interval = nav_interval
        self.timeout_ms = timeout_ms
        self._last_nav = 0.0

    @contextmanager
    def _page(self) -> Iterator:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(channel=self.channel or None, headless=True)
            except Exception as e:
                if not self.channel:
                    raise
                log.warning("ÖBO: kunde inte starta webbläsaren '%s' (%s) – provar Playwrights Chromium", self.channel, e)
                browser = p.chromium.launch(headless=True)
            try:
                ctx = browser.new_context(user_agent=USER_AGENT, locale="sv-SE")
                ctx.route("**/*", lambda route: route.abort()
                          if route.request.resource_type in BLOCKED_RESOURCES else route.continue_())
                yield ctx.new_page()
            finally:
                browser.close()

    def _capture_json(self, page, url: str, predicate: Callable[[str], bool]) -> dict:
        wait = self.nav_interval - (time.monotonic() - self._last_nav)
        if wait > 0:
            time.sleep(wait)
        self._last_nav = time.monotonic()
        with page.expect_response(lambda r: predicate(r.url), timeout=self.timeout_ms) as info:
            page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
        resp = info.value
        if resp.status != 200:
            raise RuntimeError(f"ÖBO: {resp.url} gav HTTP {resp.status}")
        return resp.json()

    def fetch(self) -> list[Listing]:
        out: list[Listing] = []
        with self._page() as page:
            for market in self.markets:
                collected: list[Listing] = []
                for page_no in range(1, MAX_PAGES + 1):
                    data = self._capture_json(
                        page, f"{SITE}/market/{market}?pageSize={PAGE_SIZE}&page={page_no}",
                        lambda u, m=market: _is_list_response(u, m),
                    )
                    items = parse_objects(data, market)
                    collected += items
                    if not items or len(collected) >= int(data.get("count") or 0):
                        break
                out += collected
        return out

    def enrich(self, listings: list[Listing]) -> None:
        if not listings:
            return
        with self._page() as page:
            for listing in listings:
                object_id = listing.url.rstrip("/").rsplit("/", 1)[-1]
                try:
                    detail = self._capture_json(
                        page, listing.url,
                        lambda u, o=object_id: urlsplit(u).path.endswith(f"/market/objects/{o}"),
                    )
                    listing.apply_by = parse_apply_by(detail)
                except Exception as e:  # en enskild detaljsida får inte stoppa körningen
                    log.warning("ÖBO: kunde inte läsa detaljer för %s: %s", listing.url, e)
