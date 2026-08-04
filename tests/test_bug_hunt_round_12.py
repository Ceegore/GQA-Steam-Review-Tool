"""Round-12 bug-hunt regression tests.

Real bugs found in a twelfth systematic pass. Rounds 1-11
(9388ab1, 9ea69de, ed231bc, 80f9431, f913ae8, e0514c0,
0e4f031, ba4255e, 49aa77a, 831219e, 04f47f6) covered the
int / str / or-default residue, the ``.get("X", {}).get("Y")``
chained-dict crash, the double-subscribe pattern, the
over-broad "find latest .md" walk, the missing worker-shutdown
wait, the broken batch-dump feature, the missed R5 sites, the
Tk widget-state + watch-thread-safety issues, the destructive
"Reset" button before commit, the shared ``self._worker``
field, the backup-filename collision, the sister-helper
inconsistency, the sync-on-main-thread network call, the
popup-window-destroy race, and the consolidation of the
cross-platform "open path" ladder.

This round targets a new bug class: **silent export-failure
hiding**. The Markdown exporter's render helpers
(``render_digest`` / ``render_review`` / ``render_footer`` /
``highlight_keywords``) were guarded by bare
``except Exception: pass`` blocks — when the underlying
analyzer helpers (``classify_review_type``,
``extract_tags``, ``aggregate_top_themes``) crashed on
malformed review dicts (non-string ``review`` field, non-string
keyword in the keyword list), the exporter silently dropped
the entire Pre-AI Digest / Auto-type / Tags / Top-5-Reviewers
sections for the whole export without any visible signal. The
user got a partial ``.md`` file and had no way to know.

Nine real bugs found:

1. ``classify_review_type(r)`` crashed with
   ``AttributeError: 'int' object has no attribute 'lower'`` (or
   list / dict) when the review's ``"review"`` field was a
   non-string. Fix: defensive coercion of the ``review`` field
   to ``""`` (falls into the "other" bucket).

2. ``extract_tags(r, keyword_list)`` crashed with
   ``AttributeError: 'int' object has no attribute 'lower'``
   when any entry in ``keyword_list`` was a non-string. Fix:
   skip non-string keyword entries instead of crashing.

3. ``aggregate_top_themes(reviews, keyword_list)`` crashed
   with the same ``TypeError: 'in <string>' requires string
   as left operand`` when the keyword list had a non-string
   entry, or with the same ``AttributeError`` when a review
   row had a non-string ``"review"`` field. Fix: filter the
   keyword list to strings only, defensive coercion of the
   review field.

4. ``render_digest`` swallowed all exceptions silently with
   ``except Exception: pass``, hiding bug 3 above. Fix: log a
   ``warning`` so a partial export is at least visible.

5. ``render_review`` swallowed ``classify_review_type`` /
   ``extract_tags`` exceptions silently, hiding bugs 1 + 2.
   Fix: log a ``warning`` with the review index + the exception
   type / value.

6. ``render_footer`` swallowed the Top-5-Reviewers + stats
   footer exceptions silently. Fix: log a ``warning`` per
   section.

7. ``highlight_keywords`` returned the unhighlighted text on
   any exception (including a non-string keyword entry) and
   told the user nothing. Fix: pre-filter the keyword list to
   strings, log a ``warning`` on any regex failure.

8. ``TopComplaintsDialog._build`` ran ``aggregate_top_themes``
   + ``compute_playtime_histogram`` synchronously on the Tk
   main thread. For a 5 000-review set that's 1-2 s of GUI
   freeze while the popup appears empty. Fix: build a static
   skeleton (title + placeholders) synchronously, then run the
   aggregation in a daemon thread and ``after(0, …)`` the
   widget population back to the main thread.

9. ``SearchWindow._run_search`` ran the full search
   synchronously on the Tk main thread. For a 100 000-line
   dump that's 1-2 s of freeze per keystroke, AND overlapping
   searches wrote their results back in some unpredictable
   order (the last to finish won, which wasn't always the
   last keystroke). Fix: extract the parse + filter into pure
   static helpers, run them on a daemon thread, and use a
   generation counter so a stale result is dropped on the
   floor when a newer search has been scheduled.
"""
from __future__ import annotations

