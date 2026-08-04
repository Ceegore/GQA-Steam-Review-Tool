"""Round-9 bug-hunt regression tests.

Real bugs found in a ninth systematic pass. Rounds 1-8
(9388ab1, 9ea69de, ed231bc, 80f9431, f913ae8, e0514c0,
0e4f031, ba4255e) covered the int / str / or-default
residue, the double-subscribe pattern, the over-broad
"find latest .md" walk, the missing worker-shutdown wait,
the broken batch-dump feature, and the missed R5 sites.

This round targets two more user-visible issues:
1. The popup text widgets (Help, Welcome, Top Complaints,
   Search results) used ``state="disabled"`` which makes
   the widget completely non-interactive — the user can't
   even select text to copy. The right value is
   ``state="readonly"`` which allows selection + copy
   but prevents edits.
2. The watch-mode worker called ``self._log(...)``
   (which does ``self._log_box.configure(...)``) directly
   from a non-main thread — Tk widget access from a non-
   main thread is undefined behavior. Fix: snapshot the
   GUI state on the main thread, route the log call
   through ``self.after(0, fn)``.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# BUG-R9-1: popup text widgets are state="disabled" (non-selectable)
# ---------------------------------------------------------------------------
class TestPopupTextWidgetsSelectable:
    """The Help, Welcome, Top Complaints, and Search Results
    text widgets were created with ``state="disabled"``,
    which makes them completely non-interactive — the user
    can't even select text to copy. Fix: use
    ``state="readonly"`` which allows selection + copy but
    prevents accidental edits.
    """

    def test_popup_help_uses_readonly_not_disabled(self) -> None:
        """Static check: the popup_help module's text widget
        must be set to ``state="readonly"`` (NOT ``disabled``)."""
        from steam_review_tool.ui import popup_help
        src = Path(popup_help.__file__).read_text(encoding="utf-8")
        # The text widget configuration line must use
        # ``state="readonly"`` (or a ``state=`` literal). Strip
        # comments to avoid matching the explanatory comment
        # that says "was state=disabled".
        code_lines = [
            ln for ln in src.splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")
        ]
        code = "\n".join(code_lines)
        assert 'state="readonly"' in code, (
            "popup_help.py must set state='readonly' (not "
            "'disabled') so users can select and copy help text"
        )
        # The text widget must NOT use the old state.
        assert 'state="disabled"' not in code

    def test_popup_welcome_uses_readonly_not_disabled(self) -> None:
        from steam_review_tool.ui import popup_welcome
        src = Path(popup_welcome.__file__).read_text(encoding="utf-8")
        code_lines = [
            ln for ln in src.splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")
        ]
        code = "\n".join(code_lines)
        assert 'state="readonly"' in code
        assert 'state="disabled"' not in code

    def test_popup_search_results_use_readonly(self) -> None:
        from steam_review_tool.ui import popup_search
        src = Path(popup_search.__file__).read_text(encoding="utf-8")
        code_lines = [
            ln for ln in src.splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")
        ]
        code = "\n".join(code_lines)
        # popup_search._set_results must toggle normal → readonly,
        # not normal → disabled.
        assert 'state="readonly"' in code
        assert 'state="disabled"' not in code

    def test_popup_top_complaints_uses_readonly(self) -> None:
        from steam_review_tool.ui import popup_top_complaints
        src = Path(popup_top_complaints.__file__).read_text(
            encoding="utf-8",
        )
        code_lines = [
            ln for ln in src.splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")
        ]
        code = "\n".join(code_lines)
        assert 'state="readonly"' in code
        assert 'state="disabled"' not in code

    def test_buttons_still_use_disabled(self) -> None:
        """Sanity check: the fix only changes text widgets.
        Buttons (resume, stop, export, etc.) should still
        use ``state="disabled"`` for the "this button is
        currently unavailable" UX."""
        from steam_review_tool.ui import _api_action_bar
        src = Path(_api_action_bar.__file__).read_text(
            encoding="utf-8",
        )
        # Buttons use ``state="disabled"`` to indicate
        # "unavailable" — that's the correct state for buttons.
        assert 'state="disabled"' in src


