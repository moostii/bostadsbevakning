"""Orkestrering: hämta → filtrera → deduplicera → notifiera → uppdatera state."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Sequence
from zoneinfo import ZoneInfo

from .config import Config
from .dedupe import fingerprint
from .filters import match
from .models import Listing
from .notify import Notifier, format_listing, format_summary, format_warning
from .sources.base import Source
from .state import State

log = logging.getLogger(__name__)
TZ = ZoneInfo("Europe/Stockholm")
SUMMARY_THRESHOLD = 5


@dataclass
class Match:
    listing: Listing
    markers: list[str]
    is_new: bool


@dataclass
class RunReport:
    fetched: dict[str, int] = field(default_factory=dict)
    failed: dict[str, str] = field(default_factory=dict)
    matches: list[Match] = field(default_factory=list)
    initialized: list[str] = field(default_factory=list)
    notified: int = 0


def _fetch_all(sources: Sequence[Source], report: RunReport) -> dict[str, list[Listing]]:
    fetched: dict[str, list[Listing]] = {}
    for src in sources:
        try:
            listings = src.fetch()
            if not listings:
                raise RuntimeError("0 annonser hittades (trolig layoutändring)")
        except Exception as e:
            log.exception("Källan %s misslyckades", src.name)
            report.failed[src.name] = f"{type(e).__name__}: {e}"
            continue
        fetched[src.name] = listings
        report.fetched[src.name] = len(listings)
    return fetched


def run(cfg: Config, state: State, sources: Sequence[Source], notifier: Notifier | None,
        *, now: datetime, dry_run: bool = False) -> RunReport:
    """En körning. I dry-run skickas inget och state ändras inte; alla aktuella
    matchningar redovisas (nya och redan sedda)."""
    today = now.astimezone(TZ).date()
    report = RunReport()
    fetched = _fetch_all(sources, report)

    if not dry_run:
        for src in sources:
            if src.name in report.failed and state.should_warn(src.name, now):
                try:
                    notifier.send(format_warning(src, report.failed[src.name]))
                    state.mark_warned(src.name, now)
                except Exception:
                    log.exception("Kunde inte skicka varning för %s", src.name)

    # Hyresvärdens egen källa före aggregatorer: vid dubbletter vinner den (bättre länk).
    ordered = sorted((s for s in sources if s.name in fetched), key=lambda s: s.is_aggregator)
    batch_fps: set[str] = set()
    present_ids: set[str] = set()
    candidates: dict[str, list[tuple[Listing, str, bool]]] = {}

    for src in ordered:
        first_run = not state.is_initialized(src.name)
        for listing in fetched[src.name]:
            present_ids.add(listing.id)
            fp = fingerprint(listing)
            if fp in batch_fps:      # samma lägenhet från en annan källa i denna körning
                continue
            batch_fps.add(fp)
            seen = state.is_seen(listing.id, fp)
            if dry_run:
                candidates.setdefault(src.name, []).append((listing, fp, not seen))
            elif first_run:
                state.mark_seen(listing.id, fp, today)   # tyst första körning per källa
            elif not seen:
                candidates.setdefault(src.name, []).append((listing, fp, True))
        if first_run and not dry_run:
            state.mark_initialized(src.name)
            report.initialized.append(src.name)

    found: list[tuple[Match, str]] = []
    for src in ordered:
        cheap = []
        for listing, fp, is_new in candidates.get(src.name, []):
            if match(listing, cfg, check_keywords=False)[0]:
                cheap.append((listing, fp, is_new))
            elif not dry_run:
                state.mark_seen(listing.id, fp, today)
        if not cheap:
            continue
        try:
            src.enrich([l for l, _, _ in cheap])
        except Exception:
            log.exception("Berikning misslyckades för %s", src.name)
        for listing, fp, is_new in cheap:
            ok, markers = match(listing, cfg)
            if ok:
                found.append((Match(listing, markers, is_new), fp))
            elif not dry_run:
                state.mark_seen(listing.id, fp, today)

    report.matches = [m for m, _ in found]
    if dry_run or not found:
        if not dry_run:
            state.prune(today, present_ids, set(fetched))
        return report

    # Markera som sedd först när notisen gått iväg – annars försöker vi igen nästa körning.
    if len(found) > SUMMARY_THRESHOLD:
        try:
            notifier.send(format_summary([(m.listing, m.markers) for m, _ in found], sources))
            for m, fp in found:
                state.mark_seen(m.listing.id, fp, today)
            report.notified = len(found)
        except Exception:
            log.exception("Kunde inte skicka samlad notis")
    else:
        for m, fp in found:
            try:
                notifier.send(format_listing(m.listing, m.markers))
            except Exception:
                log.exception("Kunde inte skicka notis för %s", m.listing.id)
                continue
            state.mark_seen(m.listing.id, fp, today)
            report.notified += 1

    state.prune(today, present_ids, set(fetched))
    return report