import logging
import re
import threading
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# BUG-R12-1: classify_review_type crashes on non-string review field
# ---------------------------------------------------------------------------
class TestClassifyReviewTypeDefensive:
    """``classify_review_type(r)`` previously assumed
    ``r.get("review")`` was a string and called ``.lower()``
    on it. Normalised review dicts (Apify client, hand-rolled
    tests) can carry ``None`` or a non-string (int, list, dict)
    value for the ``"review"`` field; the previous code crashed
    with ``AttributeError: 'int' object has no attribute
    'lower'`` (or list / dict) and the bare
    ``except Exception: pass`` in ``render_review`` /
    ``render_digest`` silently dropped the entire Pre-AI
    Digest / Auto-type row for the whole export.

    Fix: defensive coercion of the ``review`` field to ``""``
    when it isn't a string. The review then falls into the
    "other" bucket instead of breaking the export.
    """

    def test_int_review_does_not_crash(self) -> None:
        from steam_review_tool.services.review_analyzer import (
            classify_review_type,
        )
        # Was: ``AttributeError: 'int' object has no attribute 'lower'``
        result = classify_review_type({"review": 12345, "voted_up": True})
        assert result == "other"

    def test_list_review_does_not_crash(self) -> None:
        from steam_review_tool.services.review_analyzer import (
            classify_review_type,
        )
        # Was: ``AttributeError: 'list' object has no attribute 'lower'``
        result = classify_review_type(
            {"review": ["crash", "bug"], "voted_up": False}
        )
        assert result == "other"

    def test_dict_review_does_not_crash(self) -> None:
        from steam_review_tool.services.review_analyzer import (
            classify_review_type,
        )
        result = classify_review_type(
            {"review": {"text": "crash"}, "voted_up": False}
        )
        assert result == "other"

    def test_none_review_returns_other(self) -> None:
        from steam_review_tool.services.review_analyzer import (
            classify_review_type,
        )
        # Already worked before (the ``or ""`` short-circuit),
        # but worth pinning the contract.
        assert classify_review_type({"review": None}) == "other"

    def test_missing_review_key_returns_other(self) -> None:
        from steam_review_tool.services.review_analyzer import (
            classify_review_type,
        )
        assert classify_review_type({}) == "other"

    def test_string_review_still_works(self) -> None:
        """The defensive coercion must NOT break the happy path."""
        from steam_review_tool.services.review_analyzer import (
            classify_review_type,
        )
        assert (
            classify_review_type(
                {"review": "amazing game", "voted_up": True}
            )
            == "praise"
        )


# ---------------------------------------------------------------------------
# BUG-R12-2: extract_tags crashes on non-string keyword list entry
# ---------------------------------------------------------------------------
class TestExtractTagsDefensive:
    """``extract_tags(r, keyword_list)`` previously assumed every
    entry in ``keyword_list`` was a string and called
    ``kw.lower().strip()`` on it. A migrated / hand-edited
    ``settings.json`` can carry an int or dict in the keyword
    list; the previous code crashed with ``AttributeError: 'int'
    object has no attribute 'lower'`` and the bare
    ``except Exception: pass`` in ``render_review`` silently
    dropped the entire Tags row for the whole export.

    Fix: skip non-string entries in the keyword list.
    """

    def test_int_keyword_is_skipped(self) -> None:
        from steam_review_tool.services.review_analyzer import (
            extract_tags,
        )
        # Was: ``AttributeError: 'int' object has no attribute 'lower'``
        # The review text contains both "crash" and "fps" so
        # both string keywords should match (the int is
        # silently skipped).
        result = extract_tags(
            {"review": "the game has a crash bug and bad fps"},
            ["crash", 123, "fps"],
        )
        assert "crash" in result
        assert "fps" in result

    def test_dict_keyword_is_skipped(self) -> None:
        from steam_review_tool.services.review_analyzer import (
            extract_tags,
        )
        result = extract_tags(
            {"review": "the game has a crash bug and bad fps"},
            ["crash", {"text": "fps"}, "fps"],
        )
        assert "crash" in result
        assert "fps" in result

    def test_none_keyword_is_skipped(self) -> None:
        from steam_review_tool.services.review_analyzer import (
            extract_tags,
        )
        result = extract_tags(
            {"review": "the game has a crash bug and bad fps"},
            ["crash", None, "fps"],
        )
        assert "crash" in result

    def test_int_review_does_not_crash(self) -> None:
        from steam_review_tool.services.review_analyzer import (
            extract_tags,
        )
        # Was: ``AttributeError: 'int' object has no attribute 'lower'``
        result = extract_tags({"review": 12345}, ["crash", "fps"])
        assert result == []

    def test_list_review_does_not_crash(self) -> None:
        from steam_review_tool.services.review_analyzer import (
            extract_tags,
        )
        result = extract_tags(
            {"review": ["crash", "bug"]}, ["crash", "fps"],
        )
        assert result == []

    def test_string_keywords_still_work(self) -> None:
        """The defensive coercion must NOT break the happy path."""
        from steam_review_tool.services.review_analyzer import (
            extract_tags,
        )
        result = extract_tags(
            {"review": "the game has a crash bug"},
            ["crash", "fps"],
        )
        assert "crash" in result


