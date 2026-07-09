"""Playwright scraperis viesiejipirkimai.lt isplestine paieska."""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Iterable

from playwright.sync_api import (
    Browser,
    Page,
    Playwright,
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


def _build_chromium_launch_args(*, single_process: bool) -> list[str]:
    args = [
        "--disable-gpu",
        "--no-zygote",
        "--disable-dev-shm-usage",
    ]
    if single_process:
        args.append("--single-process")
    return args


def _launch_browser(
    p: Playwright, *, headless: bool, single_process: bool
) -> Browser:
    return p.chromium.launch(
        headless=headless,
        timeout=BROWSER_LAUNCH_TIMEOUT_MS,
        args=_build_chromium_launch_args(single_process=single_process),
    )


def _close_browser_safe(browser: Browser | None) -> None:
    if browser is None:
        return
    try:
        browser.close()
    except Exception:
        logger.warning("browser.close() nepavyko", exc_info=True)


def _is_browser_dead_error(exc: BaseException) -> bool:
    name = type(exc).__name__
    if name in {"TargetClosedError", "BrowserClosedError"}:
        return True
    msg = str(exc).lower()
    return (
        "browser has been closed" in msg
        or "target page, context or browser has been closed" in msg
    )


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


def _search_in_context(
    browser: Browser,
    keyword: str,
    *,
    max_results: int,
    timeout_ms: int,
    attempt: int,
) -> list[ResultItem]:
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
        return _extract_rows(
            table, title_idx, id_idx, published_idx, org_idx, max_results
        )
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


def _relaunch_browser(
    browser_ref: list[Browser | None],
    p: Playwright,
    *,
    headless: bool,
    single_process: bool,
    keyword: str,
) -> bool:
    _close_browser_safe(browser_ref[0])
    browser_ref[0] = None
    try:
        browser_ref[0] = _launch_browser(
            p, headless=headless, single_process=single_process
        )
        return True
    except Exception:
        logger.exception("Chromium relaunch nepavyko keyword='%s'", keyword)
        return False


def _search_keyword_on_browser(
    browser_ref: list[Browser | None],
    p: Playwright,
    keyword: str,
    *,
    headless: bool,
    single_process: bool,
    max_results: int,
    timeout_ms: int,
) -> list[ResultItem] | None:
    if browser_ref[0] is None:
        if not _relaunch_browser(
            browser_ref, p, headless=headless, single_process=single_process, keyword=keyword
        ):
            return None

    last_err: BaseException | None = None
    for attempt in range(1, SEARCH_MAX_ATTEMPTS + 1):
        browser = browser_ref[0]
        if browser is None:
            return None
        try:
            items = _search_in_context(
                browser,
                keyword,
                max_results=max_results,
                timeout_ms=timeout_ms,
                attempt=attempt,
            )
            logger.info("Keyword='%s': rasta %d rezultatu", keyword, len(items))
            return items
        except Exception as e:
            last_err = e
            if _is_browser_dead_error(e):
                if not _relaunch_browser(
                    browser_ref,
                    p,
                    headless=headless,
                    single_process=single_process,
                    keyword=keyword,
                ):
                    return None
            if attempt >= SEARCH_MAX_ATTEMPTS:
                logger.error(
                    "Keyword='%s' paieska nepavyko po %d bandymu: %s",
                    keyword,
                    SEARCH_MAX_ATTEMPTS,
                    last_err,
                )
                return None
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
    return None


def search_keywords_for_cycle(
    keywords: Iterable[str],
    *,
    headless: bool = True,
    max_results: int = 50,
    timeout_ms: int = 30000,
    single_process: bool = False,
) -> dict[str, list[ResultItem] | None]:
    """Vienas Chromium browser visam ciklui; naujas context kiekvienam keyword."""
    kw_list = list(keywords)
    if not kw_list:
        return {}

    logger.info(
        "Ieskau %d keyword(s) vienu browser (max %d/kw, single_process=%s)",
        len(kw_list),
        max_results,
        single_process,
    )

    results: dict[str, list[ResultItem] | None] = {}
    with sync_playwright() as p:
        browser_ref: list[Browser | None] = [None]
        try:
            browser_ref[0] = _launch_browser(
                p, headless=headless, single_process=single_process
            )
        except Exception:
            logger.exception("Chromium launch nepavyko")
            return {kw: None for kw in kw_list}

        for keyword in kw_list:
            logger.info("Ieskau pagal keyword='%s' (max %d)", keyword, max_results)
            results[keyword] = _search_keyword_on_browser(
                browser_ref,
                p,
                keyword,
                headless=headless,
                single_process=single_process,
                max_results=max_results,
                timeout_ms=timeout_ms,
            )

        _close_browser_safe(browser_ref[0])
        browser_ref[0] = None

    return results


def search_keyword(
    keyword: str,
    headless: bool = True,
    max_results: int = 50,
    timeout_ms: int = 30000,
    single_process: bool = False,
) -> list[ResultItem]:
    results = search_keywords_for_cycle(
        [keyword],
        headless=headless,
        max_results=max_results,
        timeout_ms=timeout_ms,
        single_process=single_process,
    )
    items = results.get(keyword)
    if items is None:
        raise SearchError(f"Keyword='{keyword}' paieska nepavyko")
    return items


def search_keywords(
    keywords: Iterable[str],
    headless: bool = True,
    max_results: int = 50,
    single_process: bool = False,
) -> dict[str, list[ResultItem]]:
    raw = search_keywords_for_cycle(
        keywords,
        headless=headless,
        max_results=max_results,
        single_process=single_process,
    )
    return {kw: (items if items is not None else []) for kw, items in raw.items()}
