"""Prane\u0161imai apie naujus skelbimus (MVP: konsole + failas)."""
from __future__ import annotations

import logging
from pathlib import Path

from .scraper import ResultItem

logger = logging.getLogger(__name__)


class ConsoleLogNotifier:
    def __init__(self, log_path: Path) -> None:
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def notify(self, keyword: str, item: ResultItem) -> None:
        msg = (
            f"[NEW] keyword='{keyword}' id={item.pirkimo_id} "
            f"title='{item.title}' org='{item.organization or '-'}' "
            f"published='{item.published_at or '-'}' url={item.url or '-'}"
        )
        logger.info(msg)
        try:
            with self.log_path.open("a", encoding="utf-8") as f:
                f.write(msg + "\n")
        except Exception:
            logger.exception("Nepavyko irasyti i log faila %s", self.log_path)

    def notify_batch(self, keyword: str, items: list[ResultItem]) -> None:
        for item in items:
            self.notify(keyword, item)