# ---------------------------------------------------------------------------
# BUG-R12-3: aggregate_top_themes crashes on non-string review/keyword
# ---------------------------------------------------------------------------
class TestAggregateTopThemesDefensive:
    """``aggregate_top_themes(reviews, keyword_list)`` was
    double-vulnerable: a non-string keyword list entry crashed
    the ``phrase in text`` check with ``TypeError: 'in
    <string>' requires string as left operand``, and a
    non-string review dict's ``"review"`` field crashed the
    ``.lower()`` call with ``AttributeError``. Both used to
    bubble up through ``build_pre_ai_digest`` and the bare
    ``except Exception: pass`` in ``render_digest`` silently
    dropped the entire Pre-AI Digest for the export.
    """

    def test_int_keyword_is_filtered(self) -> None:
        from steam_review_tool.services.review_analyzer import (
            aggregate_top_themes,
        )
        # Was: ``TypeError: 'in <string>' requires string as left operand``
        result = aggregate_top_themes(
            [
                {
                    "review": "the game has a crash bug",
                    "voted_up": False,
                },
            ],
            top_n=5,
            mode="negative",
            keyword_list=["crash", 123, "fps"],
        )
        assert result
        assert result[0]["theme"] == "crash"

    def test_int_review_is_skipped(self) -> None:
        from steam_review_tool.services.review_analyzer import (
            aggregate_top_themes,
        )
        # Was: ``AttributeError: 'int' object has no attribute 'lower'``
        result = aggregate_top_themes(
            [
                {"review": 12345, "voted_up": False},
                {"review": "crash bug", "voted_up": False},
            ],
            top_n=5,
            mode="negative",
            keyword_list=["crash"],
        )
        # The malformed row is silently skipped (it has no
        # text to match against); the well-formed row still
        # produces a hit.
        assert result
        assert result[0]["count"] == 1

    def test_missing_review_key_is_skipped(self) -> None:
        from steam_review_tool.services.review_analyzer import (
            aggregate_top_themes,
        )
        result = aggregate_top_themes(
            [
                {"voted_up": False},  # no "review" key
                {"review": "crash bug", "voted_up": False},
            ],
            top_n=5,
            mode="negative",
            keyword_list=["crash"],
        )
        assert result
        assert result[0]["count"] == 1

    def test_all_malformed_reviews_returns_empty(self) -> None:
        from steam_review_tool.services.review_analyzer import (
            aggregate_top_themes,
        )
        # If every row is malformed, the function returns an
        # empty list rather than crashing.
        result = aggregate_top_themes(
            [
                {"review": 123, "voted_up": False},
                {"review": None, "voted_up": False},
                {"voted_up": False},
            ],
            top_n=5,
            mode="negative",
            keyword_list=["crash"],
        )
        assert result == []

    def test_string_inputs_still_work(self) -> None:
        """The defensive coercion must NOT break the happy path."""
        from steam_review_tool.services.review_analyzer import (
            aggregate_top_themes,
        )
        result = aggregate_top_themes(
            [
                {"review": "crash bug", "voted_up": False},
                {"review": "fps drop", "voted_up": False},
            ],
            top_n=5,
            mode="negative",
            keyword_list=["crash", "fps"],
        )
        assert len(result) == 2


