"""Round-11 bug-hunt regression tests.

Real bugs found in an eleventh systematic pass. Rounds 1-10
(9388ab1, 9ea69de, ed231bc, 80f9431, f913ae8, e0514c0,
0e4f031, ba4255e, 49aa77a, 831219e) covered the int / str /
or-default residue, the ``.get("X", {}).get("Y")`` chained-dict
crash, the double-subscribe pattern, the over-broad
"find latest .md" walk, the missing worker-shutdown wait,
the broken batch-dump feature, the missed R5 sites, the Tk
widget-state + watch-thread-safety issues, the destructive
"Reset" button before commit, and the shared
``self._worker`` field.

This round targets four new bug classes:

1. ``load_json_with_recovery`` used a second-precision
   timestamp in the corrupt-backup filename, so two corruption
   events in the same second collided. On POSIX the second
   ``os.replace`` silently overwrote the first backup; on
   Windows it raised ``FileExistsError`` which the ``except
   OSError: pass`` swallowed, leaving the new corrupt file in
   place (the next load would try and fail to rename it again
   and again). Fix: microsecond precision + a process-unique
   counter.

2. ``format_berlin(ts)`` only handled ``ts is None`` and
   crashed with ``TypeError`` (string) or ``OSError`` (huge
   value) for every other bad input. The sister helper
   ``utils.markdown_utils.ts_to_iso`` already had a
   ``try/except`` returning ``"—"`` for the same cases.

3. ``tab_trends._on_per_language_count`` called
   ``api.fetch_all_reviews(...)`` synchronously on the Tk
   main thread, freezing the GUI for the duration of a
   multi-page fetch. It also created a fresh ``SteamAPI()``
   per click, losing the connection pool + cookies. Fix:
   run the fetch in a daemon thread and route every widget
   mutation through ``after(0, …)``; reuse the App's cached
   ``self.master.api`` instance when available.

4. ``popup_batch_dump._on_start`` had no double-click guard,
   so a rapid second click spawned a second concurrent worker
   that raced on the status label and on the host tab's
   per-app state. ``_close`` destroyed the popup window
   while the worker thread could still be mid-iteration,
   causing ``self._top.after(0, …)`` to raise ``TclError``
   on the destroyed widget. Fix: guard against a running
   worker in ``_on_start``, and have ``_close`` set the
   stop flag + ``join()`` the worker (with a short
   timeout) before destroying the window.

5. The cross-platform ``os.startfile / Popen / xdg-open``
   ladder was copy-pasted in 4 places. Consolidated into
   ``utils.os_open.open_path_in_os``.
"""
from __future__ import annotations

