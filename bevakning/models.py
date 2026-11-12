from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Listing:
    id: str            # stabilt unikt ID, prefixat med källa, t.ex. "obo:AN-12345"
    source: str
    url: str
    address: str
    area: str | None   # stadsdel/område
    rooms: float | None
    size_m2: float | None
    rent_sek: int | None
    move_in: str | None
    apply_by: str | None
    landlord: str | None
    # Annonstext (titel, beskrivning, taggar) för nyckelordsfiltren. None = okänd.
    text: str | None = None
