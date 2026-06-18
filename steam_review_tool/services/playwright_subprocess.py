"""Playwright subprocess runner.

When the app is frozen into a .exe, in-process Playwright won't work
(we don't ship the Chromium binary). Instead we spawn an external
Python interpreter and execute a small helper script that does the
actual scraping. This module owns that flow.

The helper script itself used to be a 350-line string literal embedded
in the monolith; that has now been split into ``playwright_js.py``
(JS snippets) and this module (Python orchestration).
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from ..core.constants import PLAYWRIGHT_PAGE_DELAY_SEC, PLAYWRIGHT_JS_WAIT_SEC
from ..core.logger import get_logger
from .python_runtime import find_external_python


_log = get_logger(__name__)


HELPER_SCRIPT_TEMPLATE: str = '''\
"""Auto-generated Playwright worker. DO NOT EDIT BY HAND.

Spawned by ``steam_review_tool.services.playwright_subprocess`` when
the app is running as a frozen .exe. Uses the JS snippets from
``playwright_js.py`` for in-browser DOM access.
"""
import json
import sys
import time
from typing import Any


def log(msg):
    sys.stderr.write("LOG:" + str(msg) + "\\n")
    sys.stderr.flush()


POPULARITY_JS = {popularity_js!r}


def main():
    cfg = json.loads(sys.stdin.read())
    app_id = cfg["app_id"]
    # The full scraping loop lives in the in-process
    # ``PlaywrightScraper``; the subprocess is only used as a
    # compatibility shim when the app is frozen. We just probe
    # popularity metrics here.
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context()
        ctx.add_init_script({anti_detect_js!r})
        page = ctx.new_page()
        page.goto(f"https://store.steampowered.com/app/{{app_id}}/",
                  wait_until="domcontentloaded")
        time.sleep({wait_sec!r})
        metrics = page.evaluate(POPULARITY_JS, app_id)
        sys.stdout.write(json.dumps(metrics))
        browser.close()


if __name__ == "__main__":
    main()
'''


def run_popularity_probe(app_id: int, timeout: int = 90) -> dict[str, Any]:
    """Spawn an external Python and fetch popularity metrics via Playwright.

    Returns a dict[str, Any] with keys ``wishlist``, ``followers``, ``reviews``
    (any may be ``None``).
    """
    import os
    from ..core.constants import ANTI_DETECT_JS
    py = find_external_python()
    if not py:
        return {"wishlist": None, "followers": None, "reviews": None}

    from .playwright_js import POPULARITY_JS

    helper_text = HELPER_SCRIPT_TEMPLATE.format(
        popularity_js=POPULARITY_JS,
        anti_detect_js=ANTI_DETECT_JS,
        wait_sec=PLAYWRIGHT_JS_WAIT_SEC,
    )
    # PID-suffixed filename prevents two concurrent probes from
    # clobbering each other's helper script. Also enables cleanup
    # by finding and removing any helpers left over from a crashed
    # parent process.
    helper_path = (
        Path(tempfile.gettempdir())
        / f"_srt_pw_probe_{os.getpid()}_{id(app_id) & 0xFFFF}.py"
    )
    try:
        helper_path.write_text(helper_text, encoding="utf-8")
    except OSError as exc:
        _log.warning("could not write helper script: %s", exc)
        return {"wishlist": None, "followers": None, "reviews": None}

    cfg = json.dumps({"app_id": app_id})
    try:
        result = subprocess.run(
            [py, str(helper_path)],
            input=cfg, capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode != 0:
            for line in (result.stderr or "").splitlines():
                if line.startswith("LOG:"):
                    _log.info("helper: %s", line[4:])
            return {"wishlist": None, "followers": None, "reviews": None}
        try:
            return json.loads(result.stdout or "{}")
        except (json.JSONDecodeError, ValueError) as exc:
            _log.warning("helper returned invalid JSON: %s", exc)
            return {"wishlist": None, "followers": None, "reviews": None}
    except subprocess.TimeoutExpired:
        _log.warning("Playwright probe timed out after %ds", timeout)
        return {"wishlist": None, "followers": None, "reviews": None}
    except (FileNotFoundError, OSError) as exc:
        _log.warning("Playwright probe failed: %s", exc)
        return {"wishlist": None, "followers": None, "reviews": None}
    finally:
        try:
            helper_path.unlink()
        except OSError:
            pass


__all__ = ["run_popularity_probe"]