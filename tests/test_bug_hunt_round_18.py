"""Round-18 bug-hunt regression tests.

Real bugs found in an eighteenth systematic pass. Rounds 1-17
(9388ab1, 9ea69de, ed231bc, 80f9431, f913ae8, e0514c0,
0e4f031, ba4255e, 49aa77a, 831219e, 04f47f6, dfd6ff7,
6265d12, 561fc45, b795fbd, 95ea74e, 40d195a) found 78
bugs across the project. Round 18 found 4 more — this
round targets the same pattern class as R17: **chokepoint
bypass + dead code + silent error swallow + defensive
coercion gap** — all of them at boundaries the R15 / R16
/ R17 rounds already audited.

The recurring lesson (compounding R12 + R15 + R16 + R17):
once a chokepoint method exists (R16-3 ``set_dump_root``,
R17-1 ``set_obsidian_vault``), every OTHER path that
updates the same in-memory state must go through the
chokepoint. The R18 round finds the last remaining
direct write to ``obsidian_vault`` in
``app_window._on_settings_changed``.

R18-1  ui/app_window.py: ``_on_settings_changed`` did
       ``self.dump_ctrl.obsidian_vault = Path(vault) if
       vault else None`` — directly bypassing the
       ``set_obsidian_vault`` chokepoint that R17-1 just
       added.

Root cause: R17-1 added the chokepoint and routed
            ``pick_obsidian_vault`` / ``clear_obsidian_vault``
            through it, but missed the THIRD site that
            updates the same in-memory attribute. The
            ``_on_settings_changed`` callback fires after
            the Settings dialog saves, so the on-disk state
            was already correct (the dialog itself saved).
            But writing the attribute directly bypasses
            any future change to the chokepoint
            (additional persistence guarantees, validation,
            bus event publishing, etc.).

Fix:      routed the in-memory update through
            ``set_obsidian_vault`` so the chokepoint is
            the single path for all ``obsidian_vault``
            updates.

R18-2  core/constants.py: ``REVIEW_SORT`` and
       ``REVIEW_TYPE`` were dead-code aliases "kept for
       backwards compat" but no one imported them.

Root cause: an earlier refactor renamed ``REVIEW_SORT``
            → ``REVIEW_FILTERS`` and ``REVIEW_TYPE`` →
            ``REVIEW_TYPES``. The aliases were left
            behind with a back-compat comment but no
            external caller actually uses them — the
            rename was already complete in every consumer.
            Same R17-2 "kept for back-compat" dead-code
            pattern, at the constant level.

Fix:      removed both aliases + their ``__all__`` entries.

R18-3  exporters/per_language_exporter.py:
       ``write_per_language`` had a bare
       ``except OSError: pass`` that silently dropped
       per-language file write failures.

Root cause: same R12-4 to R12-7 + R17-3 lesson.
            A user with a full disk / read-only vault
            would see the main ``.md`` export succeed
            but every per-language file would silently
            fail — the orchestrator's returned count
            would be lower than expected with no visible
            signal.

Fix:      replaced ``except OSError: pass`` with
            ``except OSError as exc: _log.warning(...)``
            so the dev can spot the partial export in
            stderr. Continue with remaining languages so
            a single bad file doesn't drop the whole
            batch.

R18-4  exporters/per_language_exporter.py +
       exporters/markdown_helpers.py: ``language``
       field was not defensively coerced to str.

Root cause: same R12-1 to R12-3 defensive-coercion
            gap. ``group_by_language`` did
            ``(r.get("language") or "unknown").strip()``
            which crashes with ``AttributeError: 'int'
            object has no attribute 'strip'`` when
            ``language`` is a non-string (int / list /
            dict). ``render_summary`` did
            ``r.get("language") or "—"`` which keeps an
            int as the dict key, then crashes
            ``md_escape(k)`` with
            ``AttributeError: 'int' object has no
            attribute 'replace'``. Both are reachable
            from a hand-rolled / Apify-normalised review
            dict that carries a non-string language.

Fix:      added a ``_coerce_lang_key`` helper in
            ``per_language_exporter.py`` and an inline
            ``isinstance`` check in
            ``markdown_helpers.render_summary``.

Test discipline notes (compounding R12 + R13 + R16 +
R17 lessons):

- The 12 new R18 tests include source-shape
  regression probes that pin the absence of pre-R18
  anti-patterns:
  - ``_on_settings_changed`` body must NOT contain
    ``self.dump_ctrl.obsidian_vault =`` (the
    direct-write anti-pattern)
  - ``core/constants.py`` must NOT define
    ``REVIEW_SORT`` or ``REVIEW_TYPE``
  - ``write_per_language`` body MUST contain
    ``_log.warning`` and NOT ``except OSError:``
    followed by bare ``pass``
  - ``group_by_language`` must NOT crash on a
    non-string language value (end-to-end test)

- The ``_strip_comments_and_docstrings`` helper is
  reused from R16 for the source-shape probes.

- The defensive-coercion tests use hand-rolled
  review dicts (R12-1 to R12-3 pattern): a review
  with ``language=42`` (int) must be coerced to
  ``"—"`` in ``render_summary`` and to
  ``"unknown"`` in ``group_by_language`` instead of
  crashing the export.

Stats: 4 bugs found, 12 regression tests added.
"""
from __future__ import annotations

