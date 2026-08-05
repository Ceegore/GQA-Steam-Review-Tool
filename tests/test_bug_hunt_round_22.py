"""Round-22 bug-hunt regression tests.

Real bugs found in a twenty-second systematic pass. Rounds
1-21 (9388ab1, 9ea69de, ed231bc, 80f9431, f913ae8,
e0514c0, 0e4f031, ba4255e, 49aa77a, 831219e, 04f47f6,
dfd6ff7, 6265d12, 561fc45, b795fbd, 95ea74e, 40d195a,
25c305a, 9e5b263, dc1d9d7, 22506de) found 95 bugs across
the project. Round 22 found 13 more — this round
extends the R21 logger-in-except audit to 5 more
files. The R21 fix-shape is preserved:

  ``except SomeException as exc: _log.warning("X: %s",
  exc)``  →  ``except SomeException as exc: _log.exception(
  "X: %s", exc)``

The R21 lesson was that ``_log.warning`` inside an
``except`` block captures the exception MESSAGE but NOT
the traceback. ``_log.exception`` calls ``sys.exc_info()``
and auto-attaches the traceback. R21 fixed 7 sites in
2 files (dump_folder_controller.py, storefront_parser.py).
R22 fixes 13 sites in 5 more files — all matching the
same anti-pattern R12-4 / R15-3 / R21 found first.

The R22 audit pattern (compounding R12 + R15 + R21):
after consolidating helpers, audit the SAME
anti-pattern at boundaries the previous rounds
already audited. R12-4 found the first
``_log.warning(..., exc)`` losing the traceback. R15-3
added more. R21 added 7 more in 2 new files. R22 adds
13 more in 5 more files. Each round tightens the audit
to a fresh code region.

R22-1  services/steam_api_service.py:88:
      ``get_app_details`` had
      ``except (requests.RequestException,
      ValueError) as exc: _log.warning(
      "get_app_details failed: %s", exc)`` — a
      Steam-API error with only the bare exception
      message hides the URL / params / network
      status the developer needs to debug.

R22-2  services/steam_api_service.py:220:
      ``fetch_all_reviews`` resume-cursor save
      branch had ``except OSError as exc:
      _log.warning("resume-cursor save failed:
      %s: %s", type(exc).__name__, exc)`` — the
      multi-line "type+exc" pattern. The
      ``type(exc).__name__`` was a defensive
      leftover from R12; with ``_log.exception``,
      the traceback's last frame already shows
      the type, so the type prefix is redundant
      and was dropped (R22 simplifies the format
      to a single ``%s, exc`` — same R21 fix-shape
      applied to a multi-line site).

R22-3  services/steam_api_service.py:263:
      ``poll_recent_reviews`` had
      ``except (requests.RequestException,
      ValueError) as exc: _log.warning(
      "poll_recent_reviews error: %s", exc)``
      — same anti-pattern at the watch-mode
      poll loop.

R22-4  services/settings_store.py:72:
      ``reset_defaults`` had
      ``except OSError as exc: _log.warning(
      "could not remove settings.json: %s",
      exc)`` — a settings-reset failure (file
      locked by another process, perms denied)
      was hidden behind a bare message.

R22-5  services/playwright_subprocess.py:107:
      ``_srt_pw_probe`` helper-script write
      branch had ``except OSError as exc:
      _log.warning("could not write helper
      script: %s", exc)`` — a tempdir full /
      read-only filesystem error was hidden.

R22-6  services/playwright_subprocess.py:125:
      ``_srt_pw_probe`` JSON-decode branch
      had ``except (json.JSONDecodeError,
      ValueError) as exc: _log.warning(
      "helper returned invalid JSON: %s",
      exc)`` — the helper script's stdout was
      not valid JSON, but the developer had no
      way to see WHICH line / char position
      caused the parse failure.

R22-7  services/playwright_subprocess.py:131:
      ``_srt_pw_probe`` subprocess-run branch
      had ``except (FileNotFoundError, OSError)
      as exc: _log.warning("Playwright probe
      failed: %s", exc)`` — the python
      interpreter was missing or un-runnable,
      but only the bare message was logged.

R22-8  exporters/markdown_helpers.py:170:
      ``highlight_keywords`` had the
      "type+exc" pattern (R12-4 first applied
      this format; R22 normalizes it to the
      R21 single-%s fix-shape).

R22-9  exporters/markdown_helpers.py:251:
      ``render_review``'s ``classify_review_type``
      call had the "type+exc" pattern.

R22-10 exporters/markdown_helpers.py:268:
      ``render_review``'s ``extract_tags`` call
      had the "type+exc" pattern.

R22-11 exporters/markdown_helpers.py:336:
      ``render_footer``'s Top-5-reviewers
      builder had the "type+exc" pattern.

R22-12 exporters/markdown_helpers.py:346:
      ``render_footer``'s ``quick_stats_footer``
      call had the "type+exc" pattern.

R22-13 exporters/per_language_exporter.py:91:
      ``write_per_language_files`` had the
      "type+exc" pattern (R18-3 first applied
      this format; R22 normalizes it to the
      R21 single-%s fix-shape for consistency
      with the rest of the codebase).

The R22-2 + R22-8 to R22-13 sites all use the
"type+exc" multi-line pattern introduced by
R12-4 (the R12 fix was to add the ``type(...)``
prefix as a defensive measure to make the
warning scannable; the R21 fix-shape drops it
because the traceback's last frame already
shows the type). The R22 message format is
``_log.exception("X: %s", exc)`` — one
``%s`` arg, not two.

Note: ``playwright_subprocess.py:128`` is
``except subprocess.TimeoutExpired:`` (NO
``as exc`` binding) — not the R21
anti-pattern, and the message has no
``exc`` to format with. Left as-is.

The cross-test-file impact for R22: the
``test_bug_hunt_round_12.py`` tests
assert that the "type+exc" prefix is
GONE from the log message — they only
check the prefix string, not the format.
The R22 simplification does not break
those tests.
"""
import inspect
import re
import textwrap
from pathlib import Path