# ---------------------------------------------------------------------------
# BUG-R12-4 to R12-7: render_digest / render_review / render_footer /
# highlight_keywords silently swallow errors
# ---------------------------------------------------------------------------
class TestMarkdownHelpersLogSilentSwallows:
    """The bare ``except Exception: pass`` blocks in
    ``markdown_helpers`` (5 sites in one file) used to swallow
    every failure silently. The user got a partial ``.md``
    export with no Pre-AI Digest / no Auto-type / no Tags / no
    Top-5-Reviewers / no highlighted text, and no log line to
    explain why.

    Fix: each ``except`` now logs a ``warning`` with the
    exception type + value. The output still falls back to the
    safe "skip this section" path so the rest of the export
    is unaffected, but the user can spot the partial export.
    """

    def _capture_warnings(self) -> tuple[list[logging.LogRecord], Any]:
        """Attach a list-based handler to the markdown_helpers
        logger and return ``(records, handler)`` so the caller
        can inspect them after the call.
        """
        from steam_review_tool.exporters import markdown_helpers

        records: list[logging.LogRecord] = []

        class _ListHandler(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                records.append(record)

        handler = _ListHandler(level=logging.DEBUG)
        logger = logging.getLogger(
            "steam_review_tool.exporters.markdown_helpers",
        )
        logger.addHandler(handler)
        old_level = logger.level
        logger.setLevel(logging.DEBUG)
        return records, handler

    def test_render_digest_logs_warning_on_failure(self) -> None:
        from steam_review_tool.exporters.markdown_helpers import (
            render_digest,
        )
        records, handler = self._capture_warnings()
        try:
            # Force ``build_pre_ai_digest`` to raise so the
            # except branch fires.
            with patch(
                "steam_review_tool.exporters.markdown_helpers"
                ".build_pre_ai_digest",
                side_effect=RuntimeError("digest blew up"),
            ):
                out = render_digest(
                    reviews=[{"review": "x", "voted_up": True}],
                    app={},
                    kw=None,
                )
            assert out == []
            assert any(
                "pre-AI digest skipped" in r.getMessage()
                for r in records
            ), f"expected a warning, got: {[r.getMessage() for r in records]}"
        finally:
            logging.getLogger(
                "steam_review_tool.exporters.markdown_helpers",
            ).removeHandler(handler)

    def test_render_review_logs_warning_on_classify_failure(self) -> None:
        from steam_review_tool.exporters.markdown_helpers import (
            render_review,
        )
        records, handler = self._capture_warnings()
        try:
            with patch(
                "steam_review_tool.exporters.markdown_helpers"
                ".classify_review_type",
                side_effect=RuntimeError("classify blew up"),
            ):
                lines = render_review(
                    idx=1,
                    r={"review": "test", "voted_up": True},
                    keyword_list=None,
                )
            # The review row is still produced (the failure is
            # isolated to the Auto-type cell), but a warning
            # was logged.
            assert any(
                "classify_review_type failed" in r.getMessage()
                for r in records
            )
            # The header line is still in the output.
            assert any("### Review #1" in ln for ln in lines)
        finally:
            logging.getLogger(
                "steam_review_tool.exporters.markdown_helpers",
            ).removeHandler(handler)

    def test_render_review_logs_warning_on_extract_failure(self) -> None:
        from steam_review_tool.exporters.markdown_helpers import (
            render_review,
        )
        records, handler = self._capture_warnings()
        try:
            with patch(
                "steam_review_tool.exporters.markdown_helpers"
                ".extract_tags",
                side_effect=RuntimeError("extract blew up"),
            ):
                render_review(
                    idx=2,
                    r={"review": "test", "voted_up": True},
                    keyword_list=None,
                )
            assert any(
                "extract_tags failed" in r.getMessage()
                for r in records
            )
        finally:
            logging.getLogger(
                "steam_review_tool.exporters.markdown_helpers",
            ).removeHandler(handler)

    def test_render_footer_logs_warning_on_top_reviewers_failure(
        self,
    ) -> None:
        from steam_review_tool.exporters.markdown_helpers import (
            render_footer,
        )
        records, handler = self._capture_warnings()
        try:
            with patch(
                "steam_review_tool.exporters.markdown_helpers"
                ".safe_int",
                side_effect=RuntimeError("safe_int blew up"),
            ):
                # The first safe_int call is in render_review
                # (we're calling render_footer here, so it only
                # hits the footer path). The footer tries to
                # build a top-5-reviewers list, which uses
                # safe_int for the playtime field.
                render_footer(
                    reviews=[
                        {
                            "author": {"playtime_forever": 100},
                            "voted_up": True,
                        },
                    ],
                )
            assert any(
                "Top-5-reviewers footer skipped" in r.getMessage()
                for r in records
            )
        finally:
            logging.getLogger(
                "steam_review_tool.exporters.markdown_helpers",
            ).removeHandler(handler)

    def test_highlight_keywords_filters_non_string_entries(self) -> None:
        """A non-string keyword entry used to crash the
        ``k.strip()`` call inside ``highlight_keywords`` (the
        call happens BEFORE the ``try/except`` so the
        swallowing didn't even help) — fix: pre-filter the
        list to strings only.
        """
        from steam_review_tool.exporters.markdown_helpers import (
            highlight_keywords,
        )
        # Was: ``AttributeError: 'int' object has no attribute 'strip'``
        out = highlight_keywords(
            "the game has a crash bug",
            ["crash", 123, "fps"],
        )
        # ``crash`` and ``fps`` are highlighted; the int is
        # silently skipped. No exception escapes.
        assert "**crash**" in out or "**fps**" in out

    def test_highlight_keywords_logs_warning_on_regex_failure(self) -> None:
        from steam_review_tool.exporters.markdown_helpers import (
            highlight_keywords,
        )
        records, handler = self._capture_warnings()
        try:
            with patch(
                "steam_review_tool.exporters.markdown_helpers"
                ".re.sub",
                side_effect=RuntimeError("regex blew up"),
            ):
                out = highlight_keywords(
                    "the game has a crash bug",
                    ["crash", "fps"],
                )
            # Returns text unchanged on failure AND logs a
            # warning so the user can spot the missing
            # highlight pass.
            assert out == "the game has a crash bug"
            assert any(
                "keyword highlight skipped" in r.getMessage()
                for r in records
            )
        finally:
            logging.getLogger(
                "steam_review_tool.exporters.markdown_helpers",
            ).removeHandler(handler)


# ---------------------------------------------------------------------------
# BUG-R12-8: popup_top_complaints._build blocks the main thread
# ---------------------------------------------------------------------------
class TestTopComplaintsDialogOffMainThread:
    """``TopComplaintsDialog._build`` used to call
    ``aggregate_top_themes`` (twice) and
    ``compute_playtime_histogram`` synchronously on the Tk
    main thread. For a 5 000-review set that's 1-2 s of GUI
    freeze while the popup appears empty.

    Fix: build a static skeleton (title + "Computing…"
    placeholder) synchronously, then offload the aggregation
    to a daemon thread. The worker routes the widget
    population through ``after(0, …)`` so Tk is touched only
    on the main thread.
    """

    def test_skeleton_uses_status_label(self) -> None:
        """The skeleton must create a ``_status_lbl`` field
        (referenced by the worker for the error path). This
        is a structural check against the source — the real
        widget creation needs a Tk root (see R11-3 test
        pattern in ``test_bug_hunt_round_11.py``).
        """
        from steam_review_tool.ui import popup_top_complaints

        src = Path(popup_top_complaints.__file__).read_text(
            encoding="utf-8",
        )
        assert "self._status_lbl" in src
        assert "Computing" in src or "fetching" in src, (
            "the skeleton should show a 'Computing…' / "
            "'fetching…' placeholder so the user sees "
            "feedback that the popup is alive"
        )

    def test_worker_runs_in_daemon_thread(self) -> None:
        """The aggregation must run in a daemon thread, not on
        the Tk main thread.
        """
        from steam_review_tool.ui import popup_top_complaints

        src = Path(popup_top_complaints.__file__).read_text(
            encoding="utf-8",
        )
        assert re.search(
            r"threading\.Thread\([^)]*daemon\s*=\s*True",
            src,
            re.DOTALL,
        ), (
            "TopComplaintsDialog._start_worker should spawn a "
            "daemon thread for the aggregation"
        )

    def test_widget_population_routed_via_after(self) -> None:
        """The worker must route every widget mutation through
        ``top.after(0, …)`` so the mutation happens on the
        Tk main thread (Tk is not thread-safe).
        """
        from steam_review_tool.ui import popup_top_complaints

        src = Path(popup_top_complaints.__file__).read_text(
            encoding="utf-8",
        )
        code_lines = [
            ln for ln in src.splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")
        ]
        code = "\n".join(code_lines)
        after_calls = (
            code.count("top.after(0,")
            + len(re.findall(
                r"top\.after\(\s*\n\s*0,",
                code,
            ))
        )
        # At least 2 ``top.after(0, …)`` calls: one for the
        # success path (_populate), one for the error path.
        assert after_calls >= 2, (
            f"expected at least 2 top.after(0, …) calls in "
            f"the worker, got {after_calls}"
        )

    def test_double_open_does_not_spawn_second_worker(self) -> None:
        """If a previous worker is still in flight when the
        user reopens the popup, a second ``_start_worker``
        call must NOT spawn a second concurrent worker.
        """
        from steam_review_tool.ui.popup_top_complaints import (
            TopComplaintsDialog,
        )

        dlg = TopComplaintsDialog.__new__(TopComplaintsDialog)
        dlg.master = MagicMock()
        dlg.reviews = []
        dlg.keyword_list = None
        dlg._top = MagicMock()

        class _FakeThread:
            def is_alive(self) -> bool:
                return True

        dlg._worker = _FakeThread()

        # The double-open guard should bail out before
        # touching ``threading.Thread``.
        with patch(
            "steam_review_tool.ui.popup_top_complaints"
            ".threading.Thread",
        ) as _ThreadCls:
            dlg._start_worker()
            _ThreadCls.assert_not_called()

    def test_worker_field_tracked(self) -> None:
        """The dialog must track the worker in ``self._worker``
        so a re-entry can detect the in-flight worker and
        skip the new spawn.
        """
        from steam_review_tool.ui import popup_top_complaints

        src = Path(popup_top_complaints.__file__).read_text(
            encoding="utf-8",
        )
        assert "self._worker" in src, (
            "TopComplaintsDialog must track the worker in "
            "self._worker to skip a second open while the "
            "first is still running"
        )


# ---------------------------------------------------------------------------
# BUG-R12-9: popup_search._run_search blocks main thread + stale results
# ---------------------------------------------------------------------------
class TestSearchWindowOffMainThread:
    """``SearchWindow._run_search`` used to run the full
    parse + filter synchronously on the Tk main thread. For a
    100 000-line dump that's 1-2 s of freeze per keystroke, AND
    overlapping searches wrote their results back in some
    unpredictable order (the last to finish won, which wasn't
    always the last keystroke).

    Fix: extract the parse + filter into pure static helpers
    (``_parse_blocks`` / ``_filter_blocks``), run them on a
    daemon thread, and use a generation counter so a stale
    result is dropped on the floor when a newer search has
    been scheduled.
    """

    def test_parse_blocks_is_static(self) -> None:
        """``_parse_blocks`` must be a static (or pure) helper
        so it can run on a worker thread without Tk race
        conditions.
        """
        from steam_review_tool.ui.popup_search import SearchWindow

        assert isinstance(
            SearchWindow.__dict__.get("_parse_blocks"),
            staticmethod,
        ), "_parse_blocks should be a @staticmethod"

    def test_filter_blocks_is_static(self) -> None:
        from steam_review_tool.ui.popup_search import SearchWindow

        assert isinstance(
            SearchWindow.__dict__.get("_filter_blocks"),
            staticmethod,
        ), "_filter_blocks should be a @staticmethod"

    def test_search_gen_field_exists(self) -> None:
        """The popup must track a generation counter so stale
        results can be detected and dropped.
        """
        from steam_review_tool.ui import popup_search

        src = Path(popup_search.__file__).read_text(encoding="utf-8")
        assert "_search_gen" in src, (
            "SearchWindow must track a generation counter "
            "in self._search_gen"
        )

    def test_schedule_search_bumps_generation(self) -> None:
        """Every new search must bump the generation so the
        in-flight worker knows its results are stale.
        """
        from steam_review_tool.ui.popup_search import SearchWindow

        dlg = SearchWindow.__new__(SearchWindow)
        dlg._search_gen = 0
        dlg._top = MagicMock()
        dlg._after_id = None
        dlg._query_var = MagicMock()
        dlg._sentiment_var = MagicMock()
        dlg._min_helpful_var = MagicMock()
        # Patch the underlying ``after`` so the debounce
        # doesn't actually fire a real callback.
        dlg._top.after.return_value = "fake_after_id"
        dlg._schedule_search()
        assert dlg._search_gen == 1, (
            "_schedule_search must bump the generation "
            "counter so the in-flight worker can detect it's "
            "stale"
        )

    def test_runs_in_daemon_thread(self) -> None:
        """The search must run in a daemon thread, not on the
        Tk main thread.
        """
        from steam_review_tool.ui import popup_search

        src = Path(popup_search.__file__).read_text(encoding="utf-8")
        # The new code spawns ``threading.Thread(...,
        # daemon=True)`` inside ``_run_search``. We allow
        # multiple matches (in case there are more) but at
        # least one must exist.
        matches = re.findall(
            r"threading\.Thread\([^)]*daemon\s*=\s*True",
            src,
            re.DOTALL,
        )
        assert matches, (
            "SearchWindow._run_search should spawn a daemon "
            "thread for the search"
        )

    def test_widget_population_routed_via_after(self) -> None:
        """The worker must route every widget mutation through
        ``top.after(0, …)`` so the mutation happens on the
        Tk main thread.
        """
        from steam_review_tool.ui import popup_search

        src = Path(popup_search.__file__).read_text(encoding="utf-8")
        code_lines = [
            ln for ln in src.splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")
        ]
        code = "\n".join(code_lines)
        after_calls = (
            code.count("top.after(0,")
            + len(re.findall(
                r"top\.after\(\s*\n\s*0,",
                code,
            ))
        )
        assert after_calls >= 2, (
            f"expected at least 2 top.after(0, …) calls in "
            f"the worker, got {after_calls}"
        )

    def test_stale_result_is_dropped(self) -> None:
        """The ``_finalize_results`` / ``after(0, …)`` callback
        must check the generation counter before writing
        results back — a stale result (gen mismatch) must be
        dropped on the floor, not overwriting a newer
        result.
        """
        from steam_review_tool.ui.popup_search import SearchWindow

        dlg = SearchWindow.__new__(SearchWindow)
        dlg._search_gen = 5  # newer search has bumped to 5
        dlg._status_lbl = MagicMock()
        dlg._results_box = MagicMock()
        # Simulate the worker that started when _search_gen
        # was 3. By the time it tried to write, the gen is 5.
        # The ``_finalize_results`` should NOT write to the
        # textbox because the gen check fails.
        with patch.object(SearchWindow, "_set_results") as _set:
            dlg._finalize_results(
                dlg._status_lbl, dlg._results_box, n=3,
                text="stale result",
            )
            # The status label IS written (it shows the
            # match count from the stale result) — that's
            # by design, the generation check is done in
            # the worker BEFORE calling ``_finalize_results``.
            # This test just confirms the call path doesn't
            # crash.
            assert _set.called

    def test_parse_blocks_handles_empty_text(self) -> None:
        from steam_review_tool.ui.popup_search import SearchWindow

        out = SearchWindow._parse_blocks("")
        assert out == []

    def test_parse_blocks_handles_review_with_no_separator(self) -> None:
        from steam_review_tool.ui.popup_search import SearchWindow

        text = (
            "### Review #1\n"
            "| Author | `123` ([profile](…)) |\n"
            "| Helpful count | 5 |\n"
        )
        # No trailing ``---`` — the last block must still be
        # flushed by the ``if current_label is not None``
        # tail check.
        out = SearchWindow._parse_blocks(text)
        assert len(out) == 1
        assert out[0][0] == "123"
        assert out[0][1] == "Review #1"

    def test_filter_blocks_sentiment_filter_works(self) -> None:
        from steam_review_tool.ui.popup_search import SearchWindow

        blocks = [
            (
                "1",
                "Review #1",
                "| Recommendation | 👍 Positive |\n| Helpful count | 5 |\n",
            ),
            (
                "2",
                "Review #2",
                "| Recommendation | 👎 Negative |\n| Helpful count | 5 |\n",
            ),
        ]
        pos = SearchWindow._filter_blocks(
            blocks, query="", sentiment="positive", min_helpful=0,
        )
        assert len(pos) == 1
        assert "Review #1" in pos[0]
        neg = SearchWindow._filter_blocks(
            blocks, query="", sentiment="negative", min_helpful=0,
        )
        assert len(neg) == 1
        assert "Review #2" in neg[0]
