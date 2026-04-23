# Viesiejipirkimai.lt hourly agent (MVP)

Agentas kas valandą automatiškai patikrina [viesiejipirkimai.lt](https://viesiejipirkimai.lt/epps/home.do)
išplėstinę paiešką pagal konfigūruojamus raktinių žodžių fragmentus (pvz. `draudim`) ir
praneša apie **naujus** skelbimus (pagal „Pirkimo ID“). Suprojektuotas Railway debesiui
kaip always-on workeris su vidiniu APScheduler. Po kiekvieno ciklo (jei įjungta) agentas
push'ina `docs/items.json` į GitHub repo, o **GitHub Pages** statiškai rodo rezultatus.

## Architektūra

- `main.py` – įėjimo taškas, paleidžia APScheduler (`IntervalTrigger` kas `CHECK_INTERVAL_MINUTES`).
- `src/scraper.py` – Playwright (Chromium) atidaro advanced search, įveda keyword į `#Title`,
  spaudžia „Ieškoti“, parsinamas rezultatų lentelę pagal stulpelių antraštes (`Pavadinimas`,
  `Pirkimo ID`, `Paskelbimo data`, `PV`).
- `src/db.py` – SQLite `seen_items` lentelė, unikalus raktas `pirkimo_id`.
- `src/notifier.py` – MVP pranešimas: `stdout` + `notifications.log`.
- `src/agent.py` – orkestruoja ciklą (paieška → dedup → pranešimas → įrašas į DB → export).
- `src/exporter.py` – nuskaitys SQLite → sugeneruos `items.json` → push'ins į GitHub per REST API.
- `run_once.py` – lokalus vienkartinis paleidimas (smoke test).
- `docs/` – statinis frontend'as (HTML/CSS/JS) skirtas GitHub Pages.

## Konfigūracija (env vars)

| Kintamasis | Default | Paaiškinimas |
| --- | --- | --- |
| `KEYWORDS` | `draudim` | Kableliais atskirti fragmentai, pvz. `draudim,kasko,civilin` |
| `CHECK_INTERVAL_MINUTES` | `60` | Kas kiek minučių kartoti ciklą |
| `MAX_RESULTS_PER_KEYWORD` | `50` | Kiek rezultatų nuskaitom per keyword |
| `HEADLESS` | `true` | Playwright headless režimas |
| `STATE_DIR` | `./state` (lokaliai) / `/data` (Docker) | Kur laikoma SQLite + log |
| `RUN_ON_START` | `true` | Ar paleisti ciklą iš karto starto metu |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `GITHUB_EXPORT_ENABLED` | `false` | Ar po kiekvieno ciklo push'inti `items.json` į GitHub |
| `GITHUB_TOKEN` | – | Fine-grained PAT (Contents: Read & Write teisė) |
| `GITHUB_REPO` | – | `owner/repo`, pvz. `DITreneris/draudimas` |
| `GITHUB_BRANCH` | `main` | Branch'as, į kurį commit'inama |
| `GITHUB_FILE_PATH` | `docs/items.json` | Kelias repo viduje |
| `GITHUB_MAX_ITEMS` | `500` | Kiek naujausių įrašų export'inti |

Pavyzdys: `.env.example`.

## Lokalus paleidimas (Windows)

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
copy .env.example .env
```

Vienkartinis smoke-test (be scheduler'io):

```bash
python run_once.py
```

Always-on režimas (kas valandą):

```bash
python main.py
```

## Railway deploy

1. Sukurk naują Railway projektą ir pasirink **Deploy from GitHub repo** (arba `railway up`).
2. Railway automatiškai naudos `Dockerfile` (bazė: oficiali Playwright Python image).
3. **Pridėk Volume**, prijungtą prie `/data` (čia bus SQLite ir log failas).
4. **Service → Variables** suvesk:
   - `KEYWORDS=draudim,kasko`
   - `CHECK_INTERVAL_MINUTES=60`
   - `MAX_RESULTS_PER_KEYWORD=50`
   - `HEADLESS=true`
   - `STATE_DIR=/data`
   - `RUN_ON_START=true`
   - `LOG_LEVEL=INFO`
5. Deploy. Service tipas – **worker** (nereikia public networking'o).
6. Logai – Railway UI (`Deployments → Logs`). Failas `/data/notifications.log` išlieka per deploy'us.

## Duomenų modelis

`seen_items` SQLite lentelė:

| Stulpelis | Tipas | Aprašymas |
| --- | --- | --- |
| `pirkimo_id` | TEXT PK | Unikalus skelbimo ID iš portalo |
| `title` | TEXT | Skelbimo pavadinimas |
| `url` | TEXT | Skelbimo nuoroda (jei ištraukiama) |
| `first_seen_at` | TEXT | ISO datetime (UTC), kada pirmą kartą aptikta |
| `keyword_first_seen` | TEXT | Kuris keyword pirmas aptiko |
| `published_at` | TEXT | Paskelbimo data (kaip rodoma portale) |

## Naujumo logika

- Unikalus raktas = `Pirkimo ID` (ne title, ne data).
- Jei skelbimas atitinka kelis keyword – pranešama **tik vieną kartą** (pirmam keyword).
- Pirmo paleidimo metu visi matomi rezultatai įrašomi į DB ir pranešami kaip „nauji“.
  Jei to nenori (pvz. jau turi istoriją), prieš paleisdami pirmą kartą „pre-seed'inkite“
  DB arba paleiskite su `LOG_LEVEL=WARNING` ir vėliau išvalykite log failą.

## Žinomi apribojimai (MVP)

- Nuskaito tik pirmą rezultatų puslapį (iki `MAX_RESULTS_PER_KEYWORD`). Jei naujų per
  valandą būna daugiau – padidinkite reikšmę arba pridėkite puslapiavimą.
- Pranešimas tik į konsolę/log. El. pašto / Telegram integracijos – ateityje.
- Nėra rate-limit / retry su eksponentiniu backoff – tik paprastas `try/except`.
- Selektoriai remiasi matomais stulpelių antraščių tekstais – jei portalas pervadins
  „Pirkimo ID“, reikės koreguoti `HEADER_*` konstantas `src/scraper.py` viršuje.

## Web frontend (GitHub Pages)

Po kiekvieno ciklo (jei `GITHUB_EXPORT_ENABLED=true`) agentas:

1. Nuskaito naujausius įrašus iš SQLite (iki `GITHUB_MAX_ITEMS`).
2. Sugeneruoja `docs/items.json` su `generated_at`, `stats`, `items`.
3. Commit'ina į nurodytą `GITHUB_REPO` / `GITHUB_BRANCH` per GitHub REST API.

Statinis frontend'as `docs/` aplanke fetch'ina `items.json` ir rodo lentelę su paieška,
raktažodžio filtru, auto-refresh kas 60s.

### Setup žingsniai

1. **Sukurk GitHub repo** (viešą) ir įkelk šį kodą.
2. **Sukurk Fine-grained PAT**: GitHub → Settings → Developer settings →
   Personal access tokens → **Fine-grained tokens** → *Generate new token*.
   - Resource owner: tavo paskyra/org.
   - Repository access: **Only select repositories** → pasirink šį repo.
   - Permissions → *Repository permissions* → **Contents: Read and write**.
   - Expiration: pasirink pagal poreikį (90 d / 1 m).
   - Sugeneruotą token'ą išsaugok — rodo tik vieną kartą.
3. **Įjunk GitHub Pages**: repo → **Settings → Pages** →
   - Source: **Deploy from a branch**
   - Branch: `main` / folder: **`/docs`**
   - Save → po ~1 min svetainė pasiekiama `https://<user>.github.io/<repo>/`.
4. **Railway Variables** pridėk:
   - `GITHUB_EXPORT_ENABLED=true`
   - `GITHUB_TOKEN=<PAT iš 2 žingsnio>`
   - `GITHUB_REPO=DITreneris/draudimas`
   - `GITHUB_BRANCH=main`
   - `GITHUB_FILE_PATH=docs/items.json`
5. Redeploy service'ą. Po pirmo ciklo pamatysi commit'ą `chore(data): update items.json ...`
   ir Pages atnaujins svetainę automatiškai.

### Saugumo pastabos

- Repo – viešas, todėl **ir duomenys bus viešai matomi**. Jei jautrūs – rinkis privatų
  repo + kitą hosting'ą (Cloudflare Pages, Netlify).
- PAT token'as **niekada** neturi atsidurti kode ar `.env` repo'je (yra `.gitignore`).
- Commit'ų istorija augs po 1 commit'ą per valandą — per metus ~8760 commit'ų, tai normalu;
  jei nepatinka, vėliau galima perkelti `items.json` į atskirą `gh-pages` branch'ą ir
  force-push'inti su `squash`.

## Raktažodžių keitimas

Keičiama **tik** per `KEYWORDS` env var. Pavyzdžiui:

```
KEYWORDS=draudim,kasko,civilin,turto
```

Po keitimo – restart service'ą (Railway padaro automatiškai po `Variables` update).
