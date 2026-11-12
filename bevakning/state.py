"""Persistent state i data/seen.json."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

VERSION = 1
PRUNE_AFTER_DAYS = 60
WARN_INTERVAL = timedelta(hours=24)


@dataclass
class State:
    # id -> {"first_seen": "YYYY-MM-DD", "fp": fingeravtryck}
    seen: dict[str, dict[str, str]] = field(default_factory=dict)
    initialized_sources: set[str] = field(default_factory=set)
    # källnamn -> ISO-tid för senaste varning
    warnings: dict[str, str] = field(default_factory=dict)
    _fps: set[str] = field(default_factory=set, repr=False, compare=False)

    def __post_init__(self) -> None:
        self._fps = {e["fp"] for e in self.seen.values() if e.get("fp")}

    # --- läs/skriv -------------------------------------------------------
    @classmethod
    def load(cls, path: Path) -> State:
        path = Path(path)
        if not path.exists():
            return cls()
        raw = json.loads(path.read_text(encoding="utf-8") or "{}")
        return cls(
            seen=dict(raw.get("seen", {})),
            initialized_sources=set(raw.get("initialized_sources", [])),
            warnings=dict(raw.get("warnings", {})),
        )

    def dumps(self) -> str:
        data = {
            "version": VERSION,
            "initialized_sources": sorted(self.initialized_sources),
            "seen": self.seen,
            "warnings": self.warnings,
        }
        return json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n"

    def save(self, path: Path) -> bool:
        """Skriver bara om innehållet ändrats. Returnerar True om filen skrevs."""
        path = Path(path)
        new = self.dumps()
        if path.exists() and path.read_text(encoding="utf-8") == new:
            return False
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(new, encoding="utf-8")
        return True

    # --- källor ------------------------------------------------------------
    def is_initialized(self, source: str) -> bool:
        return source in self.initialized_sources

    def mark_initialized(self, source: str) -> None:
        self.initialized_sources.add(source)

    # --- sedda annonser ------------------------------------------------------
    def is_seen(self, listing_id: str, fp: str) -> bool:
        return listing_id in self.seen or fp in self._fps

    def mark_seen(self, listing_id: str, fp: str, today: date) -> None:
        if listing_id in self.seen:
            return
        self.seen[listing_id] = {"first_seen": today.isoformat(), "fp": fp}
        self._fps.add(fp)

    def prune(self, today: date, present_ids: set[str], ok_sources: set[str]) -> None:
        """Tar bort poster äldre än 60 dagar – men bara om annonsen inte syntes i
        den här körningen och dess källa fungerade (annars riskeras dubbelnotiser)."""
        cutoff = today - timedelta(days=PRUNE_AFTER_DAYS)
        for lid in list(self.seen):
            source = lid.split(":", 1)[0]
            if (
                source in ok_sources
                and lid not in present_ids
                and date.fromisoformat(self.seen[lid]["first_seen"]) < cutoff
            ):
                del self.seen[lid]
        self._fps = {e["fp"] for e in self.seen.values() if e.get("fp")}

    # --- varningar --------------------------------------------------------
    def should_warn(self, source: str, now: datetime) -> bool:
        last = self.warnings.get(source)
        return last is None or now - datetime.fromisoformat(last) >= WARN_INTERVAL

    def mark_warned(self, source: str, now: datetime) -> None:
        self.warnings[source] = now.isoformat(timespec="seconds")
