"""Agento ciklas: paieska + dedup + prane\u0161imai."""
from __future__ import annotations

import logging
from datetime import datetime

from .config import Settings
from .db import SeenStore
from .exporter import GithubConfig, export_and_push
from .notifier import ConsoleLogNotifier, SmtpEmailNotifier, TelegramNotifier
from .scraper import ResultItem, search_keyword

logger = logging.getLogger(__name__)


def run_cycle(settings: Settings) -> dict[str, int]:
    """Vykdo viena pilna cikla per visus keywords. Grazina {keyword: new_count}."""
    store = SeenStore(settings.db_path)
    notifier = ConsoleLogNotifier(settings.log_path)
    telegram: TelegramNotifier | None = None
    if (
        settings.telegram_enabled
        and settings.telegram_bot_token
        and settings.telegram_chat_id
    ):
        telegram = TelegramNotifier(
            settings.telegram_bot_token, settings.telegram_chat_id
        )
        logger.info("Telegram notifier aktyvus (chat_id=%s)", settings.telegram_chat_id)

    email_notifier: SmtpEmailNotifier | None = None
    if settings.email_enabled:
        if (
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
                "EMAIL_ENABLED=true bet truksta SMTP_HOST, EMAIL_FROM arba EMAIL_TO "
                "- el. pastas praleidziamas"
            )

    started = datetime.now()
    logger.info(
        "Ciklas PRADETAS %s | keywords=%s | max_per_kw=%d | db=%s",
        started.isoformat(timespec="seconds"),
        settings.keywords,
        settings.max_results_per_keyword,
        settings.db_path,
    )

    summary: dict[str, int] = {}
    for keyword in settings.keywords:
        try:
            items = search_keyword(
                keyword,
                headless=settings.headless,
                max_results=settings.max_results_per_keyword,
            )
        except Exception:
            logger.exception("Keyword='%s' paieska nepavyko", keyword)
            summary[keyword] = 0
            continue

        new_items = _select_new_items(store, items)
        if new_items:
            logger.info(
                "Keyword='%s': %d nauju is %d rezultatu",
                keyword,
                len(new_items),
                len(items),
            )
            # Notifier: newest-published first (scraper order), kad Telegram
            # chat'e naujausi pasirodytu virsuje.
            for item in new_items:
                notifier.notify(keyword, item)
                if telegram is not None:
                    telegram.notify(keyword, item)
                if email_notifier is not None:
                    email_notifier.notify(keyword, item)
            # DB insert: reversed, kad seniausiai publikuotas gautu anksciausia
            # `first_seen_at` timestamp'a, o naujausiai publikuotas - veliausia.
            # Tada `ORDER BY first_seen_at DESC` exporter'yje natūraliai pateikia
            # naujausiai publikuotus virsuje.
            for item in reversed(new_items):
                store.mark_seen(
                    pirkimo_id=item.pirkimo_id,
                    title=item.title,
                    url=item.url,
                    keyword=keyword,
                    published_at=item.published_at,
                    organization=item.organization,
                )
        else:
            logger.info(
                "Keyword='%s': nauju nera (is %d rezultatu)", keyword, len(items)
            )
        summary[keyword] = len(new_items)

    finished = datetime.now()
    total_new = sum(summary.values())
    logger.info(
        "Ciklas BAIGTAS %s | trukme=%.1fs | nauji=%d | db_dydis=%d",
        finished.isoformat(timespec="seconds"),
        (finished - started).total_seconds(),
        total_new,
        store.count(),
    )

    try:
        gh_cfg = GithubConfig(
            enabled=settings.github_enabled,
            token=settings.github_token,
            repo=settings.github_repo,
            branch=settings.github_branch,
            file_path=settings.github_file_path,
            max_items=settings.github_max_items,
        )
        export_and_push(
            db_path=settings.db_path,
            keywords=settings.keywords,
            local_path=settings.local_export_path,
            cfg=gh_cfg,
        )
    except Exception:
        logger.exception("Export/push \u012f GitHub nepavyko (ciklas nesustabdomas)")

    return summary


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
