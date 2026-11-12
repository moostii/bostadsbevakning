from datetime import datetime, timedelta, timezone

from bevakning.config import Config
from bevakning.models import Listing
from bevakning.runner import run
from bevakning.state import State

NOW = datetime(2026, 11, 12, 10, 0, tzinfo=timezone.utc)
CFG = Config(min_rooms=2, max_rent_sek=10000, keywords_exclude=["korttidskontrakt"])


def mk(lid, source="obo", address=None, rooms=2.0, rent=8000, text="Trevlig lägenhet") -> Listing:
    return Listing(id=f"{source}:{lid}", source=source, url=f"https://example.invalid/{source}/{lid}",
                   address=address or f"Gatan {lid}", area="Centrum", rooms=rooms, size_m2=60,
                   rent_sek=rent, move_in=None, apply_by=None, landlord=source, text=text)


class FakeSource:
    def __init__(self, name, listings, aggregator=False, error=None):
        self.name = name
        self.label = name.upper()
        self.is_aggregator = aggregator
        self.search_url = f"https://example.invalid/{name}/sok"
        self.listings = listings
        self.error = error
        self.enriched = []

    def fetch(self):
        if self.error:
            raise self.error
        return list(self.listings)

    def enrich(self, listings):
        self.enriched += [l.id for l in listings]


class FakeNotifier:
    def __init__(self, fail_ids=()):
        self.sent = []
        self.fail_ids = set(fail_ids)

    def send(self, payload):
        if any(payload.get("click", "").endswith("/" + i) for i in self.fail_ids):
            raise RuntimeError("ntfy nere")
        self.sent.append(payload)


def initialized_state(*names):
    s = State()
    for n in names:
        s.mark_initialized(n)
    return s


def test_first_run_silent():
    state, notifier = State(), FakeNotifier()
    src = FakeSource("obo", [mk("1"), mk("2")])
    report = run(CFG, state, [src], notifier, now=NOW)
    assert notifier.sent == [] and report.notified == 0
    assert state.is_initialized("obo")
    assert state.is_seen("obo:1", "x") and state.is_seen("obo:2", "x")
    assert report.initialized == ["obo"]


def test_new_source_first_run_silent():
    state = initialized_state("obo")
    notifier = FakeNotifier()
    run(CFG, state, [FakeSource("obo", [mk("1")]), FakeSource("ny", [mk("9", source="ny")])],
        notifier, now=NOW)
    assert [p["click"] for p in notifier.sent] == ["https://example.invalid/obo/1"]
    assert state.is_initialized("ny") and state.is_seen("ny:9", "x")


def test_notifies_new_match_once():
    state, notifier = initialized_state("obo"), FakeNotifier()
    src = FakeSource("obo", [mk("1"), mk("dyr", rent=12000), mk("kort", text="Korttidskontrakt")])
    report = run(CFG, state, [src], notifier, now=NOW)
    assert [p["click"] for p in notifier.sent] == ["https://example.invalid/obo/1"]
    assert report.notified == 1
    assert state.is_seen("obo:dyr", "x") and state.is_seen("obo:kort", "x")
    assert src.enriched == ["obo:1", "obo:kort"]     # bara billiga filtret före berikning

    run(CFG, state, [src], notifier, now=NOW + timedelta(minutes=15))
    assert len(notifier.sent) == 1


def test_cross_source_dedupe_prefers_landlord():
    state, notifier = initialized_state("obo", "boio"), FakeNotifier()
    boio = FakeSource("boio", [mk("b1", source="boio", address="Tallrisvägen 37 C, Örebro")], aggregator=True)
    obo = FakeSource("obo", [mk("AN-1", address="Tallrisvägen 37  C")])
    run(CFG, state, [boio, obo], notifier, now=NOW)
    assert [p["click"] for p in notifier.sent] == ["https://example.invalid/obo/AN-1"]
    run(CFG, state, [boio, obo], notifier, now=NOW + timedelta(minutes=15))
    assert len(notifier.sent) == 1


def test_more_than_five_gives_summary():
    state, notifier = initialized_state("obo"), FakeNotifier()
    src = FakeSource("obo", [mk(str(i)) for i in range(6)])
    report = run(CFG, state, [src], notifier, now=NOW)
    assert len(notifier.sent) == 1
    assert notifier.sent[0]["title"] == "🏠 6 nya lägenheter matchar"
    assert report.notified == 6 and all(state.is_seen(f"obo:{i}", "x") for i in range(6))


def test_exactly_five_gives_individual():
    state, notifier = initialized_state("obo"), FakeNotifier()
    run(CFG, state, [FakeSource("obo", [mk(str(i)) for i in range(5)])], notifier, now=NOW)
    assert len(notifier.sent) == 5


def test_broken_source_warns_once_per_day():
    state, notifier = initialized_state("obo", "boio"), FakeNotifier()
    sources = [FakeSource("boio", [], error=ValueError("ny layout")), FakeSource("obo", [mk("1")])]
    report = run(CFG, state, sources, notifier, now=NOW)
    titles = [p["title"] for p in notifier.sent]
    assert "⚠️ Parsern för BOIO verkar trasig" in titles
    assert any(t.startswith("🏠") for t in titles)           # övriga källor körs ändå
    assert "boio" in report.failed and report.fetched == {"obo": 1}

    run(CFG, state, sources, notifier, now=NOW + timedelta(hours=1))
    assert sum(t.startswith("⚠️") for t in (p["title"] for p in notifier.sent)) == 1
    run(CFG, state, sources, notifier, now=NOW + timedelta(hours=25))
    assert sum(t.startswith("⚠️") for t in (p["title"] for p in notifier.sent)) == 2


def test_zero_listings_counts_as_broken():
    state, notifier = initialized_state("obo"), FakeNotifier()
    report = run(CFG, state, [FakeSource("obo", [])], notifier, now=NOW)
    assert "0 annonser" in report.failed["obo"]
    assert notifier.sent[0]["title"] == "⚠️ Parsern för OBO verkar trasig"


def test_failed_send_not_marked_seen():
    state, notifier = initialized_state("obo"), FakeNotifier(fail_ids={"2"})
    src = FakeSource("obo", [mk("1"), mk("2")])
    run(CFG, state, [src], notifier, now=NOW)
    assert state.is_seen("obo:1", "x") and not state.is_seen("obo:2", "obo-2-fp")

    notifier.fail_ids.clear()
    run(CFG, state, [src], notifier, now=NOW + timedelta(minutes=15))
    assert [p["click"].rsplit("/", 1)[-1] for p in notifier.sent] == ["1", "2"]


def test_dry_run_no_send_no_state_change(tmp_path):
    p = tmp_path / "seen.json"
    state = initialized_state("obo")
    state.mark_seen("obo:1", "gatan 1|2|8000", NOW.date())
    state.save(p)
    before = p.read_text()

    state = State.load(p)
    src = FakeSource("obo", [mk("1"), mk("2"), mk("dyr", rent=20000)])
    report = run(CFG, state, [src], None, now=NOW, dry_run=True)
    assert {(m.listing.id, m.is_new) for m in report.matches} == {("obo:1", False), ("obo:2", True)}
    assert state.save(p) is False and p.read_text() == before


def test_prune_runs_after_notify():
    state = initialized_state("obo")
    state.mark_seen("obo:gammal", "gammal|2|1", (NOW - timedelta(days=70)).date())
    run(CFG, state, [FakeSource("obo", [mk("1")])], FakeNotifier(), now=NOW)
    assert "obo:gammal" not in state.seen and "obo:1" in state.seen
