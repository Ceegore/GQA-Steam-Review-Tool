"""Round-8 bug-hunt regression tests.

Real bugs found in an eighth systematic pass. Rounds 1-7
(9388ab1, 9ea69de, ed231bc, 80f9431, f913ae8, e0514c0,
0e4f031) covered the int / str / or-default residue, the
double-subscribe pattern, the over-broad "find latest .md"
walk, and the missing worker-shutdown wait on app close.

This round targets the **broken batch-dump feature** and
**missed R5 str(r.get) sites**:

1. The batch-dump dialog iterated over queued app IDs and
   published ``batch.run_item`` to the bus, but no one
   subscribed — the entire feature was non-functional.
2. ``per_language_exporter.build_summary`` had the same R5
   ``str(r.get("KEY", "—"))`` pattern (None rendered as
   the literal "None" in the per-game summary URL).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# BUG-R8-1: per_language_exporter.build_summary missed R5 fix
# ---------------------------------------------------------------------------
class TestPerLanguageExporterBuildSummaryNoneSafe:
    """The R5 fix consolidated the ``str(r.get("KEY", ""))``
    pattern (which renders ``None`` as the literal ``"None"``)
    via ``utils.coercion.safe_str``. It covered the main
    ``render_summary`` + ``render_footer`` in
    markdown_helpers.py and the export_orchestrator /
    csv_exporter paths, but missed the standalone
    ``per_language_exporter.build_summary`` — which builds
    the per-game ``.summary.md`` file. A present-but-None
    ``steamid`` or ``recommendationid`` was rendered as
    the literal ``"None"`` in the per-reviewer row URL
    (``https://steamcommunity.com/profiles/None/review/None``)."""

    def test_none_steamid_does_not_render_none_in_url(self) -> None:
        from steam_review_tool.exporters.per_language_exporter import (
            build_summary,
        )
        reviews = [
            {
                "voted_up": True,
                "author": {"steamid": None, "playtime_forever": 60},
                "recommendationid": "rec-1",
            },
        ]
        out = build_summary(reviews)
        assert "/profiles/None" not in out
        assert "/review/None" not in out

    def test_none_recommendationid_does_not_render_none_in_url(
        self,
    ) -> None:
        from steam_review_tool.exporters.per_language_exporter import (
            build_summary,
        )
        reviews = [
            {
                "voted_up": True,
                "author": {"steamid": "12345", "playtime_forever": 60},
                "recommendationid": None,
            },
        ]
        out = build_summary(reviews)
        assert "/review/None" not in out

    def test_both_none_does_not_render_none_in_url(self) -> None:
        from steam_review_tool.exporters.per_language_exporter import (
            build_summary,
        )
        reviews = [
            {
                "voted_up": True,
                "author": {"steamid": None, "playtime_forever": 60},
                "recommendationid": None,
            },
        ]
        out = build_summary(reviews)
        assert "None" not in out

    def test_real_steamid_renders_correct_url(self) -> None:
        from steam_review_tool.exporters.per_language_exporter import (
            build_summary,
        )
        reviews = [
            {
                "voted_up": True,
                "author": {"steamid": "76561198000000001", "playtime_forever": 120},
                "recommendationid": "rec-1",
            },
        ]
        out = build_summary(reviews)
        # The URL should contain the real steamid, not the literal
        # "None" or any other placeholder.
        assert "76561198000000001" in out
        assert "profiles/None" not in out
        assert "review/None" not in out


# ---------------------------------------------------------------------------
# BUG-R8-2: batch-dump dialog wired to an unsubscribed bus event
# ---------------------------------------------------------------------------
class TestBatchDumpFeature:
    """The batch-dump dialog iterated over queued app IDs
    and called ``on_run_item(app_id)`` for each, but the
    caller's ``on_run_item`` published ``batch.run_item`` to
    the bus and NO ONE SUBSCRIBED. The entire batch feature
    was non-functional — the user queued 10 app IDs, clicked
    Start, and the worker iterated but no fetch was triggered.

    Fix: ``TabActions.__init__`` now takes a ``fetch_item``
    callable. The API tab passes
    ``fetch_item=self._fetch_item`` (which calls
    ``self.api_wf.start_fetch + bus.subscribe_once(FETCH_COMPLETED,
    auto_export)``); the Playwright tab passes
    ``fetch_item=self._fetch_item`` (same pattern with
    ``pw_wf.scrape``). The batch dialog now actually does
    work.
    """

    def test_tab_actions_takes_fetch_item_param(self) -> None:
        from steam_review_tool.ui._tab_actions import TabActions
        import inspect
        sig = inspect.signature(TabActions.__init__)
        assert "fetch_item" in sig.parameters

    def test_tab_actions_batch_dump_uses_fetch_item(self) -> None:
        """Static check: the batch_dump method must use
        self._fetch_item, not the old bus.publish pattern."""
        from pathlib import Path
        from steam_review_tool.controllers.dump_folder_controller import (
            DumpFolderController,
        )
        from steam_review_tool.ui._tab_actions import TabActions
        # Build a TabActions directly (without the bus
        # publishing path) to test the method body in isolation.
        captured: list[int] = []

        def fetch_item(app_id: int) -> None:
            captured.append(app_id)

        actions = TabActions(
            master=type("Stub", (), {"app_id": None})(),
            dump_ctrl=DumpFolderController(dump_root=Path("/tmp")),
            log_fn=lambda _m: None,
            fetch_item=fetch_item,
        )
        # Patch BatchDumpDialog to a stub that records the
        # callbacks and immediately invokes on_run_item for
        # each id.
        from steam_review_tool.ui import _tab_actions

        class _StubDialog:
            def __init__(self, master: Any) -> None:
                self._on_run_item = None
                self._get_current = None
            def open(self, on_run_item: Any, get_current_app_id: Any) -> None:
                self._on_run_item = on_run_item
                self._get_current = get_current_app_id
                # Simulate the dialog iterating over two IDs.
                on_run_item(100)
                on_run_item(200)
                on_run_item(300)

        original = _tab_actions.BatchDumpDialog
        _tab_actions.BatchDumpDialog = _StubDialog
        try:
            actions.batch_dump()
        finally:
            _tab_actions.BatchDumpDialog = original
        # The fetch_item callable was called once per queued ID.
        assert captured == [100, 200, 300]

    def test_batch_run_item_event_has_no_subscribers(self) -> None:
        """Sanity check: the old bus event "batch.run_item" is
        no longer relied on. The only way a fetch happens is
        via the TabActions._fetch_item callback."""
        from steam_review_tool.core import event_bus
        listeners = event_bus.bus._listeners.get("batch.run_item", [])
        assert len(listeners) == 0, (
            "batch.run_item still has subscribers — the broken "
            "bus-publish path is still wired up somewhere"
        )

    def test_tab_api_wires_fetch_item(self) -> None:
        """Static check: ApiTabController._build passes
        ``fetch_item=self._fetch_item`` to TabActions."""
        from steam_review_tool.ui import tab_api
        src = Path(tab_api.__file__).read_text(encoding="utf-8")
        code_lines = [
            ln for ln in src.splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")
        ]
        code = "\n".join(code_lines)
        assert "fetch_item=self._fetch_item" in code, (
            "ApiTabController must pass fetch_item to TabActions"
        )

    def test_tab_playwright_wires_fetch_item(self) -> None:
        """Static check: PlaywrightTabController._build passes
        ``fetch_item=self._fetch_item`` to TabActions."""
        from steam_review_tool.ui import tab_playwright
        src = Path(tab_playwright.__file__).read_text(encoding="utf-8")
        code_lines = [
            ln for ln in src.splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")
        ]
        code = "\n".join(code_lines)
        assert "fetch_item=self._fetch_item" in code, (
            "PlaywrightTabController must pass fetch_item to "
            "TabActions"
        )

    def test_old_bus_publish_path_removed(self) -> None:
        """Static check: the broken ``bus.publish("batch.run_item")``
        pattern is gone from _tab_actions.py."""
        from steam_review_tool.ui import _tab_actions
        src = Path(_tab_actions.__file__).read_text(encoding="utf-8")
        code_lines = [
            ln for ln in src.splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")
        ]
        code = "\n".join(code_lines)
        assert "batch.run_item" not in code
        assert "bus.publish" not in code
        # The bus import should also be gone.
        assert "from ..core.event_bus" not in code


# ---------------------------------------------------------------------------
# BUG-R8-3: import error on missing safe_str (defensive test)
# ---------------------------------------------------------------------------
class TestPerLanguageExporterImportSafety:
    """Regression: the R8 fix added ``safe_str`` to
    ``per_language_exporter.build_summary``. If the import
    was ever removed, the function would NameError on the
    first None-valued row. This test guards against
    import-error regressions."""

    def test_safe_str_is_imported(self) -> None:
        from steam_review_tool.exporters import per_language_exporter
        assert hasattr(per_language_exporter, "safe_str")
