# Changelog

Visos reiksmingos projekto pakeitimai dokumentuojami siame faile.

Formatas remiasi [Keep a Changelog](https://keepachangelog.com/lt/1.1.0/),
versijavimas - [Semantic Versioning](https://semver.org/lang/lt/).

## [Unreleased]

### Added
- **DB seed** (`run_seed_items.py`, `fixtures/seed_items_59.json`): vienkartinis
  `seen.sqlite3` atkūrimas iš `items.json` su originaliu `first_seen_at` (`--fresh`);
  be `notify` / `run_cycle`. Operacinis startup: `SEED_ITEMS_JSON` + `SEED_ITEMS_FRESH`
  (`main.py`). README RUNBOOK — Volume `/data` + seed po redeploy.
- **`health.json`**: `last_search_ok`, `search_fail_streak`; ops alert
  `search_fail_streak` po 2 nesekmingu ciklu is eiles (Chromium/launch gedimas).
- **`CHROMIUM_SINGLE_PROCESS`** env (`Settings.chromium_single_process`) — mažesnis
  Chromium RAM ant Railway.

### Changed
- **Notify tada mark_seen** (`src/agent.py`): ijungti kanalai pirmi; `mark_seen`
  tik jei visi grazino `True`. `cycle_claimed` blokuoja antra keyword tame
  paciame cikle. Dublikatas galimas tik po kanalo klaidos. Notifieriai
  grazina `bool`.
- **search_fail vs DB fail**: `search_fail_streak` / `search_fail:all` tik kai
  visu keyword paieska `None`. DB klaida -> `keywords_db_failed` + `db_fail`.
  `last_search_ok` nuo DB nepriklauso; `cycle_ok` vis tiek false.
- **Cycle timeout** (`main.py`): Linux `killpg`, Windows `taskkill /T` —
  Playwright medis nezombieja po `CYCLE_MAX_SECONDS`.
- **Search deadline**: retry sustoja `cycle_max_seconds-90s` pries tevo kill
  (tik kai `CYCLE_MAX_SECONDS > 150`), kad `health.json` + export spetu.
- **Seed migracija**: `run_seed_items.py` pries INSERT atidaro `SeenStore`
  (`organization` ALTER), `first_seen_at` is JSON lieka.
- **Parserio patikra**: `run_parser_check.py` tikrina pirmo fixture iraso
  id, title, url, data ir organizacija (stulpeliu poslinkis nebepraslysta).
- **Scraper** (`src/scraper.py`): vienas `chromium.launch` per `run_cycle`
  (`search_keywords_for_cycle`); naujas context kiekvienam keyword; container launch
  args (`--disable-gpu`, `--no-zygote`, `--disable-dev-shm-usage`).
- **`run_cycle`**: viena batch paieska vietoj atskiru `search_keyword` kvietimu;
  ciklo pradzioje log `cgroup_memory_limit_mb` (Linux).
- **Chromium launch fallback**: jei `single_process=false` ir klaida turi
  `pthread_create` / `Resource temporarily unavailable` — vienas pakartotinis
  launch su `--single-process` (pirmas launch ir `_relaunch_browser`).
- **`run_cycle` diagnostika**: Linux `cgroup_pids_max` + `nproc_soft`;
  `search_fail_streak` ops alert — pthread/PID + Restart; RAM tik jei
  `cgroup_memory_limit_mb` < 1024.
- **GitHub export**: GET 401/403 — vienas `credentials rejected` ERROR, be
  retry ir be PUT.

### Fixed
- **Telegram URL**: `item.url` eina per `html.escape` (`parse_mode=HTML`).
- **Ops alert cooldown**: `ops_alert_state.json` rasomas tik po sekmingo
  Telegram `notify_ops` — nepavykes siuntimas kito ciklo nebetylina 30 min.
- **Scraper context**: `new_context` / `new_page` `try/finally` — `new_page`
  klaida uzdaro context (`--single-process` kasko).
- **False-positive „sistema veikia“**: GitHub export OK nebeslepia visiskai neveikianio
  skraperio — `search_fail_streak` + `last_search_ok` health.json.

### Notes
- **pthread EAGAIN + GitHub 401 (2026-10-05):**
  - **Simptomai (04:00–06:00 UTC):** `pthread_create: Resource temporarily
    unavailable (11)` tada `TargetClosedError` ant `launch`; ciklas **2–4 s**;
    `rasta X` nera; `db_dydis=152`; lokalus export digest `a9993a23e936`;
    GitHub GET/PUT **401 Bad credentials**; `exit code 1`. D-Bus
    `/run/dbus/system_bus_socket` — triukšmas.
  - **Root cause (du nepriklausomi):** (1) PID/gijų limitas, ne OOM
    (`cgroup_memory_limit_mb=7629`, `single_process=False`, vienas browser —
    ne liepos 6× launch). (2) nebegaliojantis `GITHUB_TOKEN`.
  - **Fix:** vienas `--single-process` fallback ant EAGAIN; 401/403 be retry;
    Railway: `CHROMIUM_SINGLE_PROCESS=true`, Restart, naujas PAT.
  - **Production verify (~10:51 UTC, deploy `416c7970`):** env
    `CHROMIUM_SINGLE_PROCESS=true` + Restart (senas image — nėra
    `cgroup_pids_max` loge); `draudim` **rasta 10**; `kasko` 1/3
    `new_page` / browser closed (`--single-process` krito po pirmo
    keyword); po 15 s retry **rasta 10**; `nauju nera`, `db_dydis=162`
    (ryte 152 — 10 jau buvo ankstesniame cikle), trukme **21.2 s**;
    **GitHub push OK** `sha=50ca618` digest `17889abbf167`. Tokenas
    pataisytas atskirai nuo kodo.
  - **Ops:** `nauju nera` = laiško / Telegram `[NEW]` nėra (dedup);
    dashboard vis tiek atsinaujina. `kasko` 1/3 warning su `--single-process`
    yra tikėtinas, kol retry duoda `rasta`.
- **Railway Volume + DB atkūrimas (2026-06-08, commit `29508fe`):**
  - **Root cause:** Volume nebuvo prijungtas prie `/data` — kiekvienas redeploy
    pradėdavo su tuscia `seen.sqlite3` (false-positive `[NEW]` pranešimai).
  - **Fix:** Railway Volume mount `/data`; `STATE_DIR=/data`; seed
    `SEED_ITEMS_JSON=fixtures/seed_items_59.json`, `SEED_ITEMS_FRESH=true`,
    `RUN_ON_START=false` → loguose `inserted=59 db_total=59` (~07:29 UTC).
  - Po seed: ištrinti `SEED_ITEMS_*`, `RUN_ON_START=true`.
  - **Production verify (~07:33 UTC):** `nauju nera`, `db_dydis=59`, ciklas **7.2 s**,
    `GitHub push OK` (`items.json` `2026-06-08T07:33:10+00:00`, `total_items=59`).
  - **Laikinas portalo timeout (~07:22–07:26 UTC):** abu keyword `#Title` timeout
    (3/3 bandymai) — ne Volume bug; `db_dydis=20` issilaikė, `nauji=0`.
- **Playwright launch gedimas + atkūrimas (2026-07-09, commit `eeb9660`):**
  - **Simptomai (~2026-06-26 – 07-09):** `BrowserType.launch: Target page, context or browser
    has been closed`; 0× `rasta X rezultatu`; ciklas ~64 s; `exit code 1`; bet `GitHub push OK`
    ir `db_dydis=85` — **export maskavo neveikiantį skraperį**.
  - **Root cause (patvirtinta po fix):** per daug `chromium.launch` per ciklą (2 keyword × 3
    retry = iki 6 launch); ne cgroup RAM limitas (production `cgroup_memory_limit_mb=7629`).
  - **Fix:** vienas browser per `run_cycle` (`search_keywords_for_cycle`); `health.json`
    `last_search_ok` / `search_fail_streak`; ops alert po 2 nesėkmingų ciklų.
  - **Production verify (~15:06 UTC):** `rasta 10` + `rasta 10`, ciklas **20.0 s**,
    `db_dydis=96`, `GitHub push OK` (`sha=f8ffa47`); pirmas ciklas po outage — **11 [NEW]**
    (backlog, tikėtina).
  - **Monitor:** ne tik `GitHub push OK` — tikrinti `last_search_ok`, `rasta X rezultatu`,
    `search_fail_streak` (`$STATE_DIR/health.json`).

## [0.3.0] - 2026-06-05

### Added
- **Definition of Done** (`dod_system.md`): uzduociu tipai (`QA`, `FIX`, `FEAT`, `CFG`, `SCR`, `DB`, `UI`, `DOC`, `REL`), patikros sarasai, verifikacijos matrica, escalation ir anti-pattern'ai; nuorodu zemelapis i `AGENTS.md` ir `.cursor/rules/`.
- **Offline parserio smoke** (`run_parser_check.py`, `fixtures/search_results_table.html`):
  `_find_header_indices` / `_extract_rows` be portalo (`page.set_content`).
- **Launch hardening** (`src/agent.py`, `src/exporter.py`, `src/notifier.py`):
  - `health.json`: `zero_results_streak` (ops alert po 3 is eiles tuscu ciklu),
    `last_export_http_status`.
  - GitHub export retry: GET sha po transient klaidos; PUT retry po 409/422.
  - Ops alert `db_fail:{keyword}` kai DB/notify etapas nepavyko.
- **Subprocess ciklo izoliacija** (`main.py`): `run_once.py` subprocess su
  `CYCLE_MAX_SECONDS` (default 600) — uzstriges Playwright nebeblokuoja slot'u.
- **Ops Telegram alert'ai** (`send_ops_alert`, `notify_ops`): ciklo timeout, export
  fail, paieskos fail, `WIPE_DB_ON_START`, scheduler skip; rate-limit 30 min /
  `alert_key` (`ops_alert_state.json`).
- **`health.json`** (`$STATE_DIR/health.json`): ciklo laikas, export OK,
  `keywords_failed`, `cycle_exit_code`.
- Nauji env: `CYCLE_MAX_SECONDS`, `SEARCH_TIMEOUT_MS`, `OPS_ALERT_ENABLED`.
- **Scraper retry** (`src/scraper.py`): iki 3 bandymu, 15 s pauze; `chromium.launch`
  timeout 60 s; saugus `context.close()` / `browser.close()`; `search_timeout_ms`
  is `Settings`.
- **Resend el. pastas (HTTPS):** `RESEND_API_KEY` + `EMAIL_FROM` / `EMAIL_TO`
  (`ResendEmailNotifier`, `urllib`).
- **SMTP el. pasto pranesimai** (`SmtpEmailNotifier`, stdlib `smtplib`).
- **`WIPE_DB_ON_START`** (default `false`) — operacinis `seen.sqlite3` wipe
  per Railway Variables (`main.py`).
- **`organization` laukas** visoje pipeline (DB, export, `docs/` UI).
- **UI klasifikacija** (`docs/app.js` `classify`): brokeris / draudikas /
  rinkos konsultacija + broker mention indikatorius.
- **Telegram pranesimai** (`TelegramNotifier`, Bot API, `urllib`).
- **Projekto agentu sistema:** `AGENTS.md`, `.cursor/rules/` (8 `.mdc`).

### Changed
- **Agentu / DoD integracija:** `AGENTS.md` (§4 Q&A, §5 code-change susieti su `dod_system.md`); `.cursor/rules/qa-changes.mdc` ir `project-map.mdc` — kanoninis DoD pointer; `README.md` — skyrius „Dokumentacija ir agentams“.
- **`run_cycle`**: `mark_seen` **pries** `notify` (duplicate alert prevencija po
  crash/restart); DB/notify etapas atskirame `try/except` per keyword.
- **`export_and_push`** / **`push_to_github`**: grazina `(bool, http_status)`;
  statusas irasomas i `health.json`.
- **`send_ops_alert`**: `ERROR` logas, kai `OPS_ALERT_ENABLED=true` bet Telegram
  neaktyvus.
- **`run_cycle`** grazina `CycleResult(summary, ok)`; `run_once.py` exit `1` jei
  `ok=False` arba exception.
- **`src/agent.py`**: `search_failed` seka; tikrinamas export rezultatas.
- **Playwright 1.51.0** — `requirements.txt`, `Dockerfile`
  (`mcr.microsoft.com/playwright/python:v1.51.0-jammy`).
- **`first_seen_at`**: `timespec="microseconds"` (`src/db.py` `mark_seen`).
- **DB insert eiliskumas**: `mark_seen` — `reversed(new_items)`; `notify` — scraper
  tvarka (naujausi virsuje Telegram'e).
- **Scheduler**: `IntervalTrigger` -> `CronTrigger` (`mon-fri`, `7-21`,
  `Europe/Vilnius`); `CHECK_INTERVAL_MINUTES` deprecated.
- **Dokumentacija:** `README.md` (`run_parser_check.py`, 24h log watch runbook,
  `health.json` laukai), `AGENTS.md`, `.cursor/rules/`, `.env.example`.

### Fixed
- **Windows stdout UTF-8** (`main.py` `setup_logging`) — lietuviskos diakritikos
  `UnicodeEncodeError` PowerShell'e.
- **Duplicate pranesimai po restart** — `mark_seen` pries `notify` (`src/agent.py`).

### Notes
- **Railway gedimas 2026-05-27–06-05:** uzstriges `run_cycle` + `max_instances=1`
  — visi cron slot'ai `skipped` (`maximum number of running instances reached`).
  Fix: subprocess izoliacija + `CYCLE_MAX_SECONDS`. Po deploy — **Restart** Railway.
- **v0.3.0 production verify (2026-06-05 ~06:03 UTC, commit `091cbb3`):**
  - Loguose: `cycle_max_seconds=600`, `run_once` subprocess, `Ciklas BAIGTAS`
    per **23 s**, `GitHub push OK` (`items.json` 2026-06-05T06:03:37+00:00).
  - `Apibendrinimas: {'draudim': 10, 'kasko': 10}` — `scheduler_skip` nerasta.
  - Railway Variables: `STATE_DIR=/data`, `WIPE_DB_ON_START=false` (patvirtinta).
  - **Atidaryta (išspręsta 2026-06-08):** Volume nebuvo prijungtas — `db_dydis=20`
    po backfill; atkurtas per seed (žr. `[Unreleased]` Notes).
- **Railway logai** (~2026-05-08–05-15): 68 ciklai, 69 `GitHub push OK`, 0 push
  klaidu; ~6.6% paiesku nesekmes (laikini portalo sutrikimai 2026-05-13).
- **Redeploy / restart:** jei `$STATE_DIR/seen.sqlite3` issilaiko (Volume `/data`)
  ir `WIPE_DB_ON_START=false`, tie patys `pirkimo_id` **nebesiunciami** dar karta.

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

Pradine MVP versija — agentas su `IntervalTrigger` (kas ~60 min, visa para)
tikrina viesiejipirkimai.lt isplestine paieska, aptinka naujus skelbimus pagal
Pirkimo ID, saugo busena SQLite'e ir loginsi stdout + `notifications.log`.

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
- **Deploy** (ispleidimo dienos baze; veliau atnaujinta zr. neisskleistos versijos
  `### Changed`):
  - `Dockerfile` — pradzioje `mcr.microsoft.com/playwright/python:v1.47.0-jammy`.
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

[Unreleased]: https://github.com/DITreneris/draudimas/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/DITreneris/draudimas/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/DITreneris/draudimas/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/DITreneris/draudimas/releases/tag/v0.1.0
