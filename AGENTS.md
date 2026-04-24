# AGENTS.md — viesiejipirkimai.lt hourly agent

This file is the shared guide for every AI agent (Cursor, CLI, Copilot, etc.) working on this repo. Keep the project **lean**: smallest possible delta, no extra dependencies, no feature creep.

> Finer-grained Cursor rules live in `.cursor/rules/` (auto-applied via file globs).

---

## 1. Mission (one-liner)

Every hour, poll `viesiejipirkimai.lt` using configured keyword fragments, detect **new** tenders by `Pirkimo ID`, emit a notification (log/file), and push `docs/items.json` to GitHub Pages for the frontend.

## 2. Architecture map

```
main.py            -> APScheduler BlockingScheduler, CronTrigger mon-fri 7-21:00 Europe/Vilnius
run_once.py        -> Smoke test: single run_cycle, no scheduler
src/config.py      -> Settings (frozen dataclass) + load_settings() from env
src/scraper.py     -> Playwright (Chromium sync) -> ResultItem list
src/db.py          -> SeenStore (SQLite, pirkimo_id PK)
src/notifier.py    -> ConsoleLogNotifier (stdout + notifications.log)
src/exporter.py    -> SQLite -> items.json -> GitHub REST API (urllib only)
src/agent.py       -> run_cycle() orchestrates everything
docs/              -> Vanilla HTML/CSS/JS GitHub Pages frontend
Dockerfile         -> mcr.microsoft.com/playwright/python:v1.47.0-jammy
railway.json       -> Railway deploy config (worker, ON_FAILURE restart)
```

Data flow per cycle:

```
search_keyword(kw) -> [ResultItem]
  -> SeenStore.filter_new(ids) -> only new
  -> notifier.notify(kw, item)  (also appends to notifications.log)
  -> store.mark_seen(...)       (INSERT OR IGNORE)
-> for every keyword
-> export_and_push(db_path, keywords, local_path, GithubConfig)
```

## 3. Invariants (DON'Ts)

- **`pirkimo_id` is the unique key.** Never use title / url / date for dedup.
- **No new pip dependencies** without a clear justification. Stdlib first (especially `urllib` over `requests`).
- **Scraper header constants** (`HEADER_TITLE`, `HEADER_PIRKIMO_ID`, `HEADER_PUBLISHED`, `HEADER_ORG` at the top of `src/scraper.py`) — change only when the portal itself rewrites them.
- **No non-idempotent mutations at runtime.** `mark_seen` uses `INSERT OR IGNORE`; `push_to_github` uses `sha` from `GET /contents`.
- **Never commit secrets** (`GITHUB_TOKEN`, etc.) to code, `docs/`, commit messages, or logs. `.env` is gitignored.
- **`run_cycle` never aborts** on export/push failure — it only logs `exception`. A single keyword search error must not stop the rest.
- **SQLite schema changes** require an explicit migration step — add an `ALTER TABLE` or a new `CREATE TABLE IF NOT EXISTS` to `SCHEMA` (`src/db.py`).
- **UTC everywhere** (`datetime.now(timezone.utc)`). UI formatting happens client-side.

## 4. Q&A workflow (how to answer questions about this repo)

1. **Start from this file + `.cursor/rules/project-map.mdc`** to build the mental model.
2. If the question is about a specific module — open **only that file** plus the matching rule.
3. Reply in the user's language (Lithuanian by default, ASCII-safe; otherwise English).
4. Ground answers in **facts from the code** (cite `src/file.py:Lx-Ly`); don't speculate.
5. For env-var questions, check `src/config.py` + `.env.example` (not `.env`, to avoid exposing secrets).

## 5. Code-change workflow (how to make changes)

1. **Read the relevant `.cursor/rules/` files and this one.**
2. **Smallest possible delta.** If the fix is <5 lines — don't create a new file, don't change public API.
3. **Don't expand scope.** If you spot a bug six lines away — file a separate TODO; don't mix it with the current change.
4. **Smoke test:** `python run_once.py` must complete at least one cycle successfully (HEADLESS=true, KEYWORDS=draudim).
5. **Stdlib first.** A new dependency is allowed only when:
   - the functionality is substantial (not a helper),
   - a stdlib alternative would be >50 lines,
   - the `requirements.txt` entry is pinned (`==X.Y.Z`).
6. **CHANGELOG.md** — every meaningful change goes under `[Unreleased]` (`### Added` / `### Changed` / `### Fixed`).
7. **Lint / types:** no formal linter, but follow existing style (`from __future__ import annotations`, `logging.getLogger(__name__)`, frozen dataclasses, type annotations).

## 6. When to escalate to the user

- Adding a new dependency to `requirements.txt`.
- Changing `SCHEMA` in `src/db.py`.
- Changing `HEADER_*` in `src/scraper.py`.
- Reordering `run_cycle` steps (especially the export — it must stay at the end, wrapped in `try/except`).
- Adding a new env var (requires updating `.env.example` + README `## Konfiguracija` + `src/config.py` together).

## 7. Environment notes

- **OS:** Windows 10, PowerShell. Commands e.g. `copy`, `.\\.venv\\Scripts\\activate`.
- **Python:** 3.13 (per `__pycache__/*.cpython-313.pyc`).
- **Railway:** `STATE_DIR=/data` (mounted volume). Locally `./state`.
- **GitHub Pages:** `docs/` folder on `main` branch; `items.json` is committed via the agent's REST call.

## 8. What **not** to do

- Don't introduce a test framework (pytest, etc.) unless asked. Smoke tests go through `run_once.py`.
- Don't add FastAPI / Flask / Django — this is a worker, not a web service.
- Don't turn `docs/` into React/Vue — vanilla JS is intentional.
- Don't log tokens even at `DEBUG` level.