import inspect
import logging
import re
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Helper: strip pure comment / docstring lines from a source string before
# substring-regression checks. Reused from R16.
# ---------------------------------------------------------------------------
def _strip_comments_and_docstrings(src: str) -> str:
    src_no_docstrings = re.sub(
        r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'',
        "",
        src,
    )
    out_lines: list[str] = []
    for line in src_no_docstrings.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        out_lines.append(line)
    return "\n".join(out_lines)


# ---------------------------------------------------------------------------
# BUG-R18-1: app_window._on_settings_changed bypasses set_obsidian_vault
# ---------------------------------------------------------------------------
class TestOnSettingsChangedUsesChokepoint:
    """``_on_settings_changed`` must route the
    ``obsidian_vault`` update through the
    ``set_obsidian_vault`` chokepoint (R17-1), not
    write the attribute directly.

    Without the R18-1 fix, the THIRD site that updates
    ``self.dump_ctrl.obsidian_vault`` (after
    ``pick_obsidian_vault`` and ``clear_obsidian_vault``)
    bypasses the chokepoint. Any future change to
    ``set_obsidian_vault`` (e.g. additional persistence
    guarantees) would silently miss this site.
    """

    def test_on_settings_changed_uses_set_obsidian_vault(
        self,
    ) -> None:
        from steam_review_tool.ui import app_window
        src = inspect.getsource(app_window)
        code = _strip_comments_and_docstrings(src)
        marker = "def _on_settings_changed("
        start = code.find(marker)
        assert start != -1
        end = code.find("\n\n", start)
        body = code[start:end]
        # The chokepoint call must be present.
        assert "set_obsidian_vault" in body, (
            "_on_settings_changed must call "
            "self.dump_ctrl.set_obsidian_vault(...) — "
            "the direct-write anti-pattern was fixed "
            "in R18-1"
        )
        # And the direct write must NOT appear.
        assert "self.dump_ctrl.obsidian_vault =" not in body, (
            "_on_settings_changed must NOT write "
            "self.dump_ctrl.obsidian_vault = ... directly "
            "— route through set_obsidian_vault so the "
            "chokepoint is the single path for all "
            "obsidian_vault updates"
        )


