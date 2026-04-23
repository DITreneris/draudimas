# Changelog

Visos reiksmingos projekto pakeitimai dokumentuojami siame faile.

Formatas remiasi [Keep a Changelog](https://keepachangelog.com/lt/1.1.0/),
versijavimas - [Semantic Versioning](https://semver.org/lang/lt/).

## [Unreleased]

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
