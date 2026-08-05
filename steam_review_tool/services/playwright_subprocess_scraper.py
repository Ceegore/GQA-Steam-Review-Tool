"""Subprocess-based Playwright scraper (frozen-.exe path).

When the app is frozen into a single-file .exe, ``from playwright.sync_api
import sync_playwright`` fails in-process because the binary has no
Python interpreter. This module owns the fallback that spawns an
external Python and streams the scrape back via JSON-lines on stdout.

Public surface:

* :func:`scrape_reviews_subprocess` — runs the full scrape in a
  subprocess and returns a list of normalised review dicts.
* :data:`HELPER_SCRIPT_TEMPLATE` — the auto-generated helper script
  (string template, ``string.Template`` style with ``$NAME``
  substitutions).

Communication protocol
----------------------
The parent writes a single JSON object to the helper's stdin:

    {"app_id": 4311090, "language": "all", "sort": "recent",
     "max_reviews": 100, "num_per_page": 100}

The helper emits one JSON object per line on stdout:

    {"type": "log",      "text": "..."}
    {"type": "progress", "page": N, "fetched": N, "total": N}
    {"type": "review",   "review": {...}}
    {"type": "error",    "error": "..."}
    {"type": "done"}

The parent forwards ``log`` to its log callback, ``progress`` to
its progress callback, accumulates ``review`` payloads, logs
``error``, and terminates the loop on ``done``.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from string import Template
from typing import Any, Callable, Optional

from ..core.constants import (
    ANTI_DETECT_JS, DEFAULT_USER_AGENT, PLAYWRIGHT_JS_WAIT_SEC,
)
from ..utils.coercion import safe_int
from .python_runtime import find_external_python


# ---------------------------------------------------------------------------
# Helper script template (filled in by ``string.Template.substitute``).
# The leading "$NAME" tokens are the only placeholders; everything else
# is literal Python that runs inside the subprocess interpreter.
# ---------------------------------------------------------------------------

HELPER_SCRIPT_TEMPLATE: str = '''\
"""Auto-generated scrape worker. Spawned by playwright_scraper when
the app is running as a frozen .exe. Reads JSON config on stdin, emits
one JSON event per line on stdout.

