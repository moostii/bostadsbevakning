from bevakning.models import Listing
from bevakning.notify import format_listing, format_summary, format_warning, listing_title


def mk(**kw) -> Listing:
    base = dict(id="obo:AN-1", source="obo", url="https://minasidor.obo.se/market/residential/X",
                address="Storgatan 1", area="Adolfsberg", rooms=2.0, size_m2=58.4, rent_sek=8950,
                move_in="2027-01-01", apply_by="2026-11-14", landlord="ÖBO")
    base.update(kw)
    return Listing(**base)


class Src:
    def __init__(self, name, label, url):
        self.name, self.label, self.search_url, self.is_aggregator = name, label, url, False


def test_title_format():
    assert listing_title(mk()) == "🏠 2 rok · 8 950 kr · Adolfsberg"
    assert listing_title(mk(rooms=1.5, rent_sek=12472, area=None)) == "🏠 1,5 rok · 12 472 kr · Storgatan 1"
    assert listing_title(mk(rooms=None, rent_sek=None)) == "🏠 ? rok · ? kr · Adolfsberg"


def test_message_lines_and_markers():
    p = format_listing(mk(), [])
    assert p["message"] == "Storgatan 1\n58,4 m² · ÖBO\nInflytt: 2027-01-01 · Sista ansökan: 2026-11-14"
    assert p["click"] == "https://minasidor.obo.se/market/residential/X"
    assert "topic" not in p

    p = format_listing(mk(size_m2=None, apply_by=None), ["⚠️ okänd yta"])
    assert p["message"] == "Storgatan 1\nÖBO\nInflytt: 2027-01-01\n⚠️ okänd yta"


def test_summary_links_to_search_of_biggest_source():
    obo = Src("obo", "ÖBO", "https://minasidor.obo.se/market/residential")
    boio = Src("boio", "Boio", "https://boio.se/objekt?mode=rent&city=%C3%96rebro")
    matches = [(mk(id=f"obo:{i}", rent_sek=8000 + i), []) for i in range(10)]
    matches += [(mk(id=f"boio:{i}", source="boio"), []) for i in range(2)]
    p = format_summary(matches, [boio, obo])
    assert p["title"] == "🏠 12 nya lägenheter matchar"
    assert p["click"] == obo.search_url
    assert [a["url"] for a in p["actions"]] == [obo.search_url, boio.search_url]
    lines = p["message"].split("\n")
    assert lines[0] == "2 rok · 8 000 kr · Adolfsberg (ÖBO)"
    assert lines[-1] == "…och 2 till"


def test_warning_format():
    p = format_warning(Src("boio", "Boio", "https://boio.se/x"), "ValueError: hittade inte initialListings")
    assert p["title"] == "⚠️ Parsern för Boio verkar trasig"
    assert p["message"].startswith("ValueError: hittade inte initialListings")
