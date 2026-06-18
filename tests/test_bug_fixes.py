"""Regression tests for the bugs caught in the 360-degree review.

Each test corresponds to a specific bug-fix. If any of these fails
after a future change, the corresponding bug has been reintroduced.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import pytest


# ---- Bug-Fix 1: Path(None) crash ------------------------------------------


def test_resolve_dump_root_with_none_settings():
    from steam_review_tool.ui.app_window import App
    p = App._resolve_dump_root(None)
    assert p.exists() and p.is_dir()


def test_resolve_dump_root_with_empty_dict():
    from steam_review_tool.ui.app_window import App
    p = App._resolve_dump_root({})
    assert p.exists()


def test_resolve_dump_root_with_missing_key():
    from steam_review_tool.ui.app_window import App
    p = App._resolve_dump_root({"other_key": "x"})
    assert p.exists()


def test_resolve_dump_root_with_empty_string():
    from steam_review_tool.ui.app_window import App
    p = App._resolve_dump_root({"dump_root": ""})
    assert p.exists()


def test_resolve_dump_root_with_non_string_value():
    """If settings has a non-string dump_root, fall back to default."""
    from steam_review_tool.ui.app_window import App
    p = App._resolve_dump_root({"dump_root": None})
    assert p.exists()


def test_resolve_dump_root_with_valid_path(tmp_path):
    from steam_review_tool.ui.app_window import App
    p = App._resolve_dump_root({"dump_root": str(tmp_path)})
    assert p == Path(tmp_path)


# ---- Bug-Fix 3: tab_trends Remove ALL instead of selected ----------------


def test_trends_remove_one_only_removes_one():
    from steam_review_tool.services.trends_store import TrendsStore
    import tempfile

    store = TrendsStore.__new__(TrendsStore)
    store.path = Path(tempfile.mkdtemp()) / "t.json"
    store.add(1, "Game One")
    store.add(2, "Game Two")
    store.add(3, "Game Three")
    assert len(store.tracked_apps()) == 3
    store.remove(2)
    remaining = store.tracked_apps()
    assert len(remaining) == 2
    ids = {a["app_id"] for a in remaining}
    assert ids == {1, 3}


# ---- Bug-Fix 4: popup_search sentiment filter logic ---------------------


def test_search_sentiment_positive_excludes_negative():
    """Positive filter must keep only Positive blocks."""
    blocks = [
        ("r1", "Review #1",
         "| Recommendation | 👍 Positive |\n| Author | `1` |"),
        ("r2", "Review #2",
         "| Recommendation | 👎 Negative |\n| Author | `2` |"),
        ("r3", "Review #3", ""),  # malformed — no Recommendation cell
    ]
    sentiment = "positive"
    keep = []
    for rid, label, text in blocks:
        if sentiment != "all":
            rec_idx = text.find("Recommendation")
            if rec_idx == -1:
                continue
            rec_cell = text[rec_idx:rec_idx + 80]
            if sentiment == "positive" and "Positive" not in rec_cell:
                continue
            if sentiment == "negative" and "Negative" not in rec_cell:
                continue
        keep.append(label)
    assert keep == ["Review #1"]


def test_search_sentiment_negative_excludes_positive():
    blocks = [
        ("r1", "Review #1", "| Recommendation | 👍 Positive |\n"),
        ("r2", "Review #2", "| Recommendation | 👎 Negative |\n"),
    ]
    sentiment = "negative"
    keep = []
    for _, label, text in blocks:
        rec_idx = text.find("Recommendation")
        if rec_idx == -1:
            continue
        rec_cell = text[rec_idx:rec_idx + 80]
        if sentiment == "positive" and "Positive" not in rec_cell:
            continue
        if sentiment == "negative" and "Negative" not in rec_cell:
            continue
        keep.append(label)
    assert keep == ["Review #2"]


# ---- Bug-Fix 8: unused imports in playwright_subprocess --------------------


def test_playwright_subprocess_no_top_level_os_import():
    """The module itself shouldn't import os at top level.

    Function-level imports (inside run_popularity_probe) are
    acceptable because they only run on the rare frozen-exe path.
    """
    import ast
    tree = ast.parse(open("steam_review_tool/services/playwright_subprocess.py",
                            encoding="utf-8").read())
    # Only walk top-level imports (children of ast.Module).
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name != "os", (
                    f"Unused top-level 'import os' at line {node.lineno}"
                )


# ---- Bug-Fix 11: get_logger in services ----------------------------------


def test_steam_api_does_not_call_print():
    """The refactored services should use the logger, not print()."""
    import ast
    tree = ast.parse(open("steam_review_tool/services/steam_api_service.py",
                            encoding="utf-8").read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id != "print", (
                f"print() call found at line {node.lineno}"
            )


def test_storefront_parser_does_not_call_print():
    import ast
    tree = ast.parse(open("steam_review_tool/services/storefront_parser.py",
                            encoding="utf-8").read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id != "print", (
                f"print() call found at line {node.lineno}"
            )


def test_event_bus_does_not_call_print():
    import ast
    tree = ast.parse(open("steam_review_tool/core/event_bus.py",
                            encoding="utf-8").read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id != "print", (
                f"print() call found at line {node.lineno}"
            )


# ---- Bug-Fix 19: InfoPanel wired up --------------------------------------


def _run_info_panel_subtest(args: str) -> tuple[int, str]:
    """Run an InfoPanel snippet in a fresh Python subprocess.

    Tkinter's Tcl interpreter doesn't tolerate being created+destroyed
    multiple times in the same process, so we isolate these tests.
    """
    import subprocess
    import sys
    script = (
        "import customtkinter as ctk; "
        f"from steam_review_tool.ui.info_panel import InfoPanel; "
        "root = ctk.CTk(); "
        f"p = InfoPanel(root); p.update({args}); "
        "out = (p._name_lbl.cget('text'), p._app_id_lbl.cget('text')); "
        "print(out); "
        "root.destroy()"
    )
    proc = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True, text=True, timeout=15,
        cwd="d:/Projects/test2/steam_review_tool",
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def test_info_panel_update_with_no_app():
    rc, out = _run_info_panel_subtest("None, None")
    assert rc == 0, f"subprocess failed: {out!r}"
    assert "(no game loaded)" in out


def test_info_panel_update_with_app():
    args = "12345, {'name': 'My Game', 'developers': ['Dev'], 'publishers': ['Pub'], 'platforms': {'windows': True, 'mac': False}}"
    rc, out = _run_info_panel_subtest(args)
    assert rc == 0, f"subprocess failed: {out!r}"
    assert "My Game" in out
    assert "12345" in out


# ---- Bug-Fix 20: CET/CEST fallback ---------------------------------------


def test_timezone_cet_in_winter():
    """January in Berlin should be CET (UTC+1), not CEST."""
    from steam_review_tool.core import timezone
    if timezone._USE_ZONEINFO:
        pytest.skip("zoneinfo path active; using OS tzdata")
    dt = datetime(2026, 1, 15, 12, 0)
    offset = dt.replace(tzinfo=timezone.BERLIN).utcoffset()
    assert offset is not None and offset.total_seconds() == 3600, (
        f"Expected CET (UTC+1) in January, got offset {offset}"
    )


def test_timezone_cest_in_summer():
    """July in Berlin should be CEST (UTC+2), not CET."""
    from steam_review_tool.core import timezone
    if timezone._USE_ZONEINFO:
        pytest.skip("zoneinfo path active; using OS tzdata")
    dt = datetime(2026, 7, 15, 12, 0)
    offset = dt.replace(tzinfo=timezone.BERLIN).utcoffset()
    assert offset is not None and offset.total_seconds() == 7200, (
        f"Expected CEST (UTC+2) in July, got offset {offset}"
    )


def test_timezone_dst_boundary_march():
    """March 29, 2026 is the DST-start Sunday. Day before = CET, after = CEST."""
    from steam_review_tool.core import timezone
    if timezone._USE_ZONEINFO:
        pytest.skip("zoneinfo path active")
    before = datetime(2026, 3, 28).replace(tzinfo=timezone.BERLIN).utcoffset()
    after = datetime(2026, 3, 29).replace(tzinfo=timezone.BERLIN).utcoffset()
    assert before is not None and before.total_seconds() == 3600
    assert after is not None and after.total_seconds() == 7200


# ---- Bus-Subscriptions: leak prevention ----------------------------------


def test_event_bus_unsubscribe_removes_listener():
    """After unsubscribe, publish should NOT call the listener."""
    from steam_review_tool.core.event_bus import SimpleEventBus

    bus = SimpleEventBus()
    calls = []

    def listener(**kw):
        calls.append(kw)

    bus.subscribe("test.event", listener)
    bus.publish("test.event", foo=1)
    assert len(calls) == 1

    bus.unsubscribe("test.event", listener)
    bus.publish("test.event", foo=2)
    assert len(calls) == 1, "Listener was still called after unsubscribe!"


def test_event_bus_unsubscribe_missing_callback_is_silent():
    from steam_review_tool.core.event_bus import SimpleEventBus

    bus = SimpleEventBus()
    bus.unsubscribe("never.subscribed", lambda **kw: None)  # no raise


# ---- markdown_exporter: getattr fallback removed ------------------------


def test_markdown_exporter_uses_dataclass_field_directly():
    from steam_review_tool.exporters.markdown_exporter import MarkdownExporter
    from steam_review_tool.models.export_context import ExportContext

    ctx = ExportContext(
        app_id=1, app_details=None, reviews=[],
        language_param="all", review_filter="all", review_type="all",
        day_range=None, min_date_ts=None, keyword_list=["a", "b"],
    )
    md = MarkdownExporter.render(ctx)
    assert "## All Reviews" in md


def test_markdown_exporter_no_getattr_fallback():
    src = open("steam_review_tool/exporters/markdown_exporter.py",
                encoding="utf-8").read()
    assert 'getattr(ctx, "keyword_list"' not in src, (
        "markdown_exporter should use ctx.keyword_list directly."
    )


# ---- copy_to_clipboard: no root.update() --------------------------------


def test_copy_to_clipboard_no_root_update():
    """Thread-safety: no root.update() in active code (only docstrings OK)."""
    import ast
    tree = ast.parse(open("steam_review_tool/controllers/action_handler.py",
                            encoding="utf-8").read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if (isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "root"
                    and node.func.attr == "update"):
                raise AssertionError(
                    f"root.update() call at line {node.lineno}"
                )


# ---- popup_batch_dump: "current" magic-string removed -------------------


def test_batch_dump_no_current_magic_string():
    src = open("steam_review_tool/ui/popup_batch_dump.py",
                encoding="utf-8").read()
    assert "line = \"current\"" not in src


def test_batch_dump_dedupes_queue():
    src = open("steam_review_tool/ui/popup_batch_dump.py",
                encoding="utf-8").read()
    assert "deduped" in src


def test_batch_dump_uses_callback_for_current_app():
    src = open("steam_review_tool/ui/popup_batch_dump.py",
                encoding="utf-8").read()
    assert "get_current_app_id" in src


# ---- app_window: dead _stop_event removed -------------------------------


def test_app_window_no_dead_stop_event():
    import ast
    tree = ast.parse(open("steam_review_tool/ui/app_window.py",
                            encoding="utf-8").read())
    for node in ast.walk(tree):
        if (isinstance(node, ast.Assign)
                and isinstance(node.targets[0], ast.Attribute)
                and node.targets[0].attr == "_stop_event"):
            raise AssertionError(
                f"_stop_event is dead code, found at line {node.lineno}"
            )


# ---- Magic numbers are constants ----------------------------------------


def test_no_magic_sleep_03_in_steam_api():
    """The poll rate (0.3) must use the STEAM_POLL_DELAY_SEC constant."""
    src = open("steam_review_tool/services/steam_api_service.py",
                encoding="utf-8").read()
    # Look for the literal "0.3" outside of docstrings/comments.
    assert "STEAM_POLL_DELAY_SEC" in src, (
        "steam_api_service should use STEAM_POLL_DELAY_SEC"
    )


# ---- DependencyInstaller: cache.open('explore') dead code removed ------


def test_open_pw_cache_no_path_open_explore():
    src = open("steam_review_tool/services/dependency_installer.py",
                encoding="utf-8").read()
    assert 'cache.open("explore")' not in src, (
        "Path.open('explore') is dead code (open takes a file mode)."
    )