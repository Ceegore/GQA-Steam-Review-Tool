"""Round-4 bug-hunt regression tests.

Real bugs found in a fourth systematic pass over the project. This
round goes after the residue of the ``int(r.get("KEY", 0) or 0)``
pattern (R3-2 / R3-3 only covered the two places where it was a
crash bug; the same pattern lived in 5+ more places as a latent
crash on non-numeric strings, plus one bare-``int()`` site that
crashed on None). It also fixes the no-op regression test in
``test_security_fixes.py`` that the previous summary flagged.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# BUG-R4-1: safe_int helper
# ---------------------------------------------------------------------------
class TestSafeIntHelper:
    """A new ``utils.coercion.safe_int`` consolidates every
    ``int(r.get(key, 0) or 0)`` site. The helper handles every
    type the Steam API or a hand-rolled test can throw at it."""

    def test_missing_key_returns_default(self) -> None:
        from steam_review_tool.utils.coercion import safe_int
        assert safe_int({}, "votes_up", 0) == 0
        assert safe_int({}, "votes_up", 7) == 7

    def test_none_value_returns_default(self) -> None:
        from steam_review_tool.utils.coercion import safe_int
        assert safe_int({"votes_up": None}, "votes_up", 0) == 0
        assert safe_int({"votes_up": None}, "votes_up", 42) == 42

    def test_int_value_passes_through(self) -> None:
        from steam_review_tool.utils.coercion import safe_int
        assert safe_int({"x": 0}, "x", 99) == 0
        assert safe_int({"x": 42}, "x", 99) == 42
        assert safe_int({"x": -1}, "x", 99) == -1

    def test_bool_value_is_explicit(self) -> None:
        from steam_review_tool.utils.coercion import safe_int
        # bool is technically a subclass of int in Python, but we
        # want explicit conversion so the int / bool distinction
        # is preserved in CSV exports.
        assert safe_int({"x": True}, "x", 0) == 1
        assert safe_int({"x": False}, "x", 0) == 0

    def test_string_numeric_value_coerced(self) -> None:
        from steam_review_tool.utils.coercion import safe_int
        assert safe_int({"x": "42"}, "x", 0) == 42
        assert safe_int({"x": " 7 "}, "x", 0) == 7
        assert safe_int({"x": "-1"}, "x", 0) == -1

    def test_string_non_numeric_returns_default(self) -> None:
        from steam_review_tool.utils.coercion import safe_int
        assert safe_int({"x": "abc"}, "x", 0) == 0
        assert safe_int({"x": "abc"}, "x", 99) == 99

    def test_empty_string_returns_default(self) -> None:
        from steam_review_tool.utils.coercion import safe_int
        assert safe_int({"x": ""}, "x", 0) == 0
        assert safe_int({"x": "   "}, "x", 0) == 0

    def test_float_value_coerced_when_finite(self) -> None:
        from steam_review_tool.utils.coercion import safe_int
        assert safe_int({"x": 3.7}, "x", 0) == 3
        assert safe_int({"x": -0.5}, "x", 0) == 0

    def test_float_overflow_returns_default(self) -> None:
        from steam_review_tool.utils.coercion import safe_int
        # float('inf') and float('nan') raise OverflowError / ValueError on int()
        assert safe_int({"x": float("inf")}, "x", 99) == 99
        assert safe_int({"x": float("-inf")}, "x", 99) == 99
        assert safe_int({"x": float("nan")}, "x", 99) == 99

    def test_unexpected_type_returns_default(self) -> None:
        from steam_review_tool.utils.coercion import safe_int
        assert safe_int({"x": [1, 2]}, "x", 0) == 0
        assert safe_int({"x": {"nested": 1}}, "x", 0) == 0

    def test_none_source_returns_default(self) -> None:
        from steam_review_tool.utils.coercion import safe_int
        assert safe_int(None, "votes_up", 7) == 7

    def test_safe_coerce_int_value_only(self) -> None:
        from steam_review_tool.utils.coercion import safe_coerce_int
        assert safe_coerce_int(42, 0) == 42
        assert safe_coerce_int(None, 0) == 0
        assert safe_coerce_int("abc", 7) == 7


# ---------------------------------------------------------------------------
# BUG-R4-2: steam_api_service.fetch_all_reviews used bare int() on timestamp
# ---------------------------------------------------------------------------
class TestSteamApiFetchMinDate:
    """``fetch_all_reviews`` used
    ``int(rv.get("timestamp_created", 0))`` to apply the
    ``min_date_ts`` filter. A ``None`` value crashed the whole
    pagination loop. The fix uses ``safe_int``."""

    def test_none_timestamp_does_not_crash(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from steam_review_tool.services.steam_api_service import SteamAPI

        api = SteamAPI()
        # Cursor is empty so the loop breaks after one page.
        fake_data = {
            "success": 1,
            "reviews": [
                {"recommendationid": "a", "timestamp_created": None},
                {"recommendationid": "b", "timestamp_created": 100},
            ],
            "query_summary": {"total_reviews": 2},
            "cursor": "",
        }

        class _Resp:
            status_code = 200
            def raise_for_status(self) -> None: pass
            def json(self) -> dict[str, Any]: return fake_data

        monkeypatch.setattr(
            api.session, "get", lambda *_a, **_kw: _Resp(),
        )
        # Apply a min_date_ts that would only keep the second
        # review; the first (None) is coerced to 0 and filtered
        # out. The important guarantee: no crash.
        out = api.fetch_all_reviews(
            app_id=4311090, min_date_ts=50,
            log_cb=lambda _m: None,
        )
        assert isinstance(out, list)
        # The None row was coerced to ts=0 < min_date_ts=50, so
        # it's filtered out. The ts=100 row passes.
        assert len(out) == 1
        assert out[0]["recommendationid"] == "b"

    def test_string_timestamp_does_not_crash(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from steam_review_tool.services.steam_api_service import SteamAPI

        api = SteamAPI()
        fake_data = {
            "success": 1,
            "reviews": [
                {"recommendationid": "a", "timestamp_created": "garbage"},
            ],
            "query_summary": {"total_reviews": 1},
            "cursor": "",
        }

        class _Resp:
            status_code = 200
            def raise_for_status(self) -> None: pass
            def json(self) -> dict[str, Any]: return fake_data

        monkeypatch.setattr(
            api.session, "get", lambda *_a, **_kw: _Resp(),
        )
        # Must not raise — the bad row is coerced to ts=0 and the
        # filter still works.
        out = api.fetch_all_reviews(
            app_id=4311090, min_date_ts=0,
            log_cb=lambda _m: None,
        )
        assert len(out) == 1


# ---------------------------------------------------------------------------
# BUG-R4-3: export_orchestrator + csv_exporter tolerate non-numeric votes
# ---------------------------------------------------------------------------
class TestCsvExportersSafeInt:
    """The ``int(r.get("votes_up", 0) or 0)`` pattern in the
    exporters was None-safe (the ``or 0`` swallowed None) but
    crashed on non-numeric strings. Fixed with ``safe_int``."""

    def test_csv_exporter_handles_string_votes(
        self, tmp_path: Path,
    ) -> None:
        from steam_review_tool.exporters.csv_exporter import reviews_to_csv
        reviews = [
            {
                "recommendationid": "rec-1",
                "language": "english",
                "voted_up": True,
                "votes_up": "garbage",   # non-numeric
                "votes_funny": None,     # present-but-None
                "comment_count": 3,
                "author": {
                    "steamid": "12345",
                    "playtime_forever": "not-a-number",
                    "last_played": None,
                },
                "timestamp_created": "weird-string",
                "timestamp_updated": 0,
                "weighted_vote_score": "0.5",
                "steam_purchase": True,
                "received_for_free": False,
                "written_during_early_access": None,
                "review": "ok",
            },
        ]
        dest = tmp_path / "out.csv"
        n = reviews_to_csv(reviews, dest)
        assert n == 1
        # Parse the CSV and confirm no column is the literal
        # "garbage" — the helper coerced it to 0.
        with open(dest, "r", encoding="utf-8", newline="") as f:
            rows = list(csv.reader(f))
        assert rows[1][3] == "0"   # votes_up → 0
        assert rows[1][4] == "0"   # votes_funny → 0
        assert rows[1][7] == "0"   # playtime_forever → 0
        assert rows[1][9] == "0"   # timestamp_created → 0

    def test_export_orchestrator_csv_path_handles_malformed(
        self, tmp_path: Path,
    ) -> None:
        from datetime import datetime, timezone
        from steam_review_tool.exporters.export_orchestrator import run
        from steam_review_tool.models.export_context import ExportContext

        ctx = ExportContext(
            app_id=4311090,
            app_details={"name": "TestGame"},
            reviews=[
                {
                    "recommendationid": "rec-1",
                    "language": "english",
                    "voted_up": True,
                    "votes_up": "garbage",
                    "votes_funny": None,
                    "comment_count": "abc",
                    "author": {"steamid": "1", "playtime_forever": "x"},
                    "timestamp_created": "weird",
                    "timestamp_updated": None,
                    "weighted_vote_score": "0.5",
                    "steam_purchase": True,
                    "received_for_free": False,
                    "written_during_early_access": None,
                    "review": "ok",
                },
            ],
            language_param="all",
            review_filter="all",
            review_type="all",
            day_range=None,
            min_date_ts=None,
        )
        dest = tmp_path / "out.csv"
        run(ctx, dest, also_csv=True, log_cb=lambda _m: None)
        # The CSV file must exist and contain a header + 1 data
        # row. The csv.writer + atomic_write_text path leaves a
        # trailing blank line in the file on Windows, so we
        # filter empty rows out before asserting.
        with open(dest, "r", encoding="utf-8", newline="") as f:
            rows = [r for r in csv.reader(f) if r]
        assert len(rows) == 2
        assert rows[1][3] == "0"   # votes_up coerced
        assert rows[1][9] == "0"   # timestamp_created coerced


# ---------------------------------------------------------------------------
# BUG-R4-4: api_workflow min_helpful uses safe_int for votes_up
# ---------------------------------------------------------------------------
class TestApiWorkflowMinHelpfulSafe:
    """``_fetch_worker`` used
    ``int(r.get("votes_up", 0) or 0) >= min_helpful`` — would crash
    the whole export on a non-numeric ``votes_up`` string. Now
    uses ``safe_int``."""

    def test_min_helpful_filter_handles_string_votes(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from steam_review_tool.controllers.api_workflow import APIWorkflow
        from steam_review_tool.services.steam_api_service import SteamAPI
        from steam_review_tool.core import event_bus

        api = SteamAPI()
        wf = APIWorkflow(api, Path("/tmp"), log_cb=lambda _m: None)
        fake_data = {
            "success": 1,
            "reviews": [
                {"recommendationid": "a", "votes_up": "garbage", "timestamp_created": 100},
                {"recommendationid": "b", "votes_up": 5, "timestamp_created": 100},
            ],
            "query_summary": {"total_reviews": 2},
            "cursor": "",
        }

        class _Resp:
            status_code = 200
            def raise_for_status(self) -> None: pass
            def json(self) -> dict[str, Any]: return fake_data

        monkeypatch.setattr(
            api.session, "get", lambda *_a, **_kw: _Resp(),
        )
        # Capture the FETCH_COMPLETED payload via the bus.
        captured: dict[str, Any] = {}
        real_publish = event_bus.bus.publish

        def fake_publish(event: str, **kw: Any) -> None:
            if event == wf.FETCH_COMPLETED:
                captured["reviews"] = kw.get("reviews")
            return real_publish(event, **kw)

        monkeypatch.setattr(
            event_bus.bus, "publish", fake_publish,
        )
        # Call the worker directly (synchronous — no thread).
        wf._fetch_worker(
            app_id=4311090, language="all", review_filter="all",
            review_type="all", day_range=None, min_date_ts=None,
            min_helpful=3, num_per_page=100, start_cursor="*",
        )
        out = captured.get("reviews", [])
        # "garbage" is coerced to 0, which is < 3, so dropped.
        # The numeric 5 passes.
        assert len(out) == 1
        assert out[0]["recommendationid"] == "b"


# ---------------------------------------------------------------------------
# BUG-R4-5: review_analyzer + exporters use safe_int for playtime_forever
# ---------------------------------------------------------------------------
class TestPlaytimeSafeInt:
    """``compute_playtime_histogram``, ``aggregate_top_themes``,
    ``render_summary`` / ``render_footer``, ``pre_ai_digest``,
    and ``per_language_exporter.build_summary`` all did
    ``int(author.get("playtime_forever", 0) or 0)`` on review
    dicts. The same non-numeric string would crash the whole
    export. The fix routes through ``safe_int``."""

    def test_compute_playtime_histogram_handles_string_playtime(self) -> None:
        from steam_review_tool.services.review_analyzer import (
            compute_playtime_histogram,
        )
        reviews = [
            {"voted_up": True, "author": {"playtime_forever": "garbage"}},
            {"voted_up": False, "author": {"playtime_forever": 120}},
        ]
        # Must not raise.
        out = compute_playtime_histogram(reviews, buckets=3)
        assert isinstance(out, dict)

    def test_pre_ai_digest_handles_string_playtime(self) -> None:
        from steam_review_tool.services.pre_ai_digest import (
            build_pre_ai_digest,
        )
        reviews = [
            {"voted_up": True, "author": {"steamid": "1", "playtime_forever": "garbage"}},
            {"voted_up": False, "author": {"steamid": "2", "playtime_forever": 60}},
        ]
        out = build_pre_ai_digest(reviews)
        # The "Top 3 reviewers" section is omitted if no steamid-bearing
        # rows, but build_pre_ai_digest must not crash on the
        # non-numeric playtime value.
        assert "Pre-AI Digest" in out

    def test_render_footer_handles_string_playtime(self) -> None:
        from steam_review_tool.exporters.markdown_helpers import (
            render_footer,
        )
        reviews = [
            {"voted_up": True, "author": {"steamid": "1", "playtime_forever": "garbage"}},
        ]
        out = render_footer(reviews)
        assert isinstance(out, list)

    def test_build_summary_handles_string_playtime(self) -> None:
        from steam_review_tool.exporters.per_language_exporter import (
            build_summary,
        )
        reviews = [
            {"voted_up": True, "author": {"steamid": "1", "playtime_forever": "x"}},
        ]
        out = build_summary(reviews)
        assert "Reviewer stats summary" in out


# ---------------------------------------------------------------------------
# BUG-R4-6: the no-op test in test_security_fixes.py was tautological
# ---------------------------------------------------------------------------
class TestPlaywrightFilenamePattern:
    """The previous ``test_playwright_subprocess_temp_filename_contains_pid``
    only checked ``pattern.pattern is not None`` (always true), so
    it didn't actually exercise the module. The replacement imports
    the real module, mocks the subprocess call, and asserts the
    filename matches the expected ``<pid>_<uuid8>.py`` pattern."""

    def test_filename_contains_pid_and_uuid_suffix(self) -> None:
        # We re-run the body of the security-fixes test here, but
        # in a self-contained way that doesn't depend on the
        # security-fixes file's import order.
        import os
        import re
        import sys
        import subprocess
        from unittest.mock import MagicMock
        from steam_review_tool.services import playwright_subprocess as pws

        expected_pid = os.getpid()
        pattern = re.compile(
            rf"_srt_pw_probe_{expected_pid}_[0-9a-f]{{8}}\.py$"
        )
        captured: dict[str, str] = {}

        real_find = pws.find_external_python
        real_run = pws.subprocess.run
        try:
            pws.find_external_python = lambda: sys.executable  # type: ignore[assignment]

            def fake_run(cmd, **_kw):
                captured["helper"] = str(cmd[1])
                m = MagicMock()
                m.returncode = 1
                m.stderr = "skip"
                m.stdout = ""
                return m
            pws.subprocess.run = fake_run  # type: ignore[assignment]

            pws.run_popularity_probe(4311090)
        finally:
            pws.find_external_python = real_find  # type: ignore[assignment]
            pws.subprocess.run = real_run  # type: ignore[assignment]

        helper_path = captured.get("helper", "")
        # Extract just the filename (no leading dirs).
        helper_name = helper_path.rsplit("\\", 1)[-1].rsplit("/", 1)[-1]
        assert pattern.match(helper_name), (
            f"helper {helper_name!r} does not match {pattern.pattern!r}"
        )

    def test_two_consecutive_probes_produce_different_filenames(self) -> None:
        """The UUID suffix must differ between two consecutive
        probes (PID+id collision regression)."""
        import os
        import sys
        from unittest.mock import MagicMock
        from steam_review_tool.services import playwright_subprocess as pws

        captured: list[str] = []
        real_find = pws.find_external_python
        real_run = pws.subprocess.run
        try:
            pws.find_external_python = lambda: sys.executable  # type: ignore[assignment]
            def fake_run(cmd, **_kw):
                captured.append(str(cmd[1]))
                m = MagicMock()
                m.returncode = 1
                m.stderr = "skip"
                m.stdout = ""
                return m
            pws.subprocess.run = fake_run  # type: ignore[assignment]
            pws.run_popularity_probe(4311090)
            pws.run_popularity_probe(4311090)
        finally:
            pws.find_external_python = real_find  # type: ignore[assignment]
            pws.subprocess.run = real_run  # type: ignore[assignment]

        assert len(captured) == 2
        assert captured[0] != captured[1]
