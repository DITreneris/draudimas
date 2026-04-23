# Viesiejipirkimai.lt hourly agent (MVP)

Agentas **darbo dienomis 7:00–19:00 Vilniaus laiku** (kas valandą, 13 ciklų/dieną)
automatiškai patikrina [viesiejipirkimai.lt](https://viesiejipirkimai.lt/epps/home.do)
išplėstinę paiešką pagal konfigūruojamus raktinių žodžių fragmentus (pvz. `draudim`) ir
praneša apie **naujus** skelbimus (pagal „Pirkimo ID“). Suprojektuotas Railway debesiui
kaip always-on workeris su vidiniu APScheduler. Po kiekvieno ciklo (jei įjungta) agentas
push'ina `docs/items.json` į GitHub repo, o **GitHub Pages** statiškai rodo rezultatus.

## Architektūra

- `main.py` – įėjimo taškas, paleidžia APScheduler su
  `CronTrigger(day_of_week="mon-fri", hour="7-19", minute=0, timezone="Europe/Vilnius")`.
  Grafikas **hardcoded** — keičiama tik kode (`SCHEDULE_*` konstantos `main.py` viršuje).
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
| `CHECK_INTERVAL_MINUTES` | `60` | **Deprecated** – ignoruojamas, grafikas hardcoded (`CronTrigger mon-fri 7-19:00 Europe/Vilnius`) |
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
| `TELEGRAM_ENABLED` | `false` | Ar siųsti pranešimą į Telegram apie kiekvieną naują pirkimą |
| `TELEGRAM_BOT_TOKEN` | – | Bot token'as iš `@BotFather` (formatas `123:AAE...`) |
| `TELEGRAM_CHAT_ID` | – | Asmeninio chat `chat_id` (gauk per `@userinfobot` arba `getUpdates`) |

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

Always-on režimas (darbo dienos 7:00–19:00 Vilniaus laiku):

```bash
python main.py
```

## Railway deploy

1. Sukurk naują Railway projektą ir pasirink **Deploy from GitHub repo** (arba `railway up`).
2. Railway automatiškai naudos `Dockerfile` (bazė: oficiali Playwright Python image).
3. **Pridėk Volume**, prijungtą prie `/data` (čia bus SQLite ir log failas).
4. **Service → Variables** suvesk:
   - `KEYWORDS=draudim,kasko`
   - *(nebereikia `CHECK_INTERVAL_MINUTES` – grafikas hardcoded)*
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
- Pranešimas į konsolę/log **ir** (pasirinktinai) į Telegram asmeninį chat'ą.
  El. pašto integracija – ateityje.
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
- Commit'ų istorija augs po 1 commit'ą per ciklą — **~65 commit'ų per savaitę**
  (13 slot'ų × 5 darbo dienos), ~3400 per metus. Jei nepatinka, vėliau galima perkelti
  `items.json` į atskirą `gh-pages` branch'ą ir force-push'inti su `squash`.

## Raktažodžių keitimas

Keičiama **tik** per `KEYWORDS` env var. Pavyzdžiui:

```
KEYWORDS=draudim,kasko,civilin,turto
```

Po keitimo – restart service'ą (Railway padaro automatiškai po `Variables` update).

## Telegram asmeninis pranešimas

Agentas gali kiekvieną **naują** skelbimą (tą patį, kuris eina į `notifications.log`)
iš karto nusiųsti į tavo asmeninį Telegram chat'ą. Naudojama tik stdlib `urllib`,
jokių papildomų dependency'ų.

### Setup (vienkartinis)

1. **Sukurk botą:** Telegram'e atsidaryk [@BotFather](https://t.me/BotFather) → `/newbot`
   → duok pavadinimą → gauk `TELEGRAM_BOT_TOKEN` (formatas `1234567890:AAE...`).
2. **Paspausk `/start` savo naujam botui** (kitaip jis tau negalės siųsti žinutės).
3. **Gauk `chat_id`:** atidaryk [@userinfobot](https://t.me/userinfobot) → `/start` →
   parodys tavo skaitinį `Id: 123456789`. Tai ir yra `TELEGRAM_CHAT_ID`.
4. **Railway Variables** (arba lokaliam testui `.env`):
   - `TELEGRAM_ENABLED=true`
   - `TELEGRAM_BOT_TOKEN=<iš 1 žingsnio>`
   - `TELEGRAM_CHAT_ID=<iš 3 žingsnio>`
5. Restart service'ą. Po kito ciklo kiekvienas naujas `pirkimo_id` atsiras
   Telegram chat'e kaip HTML-formatuota žinutė su pavadinimu, ID, organizacija,
   paskelbimo data ir URL.

### Saugumo pastabos

- `TELEGRAM_BOT_TOKEN` – secret, **niekada** necommit'inti (`.env` jau yra
  `.gitignore`). Agentas nelogina token'o net `DEBUG` lygyje.
- Telegram klaida nesustabdo ciklo – tik `logger.error`/`logger.exception`.
- Jei `TELEGRAM_ENABLED=false` arba token/chat_id tušti – pranešėjas apskritai
  neinstancijuojamas.
