"""Agento ciklas: paieska + dedup + pranesimai."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .config import Settings
from .db import SeenStore
from .exporter import GithubConfig, export_and_push
from .notifier import (
    ConsoleLogNotifier,
    ResendEmailNotifier,
    SmtpEmailNotifier,
    TelegramNotifier,
    send_ops_alert,
    telegram_from_settings,
)
from .scraper import ResultItem, search_keywords_for_cycle

logger = logging.getLogger(__name__)

ZERO_RESULTS_ALERT_STREAK = 3
SEARCH_FAIL_ALERT_STREAK = 2

_CGROUP_MEMORY_PATHS = (
    "/sys/fs/cgroup/memory.max",
    "/sys/fs/cgroup/memory/memory.limit_in_bytes",
)


@dataclass(frozen=True)
class CycleResult:
    summary: dict[str, int]
    ok: bool


def run_cycle(settings: Settings) -> CycleResult:
    """Vykdo viena pilna cikla per visus keywords."""
    store = SeenStore(settings.db_path)
    notifier = ConsoleLogNotifier(settings.log_path)
    telegram = telegram_from_settings(
        settings.telegram_enabled,
        settings.telegram_bot_token,
        settings.telegram_chat_id,
    )
    if telegram is not None:
        logger.info("Telegram notifier aktyvus (chat_id=%s)", settings.telegram_chat_id)

    email_notifier: ResendEmailNotifier | SmtpEmailNotifier | None = None
    if settings.email_enabled:
        if (
            settings.resend_api_key
            and settings.email_from
            and settings.email_to
        ):
            email_notifier = ResendEmailNotifier(
                api_key=settings.resend_api_key,
                mail_from=settings.email_from,
                mail_to=list(settings.email_to),
            )
            logger.info("Resend email notifier aktyvus")
        elif (
            settings.smtp_host
            and settings.email_from
            and settings.email_to
        ):
            email_notifier = SmtpEmailNotifier(
                host=settings.smtp_host,
                port=settings.smtp_port,
                mail_from=settings.email_from,
                mail_to=list(settings.email_to),
                user=settings.smtp_user,
                password=settings.smtp_password,
            )
            logger.info("SMTP email notifier aktyvus (host=%s)", settings.smtp_host)
        else:
            logger.warning(
                "EMAIL_ENABLED=true bet truksta RESEND_API_KEY arba SMTP_HOST, "
                "ir EMAIL_FROM / EMAIL_TO - el. pastas praleidziamas"
            )

    started = datetime.now(timezone.utc)
    cgroup_mb = _read_cgroup_memory_limit_mb()
    if cgroup_mb is not None:
        logger.info("cgroup_memory_limit_mb=%d", cgroup_mb)
    logger.info(
        "Ciklas PRADETAS %s | keywords=%s | max_per_kw=%d | db=%s",
        started.isoformat(timespec="seconds"),
        settings.keywords,
        settings.max_results_per_keyword,
        settings.db_path,
    )

    summary: dict[str, int] = {}
    search_failed: dict[str, bool] = {}
    keyword_result_counts: dict[str, int] = {}
    prev_zero_streak = _read_zero_results_streak(settings.health_path)
    prev_search_fail_streak = _read_search_fail_streak(settings.health_path)

    keyword_search_results = search_keywords_for_cycle(
        settings.keywords,
        headless=settings.headless,
        max_results=settings.max_results_per_keyword,
        timeout_ms=settings.search_timeout_ms,
        single_process=settings.chromium_single_process,
    )

    for keyword in settings.keywords:
        items = keyword_search_results.get(keyword)
        if items is None:
            logger.error("Keyword='%s' paieska nepavyko", keyword)
            search_failed[keyword] = True
            summary[keyword] = 0
            send_ops_alert(
                state_path=settings.ops_alert_state_path,
                ops_alert_enabled=settings.ops_alert_enabled,
                telegram=telegram,
                alert_key=f"search_fail:{keyword}",
                message=f"Keyword '{keyword}' paieska nepavyko",
            )
            continue

        search_failed[keyword] = False
        keyword_result_counts[keyword] = len(items)

        try:
            new_items = _select_new_items(store, items)
            if new_items:
                logger.info(
                    "Keyword='%s': %d nauju is %d rezultatu",
                    keyword,
                    len(new_items),
                    len(items),
                )
                for item in reversed(new_items):
                    store.mark_seen(
                        pirkimo_id=item.pirkimo_id,
                        title=item.title,
                        url=item.url,
                        keyword=keyword,
                        published_at=item.published_at,
                        organization=item.organization,
                    )
                for item in new_items:
                    notifier.notify(keyword, item)
                    if telegram is not None:
                        telegram.notify(keyword, item)
                    if email_notifier is not None:
                        email_notifier.notify(keyword, item)
            else:
                logger.info(
                    "Keyword='%s': nauju nera (is %d rezultatu)", keyword, len(items)
                )
            summary[keyword] = len(new_items)
        except Exception:
            logger.exception("Keyword='%s' DB/notify etapas nepavyko", keyword)
            search_failed[keyword] = True
            summary[keyword] = 0
            send_ops_alert(
                state_path=settings.ops_alert_state_path,
                ops_alert_enabled=settings.ops_alert_enabled,
                telegram=telegram,
                alert_key=f"db_fail:{keyword}",
                message=f"Keyword '{keyword}' DB/notify etapas nepavyko",
            )
            continue

    failed_keywords = [kw for kw, failed in search_failed.items() if failed]
    if failed_keywords and len(failed_keywords) == len(settings.keywords):
        send_ops_alert(
            state_path=settings.ops_alert_state_path,
            ops_alert_enabled=settings.ops_alert_enabled,
            telegram=telegram,
            alert_key="search_fail:all",
            message="Visos paieskos nepavyko",
        )

    search_fail_streak = _next_search_fail_streak(
        prev_search_fail_streak,
        failed_keywords=failed_keywords,
        keywords=settings.keywords,
    )
    if search_fail_streak >= SEARCH_FAIL_ALERT_STREAK:
        send_ops_alert(
            state_path=settings.ops_alert_state_path,
            ops_alert_enabled=settings.ops_alert_enabled,
            telegram=telegram,
            alert_key="search_fail_streak",
            message=(
                f"Paieska neveikia (Chromium/launch) {search_fail_streak} ciklus "
                f"is eiles; keywords_failed={failed_keywords}. "
                "Tai ne 0 rezultatu — tikrink Railway RAM / CHROMIUM_SINGLE_PROCESS."
            ),
        )

    zero_results_streak = _next_zero_results_streak(
        prev_zero_streak,
        keyword_result_counts=keyword_result_counts,
        failed_keywords=failed_keywords,
        keywords=settings.keywords,
    )
    if zero_results_streak >= ZERO_RESULTS_ALERT_STREAK:
        send_ops_alert(
            state_path=settings.ops_alert_state_path,
            ops_alert_enabled=settings.ops_alert_enabled,
            telegram=telegram,
            alert_key="zero_results",
            message=(
                f"Visi keyword'ai grazino 0 rezultatu {zero_results_streak} "
                f"ciklus is eiles (keywords={settings.keywords})"
            ),
        )

    finished = datetime.now(timezone.utc)
    total_new = sum(summary.values())
    db_count = store.count()
    logger.info(
        "Ciklas BAIGTAS %s | trukme=%.1fs | nauji=%d | db_dydis=%d",
        finished.isoformat(timespec="seconds"),
        (finished - started).total_seconds(),
        total_new,
        db_count,
    )

    export_ok = True
    export_http_status: int | None = None
    try:
        gh_cfg = GithubConfig(
            enabled=settings.github_enabled,
            token=settings.github_token,
            repo=settings.github_repo,
            branch=settings.github_branch,
            file_path=settings.github_file_path,
            max_items=settings.github_max_items,
        )
        export_ok, export_http_status = export_and_push(
            db_path=settings.db_path,
            keywords=settings.keywords,
            local_path=settings.local_export_path,
            cfg=gh_cfg,
        )
        if settings.github_enabled and not export_ok:
            logger.error("GitHub export nepavyko (push returned False)")
            send_ops_alert(
                state_path=settings.ops_alert_state_path,
                ops_alert_enabled=settings.ops_alert_enabled,
                telegram=telegram,
                alert_key="export_fail",
                message="GitHub export FAILED",
            )
    except Exception:
        export_ok = False
        export_http_status = None
        logger.exception("Export/push i GitHub nepavyko (ciklas nesustabdomas)")
        if settings.github_enabled:
            send_ops_alert(
                state_path=settings.ops_alert_state_path,
                ops_alert_enabled=settings.ops_alert_enabled,
                telegram=telegram,
                alert_key="export_fail",
                message="GitHub export FAILED (exception)",
            )

    cycle_ok = not failed_keywords and (export_ok or not settings.github_enabled)
    last_search_ok = not failed_keywords
    _write_health(
        settings.health_path,
        started_at=started,
        completed_at=finished,
        export_ok=export_ok,
        export_http_status=export_http_status,
        db_count=db_count,
        keywords_failed=failed_keywords,
        cycle_ok=cycle_ok,
        zero_results_streak=zero_results_streak,
        last_search_ok=last_search_ok,
        search_fail_streak=search_fail_streak,
    )

    return CycleResult(summary=summary, ok=cycle_ok)


def _read_zero_results_streak(path: Path) -> int:
    try:
        if not path.is_file():
            return 0
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return int(raw.get("zero_results_streak", 0))
    except Exception:
        logger.debug("Nepavyko nuskaityti zero_results_streak is %s", path, exc_info=True)
    return 0


def _read_search_fail_streak(path: Path) -> int:
    try:
        if not path.is_file():
            return 0
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return int(raw.get("search_fail_streak", 0))
    except Exception:
        logger.debug(
            "Nepavyko nuskaityti search_fail_streak is %s", path, exc_info=True
        )
    return 0


def _read_cgroup_memory_limit_mb() -> int | None:
    for path_str in _CGROUP_MEMORY_PATHS:
        path = Path(path_str)
        try:
            if not path.is_file():
                continue
            raw = path.read_text(encoding="utf-8").strip()
            if not raw or raw == "max":
                return None
            limit_bytes = int(raw)
            if limit_bytes <= 0:
                return None
            return limit_bytes // (1024 * 1024)
        except Exception:
            logger.debug(
                "Nepavyko nuskaityti cgroup memory is %s", path_str, exc_info=True
            )
    return None


def _next_search_fail_streak(
    prev: int,
    *,
    failed_keywords: list[str],
    keywords: list[str],
) -> int:
    if not keywords:
        return 0
    if failed_keywords:
        return prev + 1
    return 0


def _next_zero_results_streak(
    prev: int,
    *,
    keyword_result_counts: dict[str, int],
    failed_keywords: list[str],
    keywords: list[str],
) -> int:
    if failed_keywords:
        return 0
    if not keywords:
        return 0
    if len(keyword_result_counts) < len(keywords):
        return 0
    if all(keyword_result_counts.get(kw, -1) == 0 for kw in keywords):
        return prev + 1
    return 0


def _write_health(
    path: Path,
    *,
    started_at: datetime,
    completed_at: datetime,
    export_ok: bool,
    export_http_status: int | None,
    db_count: int,
    keywords_failed: list[str],
    cycle_ok: bool,
    zero_results_streak: int,
    last_search_ok: bool,
    search_fail_streak: int,
) -> None:
    payload = {
        "last_cycle_started_at": started_at.isoformat(timespec="seconds"),
        "last_cycle_completed_at": completed_at.isoformat(timespec="seconds"),
        "last_export_ok": export_ok,
        "last_export_http_status": export_http_status,
        "db_count": db_count,
        "keywords_failed": keywords_failed,
        "cycle_exit_code": 0 if cycle_ok else 1,
        "zero_results_streak": zero_results_streak,
        "last_search_ok": last_search_ok,
        "search_fail_streak": search_fail_streak,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        logger.exception("Nepavyko irasyti health.json i %s", path)


def _select_new_items(
    store: SeenStore, items: list[ResultItem]
) -> list[ResultItem]:
    if not items:
        return []
    all_ids = [it.pirkimo_id for it in items]
    new_ids = store.filter_new(all_ids)
    seen_in_batch: set[str] = set()
    result: list[ResultItem] = []
    for it in items:
        if it.pirkimo_id in new_ids and it.pirkimo_id not in seen_in_batch:
            result.append(it)
            seen_in_batch.add(it.pirkimo_id)
    return result