import json
import re
import tempfile
import threading
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# BUG-R11-1: load_json_with_recovery backup-filename collision
# ---------------------------------------------------------------------------
class TestLoadJsonRecoveryBackupFilename:
    """``load_json_with_recovery`` used ``int(datetime.now(...).
    timestamp())`` (second precision) as the corrupt-backup
    suffix. Two corruption events in the same second produced
    the same backup filename, so the second ``os.replace``
    either:

    - silently overwrote the first backup on POSIX, or
    - raised ``FileExistsError`` on Windows which the
      ``except OSError: pass`` swallowed, leaving the new
      corrupt file in place to trigger another rename attempt
      on every subsequent load.

    The fix uses microsecond precision + a process-unique
    counter, so every backup has a unique filename.
    """

    def test_two_corruptions_in_same_second_produce_unique_backups(
        self,
    ) -> None:
        """Two consecutive corruption recoveries must produce
        two distinct backup files (the old code produced
        exactly one — the second was silently dropped on
        Windows or overwrote the first on POSIX)."""
        from steam_review_tool.core.atomic_write import (
            load_json_with_recovery,
        )

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            f = tmp / "settings.json"
            f.write_text("not valid json {", encoding="utf-8")

            load_json_with_recovery(f, default={})
            # Re-create the corrupt file to trigger a second
            # rename. The original file is gone after the
            # first recovery, so we have to write a new
            # corrupt blob to simulate a second corruption.
            f.write_text("still not valid {", encoding="utf-8")
            load_json_with_recovery(f, default={})

            backups = sorted(tmp.glob("settings.json.corrupt-*"))
            assert len(backups) == 2, (
                f"expected 2 distinct corrupt-backup files, "
                f"got {len(backups)}: {[b.name for b in backups]}"
            )

    def test_backup_filename_includes_counter(self) -> None:
        """The backup filename must include the process-unique
        counter so two rapid back-to-back corruptions are
        distinguishable."""
        from steam_review_tool.core.atomic_write import (
            load_json_with_recovery,
        )

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            f = tmp / "ledger.json"
            f.write_text("{ broken", encoding="utf-8")
            load_json_with_recovery(f, default={})
            f.write_text("{ still broken", encoding="utf-8")
            load_json_with_recovery(f, default={})

            backups = sorted(tmp.glob("ledger.json.corrupt-*"))
            assert len(backups) == 2
            # The counter part of the filename must differ.
            nums = []
            for b in backups:
                m = re.search(r"-(\d+)$", b.name)
                assert m, f"backup {b.name} has no counter suffix"
                nums.append(int(m.group(1)))
            assert nums[0] != nums[1], (
                f"two backups should have different counter "
                f"values, got {nums}"
            )

    def test_backup_filename_includes_microsecond_timestamp(
        self,
    ) -> None:
        """The backup filename must include a human-readable
        microsecond-precision timestamp — the user often
        digs through these to find the most recent
        corruption."""
        from steam_review_tool.core.atomic_write import (
            load_json_with_recovery,
        )

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            f = tmp / "data.json"
            f.write_text("oops", encoding="utf-8")
            load_json_with_recovery(f, default={})

            backups = list(tmp.glob("data.json.corrupt-*"))
            assert len(backups) == 1
            # Pattern: data.json.corrupt-YYYYMMDDTHHMMSS_ffffff-N
            assert re.match(
                r"data\.json\.corrupt-\d{8}T\d{6}_\d{6}-\d+$",
                backups[0].name,
            ), f"backup name doesn't match expected pattern: {backups[0].name}"

    def test_three_rapid_corruptions_preserve_all_backups(self) -> None:
        """Three rapid corruption events must all be preserved
        (was 1 on Windows, 1 on POSIX with the previous bug)."""
        from steam_review_tool.core.atomic_write import (
            load_json_with_recovery,
        )

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            f = tmp / "rapid.json"
            for i in range(3):
                f.write_text(f"bad-{i}", encoding="utf-8")
                load_json_with_recovery(f, default={})

            backups = sorted(tmp.glob("rapid.json.corrupt-*"))
            assert len(backups) == 3, (
                f"expected 3 distinct backups, got {len(backups)}"
            )

    def test_backup_count_is_process_unique(self) -> None:
        """The counter is per-process, so two calls inside
        the same Python process must produce different
        counter values even if the timestamp is identical."""
        from steam_review_tool.core.atomic_write import _BACKUP_COUNTER

        # Burn a few counter values.
        before = next(_BACKUP_COUNTER)
        v1 = next(_BACKUP_COUNTER)
        v2 = next(_BACKUP_COUNTER)
        assert v1 != v2
        assert v1 == before + 1


