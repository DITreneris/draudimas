"""Playwright scraperis viesiejipirkimai.lt isplestine paieska."""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Iterable

from playwright.sync_api import (
    Page,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)

ADVANCED_SEARCH_URL = (
    "https://viesiejipirkimai.lt/epps/prepareAdvancedSearch.do?type=cftFTS"
)
BASE_URL = "https://viesiejipirkimai.lt"

# Koloniu antrasciu pavadinimai, kuriuos ieskosim rezultatu lentelej.
HEADER_TITLE = "Pavadinimas"
HEADER_PIRKIMO_ID = "Pirkimo ID"
HEADER_PUBLISHED = "Paskelbimo data"
HEADER_ORG = "PV"

SEARCH_MAX_ATTEMPTS = 3
SEARCH_RETRY_DELAY_SEC = 15
BROWSER_LAUNCH_TIMEOUT_MS = 60_000

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResultItem:
    pirkimo_id: str
    title: str
    url: str | None
    published_at: str | None
    organization: str | None


class SearchError(RuntimeError):
    pass


def _absolute_url(href: str | None) -> str | None:
    if not href:
        return None
    href = href.strip()
    if href.startswith("http://") or href.startswith("https://"):
        return href
    if href.startswith("/"):
        return BASE_URL + href
    return f"{BASE_URL}/epps/{href}"


def _find_header_indices(page: Page) -> tuple[int, int, int | None, int | None, object]:
    """Find results table and map header name -> column index.

    Returns (title_idx, id_idx, published_idx, org_idx, table_locator).
    """
    tables = page.locator("table")
    table_count = tables.count()
    logger.debug("Found %d tables on page", table_count)

    for i in range(table_count):
        table = tables.nth(i)
        header_cells = table.locator("thead th, thead td, tr th").all()
        header_texts = [(c.inner_text() or "").strip() for c in header_cells]
        if not header_texts:
            continue

        def find_idx(name: str) -> int | None:
            for idx, txt in enumerate(header_texts):
                norm = re.sub(r"\s+", " ", txt).strip()
                if norm.lower().startswith(name.lower()):
                    return idx
            return None

        title_idx = find_idx(HEADER_TITLE)
        id_idx = find_idx(HEADER_PIRKIMO_ID)
        if title_idx is None or id_idx is None:
            continue

        published_idx = find_idx(HEADER_PUBLISHED)
        org_idx = find_idx(HEADER_ORG)
        logger.debug(
            "Results table #%d headers: title=%s id=%s published=%s org=%s",
            i,
            title_idx,
            id_idx,
            published_idx,
            org_idx,
        )
        return title_idx, id_idx, published_idx, org_idx, table

    raise SearchError(
        "Nepavyko rasti rezultatu lenteles su stulpeliais 'Pavadinimas' ir 'Pirkimo ID'."
    )


def _extract_rows(
    table,
    title_idx: int,
    id_idx: int,
    published_idx: int | None,
    org_idx: int | None,
    max_items: int,
) -> list[ResultItem]:
    rows = table.locator("tbody tr")
    total = rows.count()
    if total == 0:
        rows = table.locator("tr")
        total = rows.count()

    items: list[ResultItem] = []
    for i in range(total):
        if len(items) >= max_items:
            break
        row = rows.nth(i)
        cells = row.locator("td")
        cell_count = cells.count()
        if cell_count <= max(title_idx, id_idx):
            continue

        pirkimo_id = (cells.nth(id_idx).inner_text() or "").strip()
        if not pirkimo_id or not re.match(r"^\d+$", pirkimo_id):
            continue

        title_cell = cells.nth(title_idx)
        title = (title_cell.inner_text() or "").strip()
        link = title_cell.locator("a").first
        href: str | None = None
        try:
            if link.count() > 0:
                href = link.get_attribute("href")
        except Exception:
            href = None

        published_at = None
        if published_idx is not None and cell_count > published_idx:
            published_at = (cells.nth(published_idx).inner_text() or "").strip() or None

        organization = None
        if org_idx is not None and cell_count > org_idx:
            organization = (cells.nth(org_idx).inner_text() or "").strip() or None

        items.append(
            ResultItem(
                pirkimo_id=pirkimo_id,
                title=title,
                url=_absolute_url(href),
                published_at=published_at,
                organization=organization,
            )
        )
    return items


