from bevakning.config import Config
from bevakning.filters import match
from bevakning.models import Listing


def mk(**kw) -> Listing:
    base = dict(
        id="t:1", source="t", url="https://example.invalid/1", address="Storgatan 1",
        area="Adolfsberg", rooms=2, size_m2=55, rent_sek=8950, move_in=None,
        apply_by=None, landlord="Test", text="Fin lägenhet med balkong",
    )
    base.update(kw)
    return Listing(**base)


def test_area_matches_address_case_insensitive():
    cfg = Config(areas=["rynninge"])
    assert match(mk(area="Rynninge"), cfg)[0]
    assert match(mk(area="Norr", address="Rynningevägen 3"), cfg)[0]
    assert not match(mk(area="Norr", address="Storgatan 1"), cfg)[0]
    assert match(mk(area="Örebro, City/Centrum"), Config(areas=["Centrum"]))[0]


def test_empty_areas_means_all():
    assert match(mk(area="Vivalla"), Config())[0]


def test_exclude_area():
    cfg = Config(exclude_areas=["vivalla"])
    assert not match(mk(area="Vivalla"), cfg)[0]
    assert not match(mk(area=None, address="Vivallagatan 2"), cfg)[0]
    assert match(mk(area="Adolfsberg"), cfg)[0]


def test_room_size_rent_limits():
    cfg = Config(min_rooms=2, max_rooms=3, min_size_m2=45, max_rent_sek=10000)
    assert match(mk(), cfg) == (True, [])
    assert not match(mk(rooms=1), cfg)[0]
    assert not match(mk(rooms=4), cfg)[0]
    assert not match(mk(size_m2=44.9), cfg)[0]
    assert not match(mk(rent_sek=10001), cfg)[0]
    assert match(mk(rooms=3, size_m2=45, rent_sek=10000), cfg)[0]


def test_missing_fields_pass_with_markers():
    cfg = Config(areas=["Adolfsberg"], min_rooms=2, min_size_m2=45, max_rent_sek=10000)
    ok, markers = match(mk(area=None, address="Okänd väg 1", rooms=None, size_m2=None, rent_sek=None), cfg)
    assert ok
    assert markers == ["⚠️ område okänt", "⚠️ okänt antal rum", "⚠️ okänd yta", "⚠️ okänd hyra"]


def test_unknown_area_without_area_filter_has_no_marker():
    assert match(mk(area=None), Config()) == (True, [])


def test_keywords_any_and_exclude():
    cfg = Config(keywords_any=["balkong", "uteplats"], keywords_exclude=["korttidskontrakt"])
    assert match(mk(text="Stor BALKONG mot söder"), cfg)[0]
    assert not match(mk(text="Inget särskilt"), cfg)[0]
    assert not match(mk(text="Balkong. Korttidskontrakt pga ombyggnad"), cfg)[0]
    ok, markers = match(mk(text=None), cfg)
    assert ok and markers == ["⚠️ annonstext saknas"]


def test_check_keywords_false_skips_keywords():
    cfg = Config(keywords_any=["balkong"], keywords_exclude=["korttid"])
    assert match(mk(text="korttid"), cfg, check_keywords=False) == (True, [])
    assert match(mk(text=None), cfg, check_keywords=False) == (True, [])
