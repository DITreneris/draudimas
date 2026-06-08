"""Vienkartinis SQLite seed is items.json (be notify / run_cycle)."""
from __future__ import annotations

import argparse
import json
import logging
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any

from main import setup_logging
from src.config import load_settings
from src.db import SCHEMA

logger = logging.getLogger("run_seed_items")

_INSERT_SQL = """
INSERT OR IGNORE INTO seen_items
    (pirkimo_id, title, url, first_seen_at, keyword_first_seen,
     published_at, organization)
VALUES (?, ?, ?, ?, ?, ?, ?)
"""


def _load_payload(path: Path) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Netinkamas JSON root tipas: {path}")
    items = raw.get("items")
    if not isinstance(items, list):
        raise ValueError(f"Truksta 'items' masyvo: {path}")
    return items


def _validate_item(row: dict[str, Any], index: int) -> dict[str, Any] | None:
    pirkimo_id = str(row.get("pirkimo_id", "")).strip()
    if not pirkimo_id or not re.match(r"^\d+$", pirkimo_id):
        logger.warning("Praleidziu eilute #%d: netinkamas pirkimo_id=%r", index, pirkimo_id)
        return None
    first_seen_at = str(row.get("first_seen_at", "")).strip()
    if not first_seen_at:
        logger.warning(
            "Praleidziu eilute #%d id=%s: truksta first_seen_at", index, pirkimo_id
        )
        return None
    return {
        "pirkimo_id": pirkimo_id,
        "title": row.get("title"),
        "url": row.get("url"),
        "first_seen_at": first_seen_at,
        "keyword_first_seen": row.get("keyword_first_seen"),
        "published_at": row.get("published_at"),
        "organization": row.get("organization"),
    }


def seed_items(
    db_path: Path,
    items: list[dict[str, Any]],
    *,
    fresh: bool,
) -> tuple[int, int, int]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if fresh and db_path.is_file():
        db_path.unlink()
        logger.info("--fresh: istrinta esama DB %s", db_path)

    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA)
        inserted = 0
        skipped = 0
        for index, row in enumerate(items, start=1):
            validated = _validate_item(row, index)
            if validated is None:
                skipped += 1
                continue
            cur = conn.execute(
                _INSERT_SQL,
                (
                    validated["pirkimo_id"],
                    validated["title"],
                    validated["url"],
                    validated["first_seen_at"],
                    validated["keyword_first_seen"],
                    validated["published_at"],
                    validated["organization"],
                ),
            )
            if cur.rowcount > 0:
                inserted += 1
            else:
                skipped += 1
        conn.commit()
        total = conn.execute("SELECT COUNT(*) FROM seen_items").fetchone()[0]
    finally:
        conn.close()
    return inserted, skipped, int(total)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Seed seen.sqlite3 is items.json (be pranesimu)."
    )
    parser.add_argument(
        "json_path",
        type=Path,
        help="Kelias iki items.json (pvz. fixtures/seed_items_59.json)",
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Istrinti esama DB pries seed (rekomenduojama atkurimui)",
    )
    args = parser.parse_args()

    settings = load_settings()
    setup_logging(settings.log_level)

    json_path = args.json_path.resolve()
    if not json_path.is_file():
        logger.error("JSON failas nerastas: %s", json_path)
        return 1

    try:
        items = _load_payload(json_path)
    except (OSError, json.JSONDecodeError, ValueError):
        logger.exception("Nepavyko nuskaityti %s", json_path)
        return 1

    if not items:
        logger.error("JSON tuscias (0 items): %s", json_path)
        return 1

    logger.info(
        "Seed PRADETAS: source=%s db=%s fresh=%s items_in_json=%d",
        json_path,
        settings.db_path,
        args.fresh,
        len(items),
    )

    try:
        inserted, skipped, total = seed_items(
            settings.db_path, items, fresh=args.fresh
        )
    except Exception:
        logger.exception("Seed nepavyko")
        return 1

    logger.info(
        "Seed BAIGTAS: inserted=%d skipped=%d db_total=%d",
        inserted,
        skipped,
        total,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