Event types: log / progress / review / done / error.
"""
import json
import sys
import time


def emit(obj):
    # ``ensure_ascii=True`` so the JSON we write to stdout is pure
    # ASCII. The WindowsApps python.exe (the typical interpreter
    # used when the app runs as a frozen .exe) defaults its stdout
    # encoding to the active console code page (cp1252 on
    # Western Windows). Any non-cp1252 character in our payload
    # (e.g. a Unicode game name, a review body in another script)
    # would otherwise raise ``UnicodeEncodeError`` here. The parent
    # process parses the JSON as UTF-8 so non-ASCII values
    # round-trip correctly via ``\\uXXXX`` escapes.
    sys.stdout.write(json.dumps(obj, ensure_ascii=True) + "\\n")
    sys.stdout.flush()


def log(msg):
    emit({"type": "log", "text": str(msg)})


FETCH_PAGE_JS = $FETCH_PAGE_JS
DEFAULT_USER_AGENT = $USER_AGENT
ANTI_DETECT_JS = $ANTI_DETECT_JS
PLAYWRIGHT_JS_WAIT_SEC = $WAIT_SEC


def dismiss_gates(page):
    """Click through common Steam age / cookie consent banners."""
    for text in (
        "View Page", "View Community Hub",
        "I am 18 or older", "I am 18 years or older",
        "Yes", "Continue", "OK", "I agree",
        "Accept All Cookies", "Accept",
    ):
        try:
            btn = page.get_by_role("button", name=text, exact=False)
            if btn.count() > 0:
                btn.first.click(timeout=1500)
                log("Dismissed gate: " + repr(text))
                page.wait_for_timeout(400)
        except Exception:
            pass


def main():
    cfg = json.loads(sys.stdin.read())
    app_id = int(cfg["app_id"])
    language = cfg.get("language") or "all"
    sort = cfg.get("sort") or "recent"
    max_reviews = int(cfg.get("max_reviews") or 100)
    num_per_page = int(cfg.get("num_per_page") or 100)

    log("Scrape start: app=" + str(app_id) + " lang=" + language +
        " sort=" + sort + " max=" + str(max_reviews) +
        " num_per_page=" + str(num_per_page))

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        emit({"type": "error",
              "error": "playwright Python package not installed: " + str(exc)})
        emit({"type": "done"})
        return

    cursor = "*"
    page_num = 0
    total_reported = 0
    all_count = 0

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                ctx = browser.new_context(user_agent=DEFAULT_USER_AGENT)
                # Register the init script *before* creating the page
                # so the first navigation already carries the shim;
                # the previous order (new_page → add_init_script) left
                # the first goto uncloaked, which Steam's anti-bot
                # flags as a clear automation tell.
                ctx.add_init_script(ANTI_DETECT_JS)
                page = ctx.new_page()

                store_url = "https://store.steampowered.com/app/" + str(app_id) + "/"
                log("Navigating to " + store_url)
                page.goto(store_url, wait_until="domcontentloaded",
                          timeout=60000)
                page.wait_for_timeout(int(PLAYWRIGHT_JS_WAIT_SEC * 1000))
                dismiss_gates(page)

                while True:
                    payload = {
                        "appId": app_id, "cursor": cursor,
                        "language": language, "filter": sort,
                        "numPerPage": num_per_page,
                    }
                    try:
                        result = page.evaluate(FETCH_PAGE_JS, payload)
                    except Exception as exc:
                        log("Page " + str(page_num) + ": evaluate error: " + str(exc))
                        break
                    if not isinstance(result, dict):
                        log("Page " + str(page_num) + ": unexpected response " +
                            type(result).__name__)
                        break
                    if "error" in result:
                        log("Page " + str(page_num) + ": fetch error - " +
                            str(result["error"]))
                        break
                    if not result.get("ok"):
                        log("Page " + str(page_num) + ": HTTP " +
                            str(result.get("status")))
                        break
                    try:
                        body = result.get("body") or "{}"
                        data = json.loads(body)
                    except (ValueError, TypeError) as exc:
                        log("Page " + str(page_num) + ": bad JSON - " + str(exc))
                        break
                    if not data.get("success"):
                        log("Steam returned success=0; aborting.")
                        break

                    page_reviews = data.get("reviews") or []
                    # ``or {}`` collapses a present-but-None
                    # ``query_summary`` (e.g. from a hand-rolled test
                    # response) into an empty dict so the chained
                    # ``.get`` doesn't crash on ``None.get``. The
                    # same fix lives in ``steam_api_service`` and
                    # ``playwright_scraper`` (this file is the
                    # third copy of the Steam-response walk).
                    total_reported = (data.get("query_summary") or {}).get(
                        "total_reviews", total_reported,
                    )
                    page_num += 1
                    all_count += len(page_reviews)
                    for r in page_reviews:
                        emit({"type": "review", "review": r})
                    emit({"type": "progress", "page": page_num,
                           "fetched": all_count, "total": total_reported})
                    log("Page " + str(page_num) + ": +" + str(len(page_reviews)) +
                        " (kept " + str(all_count) +
                        " / server total " + str(total_reported) + ")")
                    if all_count >= max_reviews:
                        log("Hit max_reviews=" + str(max_reviews) + "; stopping.")
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
        emit({"type": "error", "error": type(exc).__name__ + ": " + str(exc)})
    finally:
        emit({"type": "done"})


if __name__ == "__main__":
    main()
'''


def _render_helper(fetch_page_js: str, user_agent: str,
                   anti_detect_js: str, wait_sec: float) -> str:
    """Substitute the helper template's ``$NAME`` placeholders."""
    return Template(HELPER_SCRIPT_TEMPLATE).substitute(
        FETCH_PAGE_JS=repr(fetch_page_js),
        USER_AGENT=repr(user_agent),
        ANTI_DETECT_JS=repr(anti_detect_js),
        WAIT_SEC=repr(wait_sec),
    )


