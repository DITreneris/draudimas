# Definition of Done (DoD) — viesiejipirkimai.lt agent

Vienas šaltinis tiesos, kada užduotis laikoma **baigta**. Taikoma žmonėms ir AI agentams (Cursor, CLI, Copilot).

> Kontekstas: `AGENTS.md`, `.cursor/rules/`, `README.md`. Invariantai — ten; DoD — **patikrinimo sąrašai** prieš „padaryta“.

---

## 1. Principai (visoms užduotims)

| # | Principas | Šaltinis |
| --- | --- | --- |
| 1 | **Mažiausias delta** — nekeisti viešo API (`Settings`, `run_cycle`, `items.json` schema) be būtinybės | `AGENTS.md` §5, `qa-changes.mdc` |
| 2 | **Stdlib first** — naujas `pip` dependency tik su aiškiu pagrindimu | `AGENTS.md` §3, `project-map.mdc` |
| 3 | **Dedup raktas = `pirkimo_id`** — niekada title / url / data | `dedup.mdc` |
| 4 | **Slaptai tik per env** — niekada loguose, commit'uose, `docs/` | Visi moduliai |
| 5 | **`run_cycle` nesustoja** dėl vieno keyword ar export klaidos | `AGENTS.md` §3 |
| 6 | **UTC runtime** — UI formatuoja client-side | `dedup.mdc`, `AGENTS.md` |
| 7 | **Necommit'inti** `.env`, `state/`, `__pycache__/`, atsitiktinių logų | `.gitignore` |

---

## 2. Užduočių tipai

Pasirink **vieną** pagrindinį tipą. Jei keičiasi keli sluoksniai — taikyk **visų** susijusių DoD sąrašus.

| Tipas | Kodas | Pavyzdys |
| --- | --- | --- |
| Klausimas / analizė | `QA` | „Kaip veikia dedup?“ |
| Smulkus pataisymas | `FIX` | Log lygis, retry skaičius |
| Elgsenos / funkcijos pakeitimas | `FEAT` | Naujas notifier kanalas |
| Konfigūracija (env) | `CFG` | Naujas `Settings` laukas |
| Scraper / portalas | `SCR` | Pasikeitė lentelės antraštės |
| DB schema | `DB` | Naujas stulpelis `seen_items` |
| Frontend / export schema | `UI` | Naujas laukas `items.json` |
| Tik dokumentacija | `DOC` | README, DoD, AGENTS |
| Release / deploy | `REL` | Railway redeploy po migracijos |

---

## 3. DoD pagal tipą

### 3.1 `QA` — klausimas arba code review be pakeitimų

- [ ] Atsakymas remiasi **kodu** (citatos formatu `src/file.py:Lx-Ly`), ne spėjimais.
- [ ] Atidaryti tik **reikalingi** failai + atitinkama `.cursor/rules/*.mdc` taisyklė.
- [ ] Kalba — vartotojo (LT default, ASCII-safe).
- [ ] **Neredaguota** kodo, jei vartotojas neprašė pakeitimo.
- [ ] Jei pastebėta kita problema — **footnote**, ne „bonus fix“.

**Done when:** klausimas aiškiai atsakytas; nereikalingų failų pakeitimų nėra.

---

### 3.2 `FIX` / `FEAT` — Python elgsena (numatytasis code change)

**Prieš kodą**

- [ ] Perskaityti `AGENTS.md` + `.cursor/rules/qa-changes.mdc` + modulio taisyklę (`scraper`, `dedup`, `exporter`, …).
- [ ] Suprasta, ar keičiasi invariantas — jei taip, planuojamas atnaujinimas `AGENTS.md` / rules.

**Implementacija**

- [ ] Mažiausias delta; be naujų „utility“ failų vieno helper'iui.
- [ ] Be `# TODO` be ticket / paaiškinimo.
- [ ] Be komentarų, kurie tik kartoja kodą.
- [ ] Python stilius: `python-style.mdc` (`from __future__ import annotations`, `logging`, frozen dataclass, tipai).
- [ ] Klaidos: `logger.exception`, ciklas tęsiasi (ne tuščias `except`).

