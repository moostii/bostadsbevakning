"""Formatering och utskick av ntfy-notiser (JSON-publicering, se https://docs.ntfy.sh/publish/)."""
from __future__ import annotations

from collections import Counter
from typing import Protocol, Sequence

from .http import PoliteClient
from .models import Listing
from .sources.base import Source

SUMMARY_MAX_LINES = 10


def _int(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def _num(x: float) -> str:
    return f"{x:g}".replace(".", ",")


def listing_title(l: Listing) -> str:
    rooms = "?" if l.rooms is None else _num(l.rooms)
    rent = "? kr" if l.rent_sek is None else f"{_int(l.rent_sek)} kr"
    return f"🏠 {rooms} rok · {rent} · {l.area or l.address}"


def listing_lines(l: Listing, markers: Sequence[str]) -> list[str]:
    lines = [l.address]
    facts = [f"{_num(l.size_m2)} m²" if l.size_m2 is not None else None, l.landlord]
    if any(facts):
        lines.append(" · ".join(f for f in facts if f))
    dates = [f"Inflytt: {l.move_in}" if l.move_in else None,
             f"Sista ansökan: {l.apply_by}" if l.apply_by else None]
    if any(dates):
        lines.append(" · ".join(d for d in dates if d))
    lines.extend(markers)
    return lines


def format_listing(l: Listing, markers: Sequence[str]) -> dict:
    return {
        "title": listing_title(l),
        "message": "\n".join(listing_lines(l, markers)),
        "click": l.url,
        "priority": 4,
    }


def format_summary(matches: Sequence[tuple[Listing, Sequence[str]]], sources: Sequence[Source]) -> dict:
    by_name = {s.name: s for s in sources}
    counts = Counter(l.source for l, _ in matches)
    lines = [
        f"{listing_title(l).removeprefix('🏠 ')} ({by_name[l.source].label if l.source in by_name else l.source})"
        for l, _ in matches[:SUMMARY_MAX_LINES]
    ]
    if len(matches) > SUMMARY_MAX_LINES:
        lines.append(f"…och {len(matches) - SUMMARY_MAX_LINES} till")
    ranked = [by_name[name] for name, _ in counts.most_common() if name in by_name]
    payload = {
        "title": f"🏠 {len(matches)} nya lägenheter matchar",
        "message": "\n".join(lines),
        "priority": 4,
    }
    if ranked:
        payload["click"] = ranked[0].search_url
        payload["actions"] = [
            {"action": "view", "label": f"Öppna {s.label} ({counts[s.name]})", "url": s.search_url}
            for s in ranked[:3]
        ]
    return payload


def format_warning(source: Source, error: str) -> dict:
    return {
        "title": f"⚠️ Parsern för {source.label} verkar trasig",
        "message": f"{error}\nÖvriga källor körs som vanligt. Nästa varning för {source.label} tidigast om 24 h.",
        "click": source.search_url,
        "priority": 3,
    }


class Notifier(Protocol):
    def send(self, payload: dict) -> None: ...


class NtfyNotifier:
    def __init__(self, server: str, topic: str, client: PoliteClient) -> None:
        self.server = server.rstrip("/")
        self.topic = topic
        self.client = client

    def send(self, payload: dict) -> None:
        self.client.post_json(self.server, {"topic": self.topic, **payload})
