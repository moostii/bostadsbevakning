from datetime import date, datetime, timedelta, timezone

from bevakning.state import State

NOW = datetime(2026, 11, 12, 10, 0, tzinfo=timezone.utc)
TODAY = date(2026, 11, 12)


def test_missing_file_gives_empty_state(tmp_path):
    s = State.load(tmp_path / "nope.json")
    assert not s.is_initialized("boio")
    assert not s.is_seen("boio:1", "fp")


def test_roundtrip_and_no_write_when_unchanged(tmp_path):
    p = tmp_path / "data" / "seen.json"
    s = State.load(p)
    s.mark_initialized("obo")
    s.mark_seen("obo:AN-1", "a 1|2|8950", TODAY)
    s.mark_warned("boio", NOW)
    assert s.save(p) is True
    text = p.read_text(encoding="utf-8")
    assert text.endswith("\n") and '"first_seen": "2026-11-12"' in text

    s2 = State.load(p)
    assert s2.is_initialized("obo")
    assert s2.is_seen("obo:AN-1", "other-fp")
    assert s2.save(p) is False          # oförändrat -> ingen skrivning
    assert p.read_text(encoding="utf-8") == text


def test_seen_by_id_or_fp():
    s = State()
    s.mark_seen("boio:x:1", "storgatan 1|2|8950", TODAY)
    assert s.is_seen("boio:x:1", "annat")
    assert s.is_seen("obo:AN-9", "storgatan 1|2|8950")
    assert not s.is_seen("obo:AN-9", "storgatan 2|2|8950")


def test_mark_seen_keeps_first_seen_date():
    s = State()
    s.mark_seen("a:1", "fp", TODAY - timedelta(days=5))
    s.mark_seen("a:1", "fp", TODAY)
    assert s.seen["a:1"]["first_seen"] == "2026-11-07"


def test_warn_once_per_24h():
    s = State()
    assert s.should_warn("boio", NOW)
    s.mark_warned("boio", NOW)
    assert not s.should_warn("boio", NOW + timedelta(hours=23, minutes=59))
    assert s.should_warn("boio", NOW + timedelta(hours=24))
    assert s.should_warn("obo", NOW)


def test_prune_old_absent_only():
    s = State()
    old = TODAY - timedelta(days=61)
    s.mark_seen("obo:OLD-GONE", "fp1", old)
    s.mark_seen("obo:OLD-PRESENT", "fp2", old)
    s.mark_seen("obo:NEW-GONE", "fp3", TODAY - timedelta(days=10))
    s.prune(TODAY, present_ids={"obo:OLD-PRESENT"}, ok_sources={"obo"})
    assert set(s.seen) == {"obo:OLD-PRESENT", "obo:NEW-GONE"}
    assert not s.is_seen("x:y", "fp1")   # fingeravtrycket försvinner också


def test_prune_skips_failed_sources():
    s = State()
    old = TODAY - timedelta(days=90)
    s.mark_seen("boio:a:1", "fp1", old)
    s.mark_seen("obo:AN-1", "fp2", old)
    s.prune(TODAY, present_ids=set(), ok_sources={"obo"})
    assert set(s.seen) == {"boio:a:1"}