**Patikra**

- [ ] Smoke test:

  ```bash
  python run_once.py
  ```

  Baigiasi su `Apibendrinimas:` **be** `Exception` stack trace.

- [ ] Jei keitėte **`src/scraper.py`** parserį — papildomai:

  ```bash
  python run_parser_check.py
  ```

- [ ] Jei keitėte **`docs/`** — ranka: atidaryti `docs/index.html` (arba patikrinti `state/items.json` struktūrą).

**Dokumentacija**

- [ ] `CHANGELOG.md` — eilutė po `## [Unreleased]` (`Added` / `Changed` / `Fixed` / `Removed`).
- [ ] Jei keitė invariantą (env, schema, `HEADER_*`, `run_cycle` eiga) — atnaujinti `AGENTS.md` ir/ar `.cursor/rules/`.

**Done when:** smoke test OK + CHANGELOG + susiję invariantų failai sinchronizuoti.

---

### 3.3 `CFG` — naujas ar pakeistas env kintamasis

Visi **trys** failai **toje pačioje** change:

- [ ] `src/config.py` — `Settings` laukas + parseris `load_settings()`.
- [ ] `.env.example` — default + komentaras.
- [ ] `README.md` — `## Konfiguracija` lentelės eilutė.

Papildomai taikyti **`FIX` DoD** (smoke test + CHANGELOG).

**Escalation (privaloma prieš implementaciją):** naujas env — vartotojo patvirtinimas, jei nebuvo aiškiai prašyta.

---

### 3.4 `SCR` — scraper / portalo adaptacija

Papildomai prie **`FIX` DoD**:

- [ ] Keičiami tik `HEADER_*` konstantos viršuje `src/scraper.py` (ne `_find_header_indices` logika be būtinybės).
- [ ] `pirkimo_id` validacija `^\d+$` išlaikyta.
- [ ] URL tik per `_absolute_url()`.
- [ ] Retry / fresh browser context invariantai (`scraper.mdc`) nepažeisti.
- [ ] `python run_parser_check.py` — OK.
- [ ] `python run_once.py` su `HEADLESS=false` (lokalus regėjimas), jei selektoriai / mygtukai keitėsi.

**Escalation:** keitimas `HEADER_*` — informuoti vartotoją CHANGELOG'e aiškiai.

---

### 3.5 `DB` — SQLite schema

- [ ] Migracija idempotentiška (`CREATE IF NOT EXISTS`, `ALTER` su `try/except OperationalError`).
- [ ] `INSERT OR IGNORE` — ne `REPLACE`.
- [ ] `first_seen_at` — UTC ISO.
- [ ] Atnaujinti `README.md` duomenų modelio lentelę + `AGENTS.md` + `dedup.mdc` jei reikia.
- [ ] Dokumentuoti operacinį reset (`WIPE_DB_ON_START`) jei reikalingas vienkartinis backfill.

Papildomai taikyti **`FIX` DoD**.

**Escalation:** schema change — vartotojo patvirtinimas prieš merge.

---

### 3.6 `UI` — `items.json` arba `docs/`

Visi **keturi** sluoksniai sinchronizuoti:

- [ ] `src/exporter.py` — `build_payload` / `_fetch_items`.
- [ ] `docs/app.js` — `render()`, filtrai, `escapeHtml` visur.
- [ ] `docs/index.html` — lentelės antraštės.
- [ ] `exporter.mdc` JSON contract atitinka.

Papildomai taikyti **`FIX` DoD** (be privalomo portalo smoke, jei tik UI).

**Escalation:** JSON schema change — vartotojo patvirtinimas.

---

### 3.7 `DOC` — tik dokumentacija

