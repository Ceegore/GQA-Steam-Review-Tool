"""Phase-7 Playwright scraper — real browser-driven review fetch.

Bypasses Steam's JSON review cache (which lags 24-72 h for new apps)
by loading the public Steam storefront in a headless Chromium and
hitting the same un-cached ``ajaxappreviews`` endpoint that the
storefront itself uses, but carrying the real browser cookies /
age-check state.

Workflow:
  1. Launch Chromium (sync API).
  2. Add an init script that masks ``navigator.webdriver`` and other
     automation signals (see ``ANTI_DETECT_JS``).
  3. Navigate to the store page so the storefront's JS sets up
     cookies + session.
  4. Try to dismiss common age-gate / cookie buttons.
  5. Use ``page.evaluate()`` to call the same AJAX endpoint the
     storefront's React app uses, looping through cursors until we
     reach ``max_reviews`` or the cursor stops advancing.
  6. Normalise the JSON into the same shape ``SteamAPI.fetch_all_reviews``
     returns so the existing Markdown exporter / dump repository
     work unchanged.

This is the Phase-7 deliverable. It gracefully degrades when
Playwright or Chromium is not installed: the entry-point functions
log a clear error and return ``[]`` so the GUI doesn't crash.
"""
from __future__ import annotations

import json
import time
from typing import Callable, Optional, Any

from ..core.constants import (
    ANTI_DETECT_JS, DEFAULT_USER_AGENT, PLAYWRIGHT_JS_WAIT_SEC,
    STEAM_LANGUAGES,
)
from ..core.logger import get_logger
from .browser_launcher import inject_anti_detect, try_dismiss_gates


_log = get_logger(__name__)


# JS expression invoked inside the browser context to fetch one page
# of reviews. Mirrors the storefront's own ajax call but accepts
# the cursor + language + filter from Python.
FETCH_PAGE_JS: str = """
async ({ appId, cursor, language, filter, numPerPage }) => {
    const url = new URL('/appreviews/' + appId,
        location.origin);
    url.searchParams.set('json', '1');
    url.searchParams.set('cursor', cursor || '*');
    url.searchParams.set('language', language || 'all');
    url.searchParams.set('filter', filter || 'all');
    url.searchParams.set('num_per_page', String(numPerPage || 100));
    url.searchParams.set('review_type', 'all');
    url.searchParams.set('purchase_type', 'all');
    url.searchParams.set('filter_offtopic_activity', 'true');
    try {
        const r = await fetch(url.toString(), {
            credentials: 'include',
            headers: { 'Accept': 'application/json, text/plain, */*' },
        });
        const text = await r.text();
        return { status: r.status, ok: r.ok, body: text };
    } catch (e) {
        return { error: String(e) };
    }
}
""".strip()


def _playwright_or_warn(
    log_cb: Optional[Callable[[str], None]],
) -> Optional[Any]:
    """Try to import playwright; return None + log on failure."""
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
        return sync_playwright
    except ImportError:
        msg = (
            "playwright Python package not installed — "
            "click 'Install Playwright' in the Dependencies panel."
        )
        _log.warning(msg)
        if log_cb:
            log_cb("❌ " + msg)
        return None


def scrape_reviews(
    app_id: int,
    *,
    language: str = "all",
    sort: str = "recent",
    max_reviews: int = 100,
    num_per_page: int = 100,
    log_cb: Optional[Callable[[str], None]] = None,
    stop_flag: Optional[Callable[[], bool]] = None,
    progress_cb: Optional[Callable[[int, int, int], None]] = None,
    resume: bool = False,
) -> list[dict[str, Any]]:
    """Launch Chromium, drive the storefront, return normalised reviews.

    Returns a list[Any] of dicts in the same shape ``SteamAPI.fetch_all_reviews``
    produces. Empty list[Any] on any failure (with a log message) so the
    GUI stays responsive.
    """
    log = log_cb or (lambda _msg: None)
    sync_playwright = _playwright_or_warn(log)
    if sync_playwright is None:
        return []

    if language not in STEAM_LANGUAGES:
        language = "all"
    num_per_page = max(1, min(int(num_per_page or 100), 100))
    max_reviews = max(1, int(max_reviews or 100))

    all_reviews: list[dict[str, Any]] = []
    cursor = "*"
    page = 0
    total_reported = 0

    log(f"Scrape start: app={app_id} lang={language} sort={sort} max={max_reviews}")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                ctx = browser.new_context(user_agent=DEFAULT_USER_AGENT)
                inject_anti_detect(ctx.new_page())
                page_obj = ctx.new_page()
                store_url = (
                    f"https://store.steampowered.com/app/{app_id}/"
                )
                log(f"Navigating to {store_url}")
                page_obj.goto(store_url, wait_until="domcontentloaded",
                               timeout=60000)
                page_obj.wait_for_timeout(int(PLAYWRIGHT_JS_WAIT_SEC * 1000))
                try_dismiss_gates(page_obj, log=log)

                while True:
                    if stop_flag and stop_flag():
                        log("Scrape cancelled by user.")
                        break
                    payload = {
                        "appId": app_id, "cursor": cursor,
                        "language": language, "filter": sort,
                        "numPerPage": num_per_page,
                    }
                    result = page_obj.evaluate(FETCH_PAGE_JS, payload)
                    if not isinstance(result, dict):
                        log(f"Page {page}: unexpected response {type(result).__name__}")
                        break
                    if "error" in result:
                        log(f"Page {page}: fetch error — {result['error']}")
                        break
                    if not result.get("ok"):
                        log(f"Page {page}: HTTP {result.get('status')}")
                        break
                    try:
                        data = json.loads(result.get("body") or "{}")
                    except (ValueError, TypeError) as exc:
                        log(f"Page {page}: bad JSON — {exc}")
                        break
                    if not data.get("success"):
                        log("Steam returned success=0; aborting.")
                        break

                    page_reviews = data.get("reviews") or []
                    total_reported = (
                        data.get("query_summary", {}).get(
                            "total_reviews", total_reported,
                        )
                    )
                    all_reviews.extend(page_reviews)
                    page += 1
                    if progress_cb:
                        try:
                            progress_cb(page, len(all_reviews), total_reported)
                        except Exception:
                            pass
                    log(
                        f"Page {page}: +{len(page_reviews)} "
                        f"(kept {len(all_reviews)} / server total {total_reported})",
                    )
                    if len(all_reviews) >= max_reviews:
                        log(f"Hit max_reviews={max_reviews}; stopping.")
                        break

                    new_cursor = data.get("cursor", "") or ""
                    if not new_cursor or new_cursor == cursor:
                        break
                    cursor = new_cursor
                    time.sleep(0.3)
            finally:
                try:
                    browser.close()
                except Exception:
                    pass
    except Exception as exc:
        msg = f"Playwright scrape failed: {type(exc).__name__}: {exc}"
        _log.exception(msg)
        log("❌ " + msg)
        return all_reviews

    log(f"Scrape done: {len(all_reviews)} reviews kept.")
    return all_reviews[:max_reviews]


def is_available() -> bool:
    """Cheap probe — ``True`` iff Playwright + Chromium are usable."""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch(headless=True)
            try:
                return True
            finally:
                b.close()
    except Exception:
        return False


__all__ = ["scrape_reviews", "is_available", "FETCH_PAGE_JS"]