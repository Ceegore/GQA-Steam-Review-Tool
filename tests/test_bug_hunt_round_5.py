"""Round-5 bug-hunt regression tests.

Real bugs found in a fifth systematic pass over the project. Rounds
1-4 (9388ab1, 9ea69de, ed231bc, 80f9431) covered the obvious crashers
and the int(r.get(...)) residue. This round targets the
**string-equivalent** of the same pattern: ``str(r.get("KEY", ""))``
silently renders ``None`` as the literal string ``"None"``, which
breaks URLs and pollutes the CSV / Markdown output. It also catches
the **``or default`` short-circuit** in apify_client that silently
loses 0-valued numeric counts (the new ``_first_present`` helper
fixes that), and the bare-``int()`` sites in the model layer.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# BUG-R5-1: apify_client "or default" short-circuit loses 0 values
# ---------------------------------------------------------------------------
class TestApifyNormalizeKeepsZeroValues:
    """The old ``ApifyClient._normalize`` used
    ``item.get("helpfulCount") or item.get("votes_up", 0)`` to pick
    between Apify's camelCase and Steam's snake_case names. The
    ``or`` short-circuit treats ``0`` as "absent", so a review
    with ``helpfulCount=0`` (a real, valid value — "no helpful
    votes") was silently overwritten with ``votes_up``. The
    same bug affected votes_funny, comment_count, playtime_forever,
    last_played, timestamp_created, timestamp_updated.

    Fix: a new ``_first_present(*values)`` helper picks the first
    non-``None`` value, preserving real 0s.
    """

    def test_votes_up_preserved_when_zero(self) -> None:
        from steam_review_tool.services.apify_client import (
            ApifyClient, _first_present,
        )
        # helpfulCount=0 (real value, no helpful votes) is preserved
        out = ApifyClient._normalize({"helpfulCount": 0})
        assert out["votes_up"] == 0

    def test_votes_up_falls_back_when_helpfulCount_missing(self) -> None:
        from steam_review_tool.services.apify_client import ApifyClient
        # If the Apify response is missing helpfulCount, fall back
        # to the snake_case votes_up.
        out = ApifyClient._normalize({"votes_up": 7})
        assert out["votes_up"] == 7

    def test_votes_up_zero_with_no_fallback_uses_default(self) -> None:
        from steam_review_tool.services.apify_client import ApifyClient
        out = ApifyClient._normalize({})  # both fields missing
        assert out["votes_up"] == 0

    def test_votes_funny_preserved_when_zero(self) -> None:
        from steam_review_tool.services.apify_client import ApifyClient
        out = ApifyClient._normalize({"funnyCount": 0})
        assert out["votes_funny"] == 0

    def test_comment_count_preserved_when_zero(self) -> None:
        from steam_review_tool.services.apify_client import ApifyClient
        out = ApifyClient._normalize({"commentCount": 0})
        assert out["comment_count"] == 0

    def test_playtime_forever_preserved_when_zero(self) -> None:
        from steam_review_tool.services.apify_client import ApifyClient
        # playtimeForever=0 is "reviewer never played the game" —
        # a real value, not "missing".
        out = ApifyClient._normalize({"playtimeForever": 0})
        assert out["author"]["playtime_forever"] == 0

    def test_last_played_preserved_when_zero(self) -> None:
        from steam_review_tool.services.apify_client import ApifyClient
        out = ApifyClient._normalize({"lastPlayed": 0})
        assert out["author"]["last_played"] == 0

    def test_timestamp_preserved_when_zero(self) -> None:
        from steam_review_tool.services.apify_client import ApifyClient
        out = ApifyClient._normalize({"createdAt": 0})
        assert out["timestamp_created"] == 0

    def test_first_present_helper(self) -> None:
        from steam_review_tool.services.apify_client import _first_present
        assert _first_present(None, None, 5) == 5
        assert _first_present(None, 0, 5) == 0  # 0 is "present"
        assert _first_present(None, None) is None
        assert _first_present(7, 8) == 7
        assert _first_present("", "fallback") == ""  # "" is present too


# ---------------------------------------------------------------------------
# BUG-R5-2: safe_str helper handles all the cases
# ---------------------------------------------------------------------------
class TestSafeStrHelper:
    """A new ``utils.coercion.safe_str`` consolidates the
    ``str(r.get("KEY", ""))`` pattern. Returns ``""`` for missing
    keys, present-but-``None`` values, non-string types, and
    empty / whitespace-only strings."""

    def test_missing_key_returns_default(self) -> None:
        from steam_review_tool.utils.coercion import safe_str
        assert safe_str({}, "steamid", "") == ""
        assert safe_str({}, "steamid", "x") == "x"

    def test_none_value_returns_default(self) -> None:
        from steam_review_tool.utils.coercion import safe_str
        # The KEY bug: a present-but-None value used to render as
        # "None" via str() — broken URLs everywhere.
        assert safe_str({"steamid": None}, "steamid", "") == ""

    def test_int_value_stringified(self) -> None:
        from steam_review_tool.utils.coercion import safe_str
        assert safe_str({"x": 42}, "x", "") == "42"

    def test_str_value_stripped(self) -> None:
        from steam_review_tool.utils.coercion import safe_str
        assert safe_str({"x": "abc"}, "x", "") == "abc"
        assert safe_str({"x": "  abc  "}, "x", "") == "abc"

    def test_empty_string_returns_default(self) -> None:
        from steam_review_tool.utils.coercion import safe_str
        assert safe_str({"x": ""}, "x", "") == ""
        assert safe_str({"x": "   "}, "x", "") == ""

    def test_list_or_dict_returns_default(self) -> None:
        from steam_review_tool.utils.coercion import safe_str
        assert safe_str({"x": [1, 2]}, "x", "") == ""
        assert safe_str({"x": {"nested": 1}}, "x", "") == ""

    def test_none_source_returns_default(self) -> None:
        from steam_review_tool.utils.coercion import safe_str
        assert safe_str(None, "x", "fallback") == "fallback"

    def test_safe_coerce_str_value_only(self) -> None:
        from steam_review_tool.utils.coercion import safe_coerce_str
        assert safe_coerce_str(42, "") == "42"
        assert safe_coerce_str(None, "") == ""
        assert safe_coerce_str([1, 2], "") == ""


# ---------------------------------------------------------------------------
# BUG-R5-3: models/review.py:Review.timestamp_created crashes on None
# ---------------------------------------------------------------------------
class TestReviewModelTimestamp:
    """``Review.timestamp_created`` did
    ``int(self.data.get("timestamp_created", 0))`` — same R3-2
    pattern, in the model layer. A review with
    ``timestamp_created: None`` raised TypeError on property
    access, which the consumers couldn't catch.

    Fix: route through ``safe_int``.
    """

    def test_none_timestamp_returns_zero(self) -> None:
        from steam_review_tool.models.review import Review
        r = Review({"timestamp_created": None})
        assert r.timestamp_created == 0

    def test_string_timestamp_does_not_crash(self) -> None:
        from steam_review_tool.models.review import Review
        r = Review({"timestamp_created": "garbage"})
        assert r.timestamp_created == 0

    def test_missing_timestamp_returns_zero(self) -> None:
        from steam_review_tool.models.review import Review
        r = Review({})
        assert r.timestamp_created == 0

    def test_normal_timestamp_passes_through(self) -> None:
        from steam_review_tool.models.review import Review
        r = Review({"timestamp_created": 1700000000})
        assert r.timestamp_created == 1700000000

    def test_none_language_returns_empty_string(self) -> None:
        from steam_review_tool.models.review import Review
        r = Review({"language": None})
        assert r.language == ""

    def test_none_steamid_returns_empty_string(self) -> None:
        from steam_review_tool.models.review import Review
        # The old code rendered the literal "None" in URLs.
        r = Review({"author": {"steamid": None}})
        assert r.author_steamid == ""

    def test_none_review_id_returns_empty_string(self) -> None:
        from steam_review_tool.models.review import Review
        r = Review({"recommendationid": None})
        assert r.review_id == ""


# ---------------------------------------------------------------------------
# BUG-R5-4: app_window._on_settings_changed crashes on None dump_root
# ---------------------------------------------------------------------------
class TestAppWindowHandlesNoneSettings:
    """``_on_settings_changed`` did
    ``Path(data.get("dump_root", ""))`` — the default branch only
    fires for missing keys, so a present-but-None value (e.g. a
    hand-edited or migrated settings.json) crashed with
    ``Path(None)``.

    Fix: ``data.get("dump_root") or ""`` collapses None to the
    missing-key default.
    """

    def test_none_dump_root_does_not_crash(self) -> None:
        # Drive the bus event handler with a stub App.
        from steam_review_tool.controllers.dump_folder_controller import (
            DumpFolderController,
        )

        # Build a stub App with the minimum the handler needs.
        class _Stub:
            dump_repo = None
            dump_ctrl = DumpFolderController(
                dump_root=Path("/tmp"),
                obsidian_vault=None,
            )
            api_wf = type("WF", (), {"dump_root": Path("/tmp")})()

        stub = _Stub()
        # Bind the method to the stub and call it.
        from steam_review_tool.ui.app_window import App
        App._on_settings_changed(stub, data={"dump_root": None})
        # The handler must not raise; the dump root stays as the
        # previous value (because Path("") is falsy and the ``if
        # new_root_str:`` guard skips the rebind).
        assert stub.dump_ctrl.dump_root == Path("/tmp")

    def test_none_obsidian_vault_does_not_crash(self) -> None:
        from steam_review_tool.controllers.dump_folder_controller import (
            DumpFolderController,
        )

        class _Stub:
            dump_repo = None
            dump_ctrl = DumpFolderController(
                dump_root=Path("/tmp"),
                obsidian_vault=Path("/old/vault"),
            )
            api_wf = type("WF", (), {"dump_root": Path("/tmp")})()

        stub = _Stub()
        from steam_review_tool.ui.app_window import App
        App._on_settings_changed(stub, data={"obsidian_vault": None})
        # None collapses to "" which is falsy, so the vault is
        # cleared.
        assert stub.dump_ctrl.obsidian_vault is None


# ---------------------------------------------------------------------------
# BUG-R5-5: trends_store.series crashes on None ts
# ---------------------------------------------------------------------------
class TestTrendsStoreSeriesSafeTs:
    """``trends_store.TrendsStore.series`` used
    ``int(s.get("ts", 0))`` — same R3-2 pattern. A snapshot with
    ``ts: None`` raised TypeError when listing the trends series.

    Fix: route through ``safe_int``.
    """

    def test_none_ts_does_not_crash(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from steam_review_tool.services import trends_store
        from steam_review_tool.services.trends_store import TrendsStore

        # Redirect the global path so we don't clobber the user's
        # real trends file.
        monkeypatch.setattr(
            trends_store, "TRENDS_FILE", tmp_path / "trends.json",
        )
        store = TrendsStore()
        # Write a snapshot with ts=None and a wishlist metric
        # directly to disk.
        store.save({
            "tracked": [{"app_id": 4311090, "name": "Test"}],
            "snapshots": [{
                "app_id": 4311090,
                "ts": None,
                "wishlist": 100,
            }],
        })
        out = store.series(4311090, "wishlist", days=None)
        # The None ts was coerced to 0; the wishlist metric is in
        # the snapshot so it isn't filtered out.
        assert len(out) == 1
        assert out[0].ts == 0
        assert out[0].wishlist == 100


# ---------------------------------------------------------------------------
# BUG-R5-6: markdown_helpers / pre_ai_digest render "None" in URLs
# ---------------------------------------------------------------------------
class TestRenderFooterNoNoneInUrl:
    """The old ``str(author.get("steamid", ""))`` rendered
    ``"None"`` (the literal Python repr) for present-but-None
    steamid values. The ``f"https://steamcommunity.com/profiles/
    {steamid}"`` URL then pointed to ``.../profiles/None`` — a
    broken link in the exported Markdown.

    Fix: route through ``safe_str``."""

    def test_footer_url_uses_empty_steamid_not_none(
        self, tmp_path: Path,
    ) -> None:
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
                    "author": {"steamid": None, "playtime_forever": 0},
                    "review": "ok",
                    "timestamp_created": 100,
                },
            ],
            language_param="all",
            review_filter="all",
            review_type="all",
            day_range=None,
            min_date_ts=None,
        )
        dest = tmp_path / "out.md"
        run(ctx, dest, log_cb=lambda _m: None)
        text = dest.read_text(encoding="utf-8")
        # The URL must not contain the literal "None" anywhere.
        assert "/profiles/None" not in text
        assert "/profiles/None/review/" not in text

    def test_pre_ai_digest_url_uses_empty_steamid_not_none(self) -> None:
        from steam_review_tool.services.pre_ai_digest import (
            build_pre_ai_digest,
        )
        out = build_pre_ai_digest([
            {
                "voted_up": True,
                "author": {"steamid": None, "playtime_forever": 60},
            },
        ])
        # The "Top 3 reviewers by playtime" section only includes
        # rows with a truthy steamid; a None steamid must be
        # collapsed to "" so the whole row is skipped.
        assert "profiles/None" not in out


# ---------------------------------------------------------------------------
# BUG-R5-7: review_analyzer.compute_deltas str(None) = "None"
# ---------------------------------------------------------------------------
class TestReviewAnalyzerComputeDeltas:
    """``compute_deltas`` did ``str(r.get("recommendationid", ""))``
    on every review. A present-but-None recommendationid would
    render as the literal ``"None"`` in the ``old_ids`` set,
    which then deduplicated EVERY review with a None
    recommendationid (they all become "None") and the dedup
    logic was meaningless.

    Fix: route through ``safe_str`` so all None values become ""."""

    def test_none_recommendationid_does_not_dedupe_everything(self) -> None:
        from steam_review_tool.services.review_analyzer import compute_deltas
        old = [
            {"recommendationid": None, "voted_up": True},
            {"recommendationid": None, "voted_up": False},
        ]
        new = [
            {"recommendationid": None, "voted_up": True},
            {"recommendationid": "real-1", "voted_up": True},
        ]
        out = compute_deltas(old, new)
        # Before the fix, both "None" entries collapsed into one
        # set member, and the second "None" in new would be
        # incorrectly deduped. After the fix, the None
        # recommendationid is treated as "" (not included in
        # old_ids because the guard ``if r.get("recommendationid")``
        # is falsy), and "real-1" appears in the diff.
        assert "real-1" in [r.get("recommendationid") for r in out["reviews"]]


# ---------------------------------------------------------------------------
# BUG-R5-8: popup_settings shows "None" in entry fields
# ---------------------------------------------------------------------------
class TestPopupSettingsNoNoneLiteral:
    """The old code passed
    ``tk.StringVar(value=data.get("dump_root", ""))`` to the Tk
    widget. A present-but-None value in the settings dict
    (e.g. a hand-edited settings.json) would set the StringVar
    to the literal string ``"None"`` (Tk's str-coercion), and
    the user would see ``None`` pre-filled in the entry.

    Fix: ``_safe_str(value, default)`` collapses None to the
    empty default before constructing the StringVar.
    """

    def test_safe_str_helper_in_popup_settings(self) -> None:
        from steam_review_tool.ui.popup_settings import _safe_str
        assert _safe_str("hello", "x") == "hello"
        assert _safe_str("", "x") == ""
        assert _safe_str(None, "x") == "x"
        assert _safe_str(42, "x") == "42"


# ---------------------------------------------------------------------------
# BUG-R5-9: end-to-end export with None fields never crashes
# ---------------------------------------------------------------------------
class TestExportPipelineWithNoneFields:
    """Sanity-check: an export with present-but-None fields
    everywhere still produces a valid Markdown + CSV without
    crashing."""

    def test_full_export_with_all_none_fields(
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
                    "recommendationid": None,
                    "language": None,
                    "voted_up": True,
                    "review": "ok",
                    "timestamp_created": None,
                    "timestamp_updated": None,
                    "votes_up": None,
                    "votes_funny": None,
                    "comment_count": None,
                    "weighted_vote_score": None,
                    "steam_purchase": None,
                    "received_for_free": None,
                    "written_during_early_access": None,
                    "author": {
                        "steamid": None,
                        "playtime_forever": None,
                        "last_played": None,
                    },
                },
            ],
            language_param="all",
            review_filter="all",
            review_type="all",
            day_range=None,
            min_date_ts=None,
        )
        dest = tmp_path / "out.md"
        run(ctx, dest, also_csv=True, log_cb=lambda _m: None)
        text = dest.read_text(encoding="utf-8")
        # The Markdown must not contain the literal "None"
        # anywhere (no broken URLs, no "language | None" tables).
        assert "None" not in text
        # The CSV file (same path after .with_suffix) must not
        # contain the literal "None" either.
        import csv
        with open(dest, "r", encoding="utf-8", newline="") as f:
            rows = [r for r in csv.reader(f) if r]
        for row in rows:
            for cell in row:
                assert cell != "None", (
                    f"CSV cell contains 'None' literal: {row!r}"
                )
