# Bostadsbevakning Örebro

Tjänsten bevakar lediga hyreslägenheter i Örebro. När en ny annons matchar dina krav får du en pushnotis i mobilen. Den körs gratis i GitHub Actions var 15:e minut, så din dator behöver inte vara på.

- **Källor:** [Boio](https://boio.se/objekt?mode=rent&city=%C3%96rebro) (Finfast, Victoriahem, K2A, LG Söderberg, Lansgården m.fl.) och [ÖBO](https://minasidor.obo.se/market/residential) (Bostad + Poängfritt – Snabbvalet).
- **Notiser:** via [ntfy.sh](https://ntfy.sh). Tryck på notisen så öppnas annonsen.
- **Inga dubbletter:** du får aldrig samma annons två gånger, inte ens om den finns hos två källor.

## 1. Installera ntfy-appen och prenumerera

1. Installera **ntfy** från [App Store](https://apps.apple.com/app/ntfy/id1625396347) eller [Google Play](https://play.google.com/store/apps/details?id=io.heckel.ntfy).
2. Öppna appen, tryck på **+** (Subscribe to topic) och skriv in ditt ämnesnamn. Det är samma värde som du lägger i `NTFY_TOPIC` nedan. Låt servern vara `ntfy.sh`.
3. Klart. Vill du testa kan du köra:

   ```bash
   curl -d "Test från bostadsbevakningen" ntfy.sh/DITT-ÄMNESNAMN
   ```

> Ämnesnamnet fungerar som ett lösenord. Alla som känner till det kan läsa dina notiser, så använd ett långt, slumpmässigt namn (t.ex. `bostad-orebro-7f3k9q2xw8`).

## 2. Lägg in `NTFY_TOPIC` som secret i GitHub

På webben: repot → **Settings → Secrets and variables → Actions → New repository secret**. Namn: `NTFY_TOPIC`, värde: ditt ämnesnamn.

Eller i terminalen:

```bash
gh secret set NTFY_TOPIC
```

Kör sedan workflowen en gång manuellt: **Actions → Bostadsbevakning → Run workflow**. Den första körningen för varje källa är tyst. Den sparar bara det som redan ligger ute, så att du inte får notiser om gamla annonser. Därefter kommer notiser bara för nya annonser.

## 3. Ändra filtren

Alla krav ligger i [`config.yaml`](config.yaml). Ändra, committa och pusha. Det går också att redigera filen direkt på GitHub (pennikonen). Nästa körning använder de nya värdena.

| Fält | Betydelse |
|---|---|
| `areas` | Områden. Matchas skiftlägesokänsligt mot **både** område och adress. Tom lista = alla. |
| `exclude_areas` | Områden som aldrig ska matcha. |
| `min_rooms` / `max_rooms` | Antal rum. Halvor fungerar (`1.5`). |
| `min_size_m2` | Minsta yta. |
| `max_rent_sek` | Högsta månadshyra. |
| `keywords_any` | Minst ett av orden måste finnas i annonstexten (om listan inte är tom). |
| `keywords_exclude` | Annonsen hoppas över om något av orden finns i annonstexten. |

Sätt ett värde till `null` för att stänga av en gräns. Om en annons saknar en uppgift (t.ex. okänd yta) släpps den igenom hellre än att du missar den, och notisen markeras med `⚠️ okänd yta`.

Ändrade filter gäller för **nya** annonser. Annonser som redan setts tas inte upp igen.

## Notiserna

- **En ny annons:** `🏠 2 rok · 8 950 kr · Adolfsberg`. Texten innehåller adress, m², hyresvärd, inflytt och sista ansökningsdag. Tryck för att öppna annonsen.
- **Fler än 5 nya i samma körning:** en samlad notis med länk till sökresultatet, i stället för en lavin.
- **`⚠️ Parsern för X verkar trasig`:** källan kastade ett fel eller gav 0 annonser, vilket troligen betyder att sajten har ändrat layout. Övriga källor körs som vanligt. Varningen kommer högst en gång per dygn och källa.

## Köra lokalt

Kräver Python 3.12 och Google Chrome (ÖBO läses via Playwright).

```bash
python3.12 -m venv .venv
```

```bash
.venv/bin/pip install -r requirements.txt
```

```bash
.venv/bin/python -m bevakning --dry-run
```

`--dry-run` hämtar från de riktiga källorna och skriver ut alla annonser som matchar just nu, markerade **NY** eller *sedd*. Den skickar inga notiser och ändrar inte `data/seen.json`.

Om du inte har Chrome installerat kan du ladda ner Playwrights egen Chromium:

```bash
.venv/bin/playwright install chromium
```

Sätt sedan `BEVAKNING_BROWSER_CHANNEL=""`.

Kör testerna:

```bash
.venv/bin/pytest
```

## Lägga till en ny hyresvärd

1. Skapa `bevakning/sources/<namn>.py` med en klass som har:
   - `name`: kort ID-prefix, t.ex. `"finfast"`
   - `label`: visningsnamn, t.ex. `"Finfast"`
   - `is_aggregator`: `False` för hyresvärdar. Vid dubbletter vinner hyresvärdens egen annons över aggregatorns.
   - `search_url`: länk till hyresvärdens lista över lediga lägenheter
   - `fetch() -> list[Listing]`: returnerar alla aktuella annonser. Varje `id` ska vara stabilt och prefixat, t.ex. `"finfast:12345"`.
   - `enrich(listings)`: fyller i dyra fält för de få annonser som är aktuella för notis. Kan vara tom.
2. Lägg till en rad i `default_sources()` i [`bevakning/sources/__init__.py`](bevakning/sources/__init__.py).
3. Spara en HTML- eller JSON-ögonblicksbild i `tests/fixtures/` och skriv ett parsertest (se `tests/test_boio.py`).
4. Läs hyresvärdens `robots.txt` och villkor först. Använd `PoliteClient` från `bevakning/http.py`. Den sätter en ärlig User-Agent och gör max ett anrop per sekund.

Den nya källans första körning är tyst, precis som den allra första körningen.

## Hur det fungerar

- `data/seen.json` innehåller ID och första-sedd-datum för varje annons, samt ett fingeravtryck (normaliserad adress + rum + hyra) för att hitta dubbletter mellan källor. Workflowen committar filen bara när den har ändrats.
- Poster äldre än 60 dagar rensas bort. Det sker bara om annonsen inte längre syns och källan fungerade vid körningen, så en annons som ligger ute länge ger ingen dubbelnotis.
- En notis som inte gick att skicka markeras inte som sedd. Den skickas i stället vid nästa körning.

## Begränsningar

- **Boio uppdateras bara en gång per dygn** (runt 04:46 svensk tid). ÖBO uppdateras löpande.
- **Boio har inga ÖBO-annonser.** Det är därför ÖBO hämtas direkt.
- **Boio:** vi läser de 24 nyaste annonserna i sökvyn. `boio.se/api/` är förbjudet i robots.txt och används inte. Länken i notisen går till Boio, där själva ansökningsvägen kräver Boios abonnemang. Hyresvärdens namn står i notisen, så du kan söka direkt hos hyresvärden.
- **ÖBO** läses via en headless webbläsare (Playwright), som besöker den publika sidan. Senior-, student- och ungdomsbostäder ingår inte, eftersom de har särskilda krav. De kan läggas till i `MARKETS` i `bevakning/sources/obo.py`.
- **GitHubs schemalagda körningar är "best effort"** och kan bli 5–30 minuter försenade vid hög last.
- **I ett publikt repo syns `config.yaml` och `seen.json` för alla.** Ämnesnamnet ligger som secret och syns inte.
- **GitHub stänger av schemat efter 60 dagar utan aktivitet i repot.** De automatiska commitarna av `seen.json` räknas som aktivitet.
