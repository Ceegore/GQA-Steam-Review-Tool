"""Playwright-safe error handling.

R28 introduces this helper to narrow the 4
``except Exception: pass`` sites in the Playwright
service files (``browser_launcher.py``,
``playwright_scraper.py``,
``playwright_subprocess_scraper.py``) to the
actually-expected exception class — Playwright's
own :class:`playwright.sync_api.Error`.

The R26 lesson was "narrow ``except Exception: pass``
to the actually-expected exception class" — but
R26 left the Playwright sites alone because the
narrowing would require a top-level
``from playwright.sync_api import Error`` import
that breaks the app when Playwright is not
installed (it's an optional dependency).

R28 closes that loop: this module does the
``ImportError``-safe import at the top of the file
ONCE, and exports ``_PlaywrightError`` which is
either ``playwright.sync_api.Error`` (when
Playwright is installed) or ``Exception`` (when
it's not — fallback to the current behavior so
the app still functions).

Usage in the affected service files::

    from ._playwright_safe import _PlaywrightError
    ...
    try:
        btn.click(timeout=2000)
    except _PlaywrightError:
        # Only swallows Playwright's own errors
        # (TimeoutError, TargetClosedError, etc.).
        # Programming bugs like AttributeError
        # propagate, which is the right behavior.
        pass
"""
from __future__ import annotations


# Try to import Playwright's public Error class.
# If Playwright is not installed (it's an optional
# dependency), fall back to the stdlib Exception
# so the app still functions. The 4 sites that
# use this helper wrap Playwright operations
# (is_visible, click, wait_for_timeout,
# browser.close) which raise from
# ``playwright._impl._errors``; when Playwright
# is missing, those operations can't run, so the
# except branches are never reached in practice
# — the fallback to Exception is just a safety net.
try:
    from playwright.sync_api import Error as _PlaywrightError
except ImportError:
    _PlaywrightError = Exception  # type: ignore[assignment,misc]


__all__ = ["_PlaywrightError"]