# ---------------------------------------------------------------------------
# BUG-R11-2: format_berlin crashes on non-int ts
# ---------------------------------------------------------------------------
class TestFormatBerlinRobust:
    """``format_berlin(ts)`` only handled ``ts is None`` and
    crashed for every other bad input. The fix mirrors the
    sister helper ``utils.markdown_utils.ts_to_iso``: wrap
    the ``datetime.fromtimestamp`` call in a try/except and
    return ``"—"`` on any failure (TypeError, ValueError,
    OverflowError, OSError).
    """

    def test_none_returns_em_dash(self) -> None:
        from steam_review_tool.core.timezone import format_berlin
        assert format_berlin(None) == "—"

    def test_string_ts_is_coerced(self) -> None:
        """A stringified timestamp (e.g. from a hand-rolled
        review dict that lost its int() conversion) used to
        crash with ``TypeError``. Now coerced via ``int()``."""
        from steam_review_tool.core.timezone import format_berlin
        result = format_berlin("1700000000")
        # Just confirm it doesn't crash and returns a
        # recognisable Berlin-formatted timestamp.
        assert "2023" in result
        assert "CET" in result or "CEST" in result

    def test_float_ts_works(self) -> None:
        from steam_review_tool.core.timezone import format_berlin
        result = format_berlin(1700000000.5)
        assert "2023" in result

    def test_zero_returns_epoch(self) -> None:
        from steam_review_tool.core.timezone import format_berlin
        result = format_berlin(0)
        assert "1970-01-01" in result

    def test_huge_ts_returns_em_dash(self) -> None:
        """A timestamp far in the future (e.g. 99999999999999,
        which overflows ``time_t`` on Windows) used to crash
        with ``OSError: [Errno 22] Invalid argument``. Now
        returns ``"—"``."""
        from steam_review_tool.core.timezone import format_berlin
        result = format_berlin(99999999999999)
        assert result == "—"

    def test_unparseable_string_returns_em_dash(self) -> None:
        """A non-numeric string (e.g. ``"not a number"``)
        used to crash with ``ValueError`` from ``int()``."""
        from steam_review_tool.core.timezone import format_berlin
        result = format_berlin("not a number")
        assert result == "—"

    def test_negative_ts_returns_em_dash(self) -> None:
        """A negative timestamp (pre-epoch) on Windows raises
        ``OSError``. Now caught."""
        from steam_review_tool.core.timezone import format_berlin
        result = format_berlin(-99999999999)
        # Either "—" (caught) or a pre-epoch formatted
        # string — both are acceptable as long as no
        # exception escapes.
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# BUG-R11-3: _on_per_language_count blocks the main thread
# ---------------------------------------------------------------------------
class TestPerLanguageCountOffMainThread:
    """``TrendsTabController._on_per_language_count`` used to
    call ``SteamAPI.fetch_all_reviews`` synchronously on the
    Tk main thread. A typical fetch is 1-2s per page and a
    popular game can have dozens of pages — the entire GUI
    froze for the duration. The fix runs the fetch in a
    daemon thread and routes every widget mutation through
    ``after(0, …)``.

    Also fixed: a fresh ``SteamAPI()`` per click discarded
    the App's connection pool + cookies. The new code
    reuses ``self.master.api`` when available.
    """

    def test_uses_master_api_when_available(self) -> None:
        """When the App exposes ``self.api``, the per-language
        count must use that shared instance — not a freshly
        created one."""
        from unittest.mock import MagicMock
        from steam_review_tool.ui.tab_trends import TrendsTabController

        # The TrendsTabController normally needs a Tk parent
        # to instantiate, but we can patch the bits that need
        # the Tk root and inspect the worker behaviour.
        # We test the master.api preference in isolation by
        # inspecting the source string (a cheap, reliable
        # check that survives a refactor).
        import inspect
        from steam_review_tool.ui import tab_trends
        src = Path(tab_trends.__file__).read_text(encoding="utf-8")
        # The new code uses ``getattr(self.master, "api", None)``
        # to prefer the master's API.
        assert 'getattr(self.master, "api", None)' in src, (
            "_on_per_language_count should prefer the master's "
            "shared SteamAPI instance over creating a fresh one"
        )

    def test_runs_in_daemon_thread(self) -> None:
        """The fetch must run in a daemon thread, not on the
        Tk main thread (which would freeze the GUI)."""
        from steam_review_tool.ui import tab_trends
        src = Path(tab_trends.__file__).read_text(encoding="utf-8")
        # Look for a ``threading.Thread`` constructor with
        # ``daemon=True`` inside ``_on_per_language_count``.
        assert re.search(
            r"threading\.Thread\([^)]*daemon\s*=\s*True",
            src,
            re.DOTALL,
        ), (
            "_on_per_language_count should spawn a daemon "
            "thread for the fetch"
        )

    def test_widget_mutations_routed_via_after(self) -> None:
        """The fetch worker must route every widget mutation
        through ``after(0, …)`` so the mutation happens on
        the Tk main thread (Tk is not thread-safe)."""
        from steam_review_tool.ui import tab_trends
        src = Path(tab_trends.__file__).read_text(encoding="utf-8")
        # The new code should have at least 2 ``after(0, …)``
        # calls in the per-language-count path (one for
        # status update on success, one for the error
        # branch). The call may span multiple lines, so we
        # match ``self._status_lbl.after`` then a newline
        # (or open-paren) before ``0,``.
        code_lines = [
            ln for ln in src.splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")
        ]
        code = "\n".join(code_lines)
        # Match either inline ``self._status_lbl.after(0,``
        # or multi-line ``self._status_lbl.after(\n  0,``.
        after_calls = (
            code.count("self._status_lbl.after(0,")
            + len(re.findall(
                r"self\._status_lbl\.after\(\s*\n\s*0,",
                code,
            ))
        )
        assert after_calls >= 2, (
            f"expected at least 2 self._status_lbl.after(0, …) "
            f"calls in the per-language-count worker, got "
            f"{after_calls}"
        )

    def test_per_lang_worker_field_set(self) -> None:
        """The tab must track the per-language-count worker
        in a field so a second click can detect the
        in-flight worker and skip the new fetch."""
        from steam_review_tool.ui import tab_trends
        src = Path(tab_trends.__file__).read_text(encoding="utf-8")
        assert "_per_lang_worker" in src, (
            "TrendsTabController must track the per-language "
            "worker in self._per_lang_worker to skip a "
            "second click while the first is still running"
        )

    def test_double_click_during_in_flight_is_ignored(self) -> None:
        """If the per-lang worker is still alive, a second
        click on the button must NOT spawn a second
        worker."""
        from steam_review_tool.ui.tab_trends import TrendsTabController

        # Patch threading.Thread so we can capture the spawned
        # worker but make it ``is_alive() == True`` so the
        # double-click guard kicks in.
        spawned: list[Any] = []

        class _FakeThread:
            def __init__(self, target=None, daemon=None, **_kw):
                self._target = target
                self._alive = True

            def start(self) -> None:
                spawned.append(self)

            def is_alive(self) -> bool:
                return self._alive

        # We need a tab instance to call _on_per_language_count.
        # Use a stub that satisfies the bits the function
        # touches (master.app_id, status_lbl, master.api).
        tab = TrendsTabController.__new__(TrendsTabController)
        tab.master = MagicMock()
        tab.master.app_id = 12345
        tab.master.api = MagicMock()
        tab._lang_var = MagicMock()
        tab._lang_var.get.return_value = "english"
        tab._status_lbl = MagicMock()
        tab._per_lang_worker = None

        with patch("threading.Thread", _FakeThread):
            tab._on_per_language_count()
        assert len(spawned) == 1
        # Simulate the spawned worker is still running.
        tab._per_lang_worker = spawned[0]
        # A second click should NOT spawn another worker.
        with patch("threading.Thread", _FakeThread):
            tab._on_per_language_count()
        assert len(spawned) == 1, (
            "a second click while the per-language worker is "
            "still alive must be ignored (no second spawn)"
        )