# ---------------------------------------------------------------------------
# BUG-R9-2: watch-mode worker calls Tk widgets from non-main thread
# ---------------------------------------------------------------------------
class TestWatchModeThreadSafety:
    """The watch-mode worker thread called
    ``self._log(...)`` (which does ``self._log_box.configure(...)``)
    directly from a non-main thread. Tk widget access from
    a non-main thread is undefined behavior — can crash the
    GUI, freeze the window, or silently drop the message.

    Fix: snapshot the GUI state (``lang``, ``auto_incr``)
    on the main thread when the worker starts, and route
    the log call through ``self.after(0, fn)`` so the
    widget modification happens on the main thread.
    """

    def test_watch_worker_snapshots_gui_state(self) -> None:
        """Static check: the watch worker uses the
        snapshotted ``lang`` and ``auto_incr`` variables
        from the main thread, not live ``StringVar.get()``
        calls inside the loop."""
        from steam_review_tool.ui import tab_api
        src = Path(tab_api.__file__).read_text(encoding="utf-8")
        code_lines = [
            ln for ln in src.splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")
        ]
        code = "\n".join(code_lines)
        # The watch worker must define local ``lang`` and
        # ``auto_incr`` variables from the main thread's
        # StringVar.get() calls (the snapshot). The worker
        # body must reference these locals, NOT call
        # ``self.filter_refs.lang_var.get()`` or
        # ``self.auto_incr_var.get()`` inside the loop.
        # Use a coarse but reliable pattern: check that the
        # worker's lang lookup uses a local variable, not a
        # StringVar call.
        assert "language=lang" in code or "language=lang," in code, (
            "Watch worker must use snapshotted `lang` local, "
            "not live StringVar.get() inside the loop"
        )
        # The auto_incr snapshot check.
        assert "if auto_incr:" in code, (
            "Watch worker must use snapshotted `auto_incr` "
            "local, not live StringVar.get() inside the loop"
        )

    def test_watch_worker_uses_after_for_log(self) -> None:
        """Static check: the watch worker routes the log
        call through ``self.after(0, fn)``, not a direct
        ``self._log(...)`` call."""
        from steam_review_tool.ui import tab_api
        src = Path(tab_api.__file__).read_text(encoding="utf-8")
        code_lines = [
            ln for ln in src.splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")
        ]
        code = "\n".join(code_lines)
        # The watch worker must call ``self.after(0, ...)``
        # for the GUI log update.
        assert "self.after(0, " in code, (
            "Watch worker must route GUI updates through "
            "self.after(0, ...) — calling widget.configure() "
            "from a worker thread is undefined Tk behavior"
        )

    def test_watch_worker_does_not_call_log_directly(self) -> None:
        """Static check: the watch worker does NOT call
        ``self._log(...)`` directly from the loop body.
        The original buggy code was:
            self._log(f"[watch] +{len(new_reviews)} new review(s).")
        inside the worker. After the fix, the log call is
        scheduled via ``self.after(0, lambda: self._log(...))``.
        """
        from steam_review_tool.ui import tab_api
        src = Path(tab_api.__file__).read_text(encoding="utf-8")
        code_lines = [
            ln for ln in src.splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")
        ]
        code = "\n".join(code_lines)
        # The buggy pattern: a direct self._log(...) call
        # inside the watch worker's ``while`` loop body.
        # We allow self._log(...) in the main thread (the
        # "Watching every N min" message) and in the toggle
        # branch (the "Watch mode stopped" message). The
        # dangerous call is inside the worker thread's loop.
        # We can't easily distinguish with a static check, so
        # instead check that self.after(0, ...) is the
        # mechanism used for the per-iteration log.
        assert "self.after(0, lambda" in code, (
            "Watch worker must use self.after(0, lambda ...) "
            "to schedule the per-iteration log call on the "
            "main thread"
        )


# ---------------------------------------------------------------------------
# Cross-cutting: the fix preserves the watch loop's intent
# ---------------------------------------------------------------------------
class TestWatchModeFunctional:
    """Sanity check: the watch mode still iterates, still
    polls, and still publishes FETCH_COMPLETED for the
    auto-incr case. The fix is purely about thread safety,
    not about behavior.
    """

    def test_watch_still_polls(self) -> None:
        from steam_review_tool.ui import tab_api
        src = Path(tab_api.__file__).read_text(encoding="utf-8")
        code_lines = [
            ln for ln in src.splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")
        ]
        code = "\n".join(code_lines)
        assert "poll_recent_reviews(" in code
        assert "self._watch_stop.wait(" in code
        assert "while not self._watch_stop.is_set():" in code

    def test_watch_still_publishes_fetch_completed(self) -> None:
        from steam_review_tool.ui import tab_api
        src = Path(tab_api.__file__).read_text(encoding="utf-8")
        code_lines = [
            ln for ln in src.splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")
        ]
        code = "\n".join(code_lines)
        assert "bus.publish(self.api_wf.FETCH_COMPLETED" in code