# ---------------------------------------------------------------------------
# Helpers (re-used from R21; kept here so the test is self-contained
# even if the R21 file is reorganized)
# ---------------------------------------------------------------------------
def _strip_comments_and_docstrings(src: str) -> str:
    """Strip pure docstring + comment lines so a source-shape
    probe doesn't false-positive on explaining comments.
    """
    # Docstrings (triple-quoted, possibly multi-line).
    src = re.sub(r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'', "", src)
    out_lines: list[str] = []
    for line in src.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        out_lines.append(line)
    return "\n".join(out_lines)


def _find_except_blocks(src: str) -> list[tuple[str, str | None]]:
    """Return ``[(block_text, var_name), ...]`` for every
    ``except ... as var:`` block in ``src``.

    A block is bounded by the ``except`` line + the
    indented body. We use a simple indent-level heuristic:
    the body ends at the first non-blank line whose
    indent is <= the ``except`` line's indent.
    """
    out: list[tuple[str, str | None]] = []
    lines = src.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r"^(\s*)except\b(.*?):\s*$", line)
        if not m:
            i += 1
            continue
        indent = m.group(1)
        rest = m.group(2)
        # ``as <var>`` may be present.
        var_match = re.search(r"\bas\s+(\w+)\b", rest)
        var_name = var_match.group(1) if var_match else None
        # Collect the body: lines that are MORE indented
        # than ``indent``, plus blank lines / comment
        # lines between them.
        body: list[str] = [line]
        j = i + 1
        while j < len(lines):
            nxt = lines[j]
            if not nxt.strip():
                body.append(nxt)
                j += 1
                continue
            stripped_indent = len(nxt) - len(nxt.lstrip())
            if stripped_indent > len(indent):
                body.append(nxt)
                j += 1
            else:
                break
        out.append(("\n".join(body), var_name))
        i = j
    return out


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


