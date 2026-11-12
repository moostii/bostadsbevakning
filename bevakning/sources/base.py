"""Gemensamt gränssnitt för alla källor (hyresvärdar och aggregatorer)."""
from __future__ import annotations

from typing import Protocol

from ..models import Listing


class Source(Protocol):
    name: str           # kort, stabilt namn – används som ID-prefix, t.ex. "obo"
    label: str          # visningsnamn i notiser, t.ex. "ÖBO"
    is_aggregator: bool  # True för t.ex. Boio; hyresvärdens egen källa vinner vid dubbletter
    search_url: str     # länk till källans sökresultat (för samlade notiser)

    def fetch(self) -> list[Listing]:
        """Hämtar alla aktuella annonser. Får kasta undantag vid fel."""
        ...

    def enrich(self, listings: list[Listing]) -> None:
        """Fyller i dyra fält (t.ex. annonstext, sista ansökningsdag) för de
        annonser som är aktuella för notis. Ska inte kasta för enskilda annonser."""
        ...
