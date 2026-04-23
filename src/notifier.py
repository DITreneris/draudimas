"""Pranesimai apie naujus skelbimus (konsole + failas + Telegram)."""
from __future__ import annotations

import html
import json
import logging
import urllib.error
import urllib.request
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


class TelegramNotifier:
    """Siuncia pranesima i Telegram asmenini chat'a per Bot API (urllib only).

    Token'a gaunam is @BotFather; chat_id - is @userinfobot arba per
    getUpdates po '/start' botui. Sios klases klaidos NIEKADA nepraleidziamos
    i iskaitomaji ciklo srauta - tik logdinamos, kad `run_cycle` tesiasi.
    """

    API_BASE = "https://api.telegram.org"

    def __init__(self, bot_token: str, chat_id: str, timeout: int = 15) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.timeout = timeout

    def notify(self, keyword: str, item: ResultItem) -> None:
        text = self._format_message(keyword, item)
        self._send(text)

    def notify_batch(self, keyword: str, items: list[ResultItem]) -> None:
        for item in items:
            self.notify(keyword, item)

    @staticmethod
    def _format_message(keyword: str, item: ResultItem) -> str:
        title = html.escape(item.title or "-")
        org = html.escape(item.organization or "-")
        published = html.escape(item.published_at or "-")
        kw = html.escape(keyword)
        pid = html.escape(item.pirkimo_id)
        lines = [
            f"<b>Naujas pirkimas</b> (raktazodis: <code>{kw}</code>)",
            f"{title}",
            f"Pirkimo ID: <code>{pid}</code>",
            f"Organizacija: {org}",
            f"Paskelbta: {published}",
        ]
        if item.url:
            lines.append(item.url)
        return "\n".join(lines)

    def _send(self, text: str) -> None:
        url = f"{self.API_BASE}/bot{self.bot_token}/sendMessage"
        body = json.dumps(
            {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": False,
            }
        ).encode("utf-8")
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("User-Agent", "viesiejipirkimai-agent")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                if resp.status != 200:
                    logger.warning(
                        "Telegram sendMessage netiketas status=%s", resp.status
                    )
        except urllib.error.HTTPError as e:
            # Never log the token; URL contains it, so only log the status and
            # the (non-sensitive) response body.
            err_body = e.read().decode("utf-8", errors="replace")
            logger.error(
                "Telegram sendMessage HTTP %s chat_id=%s body=%s",
                e.code,
                self.chat_id,
                err_body,
            )
        except Exception:
            logger.exception(
                "Telegram sendMessage nepavyko (chat_id=%s)", self.chat_id
            )
