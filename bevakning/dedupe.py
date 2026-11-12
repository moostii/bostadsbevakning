"""Deduplicering mellan källor: normaliserad adress + rum + hyra."""
from __future__ import annotations

import re

from .models import Listing


def normalize_address(address: str) -> str:
    a = address.casefold()
    a = re.sub(r",?\s*örebro\b.*$", "", a)       # ", Örebro" / ", ÖREBRO, Sverige"
    a = re.sub(r"[-,.]", " ", a)
    a = re.sub(r"\s+", " ", a).strip()
    a = re.sub(r"(\d)\s+([a-zåäö])\b", r"\1\2", a)  # "37 c" -> "37c"
    return a


def fingerprint(listing: Listing) -> str:
    rooms = "?" if listing.rooms is None else f"{listing.rooms:g}"
    rent = "?" if listing.rent_sek is None else str(listing.rent_sek)
    return f"{normalize_address(listing.address)}|{rooms}|{rent}"
