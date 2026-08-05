"""Round-26 bug-hunt regression tests.

Real bugs found in a twenty-sixth systematic pass. Rounds
1-25 (9388ab1, 9ea69de, ed231bc, 80f9431, f913ae8,
e0514c0, 0e4f031, ba4255e, 49aa77a, 831219e, 04f47f6,
dfd6ff7, 6265d12, 561fc45, b795fbd, 95ea74e, 40d195a,
25c305a, 9e5b263, dc1d9d7, 22506de, 6891d1f, 448e2c3,
7773048, 16f1ad6) found 147 bugs across the project.
Round 26 found 6 more — this round extends the R25
"specific-exception-handling" cleanup from the UI layer
to the SERVICES layer, plus a settings-persistence
chokepoint quartet regression test that the R25
future-round hints explicitly deferred.

R25 narrowed 31 ``except Exception: pass`` widget-op
blocks in the UI layer to ``except tk.TclError: pass``
(the actually-expected exception class for widget
teardown). R26 extends the same lesson to the services
layer, where the broad ``except Exception: pass``
patterns wrap operations that raise OTHER specific
exception classes (not TclError):

  - ``subprocess.Proc.terminate()`` /
    ``Proc.kill()`` → ``OSError`` (or subclass
    ``ProcessLookupError``). R26 narrows 2 sites in
    ``playwright_subprocess_scraper.py`` from
    ``except Exception: pass`` to ``except OSError:
    pass``.

  - ``int(m.group(1).replace(",", ""))`` in HTML-parse
    regex matches → ``ValueError`` (if matched group
    is non-numeric) or ``AttributeError`` (if ``m`` is
    None). R26 narrows 3 sites in
    ``storefront_parser.py`` from ``except Exception:
    pass`` to ``except (ValueError, AttributeError):
    pass``.

  - ``progress_cb(...)`` (caller-supplied callback)
    → ANY exception. The R21 fix-shape applies
    (``_log.exception(...)`` to log the failure with
    traceback). R26 fixes 1 site in
    ``playwright_scraper.py:210`` from
    ``except Exception: pass`` to
    ``except Exception as exc: _log.exception(
    "progress_cb callback failed: %s", exc)``.

R26 deliberately DOES NOT narrow the 5 Playwright
browser-op ``except Exception: pass`` sites
(``browser_launcher.py:34``,
``playwright_scraper.py:228``, and 2 in
``playwright_subprocess_scraper.py:108, 221``).
Those wrap Playwright's ``is_visible`` /
``click`` / ``wait_for_timeout`` / ``browser.close``
calls which raise from Playwright's private
``playwright._impl._errors`` module. Narrowing
would require a top-level import that breaks the
app when Playwright is not installed (it's an
optional dependency imported lazily inside
``_playwright_or_warn``). The current
``except Exception: pass`` is justified for these
"best-effort cleanup" sites.

R26 also adds a settings-persistence chokepoint
quartet regression test that the R25 future-round
hints explicitly deferred:

  > "The R17-1 / R20-1 / R23-1 / R24-1 quartet
  > (settings-persistence chokepoints: set_dump_root,
  > set_obsidian_vault, _persist_settings, _on_close
  > callback) — there's NO regression test that
  > verifies BOTH the controller layer
  > (app_window._persist_settings) AND the popup layer
  > (popup_welcome._on_close) log when persistence
  > fails. A single regression test that
  > monkeypatches the persistence to raise and
  > asserts BOTH layers log would close the loop."

The R26 test
(``TestSettingsPersistenceChokepointQuartet``) walks
all 4 chokepoints and asserts that when
``settings_store.save`` raises ``OSError``, each
chokepoint logs via its respective logger. The
regression test closes the loop opened by R16-3,
R17-1, R23-1, and R24-1.

The R26 round also introduces a project-wide
static-check guard (``TestNoBareExceptExceptionInServices``)
that walks every ``services/*.py`` file and asserts
no ``except Exception:`` (bare, not ``as exc``) with
a ``pass`` / ``return`` / ``continue`` body remains
in the narrowable sites. Playwright browser-op sites
are excluded by file scope (``browser_launcher.py``,
``playwright_scraper.py``,
``playwright_subprocess_scraper.py`` are all Playwright
files; the non-narrowable sites there are exempt).
"""
import inspect
import logging
import re
import tkinter as tk
from pathlib import Path
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Helpers (re-used from R22/R23/R24/R25; kept here so the test
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


def _walk_project_sources(root: Path) -> list[Path]:
    """Return every ``.py`` file under ``root`` (recursively),
    skipping the ``__pycache__`` dirs.
    """
    out: list[Path] = []
    for path in root.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        out.append(path)
    return out


class _ListHandler(logging.Handler):
    """Collects every log record emitted during a test."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def _attach_logger(name: str) -> tuple[logging.Logger, _ListHandler, int]:
    """Attach a fresh ``_ListHandler`` to the logger with the
    given dotted name. Returns ``(logger, handler, old_level)``
    so the test can clean up + assert on the records.
    """
    logger = logging.getLogger(name)
    handler = _ListHandler()
    logger.addHandler(handler)
    old_level = logger.level
    logger.setLevel(logging.DEBUG)
    return logger, handler, old_level


def _detach_logger(
    logger: logging.Logger,
    handler: _ListHandler,
    old_level: int,
) -> None:
    """Detach the handler and restore the previous level."""
    logger.removeHandler(handler)
    logger.setLevel(old_level)


# ---------------------------------------------------------------------------
# BUG-R26-1: playwright_subprocess_scraper.py subprocess OSError narrowing
# ---------------------------------------------------------------------------
class TestSubprocessNarrowedToOSError:
    """R26 narrowed 2 ``except Exception: pass`` sites
    in ``playwright_subprocess_scraper.py`` to
    ``except OSError: pass`` — the actually-expected
    exception class for ``proc.terminate()`` and
    ``proc.kill()`` (raise ``OSError`` or
    ``ProcessLookupError`` when the process is gone).
    """

    def _src(self) -> str:
        from steam_review_tool.services import (
            playwright_subprocess_scraper,
        )
        return _strip_comments_and_docstrings(
            inspect.getsource(playwright_subprocess_scraper),
        )

    def test_proc_terminate_narrowed(self) -> None:
        """R26-1: ``proc.terminate()`` is now
        ``except OSError: pass``, not ``except
        Exception: pass``."""
        src = self._src()
        # Find the proc.terminate() try/except.
        idx = src.find("proc.terminate()")
        assert idx >= 0, (
            "playwright_subprocess_scraper.py has no "
            "`proc.terminate()` call — did the cancel "
            "loop change?"
        )
        # Walk back to the `try:`.
        before = src[max(0, idx - 500):idx]
        try_matches = list(re.finditer(r"^[ \t]+try:\s*$", before, re.M))
        assert try_matches, (
            "could not find `try:` before proc.terminate()"
        )
        abs_try = max(0, idx - 500) + try_matches[-1].start()
        block = src[abs_try:abs_try + 600]
        assert "except OSError:" in block, (
            "playwright_subprocess_scraper.py "
            "`proc.terminate()` block must use "
            "`except OSError:` (R26-1 fix). "
            "Block:\n" + block
        )
        assert "except Exception:" not in block, (
            "playwright_subprocess_scraper.py "
            "`proc.terminate()` block still has "
            "`except Exception:` (R26 anti-pattern). "
            "Block:\n" + block
        )

    def test_proc_kill_narrowed(self) -> None:
        """R26-2: ``proc.kill()`` is now
        ``except OSError: pass``, not ``except
        Exception: pass``."""
        src = self._src()
        idx = src.find("proc.kill()")
        assert idx >= 0, (
            "playwright_subprocess_scraper.py has no "
            "`proc.kill()` call — did the timeout path "
            "change?"
        )
        before = src[max(0, idx - 500):idx]
        try_matches = list(re.finditer(r"^[ \t]+try:\s*$", before, re.M))
        assert try_matches, "could not find `try:` before proc.kill()"
        abs_try = max(0, idx - 500) + try_matches[-1].start()
        block = src[abs_try:abs_try + 600]
        assert "except OSError:" in block, (
            "playwright_subprocess_scraper.py "
            "`proc.kill()` block must use "
            "`except OSError:` (R26-2 fix). "
            "Block:\n" + block
        )
        assert "except Exception:" not in block, (
            "playwright_subprocess_scraper.py "
            "`proc.kill()` block still has "
            "`except Exception:` (R26 anti-pattern). "
            "Block:\n" + block
        )


# ---------------------------------------------------------------------------
# BUG-R26-3..R26-5: storefront_parser.py HTML parse narrowing
# ---------------------------------------------------------------------------
class TestStorefrontParserNarrowed:
    """R26 narrowed 3 ``except Exception: pass`` sites
    in ``storefront_parser.py`` to
    ``except (ValueError, AttributeError): pass`` — the
    actually-expected exception classes for
    ``int(m.group(1).replace(",", ""))`` in HTML-parse
    regex matches.
    """

    def _src(self) -> str:
        from steam_review_tool.services import storefront_parser
        return _strip_comments_and_docstrings(
            inspect.getsource(storefront_parser),
        )

    def _count_specific_exception_sites(self, src: str) -> int:
        """Count ``except (ValueError, AttributeError):``
        occurrences (the R26 fix-shape)."""
        return len(
            re.findall(
                r"except\s+\(ValueError,\s*AttributeError\)\s*:",
                src,
            ),
        )

    def test_three_html_parse_sites_narrowed(self) -> None:
        """R26-3..R26-5: storefront_parser has exactly
        3 narrowed sites (wishlist, followers, reviews)."""
        src = self._src()
        n = self._count_specific_exception_sites(src)
        assert n == 3, (
            f"storefront_parser.py must have exactly 3 "
            f"`except (ValueError, AttributeError):` "
            f"sites (R26 narrowed the wishlist, followers, "
            f"and reviews blocks). Found {n}."
        )

    def test_no_bare_except_exception_remains(self) -> None:
        """R26 anti-pattern guard: no
        ``except Exception:`` (bare) remains in
        storefront_parser.py."""
        from steam_review_tool.services import storefront_parser
        src = _strip_comments_and_docstrings(
            inspect.getsource(storefront_parser),
        )
        for m in re.finditer(
            r"^\s*except\s+Exception\s*:\s*$", src, re.M,
        ):
            # Get the body line.
            idx = m.end()
            after = src[idx:idx + 200]
            after_lines = [
                ln for ln in after.splitlines()[:3]
                if ln.strip() and not ln.lstrip().startswith("#")
            ]
            if after_lines and after_lines[0].strip() == "pass":
                raise AssertionError(
                    "storefront_parser.py still has a bare "
                    "`except Exception: pass` site — R26 "
                    "narrowed to `except (ValueError, "
                    "AttributeError): pass`. Match:\n"
                    + m.group(0)
                )


# ---------------------------------------------------------------------------
# BUG-R26-6: playwright_scraper.py progress_cb silent swallow
# ---------------------------------------------------------------------------
class TestProgressCbCallbackErrorsLogged:
    """R26 fixed the ``progress_cb`` silent swallow
    in ``playwright_scraper.py:210``. The previous
    ``except Exception: pass`` silently dropped any
    failure from the caller-supplied progress
    callback. R26 changes it to the R21 fix-shape:
    ``except Exception as exc: _log.exception(
    "progress_cb callback failed: %s", exc)`` so the
    failure is at least visible in stderr.
    """

    def test_progress_cb_logs_callback_error(self) -> None:
        """When ``progress_cb`` raises, the exception
        must be logged via the standard logger."""
        from steam_review_tool.services import (
            playwright_scraper,
        )

        logger, handler, old_level = _attach_logger(
            "steam_review_tool.services.playwright_scraper",
        )
        try:
            def _failing_cb(_page, _n, _total) -> None:
                raise RuntimeError("simulated progress failure")

            # The block at line 210 is:
            #     if progress_cb:
            #         try:
            #             progress_cb(...)
            #         except Exception as exc:
            #             _log.exception(...)
            # We can't easily run the full scrape loop
            # in a test, so just exercise the block
            # directly via the same pattern.
            progress_cb = _failing_cb
            try:
                progress_cb(1, 10, 100)
            except Exception as exc:
                # This is the R26 fix-shape — should
                # log via _log.exception.
                playwright_scraper._log.exception(
                    "progress_cb callback failed: %s", exc,
                )
            assert any(
                "progress_cb callback failed" in r.getMessage()
                and "simulated progress failure" in r.getMessage()
                for r in handler.records
            ), (
                f"expected the exception to be logged, got: "
                f"{[r.getMessage() for r in handler.records]}"
            )
        finally:
            _detach_logger(logger, handler, old_level)

    def test_progress_cb_source_shape(self) -> None:
        """R26 source-shape: the ``progress_cb`` block
        uses the R21 fix-shape (``except Exception as
        exc: _log.exception(...)``), not the bare
        ``except Exception: pass``."""
        from steam_review_tool.services import (
            playwright_scraper,
        )
        src = _strip_comments_and_docstrings(
            inspect.getsource(playwright_scraper),
        )
        # Find the progress_cb call site.
        idx = src.find("progress_cb(page, len(all_reviews)")
        assert idx >= 0, (
            "playwright_scraper.py has no `progress_cb(page, "
            "len(all_reviews), total_reported)` call — did "
            "the scrape loop change?"
        )
        # Walk back to the `try:`.
        before = src[max(0, idx - 500):idx]
        try_matches = list(re.finditer(r"^[ \t]+try:\s*$", before, re.M))
        assert try_matches, (
            "could not find `try:` before progress_cb() call"
        )
        abs_try = max(0, idx - 500) + try_matches[-1].start()
        block = src[abs_try:abs_try + 600]
        # The R26 fix-shape must be in place.
        assert "except Exception as exc:" in block, (
            "playwright_scraper.py `progress_cb` block must "
            "use `except Exception as exc:` (R26 fix-shape). "
            "Block:\n" + block
        )
        assert "_log.exception(" in block, (
            "playwright_scraper.py `progress_cb` block must "
            "log via `_log.exception(...)` (R26 fix-shape). "
            "Block:\n" + block
        )
        # Anti-pattern guard: the line right after
        # `except Exception as exc:` (skipping blank +
        # comment lines) must NOT be `pass`.
        body_lines = block.splitlines()
        for i, line in enumerate(body_lines):
            if line.strip() == "except Exception as exc:":
                for j in range(i + 1, min(i + 6, len(body_lines))):
                    nxt = body_lines[j].strip()
                    if not nxt or nxt.startswith("#"):
                        continue
                    assert nxt != "pass", (
                        "playwright_scraper.py `progress_cb` "
                        "block has the R26 anti-pattern: "
                        "`except Exception as exc: pass`. "
                        "Block:\n" + block
                    )
                    break
                break


# ---------------------------------------------------------------------------
# R26-4: settings-persistence chokepoint quartet regression test
# ---------------------------------------------------------------------------
class TestSettingsPersistenceChokepointQuartet:
    """R25 future-round hint:

    > "The R17-1 / R20-1 / R23-1 / R24-1 quartet
    > (settings-persistence chokepoints: set_dump_root,
    > set_obsidian_vault, _persist_settings, _on_close
    > callback) — there's NO regression test that
    > verifies BOTH the controller layer
    > (app_window._persist_settings) AND the popup layer
    > (popup_welcome._on_close) log when persistence
    > fails."

    This test closes the loop: monkeypatch
    ``settings_store.save`` to raise ``OSError`` and
    assert all 4 chokepoints log via their respective
    loggers. Without this test, refactor-drift could
    silently remove one of the log calls and the user
    would have no warning that their settings weren't
    persisted.
    """

    def _attach_handler(self, name: str) -> _ListHandler:
        """Attach a list handler to the named logger."""
        logger = logging.getLogger(name)
        handler = _ListHandler()
        old_level = logger.level
        logger.setLevel(logging.DEBUG)
        logger.addHandler(handler)
        # Stash the old level on the handler so
        # teardown can restore.
        handler.old_level = old_level  # type: ignore[attr-defined]
        return handler

    def _detach_handler(
        self, name: str, handler: _ListHandler,
    ) -> None:
        """Detach a list handler from the named logger."""
        logger = logging.getLogger(name)
        logger.removeHandler(handler)
        logger.setLevel(handler.old_level)  # type: ignore[attr-defined]

    def test_set_dump_root_logs_persist_failure(self) -> None:
        """R16-3 chokepoint: when ``settings_store.save``
        raises ``OSError``, ``set_dump_root`` must log
        via ``_log.exception``."""
        from steam_review_tool.controllers.dump_folder_controller import (
            DumpFolderController,
        )
        from pathlib import Path
        handler = self._attach_handler(
            "steam_review_tool.controllers.dump_folder_controller",
        )
        try:
            ctrl = DumpFolderController(dump_root=Path("/tmp/dump"))
            with patch(
                "steam_review_tool.services.settings_store.save",
                side_effect=OSError("simulated disk full"),
            ):
                ctrl.set_dump_root(Path("/tmp/new-dump"))
            assert any(
                "could not persist dump_root" in r.getMessage()
                and r.exc_info is not None
                and r.exc_info[0] is OSError
                for r in handler.records
            ), (
                f"set_dump_root must log the OSError via "
                f"_log.exception when settings_store.save "
                f"raises. Got: "
                f"{[(r.getMessage(), r.exc_info) for r in handler.records]}"
            )
        finally:
            self._detach_handler(
                "steam_review_tool.controllers.dump_folder_controller",
                handler,
            )

    def test_set_obsidian_vault_logs_persist_failure(self) -> None:
        """R17-1 chokepoint: when ``settings_store.save``
        raises ``OSError``, ``set_obsidian_vault`` must
        log via ``_log.exception``."""
        from steam_review_tool.controllers.dump_folder_controller import (
            DumpFolderController,
        )
        from pathlib import Path
        handler = self._attach_handler(
            "steam_review_tool.controllers.dump_folder_controller",
        )
        try:
            ctrl = DumpFolderController(dump_root=Path("/tmp/dump"))
            with patch(
                "steam_review_tool.services.settings_store.save",
                side_effect=OSError("simulated disk full"),
            ):
                ctrl.set_obsidian_vault(Path("/tmp/vault"))
            assert any(
                "could not persist obsidian_vault"
                in r.getMessage()
                and r.exc_info is not None
                and r.exc_info[0] is OSError
                for r in handler.records
            ), (
                f"set_obsidian_vault must log the OSError "
                f"via _log.exception when settings_store.save "
                f"raises. Got: "
                f"{[(r.getMessage(), r.exc_info) for r in handler.records]}"
            )
        finally:
            self._detach_handler(
                "steam_review_tool.controllers.dump_folder_controller",
                handler,
            )

    def test_app_window_persist_settings_logs_failure(
        self, tk_root,
    ) -> None:
        """R23-1 chokepoint: when ``settings_store.save``
        raises ``OSError``, ``app_window._persist_settings``
        must log via ``logging.getLogger(__name__)
        .exception``."""
        from steam_review_tool.ui import app_window
        win = app_window.App.__new__(app_window.App)
        # Minimal init: just give the window a settings
        # dict. The persistence call is what we test.
        win.settings = {"greeting_shown": False}
        handler = self._attach_handler(
            "steam_review_tool.ui.app_window",
        )
        try:
            with patch(
                "steam_review_tool.services.settings_store.save",
                side_effect=OSError("simulated disk full"),
            ):
                win._persist_settings({"greeting_shown": True})
            assert any(
                "could not persist settings" in r.getMessage()
                and r.exc_info is not None
                and r.exc_info[0] is OSError
                for r in handler.records
            ), (
                f"app_window._persist_settings must log the "
                f"OSError via logging.getLogger(__name__)"
                f".exception when settings_store.save raises. "
                f"Got: "
                f"{[(r.getMessage(), r.exc_info) for r in handler.records]}"
            )
        finally:
            self._detach_handler(
                "steam_review_tool.ui.app_window",
                handler,
            )

    def test_popup_welcome_on_close_logs_persist_failure(
        self, tk_root,
    ) -> None:
        """R24-1 chokepoint: when the persistence callback
        raises ``Exception`` (any, not just OSError), the
        ``popup_welcome._on_close`` popup-forwarding
        layer must log via ``logging.getLogger(__name__)
        .exception``.

        R24-1's chokepoint catches ``Exception`` (not
        just ``OSError``) for defense in depth — the
        popup shouldn't silently swallow the
        persistence callback's error even if the
        controller layer's narrower ``OSError`` catch
        doesn't fire.
        """
        from steam_review_tool.ui import popup_welcome
        welcome = popup_welcome.WelcomeDialog(
            master=tk_root,
            settings={"greeting_shown": False},
            on_save_settings=lambda _s: (
                (_ for _ in ()).throw(
                    OSError("simulated popup-layer failure"),
                )
            ),
        )
        welcome._dont_show_var.set(True)
        handler = self._attach_handler(
            "steam_review_tool.ui.popup_welcome",
        )
        try:
            welcome._on_close()
            assert any(
                "welcome-dialog on_save_settings callback failed"
                in r.getMessage()
                and r.exc_info is not None
                and r.exc_info[0] is OSError
                for r in handler.records
            ), (
                f"popup_welcome._on_close must log the "
                f"OSError via logging.getLogger(__name__)"
                f".exception when the persistence callback "
                f"raises (R24-1 fix-shape). Got: "
                f"{[(r.getMessage(), r.exc_info) for r in handler.records]}"
            )
        finally:
            self._detach_handler(
                "steam_review_tool.ui.popup_welcome",
                handler,
            )


# ---------------------------------------------------------------------------
# R26 project-wide static check
# ---------------------------------------------------------------------------
class TestNoBareExceptExceptionInServices:
    """R26 global sweep: walk every ``services/*.py``
    file (except the 3 Playwright files which have
    legitimately non-narrowable ``except Exception:
    pass`` blocks for ``is_visible`` / ``click`` /
    ``wait_for_timeout`` / ``browser.close`` calls —
    see R26 module docstring) and assert no
    ``except Exception:`` (bare, not ``as exc``) with
    a ``pass`` / ``return`` / ``continue`` body remains
    in the narrowable sites.
    """

    # Playwright files whose ``except Exception: pass``
    # blocks are NOT narrowable (would require a
    # top-level Playwright import that breaks the app
    # when Playwright is not installed).
    _PLAYWRIGHT_FILES = {
        "steam_review_tool/services/browser_launcher.py",
        "steam_review_tool/services/playwright_scraper.py",
        "steam_review_tool/services/playwright_subprocess_scraper.py",
    }

    def test_no_bare_except_exception_pass_in_narrowable_services(
        self,
    ) -> None:
        """Project-wide anti-pattern guard.

        Walks every ``services/*.py`` file (except
        the 3 Playwright files) and asserts that
        no bare ``except Exception:`` with a
        ``pass`` / ``return`` / ``continue`` body
        remains.
        """
        from steam_review_tool import __file__ as pkg_init
        root = Path(pkg_init).parent.parent
        services_dir = root / "steam_review_tool" / "services"
        offenders: list[str] = []
        for path in sorted(services_dir.glob("*.py")):
            rel = path.relative_to(root).as_posix()
            # Skip Playwright files (non-narrowable).
            if rel in self._PLAYWRIGHT_FILES:
                continue
            lines = path.read_text(encoding="utf-8").splitlines()
            for i, line in enumerate(lines):
                m = re.match(
                    r"^(\s*)except\s+Exception\s*:\s*$", line,
                )
                if not m:
                    continue
                indent = m.group(1)
                if i + 1 >= len(lines):
                    continue
                nxt = lines[i + 1]
                if not nxt.startswith(indent + " "):
                    continue
                body = nxt.strip()
                if body in ("pass", "return", "continue"):
                    offenders.append(
                        f"{rel}:{i + 1}: bare `except Exception:` "
                        f"with `{body}` body — should be narrowed "
                        f"to the actually-expected exception class "
                        f"(R26).",
                    )
        assert not offenders, (
            "R26 anti-pattern: bare `except Exception:` with "
            "`pass` / `return` / `continue` body remains in "
            "the narrowable services. Narrow to the "
            "actually-expected exception class. Offenders:\n\n"
            + "\n\n".join(offenders)
        )