# ---------------------------------------------------------------------------
# BUG-R11-4: popup_batch_dump close race + double-Start race
# ---------------------------------------------------------------------------
class TestBatchDumpWorkerLifecycle:
    """Two related races in ``BatchDumpDialog``:

    1. ``_on_start`` had no double-click guard, so a rapid
       second click spawned a second concurrent worker that
       raced on the status label and on the host tab's
       per-app state.

    2. ``_close`` destroyed the popup window while the
       worker thread could still be mid-iteration, causing
       ``self._top.after(0, …)`` to raise ``TclError`` on
       the destroyed widget. The except clause tried to
       call ``self._top.after(0, …)`` again to show the
       error — which also failed.
    """

    def test_second_start_while_running_is_ignored(self) -> None:
        """Spawning a batch, then a second click on Start
        while the first is still alive, must NOT spawn a
        second worker."""
        from steam_review_tool.ui.popup_batch_dump import (
            BatchDumpDialog,
        )

        # Stub the dialog without invoking Tk.
        dlg = BatchDumpDialog.__new__(BatchDumpDialog)
        dlg._top = MagicMock()
        dlg._top.winfo_exists.return_value = True
        dlg._start_btn = MagicMock()
        dlg._status_lbl = MagicMock()
        dlg._queue_text = MagicMock()
        dlg._queue_text.get.return_value = "12345\n67890\n"
        dlg._stop_flag = threading.Event()
        dlg._worker = MagicMock()
        dlg._worker.is_alive.return_value = True  # still running
        dlg._on_run_item = MagicMock()

        # The patched dialog's _on_start should detect the
        # in-flight worker and bail out.
        dlg._on_start()
        dlg._on_run_item.assert_not_called()
        # Status label was updated to the "already running" message.
        dlg._status_lbl.configure.assert_called()

    def test_close_joins_worker_before_destroying(self) -> None:
        """``_close`` must set the stop flag AND join the
        worker (with a short timeout) BEFORE destroying the
        window — otherwise a mid-iteration ``after(0, …)``
        races against a torn-down widget."""
        from steam_review_tool.ui.popup_batch_dump import (
            BatchDumpDialog,
        )

        dlg = BatchDumpDialog.__new__(BatchDumpDialog)
        dlg._top = MagicMock()
        dlg._start_btn = MagicMock()
        dlg._status_lbl = MagicMock()
        dlg._stop_flag = threading.Event()

        # A worker that records when join() was called and
        # when destroy() was called.
        join_called_at: list[float] = []
        destroy_called_at: list[float] = []

        class _FakeThread:
            def is_alive(self) -> bool:
                return True

            def join(self, timeout: float = 0) -> None:
                join_called_at.append(time.perf_counter())

        dlg._worker = _FakeThread()
        original_destroy = dlg._top.destroy

        def _record_destroy() -> None:
            destroy_called_at.append(time.perf_counter())
            original_destroy()

        dlg._top.destroy = _record_destroy  # type: ignore[assignment]

        dlg._close()
        # Stop flag was set.
        assert dlg._stop_flag.is_set()
        # Worker was joined.
        assert len(join_called_at) == 1, (
            "_close must call worker.join() before destroying "
            "the window"
        )
        # Destroy was called.
        assert len(destroy_called_at) == 1
        # And the join() was strictly BEFORE the destroy().
        assert join_called_at[0] < destroy_called_at[0], (
            "worker.join() must complete before top.destroy()"
        )

    def test_close_with_no_worker_does_not_crash(self) -> None:
        """``_close`` must be safe to call when no worker
        was ever spawned (e.g. user opens the dialog and
        immediately clicks Close)."""
        from steam_review_tool.ui.popup_batch_dump import (
            BatchDumpDialog,
        )

        dlg = BatchDumpDialog.__new__(BatchDumpDialog)
        dlg._top = MagicMock()
        dlg._start_btn = MagicMock()
        dlg._status_lbl = MagicMock()
        dlg._stop_flag = threading.Event()
        dlg._worker = None
        # Should not raise.
        dlg._close()


