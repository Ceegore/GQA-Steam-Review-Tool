"""Tests for the Phase-7 Playwright scraper.

Most of the scraper requires a real Chromium browser (downloaded by
``playwright install chromium``), which is not available in the
default test environment. These tests therefore cover only the
import-time helpers + the ``is_available`` smoke probe (which
short-circuits if Playwright isn't installed).
"""
from __future__ import annotations

import pytest

from steam_review_tool.services import playwright_scraper


def test_fetch_page_js_is_a_string():
    """The JS template is an async arrow function string."""
    assert isinstance(playwright_scraper.FETCH_PAGE_JS, str)
    assert "fetch" in playwright_scraper.FETCH_PAGE_JS
    assert "credentials" in playwright_scraper.FETCH_PAGE_JS


def test_scrape_returns_empty_when_playwright_missing(monkeypatch):
    """Without Playwright installed, ``scrape_reviews`` returns ``[]``
    and logs a clear error — never raises."""
    def _missing_import(*_args, **_kwargs):
        raise ImportError("playwright is not installed")

    # Stub the import inside the scraper module so it raises.
    monkeypatch.setattr(playwright_scraper, "_playwright_or_warn",
                        lambda _log: None)

    out = playwright_scraper.scrape_reviews(
        4311090, language="all", sort="recent", max_reviews=10,
        log_cb=lambda _m: None,
    )
    assert out == []


def test_is_available_returns_bool():
    """``is_available`` is a boolean probe — may return False in
    environments without Chromium installed, but must not raise.
    """
    assert isinstance(playwright_scraper.is_available(), bool)


def test_module_reexports():
    """Public symbols are exposed via ``__all__``."""
    assert "scrape_reviews" in playwright_scraper.__all__
    assert "is_available" in playwright_scraper.__all__
    assert "FETCH_PAGE_JS" in playwright_scraper.__all__