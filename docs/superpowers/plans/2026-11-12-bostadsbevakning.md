# Bostadsbevakning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A GitHub Actions job that runs every 15 minutes, fetches vacant rentals in Örebro from Boio and ÖBO, and sends an ntfy push for each new listing that matches `config.yaml`.

**Architecture:** One module per source behind a shared `Source` protocol. A pure core (filters, dedupe, state, notification formatting) is unit-tested against fixtures, and a thin runner wires them together. ÖBO is read through Playwright (headless Chrome), which captures the JSON the public page fetches itself. Boio is read from the server-rendered `initialListings` in its HTML.

**Tech Stack:** Python 3.12, httpx, selectolax, PyYAML, Playwright (`channel="chrome"`), pytest, ntfy.sh, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-11-12-bostadsbevakning-design.md`

## Global Constraints

- Python 3.12. Run as `python -m bevakning [--dry-run]`.
- User-Agent: `bostadsbevakning/0.1 (privat bevakning av lediga hyreslagenheter; max 1 anrop/s)`. Max 1 request/s per domain. Never call `boio.se/api/*` or the ÖBO API directly.
- State lives in `data/seen.json`. Entries are pruned after 60 days. The file is written only when its content changed (sorted keys, `indent=1`, `ensure_ascii=False`, trailing newline).
- The topic comes from env `NTFY_TOPIC`. Without it, a real run fails. Server: env `NTFY_SERVER`, default `https://ntfy.sh`.
- More than 5 new matches in one run gives a single summary notification. A source warning goes out at most once per 24 h per source.
- Listing IDs are prefixed with the source: `boio:<provider>:<id>` and `obo:<AN-number>`.
- All user-facing text is in Swedish.

## Review Focus

1. **Missing fields** (`size_m2`, `rent_sek`, `rooms` or `area` is None): the listing passes and gets a `⚠️` marker. Owned by Task 2 (`test_missing_fields_pass_with_markers`).
2. **A source that fails or returns 0 listings**: the other sources still run, at most one warning per 24 h, and the source's entries are not pruned. Owned by Tasks 3 and 6 (`test_prune_skips_failed_sources`, `test_broken_source_warns_once_per_day`).
3. **A newly added source**: its first run is silent, even when the rest of the state is old. Owned by Task 6 (`test_new_source_first_run_silent`).
4. **ntfy send failure**: the listing is not marked as seen, so it is retried on the next run. Owned by Task 6 (`test_failed_send_not_marked_seen`).
5. **Boio sentinel deadline `9999-12-31`** and **landlord name stored as the area** (e.g. "Uthyrning 2663"): these become None. Owned by Task 4 (`test_boio_sentinel_deadline_and_bad_area`).

---

### Task 1: Project skeleton + Listing + config

**Files:** Create `requirements.txt`, `pytest.ini`, `config.yaml`, `bevakning/__init__.py`, `bevakning/models.py`, `bevakning/config.py`, `tests/test_config.py`

**Interfaces – Produces:**
- `Listing` dataclass: the fields from the spec, plus `text: str | None = None`.
- `Config` dataclass: `areas, exclude_areas, keywords_any, keywords_exclude: list[str]`; `min_rooms, max_rooms, min_size_m2: float | None`; `max_rent_sek: int | None`.
- `load_config(path: Path) -> Config`. Unknown keys raise `ValueError` that names the key. Missing keys get default None or [].

- [ ] Tests: `test_load_example_config` (values from the spec's example), `test_unknown_key_raises`, `test_missing_keys_default`
- [ ] Implement, run `pytest tests/test_config.py`, commit

### Task 2: Filters

**Files:** Create `bevakning/filters.py`, `tests/test_filters.py`

**Interfaces – Produces:** `match(listing: Listing, cfg: Config, *, check_keywords: bool = True) -> tuple[bool, list[str]]` returns (ok, markers).

- Areas: case-insensitive substring match against `area` and `address`. An empty list means all areas.
- If `area` is None and the address matches no area, the listing passes with the marker `⚠️ område okänt`.
- `exclude_areas` uses the same matching, and a hit rejects the listing.
- Each numeric limit is checked only when its value is known. Unknown values give the markers `⚠️ okänt antal rum`, `⚠️ okänd yta` and `⚠️ okänd hyra`.
- Keywords are matched against `text`. When `text` is None the listing passes with `⚠️ annonstext saknas`.

- [ ] Tests: `test_area_matches_address_case_insensitive`, `test_exclude_area`, `test_room_size_rent_limits`, `test_missing_fields_pass_with_markers`, `test_keywords_any_and_exclude`, `test_check_keywords_false_skips_keywords`
- [ ] Implement, run, commit

### Task 3: Dedupe + state

**Files:** Create `bevakning/dedupe.py`, `bevakning/state.py`, `tests/test_dedupe.py`, `tests/test_state.py`

**Interfaces – Produces:**
- `fingerprint(l: Listing) -> str`: `"<norm address>|<rooms:g or ?>|<rent or ?>"`. Normalization: lowercase; strip `, örebro`; turn `-` and `,` into spaces; collapse whitespace; join digit + space + single letter (`37 c` → `37c`).
- `State` with:
  - `State.load(path) -> State` (a missing file gives an empty state) and `save(path) -> bool` (True if written)
  - `is_initialized(source) / mark_initialized(source)`
  - `is_seen(listing_id, fp) -> bool` and `mark_seen(listing_id, fp, today: date)`
  - `should_warn(source, now) -> bool` and `mark_warned(source, now)`
  - `prune(today, present_ids: set[str], ok_sources: set[str])`: removes entries older than 60 days that are not in `present_ids`, but only if their prefix is in `ok_sources`

- [ ] Tests: `test_fingerprint_normalizes` (`"Tallrisvägen 37  C"` and `"tallrisvägen 37c, Örebro"` give the same fp), `test_roundtrip_and_no_write_when_unchanged`, `test_seen_by_id_or_fp`, `test_warn_once_per_24h`, `test_prune_old_absent_only`, `test_prune_skips_failed_sources`
- [ ] Implement, run, commit

### Task 4: Polite HTTP + Boio source

**Files:** Create `bevakning/http.py`, `bevakning/sources/__init__.py`, `bevakning/sources/base.py`, `bevakning/sources/boio.py`, `tests/test_boio.py`

**Interfaces – Produces:**
- `PoliteClient(min_interval=1.1)` with `get_text(url) -> str`: per-host throttling and one retry on transport error or 5xx.
- `Source` protocol: `name: str`, `label: str`, `is_aggregator: bool`, `search_url: str`, `fetch() -> list[Listing]`, `enrich(listings: list[Listing]) -> None`
- `boio.parse_search(html: str) -> list[Listing]` and `boio.parse_detail_tags(html: str, boio_id: str) -> list[str]`
- `BoioSource`: `search_url = "https://boio.se/objekt?mode=rent&city=%C3%96rebro"`. `enrich` fetches `https://boio.se/objekt/<slug>` and sets `text`.

Parsing works on the joined `self.__next_f.push([1,"…"])` chunks. Find `"initialListings":`, then `raw_decode` from the enclosing `{`. In the detail page, `raw_decode` the object that starts at `{"id":"<boio_id>"`, then read `tags`.

- [ ] Tests on the fixtures:
  - `test_boio_parse_search`: 24 listings. The first has id `boio:soderberg-fastigheter-momentum:GF6MCdFTXDpCQjWTwq7cpFDr`, address `Engelbrektsgatan 27 A`, rooms 3, 89 m², 11650 kr, move_in `2027-02-01`, apply_by `2026-11-18`, landlord `LG Soderberg Fastigheter`, url `https://boio.se/objekt/engelbrektsgatan-27-a-orebro-gf6mcdftxd-1y0baxs`.
  - `test_boio_sentinel_deadline_and_bad_area`: for Olaigatan 3 B, apply_by is None. For Lars Wivallius väg 95, area is None.
  - `test_boio_detail_tags`: contains `"Inglasad balkong"`.
  - `test_boio_no_payload_raises`: a page without `initialListings` raises `ValueError`.
- [ ] Implement, run, commit

### Task 5: ÖBO source (Playwright)

**Files:** Create `bevakning/sources/obo.py`, `tests/test_obo.py`

**Interfaces – Produces:**
- `obo.parse_objects(data: dict, market: str) -> list[Listing]` and `obo.parse_apply_by(detail: dict) -> str | None`
- `OboSource` with `MARKETS = {"residential": "Bostad", "VJKbFxvkM99GGWCvwXyhWYCX": "Poängfritt – Snabbvalet"}`.
  - `fetch` visits `https://minasidor.obo.se/market/<m>?pageSize=100&page=1` and waits for a response whose path ends in `/market/objects` with `type=<m>`.
  - `enrich` visits `https://minasidor.obo.se/market/<m>/<id>` and waits for `/market/objects/<id>`.
  - Images, fonts and media are blocked. The browser channel comes from env `BEVAKNING_BROWSER_CHANNEL` (default `chrome`), with fallback to the bundled Chromium.

Field mapping:
- `/Date(ms)/` is converted to a date in Europe/Stockholm.
- `area` is `location.area.displayName`, followed by `, <areaPath names>` when they differ.
- Rooms come from the regex `(\d+(?:[.,]\d+)?)\s*rum`.
- `text` is `displayName + description`.

- [ ] Tests on the fixtures:
  - `test_obo_parse_objects`: 25 listings. AN-22175 gives id `obo:AN-22175`, address `Höglundagatan 50`, area `Norrby, Norr`, rooms 2, 58.4 m², 9012 kr, move_in `2027-01-01`, url `https://minasidor.obo.se/market/residential/K8WKpjq9RJVKBFYjpcVcFwXJ`, landlord `ÖBO`.
  - `test_obo_korttid_text`: the text of AN-24706 contains "Korttidskontrakt".
  - `test_obo_parse_apply_by`: `2026-11-14`.
- [ ] Implement, run, commit

### Task 6: Notifications + runner + CLI

**Files:** Create `bevakning/notify.py`, `bevakning/runner.py`, `bevakning/__main__.py`, `tests/test_notify.py`, `tests/test_runner.py`

**Interfaces – Produces:**
- `format_listing(l, markers) -> dict`: an ntfy JSON payload without `topic`, with `title`, `message`, `click`, `tags=["house"]`, `priority=4`.
- `format_summary(matches, sources) -> dict` and `format_warning(source_label, error) -> dict`
- `Notifier` protocol: `send(payload: dict) -> None`. `NtfyNotifier(server, topic, client)` POSTs JSON to `server`.
- `run(cfg, state, sources, notifier, *, now: datetime, dry_run: bool) -> RunReport`, where `RunReport` holds `fetched: dict[str,int]`, `failed: dict[str,str]`, `matches: list[tuple[Listing, list[str], bool]]` and `notified: int`.

Formatting:
- Title: `🏠 2 rok · 8 950 kr · Adolfsberg`. Decimal rooms are written as `1,5`. The place is `area` or else `address`.
- Message: line 1 is the address. Line 2 is `58,4 m² · <landlord>`. Line 3 is `Inflytt: … · Sista ansökan: …` (only the known parts). Markers follow on their own lines.

Runner order:
1. Fetch each source in a try block.
2. Warn about failures.
3. Order the sources: non-aggregators first.
4. For each listing, compute the fp. It is new if it is neither seen in state nor already handled in this batch.
5. For an uninitialized source: mark everything seen and initialize it.
6. Otherwise: new listings go through `match(check_keywords=False)`, then `enrich`, then the full `match`.
7. Non-matches are marked seen right away. Matches are marked seen only after a successful send.
8. If there are more than 5 matches, send the summary. Otherwise send one notification per listing.
9. Prune.

In dry-run: nothing is sent and nothing is saved. Every current match is shown (new or old), and enrichment runs on all cheap-filter passes.

CLI: `--dry-run`, `--config` (default `config.yaml`), `--state` (default `data/seen.json`). It prints the report. A real run without `NTFY_TOPIC` exits 2. If every source failed, it exits 1.

- [ ] Tests:
  - `test_title_format` (`2 rok · 8 950 kr · Adolfsberg`, `1,5 rok`)
  - `test_message_lines_and_markers`
  - `test_first_run_silent`
  - `test_new_source_first_run_silent`
  - `test_notifies_new_match_once`
  - `test_cross_source_dedupe_prefers_landlord`
  - `test_more_than_five_gives_summary`
  - `test_broken_source_warns_once_per_day`
  - `test_zero_listings_counts_as_broken`
  - `test_failed_send_not_marked_seen`
  - `test_dry_run_no_send_no_state_change`
- [ ] Implement, run the full suite, commit

### Task 7: Workflow + README

**Files:** Create `.github/workflows/bevakning.yml`, `README.md`, `data/.gitkeep`

- Workflow:
  - Triggers: cron `*/15 * * * *` and `workflow_dispatch`
  - `permissions: contents: write`, `concurrency: bevakning`, `timeout-minutes: 10`
  - Steps: checkout → setup-python 3.12 (pip cache) → `pip install -r requirements.txt` → `python -m bevakning` with `NTFY_TOPIC: ${{ secrets.NTFY_TOPIC }}` → if `git status --porcelain data/` shows changes, commit as `github-actions[bot]` and push
- README (Swedish) covers:
  - installing the ntfy app and subscribing to the topic
  - setting the `NTFY_TOPIC` secret
  - changing `config.yaml`
  - adding a landlord (new module + one line in `SOURCES`)
  - running locally with `--dry-run`
  - limitations
- [ ] Verify with `python -c "import yaml; yaml.safe_load(open('.github/workflows/bevakning.yml'))"`, then commit

### Task 8: Dry run against real sources

- [ ] `python -m bevakning --dry-run` and show the output to the user. Do not create the repo or activate the schedule before the user says yes.
