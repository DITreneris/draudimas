"""SQLite busenos sluoksnis - 'seen_items' saugojimas."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS seen_items (
    pirkimo_id TEXT PRIMARY KEY,
    title TEXT,
    url TEXT,
    first_seen_at TEXT NOT NULL,
    keyword_first_seen TEXT,
    published_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_seen_items_first_seen
    ON seen_items (first_seen_at);
"""


class SeenStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def filter_new(self, pirkimo_ids: Iterable[str]) -> set[str]:
        ids = [pid for pid in pirkimo_ids if pid]
        if not ids:
            return set()
        placeholders = ",".join("?" for _ in ids)
        with self._connect() as conn:
            cur = conn.execute(
                f"SELECT pirkimo_id FROM seen_items WHERE pirkimo_id IN ({placeholders})",
                ids,
            )
            seen = {row["pirkimo_id"] for row in cur.fetchall()}
        return set(ids) - seen

    def mark_seen(
        self,
        pirkimo_id: str,
        title: str | None,
        url: str | None,
        keyword: str,
        published_at: str | None = None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO seen_items
                    (pirkimo_id, title, url, first_seen_at, keyword_first_seen, published_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (pirkimo_id, title, url, now, keyword, published_at),
            )

    def count(self) -> int:
        with self._connect() as conn:
            cur = conn.execute("SELECT COUNT(*) AS c FROM seen_items")
            return int(cur.fetchone()["c"])
