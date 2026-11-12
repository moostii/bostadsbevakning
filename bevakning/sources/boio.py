"""Boio (boio.se) – aggregator för bl.a. Finfast, Victoriahem, K2A, LG Söderberg.

robots.txt förbjuder /api/, så vi läser bara den server-renderade HTML:en:
sökvyn bakar in de 24 nyaste annonserna som `initialListings` i Next.js-payloaden.
Boio importerar nya annonser en gång per dygn (~04:46 svensk tid).
"""
from __future__ import annotations

import json
import logging
import re

from selectolax.lexbor import LexborHTMLParser as HTMLParser

from ..http import PoliteClient
from ..models import Listing

log = logging.getLogger(__name__)

BASE = "https://boio.se"
SEARCH_URL = f"{BASE}/objekt?mode=rent&city=%C3%96rebro"
_PUSH_RE = re.compile(r'self\.__next_f\.push\(\[1,\s*("(?:[^"\\]|\\.)*")\]\)')
_DECODER = json.JSONDecoder()


def _rsc_payload(html: str) -> str:
    parts: list[str] = []
    for node in HTMLParser(html).css("script"):
        text = node.text(deep=True) or ""
        for m in _PUSH_RE.finditer(text):
            parts.append(json.loads(m.group(1)))
    return "".join(parts)


def _clean_area(neighbourhood: str | None, landlord: str | None) -> str | None:
    if not neighbourhood:
        return None
    a = re.sub(r"^\s*örebro\s*[,\-–]\s*", "", neighbourhood.strip(), flags=re.I).strip()
    if not a or a.casefold() == "örebro":
        return None
    # Boio lägger ibland hyresvärdens namn eller ett internt ID i områdesfältet.
    if "uthyrning" in a.casefold() or re.search(r"\bAB\b", a):
        return None
    if landlord and landlord.casefold() in a.casefold():
        return None
    return a


def _to_listing(x: dict) -> tuple[Listing, str]:
    raw_id = x["id"]
    landlord = x.get("broker") or x.get("source")
    deadline = x.get("application_deadline")
    apply_by = None if not deadline or deadline.startswith("9999") else deadline[:10]
    listing = Listing(
        id="boio:" + raw_id.removeprefix("ko-listing:"),
        source="boio",
        url=f"{BASE}/objekt/{x['slug']}",
        address=re.sub(r"\s+", " ", x.get("address") or x.get("title") or "").strip(),
        area=_clean_area(x.get("neighbourhood"), landlord),
        rooms=float(x["rooms"]) if x.get("rooms") is not None else None,
        size_m2=float(x["area"]) if x.get("area") is not None else None,
        rent_sek=int(round(x["price"])) if x.get("price") is not None else None,
        move_in=(x.get("available_from") or None),
        apply_by=apply_by,
        landlord=landlord,
    )
    base_text = " ".join(t for t in (x.get("title"), x.get("property_type")) if t)
    return listing, base_text


def _parse_with_text(html: str) -> list[tuple[Listing, str]]:
    rsc = _rsc_payload(html)
    i = rsc.find('"initialListings":')
    if i < 0:
        raise ValueError("Boio: hittade inte initialListings i sidan (layoutändring?)")
    arr, _ = _DECODER.raw_decode(rsc, rsc.index("[", i))
    return [_to_listing(x) for x in arr if x.get("type", "rent") == "rent"]


def parse_search(html: str) -> list[Listing]:
    return [listing for listing, _ in _parse_with_text(html)]


def parse_detail_tags(html: str, boio_raw_id: str) -> list[str]:
    rsc = _rsc_payload(html)
    needle = '{"id":' + json.dumps(boio_raw_id)
    start = rsc.find(needle)
    while start >= 0:
        obj, _ = _DECODER.raw_decode(rsc, start)
        if "tags" in obj:
            return [str(t) for t in (obj.get("tags") or [])]
        start = rsc.find(needle, start + 1)
    raise ValueError(f"Boio: hittade inte annonsen {boio_raw_id} på detaljsidan")


class BoioSource:
    name = "boio"
    label = "Boio"
    is_aggregator = True
    search_url = SEARCH_URL

    def __init__(self, client: PoliteClient) -> None:
        self.client = client
        self._base_text: dict[str, str] = {}

    def fetch(self) -> list[Listing]:
        out = []
        for listing, base_text in _parse_with_text(self.client.get_text(SEARCH_URL)):
            self._base_text[listing.id] = base_text
            out.append(listing)
        return out

    def enrich(self, listings: list[Listing]) -> None:
        for listing in listings:
            raw_id = "ko-listing:" + listing.id.removeprefix("boio:")
            try:
                tags = parse_detail_tags(self.client.get_text(listing.url), raw_id)
            except Exception as e:  # en trasig detaljsida ska inte stoppa körningen
                log.warning("Boio: kunde inte läsa detaljer för %s: %s", listing.url, e)
                continue
            listing.text = " ".join([self._base_text.get(listing.id, ""), listing.address, *tags]).strip()
