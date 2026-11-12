import json
from pathlib import Path

import pytest

from bevakning.sources import obo

FIX = Path(__file__).parent / "fixtures"
LIST = json.loads((FIX / "obo_residential.json").read_text(encoding="utf-8"))
DETAIL = json.loads((FIX / "obo_detail.json").read_text(encoding="utf-8"))


def by_id(listings, lid):
    return next(l for l in listings if l.id == lid)


def test_obo_parse_objects():
    listings = obo.parse_objects(LIST, "residential")
    assert len(listings) == 25
    l = by_id(listings, "obo:AN-22175")
    assert l.source == "obo"
    assert l.address == "Höglundagatan 50"
    assert l.area == "Norrby, Norr"
    assert l.rooms == 2 and l.size_m2 == 58.4 and l.rent_sek == 9012
    assert l.move_in == "2027-01-01"
    assert l.apply_by is None
    assert l.url == "https://minasidor.obo.se/market/residential/K8WKpjq9RJVKBFYjpcVcFwXJ"
    assert l.landlord == "ÖBO"


def test_obo_whitespace_and_same_area_names():
    listings = obo.parse_objects(LIST, "residential")
    l = by_id(listings, "obo:AN-24711")
    assert l.address == "Krönikegatan 1 B"
    assert l.area == "Vivalla"          # area och areaPath är samma -> ingen dubblering
    assert l.rooms == 4


def test_obo_korttid_text():
    listings = obo.parse_objects(LIST, "residential")
    assert "Korttidskontrakt" in by_id(listings, "obo:AN-24706").text


def test_obo_parse_apply_by():
    assert obo.parse_apply_by(DETAIL) == "2026-11-14"
    assert obo.parse_apply_by({}) is None


def test_obo_rooms_parsing():
    assert obo._rooms("1 rum o pentry omöblerat") == 1
    assert obo._rooms("1,5 rum och kök") == 1.5
    assert obo._rooms("Lokal") is None


def test_obo_unexpected_payload_raises():
    with pytest.raises(ValueError, match="items"):
        obo.parse_objects({"error": "x"}, "residential")


def test_is_list_response():
    base = "https://obo-fastighet.momentum.se/Prod/Obo/PmApi/v2/market/objects"
    assert obo._is_list_response(base + "?type=residential&limit=100", "residential")
    assert not obo._is_list_response(base + "/types/residential", "residential")
    assert not obo._is_list_response(base + "?type=parking&limit=100", "residential")