def _click_search(page: Page) -> None:
    """Paspaudziam 'Ieskoti' mygtuka keliais fallback budais."""
    candidates = [
        lambda: page.get_by_role("button", name=re.compile(r"Ie[sš]koti", re.I)),
        lambda: page.get_by_role("button", name=re.compile(r"Search", re.I)),
        lambda: page.locator("input[type=submit][value*='Ie']"),
        lambda: page.locator("button[type=submit]"),
    ]
    last_err: Exception | None = None
    for get_loc in candidates:
        try:
            loc = get_loc()
            if loc.count() > 0:
                loc.first.click(timeout=5000)
                return
        except Exception as e:
            last_err = e
            continue
    try:
        page.locator("#Title").press("Enter")
        return
    except Exception as e:
        last_err = e
    raise SearchError(f"Nepavyko paspausti 'Ieskoti' mygtuko: {last_err}")


def _log_search_debug(page: Page, keyword: str, attempt: int) -> None:
    if not logger.isEnabledFor(logging.DEBUG):
        return
    try:
        logger.debug(
            "Search debug keyword='%s' attempt=%d url=%s title=%r",
            keyword,
            attempt,
            page.url,
            page.title(),
        )
    except Exception:
        logger.debug(
            "Search debug keyword='%s' attempt=%d capture failed",
            keyword,
            attempt,
            exc_info=True,
        )


def _search_keyword_once(
    keyword: str,
    *,
    headless: bool,
    max_results: int,
    timeout_ms: int,
    attempt: int,
) -> list[ResultItem]:
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless, timeout=BROWSER_LAUNCH_TIMEOUT_MS
        )
        context = browser.new_context(locale="lt-LT")
        page = context.new_page()
        page.set_default_timeout(timeout_ms)
        try:
            page.goto(ADVANCED_SEARCH_URL, wait_until="domcontentloaded")
            page.wait_for_selector("#Title", timeout=timeout_ms)
            page.fill("#Title", keyword)
            _click_search(page)

            try:
                page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
            except PlaywrightTimeoutError:
                pass

            try:
                page.wait_for_function(
                    "() => Array.from(document.querySelectorAll('th,td'))"
                    ".some(el => /Pirkimo\\s*ID/i.test(el.textContent || ''))",
                    timeout=timeout_ms,
                )
            except PlaywrightTimeoutError:
                logger.warning(
                    "Laukiant rezultatu lenteles (Pirkimo ID) suveike timeout"
                )

            title_idx, id_idx, published_idx, org_idx, table = _find_header_indices(page)
            items = _extract_rows(
                table, title_idx, id_idx, published_idx, org_idx, max_results
            )
            logger.info("Keyword='%s': rasta %d rezultatu", keyword, len(items))
            return items
        except Exception:
            _log_search_debug(page, keyword, attempt)
            raise
        finally:
            try:
                context.close()
            except Exception:
                logger.warning(
                    "context.close() nepavyko keyword='%s' attempt=%d",
                    keyword,
                    attempt,
                    exc_info=True,
                )
            try:
                browser.close()
            except Exception:
                logger.warning(
                    "browser.close() nepavyko keyword='%s' attempt=%d",
                    keyword,
                    attempt,
                    exc_info=True,
                )


def search_keyword(
    keyword: str,
    headless: bool = True,
    max_results: int = 50,
    timeout_ms: int = 30000,
) -> list[ResultItem]:
    logger.info("Ieskau pagal keyword='%s' (max %d)", keyword, max_results)
    last_err: BaseException | None = None
    for attempt in range(1, SEARCH_MAX_ATTEMPTS + 1):
        try:
            return _search_keyword_once(
                keyword,
                headless=headless,
                max_results=max_results,
                timeout_ms=timeout_ms,
                attempt=attempt,
            )
        except Exception as e:
            last_err = e
            if attempt >= SEARCH_MAX_ATTEMPTS:
                raise
            logger.warning(
                "Keyword='%s' paieska nepavyko (bandymas %d/%d): %s; "
                "bandau po %ds",
                keyword,
                attempt,
                SEARCH_MAX_ATTEMPTS,
                e,
                SEARCH_RETRY_DELAY_SEC,
            )
            time.sleep(SEARCH_RETRY_DELAY_SEC)
    assert last_err is not None
    raise last_err


def search_keywords(
    keywords: Iterable[str],
    headless: bool = True,
    max_results: int = 50,
) -> dict[str, list[ResultItem]]:
    out: dict[str, list[ResultItem]] = {}
    for kw in keywords:
        try:
            out[kw] = search_keyword(kw, headless=headless, max_results=max_results)
        except Exception as e:
            logger.exception("Klaida ieskant keyword='%s': %s", kw, e)
            out[kw] = []
    return out