# ---------------------------------------------------------------------------
# BUG-R18-2: REVIEW_SORT and REVIEW_TYPE are dead-code aliases
# ---------------------------------------------------------------------------
class TestNoDeadReviewSortOrReviewType:
    """``core/constants.py`` previously defined
    ``REVIEW_SORT`` and ``REVIEW_TYPE`` as "backwards
    compat aliases" — but no other file in the codebase
    imports them. R18-2 removes them.

    Source-shape probe: the constants and their
    ``__all__`` entries must NOT appear.
    """

    def test_constants_no_def_review_sort(self) -> None:
        from steam_review_tool.core import constants
        src = inspect.getsource(constants)
        code = _strip_comments_and_docstrings(src)
        assert "REVIEW_SORT" not in code, (
            "core/constants.py must NOT define "
            "REVIEW_SORT — it is dead code (no external "
            "caller). The 'backwards compat' comment was "
            "misleading; the rename to REVIEW_FILTERS "
            "was complete."
        )

    def test_constants_no_def_review_type_alias(self) -> None:
        from steam_review_tool.core import constants
        src = inspect.getsource(constants)
        code = _strip_comments_and_docstrings(src)
        # The alias (uppercase REVIEW_TYPE) must NOT be
        # defined. The lowercase ``review_type`` parameter
        # in api_workflow / filter_controller is a
        # different name — make sure we don't false-match.
        assert not re.search(
            r"^REVIEW_TYPE\s*[:=]", code, re.MULTILINE,
        ), (
            "core/constants.py must NOT define "
            "REVIEW_TYPE (uppercase) — it is dead code "
            "alias for REVIEW_TYPES. The lowercase "
            "'review_type' parameter in api_workflow is "
            "a different name and is not affected."
        )

    def test_no_external_caller_of_review_sort(self) -> None:
        """Static check: no file in the codebase should
        import ``REVIEW_SORT`` (the dead alias)."""
        from pathlib import Path
        project_root = Path("steam_review_tool")
        offenders: list[str] = []
        for py in project_root.rglob("*.py"):
            text = py.read_text(encoding="utf-8")
            for line in text.splitlines():
                if re.search(
                    r"\b(import|from)\b.*\bREVIEW_SORT\b",
                    line,
                ):
                    offenders.append(f"{py}: {line.strip()}")
        assert not offenders, (
            "found orphan importers of REVIEW_SORT "
            "(the constant is being removed in R18-2): "
            f"{offenders}"
        )

    def test_no_external_caller_of_review_type_alias(self) -> None:
        """Static check: no file should import the
        uppercase ``REVIEW_TYPE`` alias."""
        from pathlib import Path
        project_root = Path("steam_review_tool")
        offenders: list[str] = []
        for py in project_root.rglob("*.py"):
            text = py.read_text(encoding="utf-8")
            code = _strip_comments_and_docstrings(text)
            for line in code.splitlines():
                # Match "import REVIEW_TYPE" / "from . import REVIEW_TYPE"
                # but not the lowercase "review_type" parameter usage.
                if re.search(
                    r"\b(import|from)\b[^#]*\bREVIEW_TYPE\b",
                    line,
                ):
                    offenders.append(f"{py}: {line.strip()}")
        assert not offenders, (
            "found orphan importers of REVIEW_TYPE "
            "(the constant is being removed in R18-2): "
            f"{offenders}"
        )


