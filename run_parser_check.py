"""Offline parser smoke: fixtures/search_results_table.html be portalo."""
from __future__ import annotations

import logging
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from main import setup_logging
from src.config import load_settings
from src.scraper import _extract_rows, _find_header_indices

_FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "search_results_table.html"


def main() -> int:
    settings = load_settings()
    setup_logging(settings.log_level)
    log = logging.getLogger("run_parser_check")

    if not _FIXTURE_PATH.is_file():
        log.error("Fixture nerastas: %s", _FIXTURE_PATH)
        return 1

    fixture_html = _FIXTURE_PATH.read_text(encoding="utf-8")
    log.info("Tikrinu parseri su fixture %s", _FIXTURE_PATH.name)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.set_content(fixture_html, wait_until="domcontentloaded")
                title_idx, id_idx, published_idx, org_idx, table = (
                    _find_header_indices(page)
                )
                items = _extract_rows(
                    table,
                    title_idx,
                    id_idx,
                    published_idx,
                    org_idx,
                    max_items=50,
                )
            finally:
                browser.close()
    except Exception:
        log.exception("Parserio fixture testas nepavyko")
        return 1

    if len(items) < 1:
        log.error("Parseris grazino 0 irasu (tiketas >= 1)")
        return 1

    bad_ids = [it.pirkimo_id for it in items if not re.match(r"^\d+$", it.pirkimo_id)]
    if bad_ids:
        log.error("Netinkami pirkimo_id: %s", bad_ids)
        return 1

    first = items[0]
    if first.pirkimo_id != "8202849":
        log.error("Pirmas id=%s (tiketas 8202849)", first.pirkimo_id)
        return 1
    if "vadovu civilines atsakomybes draudimas" not in (first.title or "").lower():
        log.error("Pirmas title netiketas: %r", first.title)
        return 1
    if not first.url or "resourceId=8202849" not in first.url:
        log.error("Pirmas url netiketas: %r", first.url)
        return 1
    if not first.published_at or "05/06/2026" not in first.published_at:
        log.error("Pirma data netiketa: %r", first.published_at)
        return 1
    if not first.organization or "Via Lietuva" not in first.organization:
        log.error("Pirma organizacija netiketa: %r", first.organization)
        return 1

    log.info("Parserio fixture OK: %d irasu, pirmas id=%s", len(items), first.pirkimo_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
