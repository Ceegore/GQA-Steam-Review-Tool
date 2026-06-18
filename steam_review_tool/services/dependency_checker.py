"""Detect whether Playwright and Chromium are installed."""
from __future__ import annotations

from .python_runtime import find_external_python, probe_external_python


def is_playwright_available() -> bool:
    """``True`` if the active interpreter (or external one, when frozen)
    can ``import playwright``.
    """
    ok, _ = probe_external_python("import playwright")
    return ok


def is_chromium_installed() -> bool:
    """``True`` if the Playwright Chromium binary is downloaded."""
    snippet = (
        "from playwright.sync_api import sync_playwright;"
        "p=sync_playwright().start();"
        "p.chromium.launch();"
        "p.stop()"
    )
    ok, _ = probe_external_python(snippet, timeout=45)
    return ok


__all__ = ["is_playwright_available", "is_chromium_installed"]