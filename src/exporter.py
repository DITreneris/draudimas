"""Export SQLite -> items.json ir push'as i GitHub per REST API."""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import sqlite3
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GithubConfig:
    enabled: bool
    token: str
    repo: str
    branch: str
    file_path: str
    max_items: int

    def is_valid(self) -> bool:
        return self.enabled and bool(self.token) and bool(self.repo)


def _fetch_items(db_path: Path, max_items: int) -> list[dict[str, Any]]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            """
            SELECT pirkimo_id, title, url, first_seen_at, keyword_first_seen, published_at
            FROM seen_items
            ORDER BY first_seen_at DESC
            LIMIT ?
            """,
            (max_items,),
        )
        rows = cur.fetchall()
    finally:
        conn.close()
    return [
        {
            "pirkimo_id": r["pirkimo_id"],
            "title": r["title"],
            "url": r["url"],
            "first_seen_at": r["first_seen_at"],
            "keyword_first_seen": r["keyword_first_seen"],
            "published_at": r["published_at"],
        }
        for r in rows
    ]


def build_payload(
    db_path: Path,
    keywords: list[str],
    max_items: int,
) -> dict[str, Any]:
    items = _fetch_items(db_path, max_items)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "stats": {
            "total_items": len(items),
            "keywords": keywords,
        },
        "items": items,
    }


def write_local(payload: dict[str, Any], local_path: Path) -> None:
    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _gh_request(
    method: str,
    url: str,
    token: str,
    body: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any]]:
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "viesiejipirkimai-agent")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8") or "{}"
            return resp.status, json.loads(raw)
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body_text) if body_text else {}
        except json.JSONDecodeError:
            parsed = {"raw": body_text}
        return e.code, parsed


def _get_remote_sha(cfg: GithubConfig) -> str | None:
    url = (
        f"https://api.github.com/repos/{cfg.repo}/contents/{cfg.file_path}"
        f"?ref={cfg.branch}"
    )
    status, data = _gh_request("GET", url, cfg.token)
    if status == 200 and isinstance(data, dict):
        return data.get("sha")
    if status == 404:
        return None
    logger.warning("GitHub GET %s status=%s body=%s", url, status, data)
    return None


def push_to_github(
    payload: dict[str, Any],
    cfg: GithubConfig,
    commit_message: str | None = None,
) -> bool:
    """Push payload JSON to GitHub. Returns True if commited, False if skipped/failed."""
    if not cfg.is_valid():
        logger.debug("GitHub export neaktyvus arba n\u0117ra token/repo \u2014 praleid\u017eiu")
        return False

    content_str = json.dumps(payload, ensure_ascii=False, indent=2)
    content_b64 = base64.b64encode(content_str.encode("utf-8")).decode("ascii")

    sha = _get_remote_sha(cfg)

    url = f"https://api.github.com/repos/{cfg.repo}/contents/{cfg.file_path}"
    body: dict[str, Any] = {
        "message": commit_message
        or f"chore(data): update items.json {payload.get('generated_at','')}",
        "content": content_b64,
        "branch": cfg.branch,
    }
    if sha:
        body["sha"] = sha

    status, data = _gh_request("PUT", url, cfg.token, body)
    if status in (200, 201):
        commit = (data or {}).get("commit", {})
        logger.info(
            "GitHub push OK sha=%s message='%s'",
            commit.get("sha", "?")[:7],
            body["message"],
        )
        return True
    logger.error("GitHub push FAILED status=%s body=%s", status, data)
    return False


def export_and_push(
    db_path: Path,
    keywords: list[str],
    local_path: Path,
    cfg: GithubConfig,
) -> bool:
    payload = build_payload(db_path, keywords, cfg.max_items)
    write_local(payload, local_path)
    digest = hashlib.sha256(
        json.dumps(payload["items"], sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:12]
    logger.info(
        "Export: %d items (digest=%s) -> %s",
        len(payload["items"]),
        digest,
        local_path,
    )
    if not cfg.is_valid():
        return False
    return push_to_github(payload, cfg)