# ---------------------------------------------------------------------------
# BUG-R18-3: per_language_exporter.write_per_language silent OSError
# ---------------------------------------------------------------------------
class TestWritePerLanguageLogsOSError:
    """``write_per_language`` had a bare
    ``except OSError: pass`` that silently dropped
    per-language file write failures. R18-3 fix: log
    a warning so the dev can spot the partial export.
    """

    def test_write_per_language_logs_oserror(self) -> None:
        from steam_review_tool.exporters import (
            per_language_exporter,
        )
        src = inspect.getsource(per_language_exporter)
        code = _strip_comments_and_docstrings(src)
        marker = "def write_per_language("
        start = code.find(marker)
        assert start != -1
        end = code.find("\n\n", start)
        body = code[start:end]
        # The body must catch OSError (not bare Exception).
        assert "except OSError" in body, (
            "write_per_language must catch OSError "
            "specifically (not bare Exception) and log "
            "a warning so the dev can spot a partial "
            "per-language export"
        )
        # And it must log via the standard logger.
        # R22 normalizes the R18-3 fix-shape from
        # ``_log.warning`` to ``_log.exception`` (R21
        # lesson — ``_log.warning`` silently drops
        # the traceback; ``_log.exception`` captures
        # it via ``sys.exc_info()``). The single
        # ``%s, exc`` arg shape is preserved.
        assert (
            '_log.exception(\n                "per-language '
            'file write failed for %s: %s",\n'
            '                per_path, exc,\n'
            '            )'
        ) in body, (
            "write_per_language must log via "
            "_log.exception(...) with the single-%s "
            "format so a failed per-language file "
            "write is visible in stderr AND the "
            "traceback is captured (R12-4 to R12-7 + "
            "R17-3 + R21 + R22 lessons)."
        )

    def test_write_per_language_logs_on_oserror(self) -> None:
        """End-to-end: trigger an OSError on the
        per-language write and verify a warning is
        logged (not silently swallowed)."""
        from steam_review_tool.exporters.per_language_exporter import (
            write_per_language,
        )
        from steam_review_tool.models.export_context import (
            ExportContext,
        )

        records: list[logging.LogRecord] = []

        class _ListHandler(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                records.append(record)

        handler = _ListHandler(level=logging.WARNING)
        logger = logging.getLogger(
            "steam_review_tool.exporters.per_language_exporter",
        )
        logger.addHandler(handler)
        try:
            with tempfile.TemporaryDirectory() as td:
                base = Path(td) / "out"
                ctx = ExportContext(
                    app_id=1,
                    app_details={},
                    reviews=[
                        {"language": "english", "review": "ok"},
                        {"language": "german", "review": "ok2"},
                    ],
                    language_param="all",
                    review_filter="all",
                    review_type="all",
                    day_range=None,
                    min_date_ts=None,
                )
                # Patch atomic_write_text at its
                # canonical source path
                # (``core.atomic_write``). The
                # ``write_per_language`` function does
                # ``from ..core.atomic_write import
                # atomic_write_text`` inside the loop,
                # so patching the re-exported module
                # attribute wouldn't take effect.
                with patch(
                    "steam_review_tool.core.atomic_write"
                    ".atomic_write_text",
                    side_effect=OSError("disk full"),
                ):
                    n = write_per_language(
                        ctx.reviews, base, ctx,
                    )
                # No files were written (both calls
                # raised).
                assert n == 0
                # At least one warning was logged.
                warnings = [
                    r for r in records
                    if "per-language" in r.getMessage().lower()
                ]
                assert warnings, (
                    f"expected a warning log on per-language "
                    f"OSError, got: "
                    f"{[r.getMessage() for r in records]}"
                )
        finally:
            logger.removeHandler(handler)


# ---------------------------------------------------------------------------
# BUG-R18-4: defensive coercion for the language field
# ---------------------------------------------------------------------------
class TestDefensiveLanguageCoercion:
    """The ``language`` field on a review dict is not
    defensively coerced to str in
    ``per_language_exporter.group_by_language`` or in
    ``markdown_helpers.render_summary``. A hand-rolled
    / Apify-normalised review can carry a non-string
    ``language`` (int / list / dict) — the previous
    code crashed with ``AttributeError`` on
    ``.strip()`` / ``.replace()`` and the bare
    ``except OSError: pass`` in the per-language
    exporter didn't even catch the AttributeError.
    """

    def test_group_by_language_handles_int_language(self) -> None:
        """A review with ``language=42`` (int) must NOT
        crash ``group_by_language`` — the int is
        coerced to ``"unknown"``."""
        from steam_review_tool.exporters.per_language_exporter import (
            group_by_language,
        )
        result = group_by_language([
            {"language": 42, "review": "x"},
            {"language": "english", "review": "y"},
        ])
        # The int-language review falls into "unknown".
        assert "unknown" in result
        assert len(result["unknown"]) == 1
        assert result["english"] == [
            {"language": "english", "review": "y"},
        ]

    def test_group_by_language_handles_list_language(self) -> None:
        """A review with ``language=["en", "de"]``
        (list) must NOT crash — coerced to
        ``"unknown"``."""
        from steam_review_tool.exporters.per_language_exporter import (
            group_by_language,
        )
        result = group_by_language([
            {"language": ["en", "de"], "review": "x"},
        ])
        assert "unknown" in result

    def test_group_by_language_handles_none_language(self) -> None:
        """A review with ``language=None`` falls into
        ``"unknown"`` (already worked, but make sure
        the new helper doesn't break it)."""
        from steam_review_tool.exporters.per_language_exporter import (
            group_by_language,
        )
        result = group_by_language([
            {"language": None, "review": "x"},
        ])
        assert "unknown" in result

    def test_group_by_language_handles_whitespace_only(self) -> None:
        """A review with ``language="   "`` (whitespace
        only) falls into ``"unknown"`` (defensive
        ``or "unknown"`` short-circuit)."""
        from steam_review_tool.exporters.per_language_exporter import (
            group_by_language,
        )
        result = group_by_language([
            {"language": "   ", "review": "x"},
        ])
        assert "unknown" in result

    def test_render_summary_handles_int_language(self) -> None:
        """A review with ``language=42`` (int) must NOT
        crash ``render_summary`` — the int is coerced
        to ``"—"`` so the language table renders
        without breaking."""
        from steam_review_tool.exporters.markdown_helpers import (
            render_summary,
        )
        lines = render_summary([
            {"voted_up": True, "language": 42},
            {"voted_up": False, "language": "english"},
        ])
        # The "—" placeholder is in the language table
        # (one review has int language).
        assert any("—" in ln for ln in lines), (
            f"expected '—' placeholder for non-string "
            f"language, got: {lines}"
        )
        # The markdown must not contain a literal
        # ``int(42)`` (a sign the int leaked through
        # the defensive coercion).
        assert not any("int" in ln.lower() for ln in lines)

    def test_render_summary_handles_none_language(self) -> None:
        """A review with ``language=None`` falls into
        ``"—"`` (already worked)."""
        from steam_review_tool.exporters.markdown_helpers import (
            render_summary,
        )
        lines = render_summary([
            {"voted_up": True, "language": None},
        ])
        assert any("—" in ln for ln in lines)
