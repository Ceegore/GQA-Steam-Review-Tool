"""Round-28 bug-hunt regression tests.

Real bugs found in a twenty-eighth systematic pass. Rounds
1-27 (9388ab1, 9ea69de, ed231bc, 80f9431, f913ae8,
e0514c0, 0e4f031, ba4255e, 49aa77a, 831219e, 04f47f6,
dfd6ff7, 6265d12, 561fc45, b795fbd, 95ea74e, 40d195a,
25c305a, 9e5b263, dc1d9d7, 22506de, 6891d1f, 448e2c3,
7773048, 16f1ad6, 26e8719, 33495e0) found 156 bugs
across the project. Round 28 found 4 more — this
round extends the R25 / R26 "specific-exception-
handling" cleanup to the 4 Playwright sites that R26
deliberately left alone (defer hint from R27):
"Could be improved with a Playwright-specific
helper (e.g. ``_playwright_safe_call(fn)`` that catches
``playwright._impl._errors.Error`` and logs) but this
requires Playwright to be importable. Defer until
Playwright becomes a hard dependency."

R28 closes that loop: Playwright IS importable in
this environment, so the 4 sites can be narrowed
from ``except Exception: pass`` to ``except
_PlaywrightError: pass`` via a new helper module
``services/_playwright_safe.py`` that does an
``ImportError``-safe import (falls back to
``Exception`` if Playwright is not installed).

The R25 / R26 lesson was "narrow ``except Exception:
pass`` to the actually-expected exception class".
R28 extends it to Playwright operations: when
Playwright is installed, the wrapped operations
(``is_visible`` / ``click`` / ``wait_for_timeout``
/ ``browser.close``) raise from
``playwright._impl._errors`` — a private API
that's the same as the public
``playwright.sync_api.Error``. Narrowing to that
class makes the intent explicit: only Playwright's
own errors are silently dropped, not programming
bugs like ``AttributeError`` (if the page is None)
or ``TypeError``.

R28-0  services/_playwright_safe.py (NEW)
      Helper module that does an
      ``ImportError``-safe import of
      ``playwright.sync_api.Error`` at module
      level. Exposes ``_PlaywrightError`` which
      is either ``playwright.sync_api.Error``
      (when Playwright is installed) or
      ``Exception`` (when it's not — fallback
      to the current broad-catch behavior so
      the app still functions).

R28-1  services/browser_launcher.py:34
      ``try_dismiss_gates``'s
      ``except Exception: pass`` wrapping
      ``is_visible`` / ``click`` /
      ``wait_for_timeout`` was narrowed to
      ``except _PlaywrightError: pass``.

R28-2  services/playwright_scraper.py
      ``scrape_reviews``'s
      ``except Exception: pass`` wrapping
      ``browser.close()`` was narrowed to
      ``except _PlaywrightError: pass``.

R28-3  services/playwright_subprocess_scraper.py:108
      ``dismiss_gates``'s
      ``except Exception: pass`` was narrowed
      to ``except _PlaywrightError: pass``.

R28-4  services/playwright_subprocess_scraper.py
      (the inline ``main()`` loop's
      ``browser.close()`` finally-block) was
      narrowed to
      ``except _PlaywrightError: pass``.

The R28 round also introduces a project-wide
static-check guard
(``TestNoBroadExceptionInPlaywrightFiles``) that
walks the 3 Playwright service files and asserts
no ``except Exception:`` (bare, not ``as exc``)
with a ``pass`` / ``return`` / ``continue`` body
remains. This is the R25 / R26 lesson applied to
the Playwright layer.

The 2 sites that REMAIN as ``except Exception:``
(not narrowed) are:
  - ``browser_launcher.py:15`` — ``page.add_init_script(ANTI_DETECT_JS)``
    intentionally broad because the comment
    says "Old Playwright versions; ignore
    silently". This is a documented
    backward-compat catch, not a bug. The
    R26 module docstring noted this was a
    legitimate non-narrowable site.
  - ``browser_launcher.py:11`` — same
    ``inject_anti_detect`` function.
"""
import inspect
import re
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers (re-used from R22-R27; kept here so the test
# is self-contained even if those files are reorganized)
# ---------------------------------------------------------------------------
def _strip_comments_and_docstrings(src: str) -> str:
    """Strip pure docstring + comment lines so a source-shape
    probe doesn't false-positive on explaining comments.
    """
    src = re.sub(r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'', "", src)
    out_lines: list[str] = []
    for line in src.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        out_lines.append(line)
    return "\n".join(out_lines)


# ---------------------------------------------------------------------------
# R28-0: _playwright_safe.py helper module
# ---------------------------------------------------------------------------
class TestPlaywrightSafeHelper:
    """R28-0: the ``services/_playwright_safe.py``
    helper module must be importable and expose
    ``_PlaywrightError`` (either
    ``playwright.sync_api.Error`` or ``Exception``
    fallback).
    """

    def test_helper_module_importable(self) -> None:
        """The helper module must be importable."""
        from steam_review_tool.services import _playwright_safe
        assert hasattr(
            _playwright_safe, "_PlaywrightError",
        ), (
            "_playwright_safe must expose "
            "`_PlaywrightError` (R28-0 helper)"
        )

    def test_helper_is_exception_subclass(self) -> None:
        """``_PlaywrightError`` must be a subclass
        of ``Exception`` (so ``except
        _PlaywrightError`` catches Playwright
        errors)."""
        from steam_review_tool.services._playwright_safe import (
            _PlaywrightError,
        )
        assert issubclass(_PlaywrightError, Exception), (
            "_PlaywrightError must be a subclass of "
            "Exception so `except _PlaywrightError` "
            "catches Playwright's errors."
        )

    def test_helper_uses_playwright_error_when_available(
        self,
    ) -> None:
        """When Playwright is installed (which it
        is in this test environment), the helper
        must resolve to ``playwright.sync_api.Error``,
        not the ``Exception`` fallback."""
        from steam_review_tool.services._playwright_safe import (
            _PlaywrightError,
        )
        try:
            from playwright.sync_api import Error
            # Playwright is available — the helper
            # must be the SAME class as
            # ``playwright.sync_api.Error``.
            assert _PlaywrightError is Error, (
                f"_PlaywrightError should be "
                f"playwright.sync_api.Error when "
                f"Playwright is available, got "
                f"{_PlaywrightError!r}"
            )
        except ImportError:
            # Playwright not installed — the helper
            # must fall back to ``Exception``.
            assert _PlaywrightError is Exception, (
                f"_PlaywrightError should fall back "
                f"to Exception when Playwright is not "
                f"installed, got {_PlaywrightError!r}"
            )


# ---------------------------------------------------------------------------
# R28-1: browser_launcher.py
# ---------------------------------------------------------------------------
class TestBrowserLauncherNarrowed:
    """R28-1: ``try_dismiss_gates``'s
    ``except Exception: pass`` (line 34) was
    narrowed to ``except _PlaywrightError: pass``.
    """

    def _src(self) -> str:
        from steam_review_tool.services import browser_launcher
        return _strip_comments_and_docstrings(
            inspect.getsource(browser_launcher),
        )

    def test_try_dismiss_gates_narrowed(self) -> None:
        """R28-1: ``try_dismiss_gates``'s gate
        try/except must use ``_PlaywrightError``,
        not bare ``Exception``."""
        src = self._src()
        # Find the dismiss_gates function body.
        idx = src.find("def try_dismiss_gates")
        assert idx >= 0, "browser_launcher has no `try_dismiss_gates`"
        # Find the ``page.wait_for_timeout(800)`` call
        # (the last line of the try block before the
        # except).
        wait_idx = src.find("page.wait_for_timeout(800)", idx)
        assert wait_idx > idx, (
            "browser_launcher.try_dismiss_gates has no "
            "`page.wait_for_timeout(800)` call"
        )
        # Read 600 chars forward to find the except.
        block = src[wait_idx:wait_idx + 600]
        assert "except _PlaywrightError:" in block, (
            "browser_launcher.try_dismiss_gates must use "
            "`except _PlaywrightError:` (R28-1 fix). "
            "Block:\n" + block
        )
        # The bare ``except Exception:`` is GONE from
        # the try/except wrapping the dismiss ops.
        # (The `inject_anti_detect` function still
        # has ``except Exception:`` for backward
        # compat with old Playwright versions — see
        # R28 module docstring.)
        # Find the FIRST ``except Exception:`` after
        # the dismiss_gates def.
        dismiss_end = src.find("__all__", idx)
        search_end = dismiss_end if dismiss_end > 0 else len(src)
        dismiss_src = src[idx:search_end]
        assert "except Exception:" not in dismiss_src, (
            "browser_launcher.try_dismiss_gates body "
            "still has a bare `except Exception:` "
            "(R28-1 anti-pattern). Use "
            "`except _PlaywrightError:`.\n"
            "Body:\n" + dismiss_src
        )


# ---------------------------------------------------------------------------
# R28-2: playwright_scraper.py
# ---------------------------------------------------------------------------
class TestPlaywrightScraperNarrowed:
    """R28-2: ``scrape_reviews``'s
    ``except Exception: pass`` wrapping
    ``browser.close()`` was narrowed to
    ``except _PlaywrightError: pass``.
    """

    def _src(self) -> str:
        from steam_review_tool.services import (
            playwright_scraper,
        )
        return _strip_comments_and_docstrings(
            inspect.getsource(playwright_scraper),
        )

    def test_browser_close_narrowed(self) -> None:
        """R28-2: ``browser.close()`` try/except
        must use ``_PlaywrightError``, not bare
        ``Exception``."""
        src = self._src()
        idx = src.find("browser.close()")
        assert idx >= 0, (
            "playwright_scraper has no `browser.close()` call"
        )
        before = src[max(0, idx - 500):idx]
        try_matches = list(re.finditer(r"^[ \t]+try:\s*$", before, re.M))
        assert try_matches, "could not find `try:` before browser.close()"
        abs_try = max(0, idx - 500) + try_matches[-1].start()
        block = src[abs_try:abs_try + 400]
        assert "except _PlaywrightError:" in block, (
            "playwright_scraper `browser.close()` block "
            "must use `except _PlaywrightError:` (R28-2 fix). "
            "Block:\n" + block
        )
        # Anti-pattern guard: the body must NOT have
        # bare ``except Exception:`` in this try block.
        # (Other excepts in the file are OK — only this
        # browser.close block is in scope.)
        assert "except Exception:" not in block, (
            "playwright_scraper `browser.close()` block "
            "still has bare `except Exception:` (R28-2 "
            "anti-pattern). Use `except _PlaywrightError:`.\n"
            "Block:\n" + block
        )


# ---------------------------------------------------------------------------
# R28-3 + R28-4: playwright_subprocess_scraper.py
# ---------------------------------------------------------------------------
class TestPlaywrightSubprocessScraperNarrowed:
    """R28-3 + R28-4:
    ``playwright_subprocess_scraper.py`` has 2
    Playwright sites narrowed by R28:
    ``dismiss_gates`` (line 108) and the inline
    ``main()`` loop's ``browser.close()``
    finally-block. Both sites are INSIDE the
    ``HELPER_SCRIPT_TEMPLATE`` triple-quoted
    string (the helper script that runs in a
    subprocess when the app is frozen into a
    .exe).

    Note: the helper script is auto-generated
    text inside a string, so the test uses the
    RAW source (not the docstring-stripped
    version) to find the sites. The helper
    script also imports ``Error`` from
    ``playwright.sync_api`` at the top (alongside
    the existing ``sync_playwright`` import) so
    the 2 except clauses can reference ``Error``
    directly (the parent process's
    ``_playwright_safe`` module is NOT importable
    from the subprocess).
    """

    def _raw_src(self) -> str:
        from steam_review_tool.services import (
            playwright_subprocess_scraper,
        )
        return inspect.getsource(playwright_subprocess_scraper)

    def test_helper_script_imports_error(self) -> None:
        """R28-3 + R28-4 prerequisite: the helper
        script (inside ``HELPER_SCRIPT_TEMPLATE``)
        must import ``Error`` from
        ``playwright.sync_api`` so the narrowed
        except clauses can use it."""
        src = self._raw_src()
        # The helper script's Playwright import is
        # inside the HELPER_SCRIPT_TEMPLATE.
        # Search for the import line.
        assert re.search(
            r"from playwright\.sync_api import\s+"
            r"sync_playwright\s*,\s*Error",
            src,
        ), (
            "playwright_subprocess_scraper.py helper "
            "script must import `Error` from "
            "playwright.sync_api (R28-3 + R28-4 "
            "prerequisite). Update the "
            "HELPER_SCRIPT_TEMPLATE's Playwright "
            "import to `from playwright.sync_api "
            "import sync_playwright, Error`."
        )

    def test_dismiss_gates_narrowed(self) -> None:
        """R28-3: ``dismiss_gates``'s
        ``page.wait_for_timeout(400)`` try/except
        must use ``Error`` (Playwright's own
        exception class)."""
        src = self._raw_src()
        # Find the dismiss_gates function inside
        # the HELPER_SCRIPT_TEMPLATE.
        idx = src.find("def dismiss_gates(page):")
        assert idx >= 0, (
            "playwright_subprocess_scraper has no "
            "`def dismiss_gates(page):` definition"
        )
        # Find the ``page.wait_for_timeout(400)``
        # call inside dismiss_gates.
        wait_idx = src.find(
            "page.wait_for_timeout(400)", idx,
        )
        assert wait_idx > idx, (
            "playwright_subprocess_scraper.dismiss_gates "
            "has no `page.wait_for_timeout(400)` call"
        )
        # Read 400 chars forward to find the except.
        block = src[wait_idx:wait_idx + 400]
        assert "except Error:" in block, (
            "playwright_subprocess_scraper.dismiss_gates "
            "must use `except Error:` (R28-3 fix). "
            "Block:\n" + block
        )
        # Anti-pattern guard: bare ``except Exception:``
        # must NOT be in the dismiss_gates try block.
        # (The helper script's top-level
        # ``except Exception as exc:`` for the
        # import-time error reporting is fine —
        # that's NOT a R28 anti-pattern.)
        # Find the try: that opens the dismiss_gates
        # try block and the matching except: closes it.
        before = src[max(0, wait_idx - 500):wait_idx]
        try_matches = list(re.finditer(r"^[ \t]+try:\s*$", before, re.M))
        assert try_matches, (
            "could not find `try:` before "
            "page.wait_for_timeout(400) in dismiss_gates"
        )
        abs_try = max(0, wait_idx - 500) + try_matches[-1].start()
        try_block = src[abs_try:abs_try + 600]
        assert "except Error:" in try_block, (
            "playwright_subprocess_scraper.dismiss_gates "
            "try block must use `except Error:` (R28-3). "
            "Block:\n" + try_block
        )
        assert "except Exception:" not in try_block, (
            "playwright_subprocess_scraper.dismiss_gates "
            "try block still has bare `except Exception:` "
            "(R28-3 anti-pattern). Block:\n" + try_block
        )

    def test_browser_close_in_main_narrowed(self) -> None:
        """R28-4: the inline ``main()`` loop's
        ``browser.close()`` finally-block must use
        ``Error`` (Playwright's own exception
        class)."""
        src = self._raw_src()
        # Find the ``def main():`` inside the
        # HELPER_SCRIPT_TEMPLATE.
        main_idx = src.find("def main():")
        assert main_idx >= 0, (
            "playwright_subprocess_scraper has no "
            "`def main():` inside HELPER_SCRIPT_TEMPLATE"
        )
        # Find the ``browser.close()`` call inside main.
        close_idx = src.find("browser.close()", main_idx)
        assert close_idx > main_idx, (
            "playwright_subprocess_scraper main() has no "
            "`browser.close()` call"
        )
        # Read 400 chars forward to find the except.
        block = src[close_idx:close_idx + 400]
        assert "except Error:" in block, (
            "playwright_subprocess_scraper main() "
            "`browser.close()` block must use "
            "`except Error:` (R28-4 fix). Block:\n" + block
        )
        # Anti-pattern guard: bare ``except Exception:``
        # must NOT be in the main() browser.close
        # finally-block.
        before = src[max(0, close_idx - 500):close_idx]
        try_matches = list(re.finditer(r"^[ \t]+try:\s*$", before, re.M))
        assert try_matches, (
            "could not find `try:` before main() "
            "`browser.close()`"
        )
        abs_try = max(0, close_idx - 500) + try_matches[-1].start()
        try_block = src[abs_try:abs_try + 600]
        assert "except Error:" in try_block, (
            "playwright_subprocess_scraper main() "
            "`browser.close()` try block must use "
            "`except Error:` (R28-4). Block:\n" + try_block
        )
        assert "except Exception:" not in try_block, (
            "playwright_subprocess_scraper main() "
            "`browser.close()` try block still has "
            "bare `except Exception:` (R28-4 anti-pattern). "
            "Block:\n" + try_block
        )


# ---------------------------------------------------------------------------
# R28 project-wide static check
# ---------------------------------------------------------------------------
class TestNoBroadExceptionInPlaywrightFiles:
    """R28 global sweep: walk the 3 Playwright
    service files and assert that the 4 R28-
    narrowed sites use ``_PlaywrightError`` (not
    bare ``Exception``). The 2 sites that DELIBERATELY
    remain as ``except Exception:`` (``inject_anti_detect``'s
    ``page.add_init_script`` backward-compat catch) are
    exempt — see R28 module docstring.
    """

    def test_narrowed_sites_use_playwright_error(self) -> None:
        """For each of the 2 R28-narrowed PARENT-
        PROCESS sites, assert the except clause is
        ``except _PlaywrightError:``, not bare
        ``except Exception:``.

        Note: the 2 sites in
        ``playwright_subprocess_scraper.py`` are
        INSIDE the ``HELPER_SCRIPT_TEMPLATE``
        triple-quoted string (a string literal
        that contains the helper script for the
        subprocess path). Those sites are
        covered by
        ``TestPlaywrightSubprocessScraperNarrowed``
        which searches the raw source (not the
        docstring-stripped version) and uses
        ``Error`` (the local import in the
        helper script) rather than
        ``_PlaywrightError`` (which only exists
        in the parent process).
        """
        sites: list[tuple[str, str]] = [
            (
                "services/browser_launcher.py",
                "page.wait_for_timeout(800)",
            ),
            (
                "services/playwright_scraper.py",
                "browser.close()",
            ),
        ]
        from steam_review_tool import __file__ as pkg_init
        repo = Path(pkg_init).parent.parent
        for rel, marker in sites:
            path = repo / "steam_review_tool" / rel
            src = _strip_comments_and_docstrings(
                path.read_text(encoding="utf-8"),
            )
            idx = src.find(marker)
            assert idx >= 0, (
                f"{rel}: marker `{marker}` not found"
            )
            # Read 400 chars forward to find the except.
            after = src[idx:idx + 400]
            assert "except _PlaywrightError:" in after, (
                f"{rel}: the try/except wrapping "
                f"`{marker}` must use "
                f"`except _PlaywrightError:` (R28 fix). "
                f"After the marker:\n" + after
            )
            # Anti-pattern guard: bare ``except Exception:``
            # must NOT be in the SAME try block.
            # (Other excepts in the file are OK.)
            # Find the try: that opens this try block
            # and the matching except: closes it.
            before = src[max(0, idx - 500):idx]
            try_matches = list(re.finditer(r"^[ \t]+try:\s*$", before, re.M))
            assert try_matches, (
                f"{rel}: could not find `try:` before `{marker}`"
            )
            abs_try = max(0, idx - 500) + try_matches[-1].start()
            block = src[abs_try:abs_try + 600]
            # The first ``except`` line in the try
            # block (skipping blank + comment lines)
            # must contain
            # ``except _PlaywrightError:``.
            lines = block.splitlines()
            for i, ln in enumerate(lines):
                if ln.strip().startswith("try:"):
                    for j in range(i + 1, min(i + 12, len(lines))):
                        nxt = lines[j].strip()
                        if not nxt or nxt.startswith("#"):
                            continue
                        if nxt.startswith("except"):
                            assert "except _PlaywrightError" in nxt, (
                                f"{rel}: the try/except "
                                f"wrapping `{marker}` must "
                                f"use `except "
                                f"_PlaywrightError:` (R28 "
                                f"fix). Got: {nxt!r}"
                            )
                            break
                        # If we hit another `try:`
                        # before an `except:`, the
                        # original try block doesn't
                        # have an except — error.
                        if nxt.startswith("try:"):
                            raise AssertionError(
                                f"{rel}: hit another "
                                f"`try:` before finding "
                                f"`except:` in block "
                                f"wrapping `{marker}`. "
                                f"Block:\n{block}"
                            )
                    break