# ---------------------------------------------------------------------------
# BUG-R22-1 to R22-3: steam_api_service.py logger-in-except sites
# ---------------------------------------------------------------------------
class TestSteamApiServiceUsesLogException:
    """``SteamAPI.get_app_details`` (R22-1),
    ``fetch_all_reviews`` resume-cursor save (R22-2),
    and ``poll_recent_reviews`` (R22-3) had
    ``_log.warning(..., exc)`` calls inside
    ``except ... as exc:`` blocks — silently
    dropping the traceback. R22-1 to R22-3 fixes
    convert all 3 to ``_log.exception(...)``.

    R22-2's site used the "type+exc" multi-line
    pattern (``type(exc).__name__, exc``). R22
    normalizes it to the R21 single-%s fix-shape
    (the traceback already shows the type, so
    the prefix is redundant).
    """

    def _src(self) -> str:
        from steam_review_tool.services import steam_api_service
        full_src = inspect.getsource(steam_api_service)
        return _strip_comments_and_docstrings(full_src)

    def test_get_app_details_uses_log_exception(self) -> None:
        """R22-1: ``get_app_details`` network branch
        (``except (requests.RequestException,
        ValueError) as exc:``) must use
        ``_log.exception`` so the traceback is
        captured."""
        src = self._src()
        assert (
            '_log.exception("get_app_details failed: %s", exc)'
        ) in src, (
            "get_app_details's network branch must "
            "use _log.exception (R22-1 fix) — the "
            "previous _log.warning('...: %s', exc) "
            "silently dropped the traceback."
        )
        assert (
            '_log.warning("get_app_details failed: %s", exc)'
        ) not in src, (
            "get_app_details's network branch still "
            "has the R22-1 anti-pattern "
            "'_log.warning(..., '...: %s', exc)'."
        )

    def test_resume_cursor_save_uses_log_exception(self) -> None:
        """R22-2: ``fetch_all_reviews`` resume-cursor
        save branch (``except OSError as exc:``) used
        the "type+exc" multi-line pattern. R22
        normalizes to ``_log.exception("X: %s", exc)``
        (single %s — type prefix dropped because
        the traceback already shows it)."""
        src = self._src()
        assert (
            '_log.exception(\n                        '
            '"resume-cursor save failed: %s",\n'
            '                        exc,\n'
            '                    )'
        ) in src, (
            "fetch_all_reviews's resume-cursor save "
            "branch must use _log.exception with the "
            "exc arg preserved (R22-2 fix)."
        )
        assert (
            'resume-cursor save failed: %s: %s'
        ) not in src, (
            "fetch_all_reviews's resume-cursor save "
            "branch still has the R22-2 anti-pattern "
            "'...: %s: %s' (the multi-line 'type+exc' "
            "format from R12)."
        )

    def test_poll_recent_reviews_uses_log_exception(self) -> None:
        """R22-3: ``poll_recent_reviews`` network
        branch (``except (requests.RequestException,
        ValueError) as exc:``) must use
        ``_log.exception``."""
        src = self._src()
        assert (
            '_log.exception("poll_recent_reviews error: %s", exc)'
        ) in src, (
            "poll_recent_reviews's network branch "
            "must use _log.exception (R22-3 fix)."
        )
        assert (
            '_log.warning("poll_recent_reviews error: %s", exc)'
        ) not in src, (
            "poll_recent_reviews's network branch "
            "still has the R22-3 anti-pattern."
        )

    def test_no_except_block_uses_log_warning_with_exc(self) -> None:
        """R22-1 to R22-3 static-check guard: walk
        every ``except ... as exc:`` block in
        ``steam_api_service.py`` and assert that
        none of them use the ``_log.warning("...:
        %s", exc)`` anti-pattern."""
        src = self._src()
        for block_text, var_name in _find_except_blocks(src):
            if var_name is None:
                continue
            warn_call = re.search(
                rf'_log\.warning\([^)]*%s[^)]*,\s*{var_name}\s*\)',
                block_text,
            )
            assert not warn_call, (
                f"steam_api_service.py has an "
                f"except-block using '_log.warning(...)' "
                f"with the bound variable {var_name!r} as "
                f"the last arg — the traceback is silently "
                f"dropped. Use '_log.exception(...)' instead. "
                f"Block:\n{block_text}"
            )


