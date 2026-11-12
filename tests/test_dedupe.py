from bevakning.dedupe import fingerprint, normalize_address
from bevakning.models import Listing


def mk(address, rooms=2, rent=8950) -> Listing:
    return Listing(id="x", source="x", url="u", address=address, area=None, rooms=rooms,
                   size_m2=None, rent_sek=rent, move_in=None, apply_by=None, landlord=None)


def test_normalize_address():
    assert normalize_address("Tallrisvägen 37  C") == "tallrisvägen 37c"
    assert normalize_address("tallrisvägen 37c, Örebro") == "tallrisvägen 37c"
    assert normalize_address("Karlsdalsallén 58- A") == "karlsdalsallén 58a"
    assert normalize_address("Lars Wivallius väg  95") == "lars wivallius väg 95"


def test_fingerprint_normalizes():
    assert fingerprint(mk("Tallrisvägen 37  C")) == fingerprint(mk("tallrisvägen 37c, Örebro"))
    assert fingerprint(mk("Tallrisvägen 37  C")) == "tallrisvägen 37c|2|8950"


def test_fingerprint_differs_on_rooms_or_rent():
    assert fingerprint(mk("A 1", rooms=2)) != fingerprint(mk("A 1", rooms=3))
    assert fingerprint(mk("A 1", rent=8950)) != fingerprint(mk("A 1", rent=9000))


def test_fingerprint_unknown_values():
    assert fingerprint(mk("A 1", rooms=None, rent=None)) == "a 1|?|?"
    assert fingerprint(mk("A 1", rooms=1.5)) == "a 1|1.5|8950"