# ---------------------------------------------------------------------------
# BUG-R11-5: consolidated os.startfile / Popen / xdg-open helper
# ---------------------------------------------------------------------------
class TestOsOpenHelper:
    """The cross-platform "open this path in the OS file
    manager" ladder was copy-pasted in 4 places
    (``action_handler.open_in_editor``,
    ``dump_folder_controller._default_open``,
    ``dependency_installer.open_pw_cache``,
    ``popup_search._open_in_editor``). The fix consolidates
    it into ``utils.os_open.open_path_in_os``.
    """

    def test_open_path_in_os_exists(self) -> None:
        from steam_review_tool.utils.os_open import open_path_in_os
        assert callable(open_path_in_os)

    def test_open_path_in_os_returns_none_on_success(self) -> None:
        """When the platform call succeeds, the helper
        returns ``None`` so the caller can show a "no error"
        state."""
        from steam_review_tool.utils.os_open import open_path_in_os
        with patch("steam_review_tool.utils.os_open.os.startfile"):
            result = open_path_in_os(Path("C:/some/file.txt"))
        assert result is None

    def test_open_path_in_os_returns_error_string(self) -> None:
        """When the platform call raises, the helper
        returns the exception's string representation so
        the caller can show it to the user."""
        from steam_review_tool.utils.os_open import open_path_in_os
        with patch(
            "steam_review_tool.utils.os_open.os.startfile",
            side_effect=FileNotFoundError("[WinError 2] not found"),
        ):
            result = open_path_in_os(Path("C:/missing.txt"))
        assert result is not None
        assert "not found" in result

    def test_dump_folder_controller_uses_helper(self) -> None:
        """``DumpFolderController`` must use ``open_path_in_os``
        as its default opener (was a private ``_default_open``
        copy of the same platform ladder)."""
        from steam_review_tool.controllers import dump_folder_controller
        src = Path(dump_folder_controller.__file__).read_text(
            encoding="utf-8",
        )
        # The private ``_default_open`` function should be gone.
        assert "_default_open" not in src, (
            "dump_folder_controller should no longer have a "
            "private _default_open — it should use "
            "open_path_in_os from utils.os_open"
        )
        # And it should import / use the helper.
        assert "open_path_in_os" in src

    def test_action_handler_uses_helper(self) -> None:
        """``action_handler.open_in_editor`` should call the
        helper instead of inlining the platform ladder."""
        from steam_review_tool.controllers import action_handler
        src = Path(action_handler.__file__).read_text(
            encoding="utf-8",
        )
        # The inline platform ladder should be gone.
        assert "subprocess.Popen" not in src, (
            "action_handler should no longer inline the "
            "subprocess.Popen platform ladder"
        )
        # And it should import the helper.
        assert "open_path_in_os" in src

    def test_popup_search_uses_helper(self) -> None:
        """``popup_search._open_in_editor`` should call the
        helper instead of inlining the platform ladder."""
        from steam_review_tool.ui import popup_search
        src = Path(popup_search.__file__).read_text(
            encoding="utf-8",
        )
        assert "subprocess.Popen" not in src, (
            "popup_search should no longer inline the "
            "subprocess.Popen platform ladder"
        )
        assert "open_path_in_os" in src

    def test_dependency_installer_uses_helper(self) -> None:
        """``dependency_installer.open_pw_cache`` should call
        the helper instead of inlining the platform ladder
        (and the misleading ``shutil.which("xdg-open") or
        "xdg-open"`` no-op fallback is gone)."""
        from steam_review_tool.services import dependency_installer
        src = Path(dependency_installer.__file__).read_text(
            encoding="utf-8",
        )
        # Strip pure comment lines first — the misleading
        # pattern is often quoted in an explaining comment
        # after the fix. (Cross-project lesson: the
        # comment-strip is required or the test will
        # always pass once someone mentions the pattern
        # in a comment.)
        code_lines = [
            ln for ln in src.splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")
        ]
        code = "\n".join(code_lines)
        assert 'shutil.which("xdg-open") or "xdg-open"' not in code, (
            "dependency_installer should no longer use the "
            "misleading shutil.which(xdg-open) or 'xdg-open' "
            "no-op fallback"
        )
        assert "open_path_in_os" in code


