"""Registrerade källor. Lägg till en ny hyresvärd genom att skriva en modul med
samma gränssnitt som `base.Source` och lägga till en rad i `default_sources`."""
from __future__ import annotations

from ..http import PoliteClient
from .base import Source


def default_sources(client: PoliteClient) -> list[Source]:
    from .boio import BoioSource
    from .obo import OboSource

    return [
        BoioSource(client),
        OboSource(),
    ]
