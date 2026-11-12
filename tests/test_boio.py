from pathlib import Path

import pytest

from bevakning.sources import boio

FIX = Path(__file__).parent / "fixtures"
SEARCH = (FIX / "boio_search.html").read_text(encoding="utf-8")
DETAIL = (FIX / "boio_detail.html").read_text(encoding="utf-8")


def by_address(listings, address):
    return next(l for l in listings if l.address == address)


def test_boio_parse_search():
    listings = boio.parse_search(SEARCH)
    assert len(listings) == 24
    first = listings[0]
    assert first.id == "boio:soderberg-fastigheter-momentum:GF6MCdFTXDpCQjWTwq7cpFDr"
    assert first.source == "boio"
    assert first.address == "Engelbrektsgatan 27 A"
    assert first.area == "Öster"
    assert first.rooms == 3 and first.size_m2 == 89 and first.rent_sek == 11650
    assert first.move_in == "2027-02-01"
    assert first.apply_by == "2026-11-18"
    assert first.landlord == "LG Soderberg Fastigheter"
    assert first.url == "https://boio.se/objekt/engelbrektsgatan-27-a-orebro-gf6mcdftxd-1y0baxs"
    assert len({l.id for l in listings}) == 24


def test_boio_sentinel_deadline_and_bad_area():
    listings = boio.parse_search(SEARCH)
    olai = by_address(listings, "Olaigatan 3 B")
    assert olai.apply_by is None            # 9999-12-31 = löpande
    assert olai.area == "City/Centrum"
    assert by_address(listings, "Lars Wivallius väg 95").area is None   # "Uthyrning 2663"
    assert by_address(listings, "Termikgatan 33").area is None          # "K2A Hyresbostäder i Örebro AB"
    assert by_address(listings, "Angelgatan 2").area is None            # saknas helt
    assert by_address(listings, "Karlsgatan 6").rooms == 1.5


def test_boio_detail_tags():
    listings = boio.parse_search(SEARCH)
    tallris = by_address(listings, "Tallrisvägen 1 R")
    raw_id = "ko-listing:" + tallris.id.removeprefix("boio:")
    tags = boio.parse_detail_tags(DETAIL, raw_id)
    assert "Inglasad balkong" in tags


def test_boio_no_payload_raises():
    with pytest.raises(ValueError, match="initialListings"):
        boio.parse_search("<html><body>Ny layout</body></html>")


class FakeClient:
    def __init__(self, pages):
        self.pages = pages

    def get_text(self, url):
        return self.pages[url]


def test_boio_source_fetch_and_enrich():
    tallris_url = "https://boio.se/objekt/tallrisvagen-1-r-orebro-7021-013-11502"
    src = boio.BoioSource(FakeClient({boio.SEARCH_URL: SEARCH, tallris_url: DETAIL}))
    listings = src.fetch()
    tallris = by_address(listings, "Tallrisvägen 1 R")
    assert tallris.url == tallris_url and tallris.text is None
    src.enrich([tallris])
    assert "Inglasad balkong" in tallris.text


def test_boio_enrich_failure_leaves_text_none():
    src = boio.BoioSource(FakeClient({boio.SEARCH_URL: SEARCH}))
    listing = src.fetch()[0]
    src.enrich([listing])   # detaljsidan saknas -> KeyError fångas
    assert listing.text is None
