# Bostadsbevakning Örebro – design

Datum: 2026-11-12. Underlag: ditt uppdrag + källundersökning + dina svar (Playwright för ÖBO, publikt repo, Python 3.12).

## Mål (från uppdraget)

- Kolla källorna var 15:e minut via GitHub Actions. Noll kostnad.
- Pushnotis via ntfy.sh bara för **nya** annonser som matchar `config.yaml`. Samma lägenhet ska aldrig notifieras två gånger, inte ens om den finns hos två källor.
- Robust mot trasiga källor. Första körningen fyller state tyst.

## Källor – vad undersökningen visade

| Källa | Hur | Tillåtet? | Uppdateras | Begränsning |
|---|---|---|---|---|
| **Boio** `boio.se/objekt?mode=rent&city=Örebro` | `httpx`. Läser `initialListings` som Next.js bakar in i HTML:en (24 nyaste). Detaljsidan hämtas bara för nya kandidater, för att få `tags` (nyckelordsfiltret). | robots.txt: `/api/` förbjudet, sidorna tillåtna. Villkoren förbjuder inte skrapning. | 1 gång/dygn (~04:46 svensk tid) | Har **inte** ÖBO. Ansökan via Boio kräver deras betalabonnemang. |
| **ÖBO** `minasidor.obo.se/market/residential` | Playwright (headless Chrome) besöker den publika sidan. Vi läser JSON-svaret som sidan själv hämtar (`market/objects?type=residential`) och klickar igenom pagineringen. | robots.txt tillåter allt. Ingen inloggning. | Löpande | Långsammare (~30–60 s). Studentbostäder ingår inte (egen marknad, kan läggas till). |

Boios JSON-API och den databas Boios klient hämtar från används **inte**, eftersom robots.txt förbjuder det. Av samma skäl hanterar min kod inte ÖBO:s klientnyckel direkt.

## Arkitektur

```
bevakning/
  __main__.py      CLI: python -m bevakning [--dry-run] [--config PATH] [--state PATH]
  models.py        Listing (dataclass enligt uppdraget + fältet `text`)
  config.py        Läser config.yaml → Config
  filters.py       match(listing, cfg) → (ok, saknade_fält)
  dedupe.py        fingerprint(listing): normaliserad adress + rum + hyra
  state.py         data/seen.json: läs/skriv/rensa, tysta första körningar, varningstider
  notify.py        Formaterar och skickar ntfy-notiser (JSON-publicering)
  http.py          Artig klient: ärlig User-Agent, max 1 anrop/s per domän
  runner.py        Orkestrering: hämta → filtrera → deduplicera → notifiera → spara
  sources/
    base.py        Source-protokoll: name, search_url, fetch() → list[Listing]
    boio.py
    obo.py
    __init__.py    SOURCES = [...]  ← en rad per ny hyresvärd
```

**Avvikelse från datamodellen:** `Listing` får ett extra fält, `text: str | None` (titel + taggar/beskrivning). Det behövs för `keywords_any` och `keywords_exclude`. Övriga fält är exakt som i uppdraget.

## Flöde per körning

1. Varje källa körs isolerad (try/except). Om en källa kastar fel eller returnerar 0 annonser skickas en varning (`⚠️ Parsern för X verkar trasig`), högst 1 per dygn per källa. Övriga källor körs vidare.
2. Filter: numeriska fält och områden först. Bara för **nya** kandidater hämtas annonstext där det behövs (Boio-detaljsida), och därefter körs nyckelordsfiltren. Saknade fält släpps igenom och markeras i notisen (t.ex. "⚠️ okänd yta").
3. Dedup: en annons är ny om varken dess `id` eller dess fingeravtryck finns i state. Inom samma körning vinner hyresvärdens egen källa över aggregatorn (bättre länk).
4. Notiser: 1–5 nya ger en notis per annons. Fler än 5 ger en samlad notis med länk till sökresultatet (plus knappar per källa).
5. State sparas deterministiskt (sorterade nycklar), och bara om innehållet ändrats.

## State (`data/seen.json`)

```json
{
  "version": 1,
  "initialized_sources": ["boio", "obo"],
  "seen": {"obo:AN-24711": {"first_seen": "2026-11-12", "fp": "kronikegatan 1b|4|11016"}},
  "warnings": {"boio": "2026-11-12T10:00:00+00:00"}
}
```

- **Tyst första körning per källa**, inte bara globalt. Om du lägger till en hyresvärd senare får du alltså inte notiser om allt den redan har ute.
- **Rensning efter 60 dagar**, med ett skydd: poster tas bara bort om annonsen inte syntes i den här körningen *och* källan lyckades. Det hindrar att en långlivad annons, eller en tillfälligt trasig källa, ger dubbelnotiser.

## Notisformat (ntfy)

- Titel: `🏠 2 rok · 8 950 kr · Adolfsberg` (område, annars adress)
- Text: adress · m² · hyresvärd, sedan inflytt och sista ansökningsdag, sedan eventuella ⚠️-markeringar
- Klick: öppnar annonsen
- Ämnet läses från miljövariabeln `NTFY_TOPIC` (GitHub-secret). Saknas den vid skarp körning avbryts körningen med fel.

## GitHub Actions

- `schedule: "*/15 * * * *"` + `workflow_dispatch`, `concurrency` (ingen överlappning), `timeout-minutes: 10`
- Python 3.12 med pip-cache. Playwright använder runnerns förinstallerade Chrome (`channel="chrome"`), så ingen nedladdning av Chromium behövs.
- Commit av `data/seen.json` bara om `git diff` visar en ändring.
- Notera: GitHubs cron är "best effort" och kan försenas 5–30 min under hög last.

## Tester (pytest)

- Fixtures i `tests/fixtures/`: Boio sök-HTML, Boio detalj-HTML och ÖBO JSON-svar
- Parsertester per källa, filtertester (inkl. saknade fält och områdesmatchning mot adress), dedup-tester, state-tester (första körning, rensning, varningsspärr) och notisformatering
- Runner-tester med falska källor: tyst första körning, trasig källa, sammanslagning vid >5

## `--dry-run`

Hämtar från riktiga källor och skriver ut alla annonser som matchar filtren just nu, markerade **NY** eller *redan sedd*. Skickar inga notiser och ändrar inte state.

## Utanför scope (YAGNI)

Studentbostäder, fler hyresvärdar än Boio + ÖBO, kartor/bilder i notiser, webbgränssnitt.
