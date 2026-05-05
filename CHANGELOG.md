# Changelog

Visos reiksmingos projekto pakeitimai dokumentuojami siame faile.

Formatas remiasi [Keep a Changelog](https://keepachangelog.com/lt/1.1.0/),
versijavimas - [Semantic Versioning](https://semver.org/lang/lt/).

## [Unreleased]

### Changed
- **Playwright 1.51.0** — `requirements.txt` ir `Dockerfile` baze
  `mcr.microsoft.com/playwright/python:v1.51.0-jammy` (sutampa su pip versija;
  naudinga ir kai MCR grąžina 429 ant seno tag'o — perbūkinti deploy).

### Added
- **Resend el. paštas (HTTPS):** `RESEND_API_KEY` + `EMAIL_FROM` / `EMAIL_TO` — naudojamas
  prieš SMTP, jei raktas nurodytas (`ResendEmailNotifier`, `urllib`). Tinka Railway,
  kur outbound SMTP 587 dažnai blokuojamas.
- **SMTP el. pašto pranešimai** (optional, stdlib `smtplib`): `SmtpEmailNotifier` in
  `src/notifier.py`, env `EMAIL_ENABLED`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`,
  `SMTP_PASSWORD`, `EMAIL_FROM`, `EMAIL_TO` (CSV); wired in `src/agent.py` alongside
  Telegram. Dokumentuota `.env.example`, `README.md`, `AGENTS.md`.
- **`WIPE_DB_ON_START` env var** (default `false`) - operacinis jungiklis
  `seen.sqlite3` išvalymui per Railway **Variables**, be shell prieigos ar
  `Start Command` override'o. `main.py` pradžioje (po `settings.state_dir.mkdir`)
  jei `true` - `settings.db_path.unlink(missing_ok=True)` + `log.warning` su
  priminimu išjungti kintamąjį po wipe'o. Pridėta į `src/config.py` `Settings`
  (`wipe_db_on_start: bool = False` + `_get_bool("WIPE_DB_ON_START", False)`),
  `.env.example`, `README.md` („Konfigūracija" lentelė + naujas sub-skyrius
  *DB išvalymas (migracija / backfill)* Railway deploy skyriuje su 3 žingsnių
  instrukcija).
- **`organization` laukas visoje pipeline.** `src/scraper.py` jau seniai
  istraukia perkancios organizacijos (PV) pavadinima i `ResultItem`, bet
  duomuo buvo ismetamas. Dabar pravestas iki UI:
  - `src/db.py` - naujas `organization TEXT` stulpelis `seen_items` lenteleje
    + saugi vienkartine migracija senam volume'ui (`PRAGMA table_info` +
    `ALTER TABLE ... ADD COLUMN` jei kolona dar neegzistuoja).
  - `src/db.py` `mark_seen` - naujas `organization` kwarg'as.
  - `src/agent.py` - `mark_seen` iskvieciamas su `item.organization`.
  - `src/exporter.py` - `SELECT organization` + `"organization"` key JSON'e.
  - `docs/index.html` - nauja `Vykdytojas` kolona.
  - `docs/app.js` - renderinamas organization su `title` atributu pilnam
    tekstui ant hover; paieska (`#search`) taip pat filtruoja pagal
    organizacijos pavadinima.
  - `docs/style.css` - `td.org` ellipsis stilius (max-width 200px).
- **UI klasifikacija kliente.** `docs/app.js` `classify(title)` gražina 3
  kategorijas pagal title substring taisykles (case-insensitive):
  `rinkos konsultacij` -> `market_consultation`; `brok` ar `tarpinink` ->
  `broker`; kitaip -> `insurer`. Rodoma kaip spalvotas badge'as naujoje
  `Klase` kolonoje. Papildomai - `UADBB`/`broker` regex paminejimo
  indikatorius (`*`) greta title'o (jeigu title'e minimas konkretus
  brokeris). `docs/style.css` - `.cat-broker` (melynas), `.cat-insurer`
  (zalias), `.cat-market-consultation` (pilkas), `.flag-broker`.

### Changed
- **`first_seen_at` tikslumas**: `timespec="seconds"` -> `"microseconds"`
  (`src/db.py` `mark_seen`). Seconds precision'as buvo neleidziantis
  surikiuoti batch'o viduje - visi batch'o nariai gaudavo identiska
  timestamp'a. Microseconds tiebreaker'is isprendzia si atveji.
- **DB insert eiliskumas `src/agent.py` `run_cycle`** - du atskiri ciklai:
  `notifier.notify` eina pagal scraper'io tvarka (naujausi publikuoti pirma,
  kad Telegram chat'e naujausi pasirodytu virsuje); `store.mark_seen`
  iteruoja `reversed(new_items)` - seniausiai publikuotas irasas gauna
  anksciausia `first_seen_at` timestamp'a. Tada `ORDER BY first_seen_at DESC`
  exporter'yje natūraliai patenka naujausiai publikuotas - virsuje.

- **Scheduler: `IntervalTrigger` -> `CronTrigger`** (`main.py`). Darbo valandu
  grafikas hardcoded: `day_of_week="mon-fri"`, `hour="7-21"`, `minute=0`,
  `timezone="Europe/Vilnius"` (DST-safe per `zoneinfo`). **15 ciklu/diena x 5
  darbo dienos = 75 ciklai/savaite** (vietoj 168 = 24 x 7 anksciau, -55%).
  - `BlockingScheduler(timezone="Europe/Vilnius")` (buvo `"UTC"`).
  - Job id/name atnaujinti: `business_hours_check` / `"viesiejipirkimai mon-fri
    7-21:00 Europe/Vilnius"`.
  - `datetime.utcnow()` -> `datetime.now(timezone.utc)` (Py3.12+ deprecation).
  - `CHECK_INTERVAL_MINUTES` env var tapo **deprecated** - `main.py` jo
    nebeizunaudoja. Jei reiksme != 60, `log.warning` pranesa, kad ignoruojama.
  - `SCHEDULE_TIMEZONE` / `SCHEDULE_DAYS` / `SCHEDULE_HOURS` / `SCHEDULE_MINUTE`
    konstantos `main.py` virsuje - vieninteli vieta, kur keiciamas grafikas.
  - `AGENTS.md` + `.cursor/rules/project-map.mdc` + `README.md` (header,
    Konfiguracija lentele, Railway Variables pavyzdys, commit history
    apskaiciavimas ~3900/metus vietoj ~8760) sinchronizuoti.

### Added
- **Telegram asmeninis pranesimas** (`src/notifier.py` `TelegramNotifier`) -
  kiekvienas naujas skelbimas (tas pats, kuris eina i `notifications.log`)
  papildomai issiunciamas i Telegram chat'a per Bot API `sendMessage`.
  - Naudoja tik stdlib `urllib.request` (be naujo dependency).
  - HTML parse mode, `html.escape` apsauga nuo title/org su `<`, `>`, `&`.
  - Klaidos (`HTTPError`, timeout, bet koks `Exception`) tik logdinamos -
    `run_cycle` tesiasi; token'as niekada nelogintas.
  - 3 nauji env vars: `TELEGRAM_ENABLED` (default `false`), `TELEGRAM_BOT_TOKEN`,
    `TELEGRAM_CHAT_ID`. Pridet i `src/config.py` `Settings`, `.env.example`,
    `.env` (su `[RAILWAY-ONLY]` zymejimu secret'ams) ir `README.md`
    (Konfiguracija + naujas skyrius *Telegram asmeninis pranesimas* su setup
    per `@BotFather` + `@userinfobot`).
  - `src/agent.py` `run_cycle` - notifier instancijuojamas tik kai
    `TELEGRAM_ENABLED=true` IR token'as IR `chat_id` ne tusti; iskvieciamas
    po `ConsoleLogNotifier.notify` toje pacioje `new_items` ciklo iteracijoje.
  - **Smoke test (live):** `python run_once.py` su `TELEGRAM_ENABLED=true` -
    nuskaityta 10 irasu, visi 10 sekmingai issiusti i Telegram asmenini
    chat'a (HTML formatavimas, diakritikos, URL preview - OK). Jokiu
    `HTTPError` ar `exception` stack trace'u.

### Fixed
- **Windows stdout UTF-8** (`main.py` `setup_logging`) - pries konfiguruojant
  `logging.basicConfig`, iskvieciame `sys.stdout.reconfigure(encoding="utf-8",
  errors="replace")`. Anksciau lokaliai (PowerShell, Py3.11, cp1252 default)
  `logger.info(msg)` su lietuviskom diakritikem (pvz. e, u, s su nosinem /
  varnelem) mesdavo `UnicodeEncodeError` kiekvienam pranesimui. Railway
  Linux konteineryje stdout jau UTF-8 - fix'as ten no-op. Duomenu failai
  (`notifications.log`, `items.json`) jau anksciau buvo UTF-8, tik stdout
  buvo zalojamas.

### Added
- **Projekto agentu sistema**:
  - `AGENTS.md` sakny - bendras gidas AI agentams (misija, architekturos
    zemelapis, invariants, Q&A + change workflow).
  - `.cursor/rules/` rinkinys (8 `.mdc` failai) - `project-map` ir
    `qa-changes` `alwaysApply: true`; `python-style`, `scraper`, `dedup`,
    `exporter`, `config`, `frontend` auto-aktyvuojasi pagal `globs`.
  - Smoke-test patvirtintas live'as: `python run_once.py` - 10 skelbimu
    surinkta per ~43s (pirmas paleidimas, pilna dedup'o istorija tuscia).

## [0.2.0] - 2026-04-23

### Added
- **GitHub export pipeline** - po kiekvieno ciklo `items.json` push'inamas i
  nurodyta GitHub repo per REST API (`src/exporter.py`).
  - Naudoja tik stdlib `urllib` (be papildomu dependencies).
  - `GET /contents` gauna esama `sha`, `PUT /contents` commit'ina base64 turini.
  - Klaida export'e nesustabdo agento ciklo.
- **Minimalus web frontend** `docs/` aplanke (GitHub Pages):
  - `docs/index.html` - lentele su Pirkimo ID, Pavadinimu, Raktazodziu,
    Paskelbimo ir First-seen datomis.
  - `docs/app.js` - vanilla JS, `fetch('items.json')` su cache disable,
    auto-refresh kas 60 s, paieska + keyword filtras, relative time.
  - `docs/style.css` - responsive, portalo spalvu paletej.
  - `docs/items.json` - pradinis tuscias payload (kad Pages veikia is karto).
  - `docs/.nojekyll` - isjungia Jekyll apdorojima.
- **Settings** (`src/config.py`) - 6 nauji env vars: `GITHUB_EXPORT_ENABLED`,
  `GITHUB_TOKEN`, `GITHUB_REPO`, `GITHUB_BRANCH`, `GITHUB_FILE_PATH`,
  `GITHUB_MAX_ITEMS`. Pridetas `local_export_path` property.
- **Agent hook** (`src/agent.py`) - `run_cycle()` pabaigoje iskvieciamas
  `export_and_push()`.
- **`.env`** failas su aiskiu zymejimu, kurios reiksmes skiriasi lokaliai vs
  Railway (`[LOCAL+RAILWAY]`, `[RAILWAY-DIFF]`, `[RAILWAY-ONLY]`).
- **README** skyrius *Web frontend (GitHub Pages)* su PAT setup, Pages config
  ir Railway Variables pavyzdziu.

### Changed
- `.env.example` papildytas GitHub export env vars.

## [0.1.0] - 2026-04-23

Pradine MVP versija - agentas kas valanda tikrina viesiejipirkimai.lt
isplestine paieska, aptinka naujus skelbimus pagal Pirkimo ID, saugo busena
SQLite'e ir loginsi stdout + `notifications.log`.

### Added
- Projekto strukturos pagrindas: `main.py`, `run_once.py`, `src/` modulis.
- **Scraperis** (`src/scraper.py`) - Playwright (Chromium), fill `#Title`,
  4-fallback "Ieskoti" mygtuko paspaudimas, header-based rezultatu lenteles
  parsinimas (`Pavadinimas`, `Pirkimo ID`, `Paskelbimo data`, `PV`).
- **Dedup** (`src/db.py`) - SQLite `seen_items` lentele su `pirkimo_id` PK,
  `filter_new()`, `mark_seen()`, `count()`.
- **Pranesimai** (`src/notifier.py`) - `ConsoleLogNotifier` i stdout ir
  `notifications.log`.
- **Orkestracija** (`src/agent.py`) - `run_cycle()` per visus keywords,
  nauji pranesami tik viena karta net jei atitinka kelis keyword.
- **Scheduler** (`main.py`) - `BlockingScheduler` + `IntervalTrigger` kas
  `CHECK_INTERVAL_MINUTES` (default 60), `max_instances=1`, `coalesce=True`,
  `RUN_ON_START` palaikymas, SIGINT/SIGTERM handling.
- **Konfiguracija** (`src/config.py`) - `python-dotenv`, env-based settings
  su saugiais default'ais ir tipu konversija.
- **Deploy**:
  - `Dockerfile` bazej `mcr.microsoft.com/playwright/python:v1.47.0-jammy`.
  - `railway.json` su Dockerfile builder ir `ON_FAILURE` restart policy.
  - `.dockerignore`, `.gitignore`.
- **Dokumentacija**: `README.md` su architektura, konfiguracija, lokaliu
  paleidimu, Railway deploy instrukcijomis.

### Smoke test
- AST sintakse: OK visiems failams.
- SQLite dedup: 2 ciklu simuliacija - pirmame nauji 111+222, antrame tik 333
  (222 atfiltruotas).
- Exporter pipeline: JSON payload korektiskas, lokaliai irasytas, push'as
  praleistas kai `enabled=False`.

[Unreleased]: https://github.com/DITreneris/draudimas/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/DITreneris/draudimas/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/DITreneris/draudimas/releases/tag/v0.1.0
