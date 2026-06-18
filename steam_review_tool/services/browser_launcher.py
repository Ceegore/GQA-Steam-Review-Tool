"""Anti-detection snippets + Playwright JS helpers.

The storefront DOM is sensitive to automation; we inject a small JS
shim before navigating and pre-dismiss common age / cookie gates.
"""
from __future__ import annotations

from ..core.constants import ANTI_DETECT_JS, GATE_BUTTON_TEXTS


def inject_anti_detect(page) -> None:
    """Inject the ANTI_DETECT shim into the given Playwright ``page``."""
    try:
        page.add_init_script(ANTI_DETECT_JS)
    except Exception:
        # Old Playwright versions; ignore silently.
        pass


def try_dismiss_gates(page, log=None) -> None:
    """Click through age / content / cookie gates that may block us.

    Each candidate button is tried with a short visibility timeout;
    any failure is logged but never raised, so we keep crawling.
    """
    for text in GATE_BUTTON_TEXTS:
        try:
            btn = page.get_by_text(text, exact=False).first
            if btn.is_visible(timeout=400):
                btn.click(timeout=2000)
                if log is not None:
                    log(f"Dismissed gate: {text}")
                page.wait_for_timeout(800)
        except Exception:
            pass


__all__ = ["inject_anti_detect", "try_dismiss_gates"]