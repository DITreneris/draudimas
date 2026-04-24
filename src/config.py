"""Konfiguracija is env variables."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _get_list(name: str, default: list[str]) -> list[str]:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return list(default)
    return [part.strip() for part in raw.split(",") if part.strip()]


@dataclass(frozen=True)
class Settings:
    keywords: list[str] = field(default_factory=lambda: ["draudim"])
    check_interval_minutes: int = 60
    max_results_per_keyword: int = 50
    headless: bool = True
    state_dir: Path = field(default_factory=lambda: Path("./state"))
    run_on_start: bool = True
    wipe_db_on_start: bool = False
    log_level: str = "INFO"

    github_enabled: bool = False
    github_token: str = ""
    github_repo: str = ""
    github_branch: str = "main"
    github_file_path: str = "docs/items.json"
    github_max_items: int = 500

    telegram_enabled: bool = False
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    @property
    def db_path(self) -> Path:
        return self.state_dir / "seen.sqlite3"

    @property
    def log_path(self) -> Path:
        return self.state_dir / "notifications.log"

    @property
    def local_export_path(self) -> Path:
        return self.state_dir / "items.json"


def load_settings() -> Settings:
    return Settings(
        keywords=_get_list("KEYWORDS", ["draudim"]),
        check_interval_minutes=_get_int("CHECK_INTERVAL_MINUTES", 60),
        max_results_per_keyword=_get_int("MAX_RESULTS_PER_KEYWORD", 50),
        headless=_get_bool("HEADLESS", True),
        state_dir=Path(os.getenv("STATE_DIR", "./state")).resolve(),
        run_on_start=_get_bool("RUN_ON_START", True),
        wipe_db_on_start=_get_bool("WIPE_DB_ON_START", False),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        github_enabled=_get_bool("GITHUB_EXPORT_ENABLED", False),
        github_token=os.getenv("GITHUB_TOKEN", "").strip(),
        github_repo=os.getenv("GITHUB_REPO", "").strip(),
        github_branch=os.getenv("GITHUB_BRANCH", "main").strip() or "main",
        github_file_path=os.getenv("GITHUB_FILE_PATH", "docs/items.json").strip()
        or "docs/items.json",
        github_max_items=_get_int("GITHUB_MAX_ITEMS", 500),
        telegram_enabled=_get_bool("TELEGRAM_ENABLED", False),
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
        telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", "").strip(),
    )