def scrape_reviews_subprocess(
    app_id: int, *,
    language: str, sort: str, max_reviews: int, num_per_page: int,
    fetch_page_js: str,
    log_cb: Callable[[str], None],
    stop_flag: Optional[Callable[[], bool]] = None,
    progress_cb: Optional[Callable[[int, int, int], None]] = None,
) -> list[dict[str, Any]]:
    """Spawn an external Python and stream the scrape back via JSON-lines.

    Used when the app is frozen and ``from playwright.sync_api import
    sync_playwright`` would fail in-process. Communicates with the
    helper via stdin (one JSON object) + stdout (one JSON object per
    line).
    """
    log = log_cb or (lambda _msg: None)
    py = find_external_python()
    if not py:
        log(
            "No external Python interpreter found on PATH. "
            "Install Python 3.10+ from python.org (tick 'Add to PATH') "
            "and then run 'Install Playwright'."
        )
        return []

    log(f"Running scrape in external Python: {py}")
    helper_text = _render_helper(
        fetch_page_js=fetch_page_js,
        user_agent=DEFAULT_USER_AGENT,
        anti_detect_js=ANTI_DETECT_JS,
        wait_sec=PLAYWRIGHT_JS_WAIT_SEC,
    )
    # PID + UUID-suffixed filename: two concurrent scrapes in the
    # same process used to share ``_srt_scrape_<pid>_<pid & 0xFFFF>.py``
    # because the second component duplicated the first, so a second
    # ``scrape_reviews_subprocess`` call clobbered the first helper
    # mid-scrape. UUID eliminates the collision.
    import uuid
    helper_path = (
        Path(tempfile.gettempdir())
        / f"_srt_scrape_{os.getpid()}_{uuid.uuid4().hex[:8]}.py"
    )
    try:
        helper_path.write_text(helper_text, encoding="utf-8")
    except OSError as exc:
        log(f"Could not write helper script: {exc}")
        return []

    cfg = json.dumps({
        "app_id": app_id, "language": language, "sort": sort,
        "max_reviews": max_reviews, "num_per_page": num_per_page,
    })

    all_reviews: list[dict[str, Any]] = []
    try:
        try:
            proc = subprocess.Popen(
                [py, str(helper_path)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True, bufsize=1,
            )
        except (FileNotFoundError, OSError) as exc:
            log(f"Could not launch helper: {exc}")
            return []

        try:
            proc.stdin.write(cfg)
            proc.stdin.close()
        except (BrokenPipeError, OSError):
            pass

        cancelled = False
        assert proc.stdout is not None
        for raw in proc.stdout:
            line = raw.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = msg.get("type")
            if t == "log":
                log(msg.get("text", ""))
            elif t == "progress" and progress_cb is not None:
                # ``safe_int`` tolerates None / non-numeric progress
                # fields from a buggy helper. The old bare ``int()``
                # raised on None and was swallowed by the broad
                # ``except``, silently displaying "0 / 0" to the user.
                progress_cb(
                    safe_int(msg, "page", 0),
                    safe_int(msg, "fetched", 0),
                    safe_int(msg, "total", 0),
                )
            elif t == "review":
                rv = msg.get("review")
                if isinstance(rv, dict):
                    all_reviews.append(rv)
            elif t == "error":
                log(str(msg.get("error", "")))
            elif t == "done":
                break
            if stop_flag is not None and stop_flag() and not cancelled:
                cancelled = True
                log("Scrape cancelled by user.")
                try:
                    proc.terminate()
                except OSError:
                    # R26: ``proc.terminate()`` raises
                    # ``OSError`` (or its subclass
                    # ``ProcessLookupError``) when the
                    # process is already gone. The
                    # previous bare ``except Exception: pass``
                    # would also swallow unrelated errors
                    # (e.g. ``AttributeError`` if ``proc``
                    # is None). Narrow to ``OSError`` so
                    # only the actually-expected case is
                    # silently dropped.
                    pass

        try:
            _, err = proc.communicate(timeout=10)
            if err:
                for line in err.splitlines():
                    log(f"[helper] {line}")
        except subprocess.TimeoutExpired:
            log("Scrape subprocess did not exit cleanly; terminating.")
            try:
                proc.kill()
            except OSError:
                # R26: ``proc.kill()`` raises ``OSError``
                # (or ``ProcessLookupError``) when the
                # process is already gone. The previous
                # bare ``except Exception: pass`` would
                # also swallow unrelated errors. Narrow
                # to ``OSError`` so only the
                # actually-expected case is silently
                # dropped.
                pass

        log(f"Scrape done: {len(all_reviews)} reviews kept.")
        return all_reviews[:max_reviews]
    finally:
        try:
            helper_path.unlink()
        except OSError:
            pass


__all__ = [
    "HELPER_SCRIPT_TEMPLATE",
    "scrape_reviews_subprocess",
]