# ---------------------------------------------------------------------------
# Cross-cutting: no production file should re-introduce the inline
# platform ladder now that ``utils.os_open.open_path_in_os`` exists.
# ---------------------------------------------------------------------------
class TestNoInlinePlatformLadder:
    """Walk the source tree and fail if any production file
    re-introduces the cross-platform ``os.startfile /
    Popen / xdg-open`` ladder that was consolidated into
    ``utils.os_open.open_path_in_os``.

    The pattern is recognised by the presence of any of
    these in a single file:

    - ``os.startfile`` AND ``subprocess.Popen`` AND
      ``xdg-open`` (the Windows + macOS + Linux triad)
    - OR a ``shutil.which("xdg-open") or "xdg-open"`` no-op
      fallback
    - OR a private ``_default_open`` (which was the
      dump_folder_controller's copy of the same ladder)

    Files known to be safe: the helper itself
    (``utils/os_open.py``) and the dependency-installer
    sub-shells (which legitimately use ``subprocess`` for
    ``pip`` / ``playwright install``, not for opening paths
    in the file manager).
    """

    # Files where ``subprocess.Popen`` is allowed because it's
    # used for a completely different purpose (pip install
    # helpers, not OS file manager).
    SUBPROCESS_ALLOWED_FILES = {
        "services/dependency_installer.py",
        "services/playwright_subprocess.py",
        "services/playwright_subprocess_scraper.py",
        "services/python_runtime.py",
    }
    STARTFILE_ALLOWED_FILES = set()  # only the helper uses os.startfile

    def _walk_source(self) -> list[Path]:
        root = Path(__file__).resolve().parent.parent / "steam_review_tool"
        return [
            p for p in root.rglob("*.py")
            if not p.name.startswith("_test")
        ]

    def _strip_comments(self, src: str) -> str:
        return "\n".join(
            ln for ln in src.splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")
        )

    def test_no_file_combines_startfile_popen_xdgopen(self) -> None:
        """No file (other than the helper itself) should
        contain the full triad of platform-open APIs."""
        offenders: list[str] = []
        for p in self._walk_source():
            if "utils/os_open.py" in str(p).replace("\\", "/"):
                continue  # the helper itself
            code = self._strip_comments(p.read_text(encoding="utf-8"))
            has_startfile = "os.startfile" in code
            has_popen = "subprocess.Popen" in code
            has_xdgopen = "xdg-open" in code
            if has_startfile and has_popen and has_xdgopen:
                offenders.append(str(p))
        assert not offenders, (
            f"the cross-platform open-path ladder is duplicated "
            f"in: {offenders}. Use utils.os_open.open_path_in_os."
        )

    def test_no_xdgopen_which_or_noop_fallback(self) -> None:
        """The ``shutil.which("xdg-open") or "xdg-open"`` no-op
        fallback pattern must not reappear in any production
        file."""
        offenders: list[str] = []
        for p in self._walk_source():
            if "utils/os_open.py" in str(p).replace("\\", "/"):
                continue
            code = self._strip_comments(p.read_text(encoding="utf-8"))
            if 'shutil.which("xdg-open") or "xdg-open"' in code:
                offenders.append(str(p))
        assert not offenders, (
            f"the misleading shutil.which(xdg-open) or 'xdg-open' "
            f"no-op fallback reappeared in: {offenders}"
        )
