"""Phase-7 Playwright scraper — real browser-driven review fetch.

Bypasses Steam's JSON review cache (which lags 24-72 h for new apps)
by loading the public Steam storefront in a headless Chromium and
hitting the same un-cached ``ajaxappreviews`` endpoint that the
storefront itself uses, but carrying the real browser cookies /
age-check state.

Two execution paths, picked automatically:

* **In-process** (default, ``python main.py``): Playwright is
  imported in this interpreter and the scrape loop runs directly
  on the GUI thread's worker.

* **Subprocess** (frozen ``.exe``): ``sys.frozen`` is True, so there
  is no Python interpreter inside the binary to do ``import
  playwright``. We instead spawn an external Python interpreter
  that runs the helper script in
  :mod:`steam_review_tool.services.playwright_subprocess_scraper`
  and stream progress / reviews / logs back via JSON-lines on
  stdout.
"""
from __future__ import annotations

import json
import sys
import time
from typing import Any, Callable, Optional

from ..core.constants import (
    ANTI_DETECT_JS, DEFAULT_USER_AGENT, PLAYWRIGHT_JS_WAIT_SEC,
    STEAM_LANGUAGES,
)
from ..core.logger import get_logger
from . import playwright_subprocess_scraper
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
            "playwright Python package not installed in the current "
            "Python interpreter — click 'Install Playwright' in the "
            "Dependencies panel."
        )
        _log.warning(msg)
        if log_cb:
            log_cb(msg)
        return None


def _normalise_inputs(language: str, max_reviews: int,
                      num_per_page: int) -> tuple[str, int, int]:
    if language not in STEAM_LANGUAGES:
        language = "all"
    num_per_page = max(1, min(int(num_per_page or 100), 100))
    max_reviews = max(1, int(max_reviews or 100))
    return language, max_reviews, num_per_page


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

    Returns a list of dicts in the same shape ``SteamAPI.fetch_all_reviews``
    produces. Empty list on any failure (with a log message) so the
    GUI stays responsive.

    When the app is frozen (``sys.frozen``), the whole scrape runs in
    a subprocess so we can use Playwright + Chromium installed in an
    external Python interpreter.
    """
    log = log_cb or (lambda _msg: None)
    language, max_reviews, num_per_page = _normalise_inputs(
        language, max_reviews, num_per_page,
    )

    if getattr(sys, "frozen", False):
        # Single-file .exe: we have no Python in-process, so route
        # the whole scrape through an external interpreter.
        return playwright_subprocess_scraper.scrape_reviews_subprocess(
            app_id, language=language, sort=sort,
            max_reviews=max_reviews, num_per_page=num_per_page,
            fetch_page_js=FETCH_PAGE_JS,
            log_cb=log, stop_flag=stop_flag, progress_cb=progress_cb,
        )

    sync_playwright = _playwright_or_warn(log)
    if sync_playwright is None:
        return []

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
                # Anti-detect must be installed on the *page that
                # actually navigates*. Installing it on a throwaway
                # page (the previous behaviour) left the real
                # page_obj with no shim and Steam's bot detection
                # could flag the session.
                page_obj = ctx.new_page()
                inject_anti_detect(page_obj)
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
                    # ``or {}`` collapses a present-but-None
                    # ``query_summary`` (e.g. from a hand-rolled test
                    # response) into an empty dict so the chained
                    # ``.get`` doesn't crash on ``None.get``.
                    total_reported = (
                        (data.get("query_summary") or {}).get(
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
        log(msg)
        return all_reviews

    log(f"Scrape done: {len(all_reviews)} reviews kept.")
    return all_reviews[:max_reviews]


def is_available() -> bool:
    """Cheap probe — ``True`` iff Playwright + Chromium are usable."""
    if getattr(sys, "frozen", False):
        # When frozen we can't import playwright in-process; defer to
        # the subprocess-based check the GUI already uses.
        from . import dependency_checker
        return dependency_checker.is_chromium_installed()
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
