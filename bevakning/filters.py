"""Filterlogik. Saknas ett fält släpps annonsen igenom men markeras."""
from __future__ import annotations

from .config import Config
from .models import Listing

MARK_AREA = "⚠️ område okänt"
MARK_ROOMS = "⚠️ okänt antal rum"
MARK_SIZE = "⚠️ okänd yta"
MARK_RENT = "⚠️ okänd hyra"
MARK_TEXT = "⚠️ annonstext saknas"


def _contains_any(haystacks: list[str | None], needles: list[str]) -> bool:
    hay = " ".join(h for h in haystacks if h).casefold()
    return any(n.casefold() in hay for n in needles if n)


def match(listing: Listing, cfg: Config, *, check_keywords: bool = True) -> tuple[bool, list[str]]:
    """Returnerar (matchar, markeringar för okända fält)."""
    markers: list[str] = []
    place = [listing.area, listing.address]

    if cfg.areas and not _contains_any(place, cfg.areas):
        if listing.area is not None:
            return False, []
        markers.append(MARK_AREA)
    if cfg.exclude_areas and _contains_any(place, cfg.exclude_areas):
        return False, []

    if cfg.min_rooms is not None or cfg.max_rooms is not None:
        if listing.rooms is None:
            markers.append(MARK_ROOMS)
        elif (cfg.min_rooms is not None and listing.rooms < cfg.min_rooms) or (
            cfg.max_rooms is not None and listing.rooms > cfg.max_rooms
        ):
            return False, []

    if cfg.min_size_m2 is not None:
        if listing.size_m2 is None:
            markers.append(MARK_SIZE)
        elif listing.size_m2 < cfg.min_size_m2:
            return False, []

    if cfg.max_rent_sek is not None:
        if listing.rent_sek is None:
            markers.append(MARK_RENT)
        elif listing.rent_sek > cfg.max_rent_sek:
            return False, []

    if check_keywords and (cfg.keywords_any or cfg.keywords_exclude):
        if listing.text is None:
            markers.append(MARK_TEXT)
        else:
            if cfg.keywords_exclude and _contains_any([listing.text], cfg.keywords_exclude):
                return False, []
            if cfg.keywords_any and not _contains_any([listing.text], cfg.keywords_any):
                return False, []

    return True, markers
