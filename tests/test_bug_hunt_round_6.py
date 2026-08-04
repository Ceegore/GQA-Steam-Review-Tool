"""Round-6 bug-hunt regression tests.

Real bugs found in a sixth systematic pass over the project. Rounds
1-5 covered the int/str/or-default residue. This round targets
patterns that R1-R5 didn't reach:

1. ``find_latest_dump_md`` returned ANY .md file (including
   per-language splits, the standalone summary, the AI-prompt
   bundle, or a user's own readme.md) — the "Open latest .md"
   action would randomly open the wrong file.
2. ``_on_close`` waited for the API worker but not the Playwright
   worker or the watch-mode thread, so quitting mid-fetch could
   leave partial writes behind.

The watch-mode thread-safety issue (Tk widget access from a
non-main worker thread) is a deeper refactor; deferred to a
separate change.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# BUG-R6-1: find_latest_dump_md filters to canonical export pattern
# ---------------------------------------------------------------------------
class TestFindLatestDumpMdFilters:
    """The old ``find_latest_dump_md`` returned ANY ``.md`` file
    under the dump root. The exporter produces several kinds of
    ``.md`` files (main, per-language ``.english.md``,
    ``.summary.md``, ``ai_prompt.md``), plus the user may have
    their own readme or notes. The "Open latest .md" + "Search"
    + "Copy + AI prompt" actions all use this function, so
    a stray ``ai_prompt.md`` would be returned as "the latest
    dump" after every "Save as prompt" run.

    Fix: filter to the canonical export-name pattern
    ``GQA Reviewdump_*.md`` (no second dot in the stem).
    """

    def test_main_dump_returned(self, tmp_path: Path) -> None:
        from steam_review_tool.controllers.action_handler import (
            find_latest_dump_md,
        )
        f = tmp_path / "GQA Reviewdump_BusSim27_all_20260804-1200.md"
        f.write_text("main")
        assert find_latest_dump_md(tmp_path) == f

    def test_per_language_split_excluded(self, tmp_path: Path) -> None:
        from steam_review_tool.controllers.action_handler import (
            find_latest_dump_md,
        )
        # Per-language files have a second dot ("<name>.<lang>.md").
        per_lang = tmp_path / "GQA Reviewdump_BusSim27_all_20260804-1300.english.md"
        per_lang.write_text("per-lang")
        assert find_latest_dump_md(tmp_path) is None

    def test_summary_md_excluded(self, tmp_path: Path) -> None:
        from steam_review_tool.controllers.action_handler import (
            find_latest_dump_md,
        )
        summary = tmp_path / "GQA Reviewdump_BusSim27_all_20260804-1300.summary.md"
        summary.write_text("summary")
        assert find_latest_dump_md(tmp_path) is None

    def test_ai_prompt_md_excluded(self, tmp_path: Path) -> None:
        from steam_review_tool.controllers.action_handler import (
            find_latest_dump_md,
        )
        # The AI-prompt bundle lives next to the dump and is the
        # LAST file written by the exporter, so without the
        # filter it's almost always returned as "latest dump".
        ai = tmp_path / "ai_prompt.md"
        ai.write_text("ai prompt")
        assert find_latest_dump_md(tmp_path) is None

    def test_user_readme_excluded(self, tmp_path: Path) -> None:
        from steam_review_tool.controllers.action_handler import (
            find_latest_dump_md,
        )
        readme = tmp_path / "README.md"
        readme.write_text("user notes")
        assert find_latest_dump_md(tmp_path) is None

    def test_picks_main_among_many(self, tmp_path: Path) -> None:
        from steam_review_tool.controllers.action_handler import (
            find_latest_dump_md,
        )
        # Mix of main dumps + per-language + summary + ai_prompt
        # + a user readme. Only the main dump should be returned,
        # and the most recent main dump wins.
        older_main = tmp_path / "GQA Reviewdump_Game1_all_20260803-1000.md"
        older_main.write_text("older")
        time.sleep(0.01)
        new_main = tmp_path / "GQA Reviewdump_Game1_all_20260804-1200.md"
        new_main.write_text("newer")
        time.sleep(0.01)
        # These are the "noise" files that should be ignored:
        (tmp_path / "ai_prompt.md").write_text("ai")
        (tmp_path / "GQA Reviewdump_Game1_all_20260804-1300.english.md").write_text("lang")
        (tmp_path / "GQA Reviewdump_Game1_all_20260804-1300.summary.md").write_text("summary")
        (tmp_path / "README.md").write_text("notes")
        assert find_latest_dump_md(tmp_path) == new_main

    def test_recurses_into_subdirs(self, tmp_path: Path) -> None:
        from steam_review_tool.controllers.action_handler import (
            find_latest_dump_md,
        )
        sub = tmp_path / "sub"
        sub.mkdir()
        nested = sub / "GQA Reviewdump_Game_all_20260804-1200.md"
        nested.write_text("nested")
        assert find_latest_dump_md(tmp_path) == nested

    def test_helper_recognises_canonical_name(self) -> None:
        from steam_review_tool.controllers.action_handler import (
            _is_dump_export_md,
        )
        assert _is_dump_export_md("GQA Reviewdump_Game_all_20260804-1200.md")
        assert not _is_dump_export_md("ai_prompt.md")
        assert not _is_dump_export_md("README.md")
        assert not _is_dump_export_md(
            "GQA Reviewdump_Game_all_20260804-1200.english.md",
        )
        assert not _is_dump_export_md(
            "GQA Reviewdump_Game_all_20260804-1200.summary.md",
        )
        assert not _is_dump_export_md(
            "GQA Reviewdump_Game_all_20260804-1200.csv",
        )


# ---------------------------------------------------------------------------
# BUG-R6-2: _on_close waits for pw_wf worker + watch thread
# ---------------------------------------------------------------------------
class TestAppCloseWaitsForWorkers:
    """``_on_close`` called ``self.api_wf.wait(timeout=3.0)`` but
    did NOT call ``self.pw_wf.wait`` — quitting mid-Playwright
    scrape could leave the helper script in a partial-write state
    on the next launch. It also did NOT join the watch-mode
    thread, so a daemon=True watch loop could be killed mid-iteration
    after the window was destroyed (causing the Tk widget access
    in the watch worker to run against a destroyed widget tree).

    Fix: wait for both workflows + join the watch thread.
    """

    def test_on_close_waits_for_pw_worker(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from steam_review_tool.ui import app_window

        captured: dict[str, list[str]] = {"calls": []}

        class _StubApi:
            def stop(self) -> None:
                captured["calls"].append("api.stop")
            def wait(self, timeout: float = 5.0) -> bool:
                captured["calls"].append(f"api.wait({timeout})")
                return True

        class _StubPw:
            def stop(self) -> None:
                captured["calls"].append("pw.stop")
            def wait(self, timeout: float = 5.0) -> bool:
                captured["calls"].append(f"pw.wait({timeout})")
                return True

        class _StubWatchThread:
            def __init__(self) -> None:
                self._alive = True
            def is_alive(self) -> bool:
                return self._alive
            def join(self, timeout: float = 2.0) -> None:
                captured["calls"].append(f"watch.join({timeout})")
                self._alive = False

        class _StubTabApi:
            _watch_thread = _StubWatchThread()

        class _StubSettings:
            def open(self) -> None: pass

        class _StubApp:
            tab_api_ctrl = _StubTabApi()
            settings_ctrl = _StubSettings()
            api_wf = _StubApi()
            pw_wf = _StubPw()
            _bus_subs = []
            def destroy(self) -> None:
                captured["calls"].append("destroy")

        stub = _StubApp()
        app_window.App._on_close(stub)
        # The new code MUST wait for the pw worker and join the
        # watch thread (in addition to the existing api wait).
        assert "api.stop" in captured["calls"]
        assert "api.wait(3.0)" in captured["calls"]
        assert "pw.stop" in captured["calls"]
        assert "pw.wait(3.0)" in captured["calls"], (
            "_on_close did not wait for the Playwright worker"
        )
        assert "watch.join(2.0)" in captured["calls"], (
            "_on_close did not join the watch-mode thread"
        )
        assert "destroy" in captured["calls"]
        # The destroy call must come AFTER the waits (otherwise
        # the workers could write to a destroyed window).
        destroy_idx = captured["calls"].index("destroy")
        pw_wait_idx = captured["calls"].index("pw.wait(3.0)")
        watch_idx = captured["calls"].index("watch.join(2.0)")
        assert destroy_idx > pw_wait_idx
        assert destroy_idx > watch_idx

    def test_on_close_skips_watch_join_when_not_running(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from steam_review_tool.ui import app_window

        captured: dict[str, list[str]] = {"calls": []}

        class _StubApi:
            def stop(self) -> None: pass
            def wait(self, timeout: float = 5.0) -> bool: return True

        class _StubPw:
            def stop(self) -> None: pass
            def wait(self, timeout: float = 5.0) -> bool: return True

        # No watch thread at all (None).
        class _StubTabApi:
            _watch_thread = None

        class _StubSettings:
            def open(self) -> None: pass

        class _StubApp:
            tab_api_ctrl = _StubTabApi()
            settings_ctrl = _StubSettings()
            api_wf = _StubApi()
            pw_wf = _StubPw()
            _bus_subs = []
            def destroy(self) -> None: pass

        app_window.App._on_close(_StubApp())
        # No watch.join call should have happened.
        assert not any("watch.join" in c for c in captured["calls"])

    def test_on_close_skips_watch_join_when_already_dead(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from steam_review_tool.ui import app_window

        captured: dict[str, list[str]] = {"calls": []}

        class _DeadThread:
            def is_alive(self) -> bool: return False
            def join(self, timeout: float = 2.0) -> None:
                captured["calls"].append("watch.join")

        class _StubApi:
            def stop(self) -> None: pass
            def wait(self, timeout: float = 5.0) -> bool: return True

        class _StubPw:
            def stop(self) -> None: pass
            def wait(self, timeout: float = 5.0) -> bool: return True

        class _StubTabApi:
            _watch_thread = _DeadThread()

        class _StubSettings:
            def open(self) -> None: pass

        class _StubApp:
            tab_api_ctrl = _StubTabApi()
            settings_ctrl = _StubSettings()
            api_wf = _StubApi()
            pw_wf = _StubPw()
            _bus_subs = []
            def destroy(self) -> None: pass

        app_window.App._on_close(_StubApp())
        # A dead thread must NOT be joined (it would be a no-op
        # but the call is unnecessary).
        assert not any("watch.join" in c for c in captured["calls"])
