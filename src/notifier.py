"""Pranesimai apie naujus skelbimus (konsole + failas + Telegram + SMTP)."""
from __future__ import annotations

import html
import json
import logging
import smtplib
import urllib.error
import urllib.request
from email.message import EmailMessage
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


class SmtpEmailNotifier:
    """Send one plain-text email per new tender via SMTP (stdlib smtplib).

    Connection: port 465 uses SMTP_SSL; other ports use SMTP + STARTTLS.
    Errors are logged only; they never abort run_cycle. Secrets are never logged.
    """

    def __init__(
        self,
        host: str,
        port: int,
        mail_from: str,
        mail_to: list[str],
        user: str = "",
        password: str = "",
        timeout: int = 30,
    ) -> None:
        self.host = host
        self.port = port
        self.mail_from = mail_from
        self.mail_to = mail_to
        self.user = user
        self.password = password
        self.timeout = timeout

    def notify(self, keyword: str, item: ResultItem) -> None:
        msg = self._build_message(keyword, item)
        self._send(msg)

    def notify_batch(self, keyword: str, items: list[ResultItem]) -> None:
        for item in items:
            self.notify(keyword, item)

    def _build_message(self, keyword: str, item: ResultItem) -> EmailMessage:
        msg = EmailMessage()
        msg["Subject"] = f"[Viesieji pirkimai] naujas: {item.pirkimo_id}"
        msg["From"] = self.mail_from
        msg["To"] = ", ".join(self.mail_to)
        body_lines = [
            f"Raktazodis: {keyword}",
            f"Pirkimo ID: {item.pirkimo_id}",
            f"Pavadinimas: {item.title or '-'}",
            f"Organizacija: {item.organization or '-'}",
            f"Paskelbta: {item.published_at or '-'}",
            f"URL: {item.url or '-'}",
        ]
        msg.set_content("\n".join(body_lines))
        return msg

    def _send(self, message: EmailMessage) -> None:
        try:
            if self.port == 465:
                with smtplib.SMTP_SSL(
                    self.host, self.port, timeout=self.timeout
                ) as smtp:
                    if self.user:
                        smtp.login(self.user, self.password)
                    smtp.send_message(message)
            else:
                with smtplib.SMTP(self.host, self.port, timeout=self.timeout) as smtp:
                    smtp.starttls()
                    if self.user:
                        smtp.login(self.user, self.password)
                    smtp.send_message(message)
        except Exception:
            logger.exception(
                "SMTP send_message nepavyko (host=%s port=%s)",
                self.host,
                self.port,
            )