# ---------------------------------------------------------------------------
# BUG-R22-4: settings_store.py logger-in-except site
# ---------------------------------------------------------------------------
class TestSettingsStoreUsesLogException:
    """``settings_store.reset_defaults`` had
    ``except OSError as exc: _log.warning(
    "could not remove settings.json: %s", exc)``
    — a settings-reset failure (file locked by
    another process, perms denied) was hidden
    behind a bare message. R22-4 fix converts to
    ``_log.exception(...)``.

    This is the same R12-4 / R15-3 / R21 lesson
    applied to a fresh code region: the
    ``reset_defaults`` chokepoint that the
    settings dialog calls when the user clicks
    "Reset to defaults".
    """

    def _src(self) -> str:
        from steam_review_tool.services import settings_store
        full_src = inspect.getsource(settings_store)
        return _strip_comments_and_docstrings(full_src)

    def test_reset_defaults_uses_log_exception(self) -> None:
        """R22-4: ``reset_defaults`` must use
        ``_log.exception`` so the traceback is
        captured on settings.json unlink failure."""
        src = self._src()
        assert (
            '_log.exception("could not remove settings.json: %s", exc)'
        ) in src, (
            "settings_store.reset_defaults must use "
            "_log.exception (R22-4 fix) — the previous "
            "_log.warning('...: %s', exc) silently "
            "dropped the traceback."
        )
        assert (
            '_log.warning("could not remove settings.json: %s", exc)'
        ) not in src, (
            "settings_store.reset_defaults still has "
            "the R22-4 anti-pattern."
        )

    def test_reset_defaults_captures_traceback(self) -> None:
        """R22-4 functional test: trigger an
        OSError on ``SETTINGS_FILE.unlink()`` and
        assert the log record has a non-empty
        traceback (the new ``_log.exception``
        behaviour).
        """
        import logging
        from unittest.mock import MagicMock, patch
        from steam_review_tool.services import settings_store

        records: list[logging.LogRecord] = []

        class _Capture(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                records.append(record)

        cap = _Capture(level=logging.DEBUG)
        logger = logging.getLogger(settings_store.__name__)
        logger.addHandler(cap)
        old_propagate = logger.propagate
        logger.propagate = False
        try:
            # Replace SETTINGS_FILE with a mock that
            # has an ``unlink`` method raising
            # OSError — ``Path.unlink`` is read-only
            # on WindowsPath, so we cannot patch
            # ``settings_store.SETTINGS_FILE.unlink``
            # in place.
            mock_file = MagicMock()
            mock_file.unlink.side_effect = OSError("disk full")
            with patch.object(
                settings_store, "SETTINGS_FILE", mock_file,
            ):
                # Must NOT raise — ``reset_defaults``
                # returns ``dict(DEFAULTS)`` even on
                # unlink failure.
                result = settings_store.reset_defaults()
            assert result == dict(settings_store.DEFAULTS)
            # At least one record with our message
            # + a traceback (the R22-4 fix-shape).
            matching = [
                r for r in records
                if "could not remove settings.json" in r.getMessage()
            ]
            assert matching, (
                "settings_store.reset_defaults did not log "
                "anything matching 'could not remove "
                "settings.json' on unlink failure."
            )
            # The R22-4 fix uses ``_log.exception``,
            # which sets ``exc_info`` to a 3-tuple
            # ``(type, value, tb)``. The previous
            # ``_log.warning(..., exc)`` form set
            # ``exc_info`` to None.
            assert matching[0].exc_info is not None, (
                "settings_store.reset_defaults's log "
                "record has no exc_info — the R22-4 "
                "fix should use _log.exception, which "
                "sets exc_info automatically."
            )
        finally:
            logger.removeHandler(cap)
            logger.propagate = old_propagate

    def test_no_except_block_uses_log_warning_with_exc(self) -> None:
        """R22-4 static-check guard: walk every
        ``except ... as exc:`` block in
        ``settings_store.py`` and assert that
        none of them use the ``_log.warning("...:
        %s", exc)`` anti-pattern."""
        src = self._src()
        for block_text, var_name in _find_except_blocks(src):
            if var_name is None:
                continue
            warn_call = re.search(
                rf'_log\.warning\([^)]*%s[^)]*,\s*{var_name}\s*\)',
                block_text,
            )
            assert not warn_call, (
                f"settings_store.py has an except-block "
                f"using '_log.warning(...)' with the "
                f"bound variable {var_name!r} as the "
                f"last arg — the traceback is silently "
                f"dropped. Use '_log.exception(...)' "
                f"instead. Block:\n{block_text}"
            )


# ---------------------------------------------------------------------------
# BUG-R22-5 to R22-7: playwright_subprocess.py logger-in-except sites
# ---------------------------------------------------------------------------
class TestPlaywrightSubprocessUsesLogException:
    """``playwright_subprocess._srt_pw_probe``
    helper-script write (R22-5), JSON-decode
    (R22-6), and subprocess-run (R22-7) branches
    had ``_log.warning(..., exc)`` calls inside
    ``except ... as exc:`` blocks — silently
    dropping the traceback. R22-5 to R22-7
    fixes convert all 3 to ``_log.exception(...)``.

    The line 128 ``except subprocess.TimeoutExpired:``
    (NO ``as exc`` binding) is NOT the
    anti-pattern — it has no ``exc`` to format
    with. Left as-is.
    """

    def _src(self) -> str:
        from steam_review_tool.services import playwright_subprocess
        full_src = inspect.getsource(playwright_subprocess)
        return _strip_comments_and_docstrings(full_src)

    def test_helper_write_uses_log_exception(self) -> None:
        """R22-5: ``_srt_pw_probe`` helper-script
        write branch (``except OSError as exc:``)
        must use ``_log.exception``."""
        src = self._src()
        assert (
            '_log.exception("could not write helper script: %s", exc)'
        ) in src, (
            "playwright_subprocess._srt_pw_probe's "
            "helper-script write branch must use "
            "_log.exception (R22-5 fix)."
        )
        assert (
            '_log.warning("could not write helper script: %s", exc)'
        ) not in src, (
            "playwright_subprocess._srt_pw_probe's "
            "helper-script write branch still has "
            "the R22-5 anti-pattern."
        )

    def test_helper_invalid_json_uses_log_exception(self) -> None:
        """R22-6: ``_srt_pw_probe`` JSON-decode
        branch (``except (json.JSONDecodeError,
        ValueError) as exc:``) must use
        ``_log.exception``."""
        src = self._src()
        assert (
            '_log.exception("helper returned invalid JSON: %s", exc)'
        ) in src, (
            "playwright_subprocess._srt_pw_probe's "
            "JSON-decode branch must use _log.exception "
            "(R22-6 fix)."
        )
        assert (
            '_log.warning("helper returned invalid JSON: %s", exc)'
        ) not in src, (
            "playwright_subprocess._srt_pw_probe's "
            "JSON-decode branch still has the R22-6 "
            "anti-pattern."
        )

    def test_helper_subprocess_failed_uses_log_exception(self) -> None:
        """R22-7: ``_srt_pw_probe`` subprocess-run
        branch (``except (FileNotFoundError, OSError)
        as exc:``) must use ``_log.exception``."""
        src = self._src()
        assert (
            '_log.exception("Playwright probe failed: %s", exc)'
        ) in src, (
            "playwright_subprocess._srt_pw_probe's "
            "subprocess-run branch must use "
            "_log.exception (R22-7 fix)."
        )
        assert (
            '_log.warning("Playwright probe failed: %s", exc)'
        ) not in src, (
            "playwright_subprocess._srt_pw_probe's "
            "subprocess-run branch still has the R22-7 "
            "anti-pattern."
        )

    def test_no_except_block_uses_log_warning_with_exc(self) -> None:
        """R22-5 to R22-7 static-check guard: walk
        every ``except ... as exc:`` block in
        ``playwright_subprocess.py`` and assert
        that none of them use the
        ``_log.warning("...: %s", exc)`` anti-pattern.

        The bare ``except subprocess.TimeoutExpired:``
        at line 128 is NOT covered (no ``as exc``
        binding — the pattern can't apply)."""
        src = self._src()
        for block_text, var_name in _find_except_blocks(src):
            if var_name is None:
                # No ``as exc`` binding — the
                # ``_log.warning("...: %s", exc)``
                # pattern can't apply (no ``exc``
                # in scope). Skip.
                continue
            warn_call = re.search(
                rf'_log\.warning\([^)]*%s[^)]*,\s*{var_name}\s*\)',
                block_text,
            )
            assert not warn_call, (
                f"playwright_subprocess.py has an "
                f"except-block using '_log.warning(...)' "
                f"with the bound variable {var_name!r} as "
                f"the last arg — the traceback is silently "
                f"dropped. Use '_log.exception(...)' "
                f"instead. Block:\n{block_text}"
            )


# ---------------------------------------------------------------------------
# BUG-R22-8 to R22-12: markdown_helpers.py logger-in-except sites
# ---------------------------------------------------------------------------
class TestMarkdownHelpersUsesLogException:
    """``markdown_helpers.highlight_keywords`` (R22-8),
    ``render_review``'s ``classify_review_type`` call
    (R22-9), ``render_review``'s ``extract_tags`` call
    (R22-10), ``render_footer``'s Top-5-reviewers
    builder (R22-11), and ``render_footer``'s
    ``quick_stats_footer`` call (R22-12) all used the
    "type+exc" multi-line pattern introduced by
    R12-4. R22 normalizes all 5 to the R21 single-%s
    fix-shape (``_log.exception("X: %s", exc)`` —
    one ``%s`` arg, not two). The ``type(exc).__name__``
    prefix is dropped because the traceback's last
    frame already shows the type.
    """

    def _src(self) -> str:
        from steam_review_tool.exporters import markdown_helpers
        full_src = inspect.getsource(markdown_helpers)
        return _strip_comments_and_docstrings(full_src)

    def test_highlight_keywords_uses_log_exception(self) -> None:
        """R22-8: ``highlight_keywords`` had the
        "type+exc" pattern. R22 normalizes to
        ``_log.exception("X: %s", exc)``."""
        src = self._src()
        assert (
            '_log.exception(\n            '
            '"keyword highlight skipped (text len='
            '%d, kws=%d): %s",\n'
            '            len(text), len(cleaned_kw), exc,\n'
            '        )'
        ) in src, (
            "markdown_helpers.highlight_keywords "
            "must use _log.exception with the "
            "single-%s format (R22-8 fix)."
        )
        # Anti-pattern: the old "type+exc" two-arg
        # form (``type(exc).__name__, exc``) is
        # gone.
        assert (
            'type(exc).__name__, exc,\n'
        ) not in src, (
            "markdown_helpers.highlight_keywords "
            "still has the R12 'type+exc' "
            "two-arg format — R22 normalizes to "
            "_log.exception with a single %s."
        )

    def test_classify_review_type_uses_log_exception(self) -> None:
        """R22-9: ``render_review``'s
        ``classify_review_type`` call had the
        "type+exc" pattern."""
        src = self._src()
        assert (
            '_log.exception(\n            '
            '"classify_review_type failed for '
            'review #%d: %s",\n'
            '            idx, exc,\n'
            '        )'
        ) in src, (
            "markdown_helpers.render_review's "
            "classify_review_type call must use "
            "_log.exception with the single-%s "
            "format (R22-9 fix)."
        )

    def test_extract_tags_uses_log_exception(self) -> None:
        """R22-10: ``render_review``'s
        ``extract_tags`` call had the
        "type+exc" pattern."""
        src = self._src()
        assert (
            '_log.exception(\n            '
            '"extract_tags failed for review #%d: '
            '%s",\n'
            '            idx, exc,\n'
            '        )'
        ) in src, (
            "markdown_helpers.render_review's "
            "extract_tags call must use "
            "_log.exception with the single-%s "
            "format (R22-10 fix)."
        )

    def test_top5_reviewers_uses_log_exception(self) -> None:
        """R22-11: ``render_footer``'s Top-5
        reviewers builder had the
        "type+exc" pattern."""
        src = self._src()
        assert (
            '_log.exception(\n            '
            '"Top-5-reviewers footer skipped '
            '(reviews=%d): %s",\n'
            '            len(reviews), exc,\n'
            '        )'
        ) in src, (
            "markdown_helpers.render_footer's "
            "Top-5-reviewers builder must use "
            "_log.exception with the single-%s "
            "format (R22-11 fix)."
        )

    def test_quick_stats_footer_uses_log_exception(self) -> None:
        """R22-12: ``render_footer``'s
        ``quick_stats_footer`` call had the
        "type+exc" pattern."""
        src = self._src()
        assert (
            '_log.exception(\n            '
            '"quick_stats_footer skipped (reviews='
            '%d): %s",\n'
            '            len(reviews), exc,\n'
            '        )'
        ) in src, (
            "markdown_helpers.render_footer's "
            "quick_stats_footer call must use "
            "_log.exception with the single-%s "
            "format (R22-12 fix)."
        )

    def test_no_except_block_uses_log_warning_with_exc(self) -> None:
        """R22-8 to R22-12 static-check guard: walk
        every ``except ... as exc:`` block in
        ``markdown_helpers.py`` and assert that
        none of them use the
        ``_log.warning("...: %s", exc)`` anti-pattern."""
        src = self._src()
        for block_text, var_name in _find_except_blocks(src):
            if var_name is None:
                continue
            warn_call = re.search(
                rf'_log\.warning\([^)]*%s[^)]*,\s*{var_name}\s*\)',
                block_text,
            )
            assert not warn_call, (
                f"markdown_helpers.py has an "
                f"except-block using '_log.warning(...)' "
                f"with the bound variable {var_name!r} "
                f"as the last arg — the traceback is "
                f"silently dropped. Use "
                f"'_log.exception(...)' instead. "
                f"Block:\n{block_text}"
            )

    def test_no_type_exc_format_remains(self) -> None:
        """R22-8 to R22-12 anti-pattern guard:
        no ``type(exc).__name__`` (the
        "type+exc" multi-line format
        introduced by R12-4) should remain in
        any ``_log`` call inside
        ``markdown_helpers.py``. The R22 fix
        normalizes all 5 sites to the R21
        single-%s fix-shape.
        """
        src = self._src()
        # Look for ``_log.warning(`` or
        # ``_log.exception(`` followed (within
        # the call) by ``type(exc).__name__``.
        bad_call = re.search(
            r'_log\.(?:warning|exception)\('
            r'[\s\S]*?type\(exc\)\.__name__',
            src,
        )
        assert not bad_call, (
            "markdown_helpers.py still has a "
            "_log.warning/_log.exception call "
            "using the R12 'type+exc' "
            "two-arg format (type(exc).__name__, "
            "exc). R22 normalizes to a single %s. "
            f"Match: {bad_call.group(0)!r}"
        )


# ---------------------------------------------------------------------------
# BUG-R22-13: per_language_exporter.py logger-in-except site
# ---------------------------------------------------------------------------
class TestPerLanguageExporterUsesLogException:
    """``per_language_exporter.write_per_language_files``
    had the "type+exc" multi-line pattern
    (R18-3 first applied this format; R22
    normalizes it to the R21 single-%s
    fix-shape for consistency with the rest
    of the codebase)."""

    def _src(self) -> str:
        from steam_review_tool.exporters import per_language_exporter
        full_src = inspect.getsource(per_language_exporter)
        return _strip_comments_and_docstrings(full_src)

    def test_per_language_write_uses_log_exception(self) -> None:
        """R22-13: ``write_per_language_files``
        had the "type+exc" pattern. R22
        normalizes to ``_log.exception("X: %s",
        exc)``."""
        src = self._src()
        assert (
            '_log.exception(\n                '
            '"per-language file write failed for '
            '%s: %s",\n'
            '                per_path, exc,\n'
            '            )'
        ) in src, (
            "per_language_exporter.write_per_language_files "
            "must use _log.exception with the "
            "single-%s format (R22-13 fix — was "
            "inconsistent with the R21 fix-shape "
            "applied to the rest of the codebase)."
        )
        # Anti-pattern: the R18 "type+exc" format
        # is gone.
        assert (
            'per-language file write failed for '
            '%s: %s: %s'
        ) not in src, (
            "per_language_exporter.write_per_language_files "
            "still has the R18-3 anti-pattern "
            "'per-language file write failed for %s: %s: %s' "
            "(the multi-line 'type+exc' format)."
        )

    def test_no_except_block_uses_log_warning_with_exc(self) -> None:
        """R22-13 static-check guard: walk every
        ``except ... as exc:`` block in
        ``per_language_exporter.py`` and assert
        that none of them use the
        ``_log.warning("...: %s", exc)``
        anti-pattern."""
        src = self._src()
        for block_text, var_name in _find_except_blocks(src):
            if var_name is None:
                continue
            warn_call = re.search(
                rf'_log\.warning\([^)]*%s[^)]*,\s*{var_name}\s*\)',
                block_text,
            )
            assert not warn_call, (
                f"per_language_exporter.py has an "
                f"except-block using '_log.warning(...)' "
                f"with the bound variable {var_name!r} "
                f"as the last arg — the traceback is "
                f"silently dropped. Use "
                f"'_log.exception(...)' instead. "
                f"Block:\n{block_text}"
            )


# ---------------------------------------------------------------------------
# BUG-R22-1 to R22-13: project-wide sweep
# ---------------------------------------------------------------------------
class TestNoRemainingLogWarningWithExcInProject:
    """R22 global sweep: walk every ``.py`` file
    under ``steam_review_tool/`` and assert that
    no ``except ... as exc:`` block uses the
    ``_log.warning("...: %s", exc)`` anti-pattern.

    This is the strongest regression test for the
    R12-4 / R15-3 / R21 / R22 logger-in-except
    lesson. It catches future regressions at
    boundaries the R12 + R15 + R21 + R22 rounds
    already audited (the 5 files fixed in R22
    + the 2 files fixed in R21 + any future
    code that re-introduces the pattern).
    """

    def test_no_log_warning_with_exc_in_entire_project(self) -> None:
        """Project-wide anti-pattern guard.

        Walks every ``except ... as exc:`` block
        in the project and asserts the body does
        not use ``_log.warning("...: %s", exc)``.
        """
        from steam_review_tool import __file__ as pkg_init
        root = Path(pkg_init).parent
        offenders: list[str] = []
        for path in _walk_project_sources(root):
            src = _strip_comments_and_docstrings(
                path.read_text(encoding="utf-8"),
            )
            for block_text, var_name in _find_except_blocks(src):
                if var_name is None:
                    continue
                warn_call = re.search(
                    rf'_log\.warning\([^)]*%s[^)]*,\s*{var_name}\s*\)',
                    block_text,
                )
                if warn_call:
                    rel = path.relative_to(root.parent)
                    offenders.append(
                        f"{rel}: except-block uses "
                        f"'_log.warning(..., {var_name})' — "
                        f"the traceback is silently dropped. "
                        f"Use '_log.exception(...)' instead.\n"
                        f"Block:\n{block_text}"
                    )
        assert not offenders, (
            "Project has the R22 anti-pattern "
            "'_log.warning(\"...: %s\", exc)' inside "
            "except-blocks. The traceback is silently "
            "dropped. Use '_log.exception(...)' instead. "
            "Offenders:\n\n" + "\n\n---\n\n".join(offenders)
        )