- [ ] Faktai sutampa su kodu (env default'ai — tikrinti `src/config.py`, ne atmintį).
- [ ] Nuorodos tarp `README.md`, `AGENTS.md`, `dod_system.md`, `.cursor/rules/` nuoseklios.
- [ ] `CHANGELOG.md` — jei dokumentacija vartotojui reikšminga (ne tik typo).

**Done when:** nereikia `run_once.py`, nebent doc'e minėti default'ai, kurie netikslūs ir reikalauja kodo pataisos.

---

### 3.8 `REL` — deploy / release

- [ ] Visi pakeitimai atitinka savo tipo DoD (`FIX`, `CFG`, …).
- [ ] `[Unreleased]` CHANGELOG peržiūrėtas; versija / data — pagal semver / Keep a Changelog (rankiniu release metu).
- [ ] Railway: `STATE_DIR=/data`, volume prijungtas; jokių secret'ų repo.
- [ ] Po deploy — **24h log watch** (žr. `README.md` RUNBOOK): jokio `Ciklas virsijo`, pakartotinio scheduler skip, `GitHub push FAILED`.
- [ ] Jei DB migracija — `WIPE_DB_ON_START` **tik** vienkartiniam redeploy, tada išjungti.

**Done when:** produkcijoje ciklai baigiasi sėkmingai; `health.json` atnaujinamas.

---

## 4. Verifikacijos matrica

| Komanda | Kada privaloma |
| --- | --- |
| `python run_once.py` | Bet koks Python elgsenos pakeitimas (`FIX`, `FEAT`, `CFG`, `SCR`, `DB`, `UI` su exporter) |
| `python run_parser_check.py` | `src/scraper.py` parseris / `fixtures/` |
| `HEADLESS=false` + `run_once.py` | Scraper selektoriai, mygtukai, timeout |
| Rankinė `docs/index.html` | `docs/app.js` / CSS / HTML |
| Peržiūrėti `state/health.json` | Ops / export / timeout pakeitimai |

---

## 5. Escalation — DoD **negali** būti įvykdytas be vartotojo

Stop ir klausk **prieš** implementaciją:

- Naujas `requirements.txt` dependency.
- `SCHEMA` / `HEADER_*` / `items.json` schema (jei nebuvo užduotyje).
- `run_cycle` žingsnių eiliškumas (export lieka gale su `try/except`).
- Neaiški užduotis ar keli vienodai priimtini sprendimai.

---

## 6. Kas **nėra** Done

- Smoke test praleistas „nes mažas pakeitimas“.
- CHANGELOG praleistas „nes tik vidinis refaktor“ — jei elgsena pasikeitė, CHANGELOG privalomas.
- Commit / push be vartotojo prašymo (repo taisyklė).
- Naujas failas `utils.py` / `helpers.py` vienam helper'iui.
- pytest / asyncio / naujas web framework — ne projekto DoD dalis, nebent vartotojas aiškiai prašo.

---

## 7. Nuorodų žemėlapis

```
dod_system.md (DoD checklists)
    ├── AGENTS.md          — misija, invariantai, workflow santrauka
    ├── README.md          — žmogui: konfigūracija, RUNBOOK, deploy
    ├── CHANGELOG.md       — kas pasikeitė
    └── .cursor/rules/
        ├── project-map.mdc    — architektūra (alwaysApply)
        ├── qa-changes.mdc     — Q&A vs change režimas (alwaysApply)
        ├── python-style.mdc   — **/*.py
        ├── config.mdc         — env / Settings
        ├── scraper.mdc        — src/scraper.py
        ├── dedup.mdc          — db + agent dedup
        ├── exporter.mdc       — GitHub export
        └── frontend.mdc       — docs/
```

---

## 8. Greita santrauka agentams (EN)

**Before marking any code task done:**

1. Read relevant rules; smallest delta.
2. Run `python run_once.py` — no exception trace; expect `Apibendrinimas`.
3. If scraper/parser touched — `python run_parser_check.py`.
4. Update `CHANGELOG.md` under `[Unreleased]`.
5. Sync `AGENTS.md` / `.cursor/rules/` / README config table if invariants changed.
6. Do not commit unless the user asked.

**Question-only tasks:** answer with code citations; do not edit files.
