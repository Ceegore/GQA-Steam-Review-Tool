"""Round-24 bug-hunt regression tests.

Real bugs found in a twenty-fourth systematic pass. Rounds
1-23 (9388ab1, 9ea69de, ed231bc, 80f9431, f913ae8,
e0514c0, 0e4f031, ba4255e, 49aa77a, 831219e, 04f47f6,
dfd6ff7, 6265d12, 561fc45, b795fbd, 95ea74e, 40d195a,
25c305a, 9e5b263, dc1d9d7, 22506de, 6891d1f, 448e2c3)
found 111 bugs across the project. Round 24 found 5 more —
this round targets a NEW anti-pattern class: **silent
exception swallow in UI callback-forwarding paths**.

The recurring lesson (compounding R13 + R21 + R22 + R23):
"broad ``except Exception`` in non-error-handling code
silently drops real failures". R13 fixed this pattern in
the service + controller layer (broad ``except Exception``
in non-UI code), R21 fixed the ``_log.warning(...)`` part
of the same pattern in services, R22 normalized the
"type+exc" format in exporters + services, and R23
normalized the UI layer's "type+exc" format. R24 fixes
the remaining case in the UI layer: ``except Exception:
pass`` wrapping a CALLBACK call (i.e. the popup forwards
an error to a user-supplied callback or to a
caller-supplied controller hook, and the popup silently
swallows the callback's exception).

The 5 sites share the same fix-shape (R23-style):

  ``try: callback()`` → ``except Exception: pass``

becomes

  ``try: callback()`` → ``except Exception as exc:``
  ``    logging.getLogger(__name__).exception(``
  ``        "X callback failed: %s", exc,``
  ``    )``

The previous "silent swallow" hid real bugs: a typo in
the callback, a downstream string-parse raising, a
``_persist_settings`` call failing — all invisible to
both user and developer.

R24-1  ui/popup_welcome.py:208-214
      ``WelcomeDialog._on_close`` called
      ``self._on_save_settings(self._settings)``
      (the chokepoint for the "Don't show again"
      greeting persistence) and silently swallowed
      ANY exception. R23-1 added internal logging
      in ``_persist_settings``, but a callback
      raised BEFORE the persistence call — e.g. a
      setter on ``self._settings`` raising, or a
      caller-supplied callback raising — would still
      be invisible. R24 adds the same logging at
      the popup-forwarding layer for
      defense-in-depth.

R24-2  ui/popup_date_picker.py:163-174
      ``DatePickerPopup._apply`` called the
      user-supplied ``on_change`` callback and
      silently swallowed ANY exception. A bug in
      the callback (a downstream string-parse
      that raises) would be invisible.

R24-3  ui/popup_time_picker.py:115-124
      ``TimePickerPopup._pick_clear`` called the
      user-supplied ``on_change`` callback and
      silently swallowed ANY exception. Same
      pattern as R24-2.

R24-4  ui/popup_time_picker.py:126-143
      ``TimePickerPopup._apply`` called the
      user-supplied ``on_change`` callback and
      silently swallowed ANY exception. Same
      pattern as R24-2.

R24-5  ui/_responsive.py:169-187
      ``ResponsiveGrid._relayout`` called the
      caller-supplied ``on_reflow`` callback and
      silently swallowed ANY exception. The
      callback is typically a tab controller's
      ``_refresh_button_states`` or a label-update
      hook — bugs in those handlers would be
      invisible.

The R24 round also introduces a project-wide
static-check guard (``TestNoSilentCallbackSwallowInUI``)
that walks every ``ui/popup_*.py`` and ``ui/_responsive.py``
file and asserts that for every callback-forwarding
site (``on_change`` / ``on_save_settings`` / ``on_reflow``),
the wrapping ``try/except`` is no longer a bare
``except Exception: pass``. This is the R22/R23
lesson applied at saturation phase: project-wide sweeps
catch refactor-drift at boundaries the per-file site
list missed.
"""
import inspect
import logging
import re
import tkinter as tk
from pathlib import Path
from unittest.mock import patch

import customtkinter as ctk  # used by per-bug widget tests


# ---------------------------------------------------------------------------
# Helpers (re-used from R22/R23; kept here so the test is self-contained
# even if the R22/R23 file is reorganized)
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


class _ListHandler(logging.Handler):
    """Collects every log record emitted during a test."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def _attach_logger(name: str) -> tuple[logging.Logger, _ListHandler, int]:
    """Attach a fresh ``_ListHandler`` to the logger with the
    given dotted name. Returns ``(logger, handler, old_level)``
    so the test can clean up + assert on the records.
    """
    logger = logging.getLogger(name)
    handler = _ListHandler()
    logger.addHandler(handler)
    old_level = logger.level
    logger.setLevel(logging.DEBUG)
    return logger, handler, old_level


def _detach_logger(
    logger: logging.Logger,
    handler: _ListHandler,
    old_level: int,
) -> None:
    """Detach the handler and restore the previous level."""
    logger.removeHandler(handler)
    logger.setLevel(old_level)


# ---------------------------------------------------------------------------
# BUG-R24-1: popup_welcome.py silent callback swallow
# ---------------------------------------------------------------------------
class TestWelcomeDialogLogsCallbackErrors:
    """``WelcomeDialog._on_close`` calls
    ``self._on_save_settings(self._settings)`` (the
    chokepoint for the "Don't show again" greeting
    persistence) and used to silently swallow ANY
    exception with ``except Exception: pass``.

    R23-1 added internal logging in
    ``AppWindow._persist_settings`` — but a callback
    raised BEFORE the persistence call ran, or a
    different caller-supplied callback raising, would
    still be invisible. R24 adds the same
    defense-in-depth logging at the popup-forwarding
    layer (mirrors the R21 / R23 fix-shape).
    """

    def test_on_close_logs_persistence_callback_error(
        self, tk_root,
    ) -> None:
        """When ``_on_save_settings`` raises, the
        exception must be logged via the standard
        logger (so the developer sees it in stderr) —
        NOT silently swallowed."""
        from steam_review_tool.ui.popup_welcome import (
            WelcomeDialog,
        )

        logger, handler, old_level = _attach_logger(
            "steam_review_tool.ui.popup_welcome",
        )
        try:
            welcome = WelcomeDialog(
                master=tk_root,  # needed for BooleanVar
                settings={"greeting_shown": False},
                on_save_settings=lambda _s: (_ for _ in ()).throw(
                    RuntimeError("simulated persistence failure"),
                ),
            )
            # The "Don't show again" checkbox must be
            # checked for the persistence path to run.
            welcome._dont_show_var.set(True)
            welcome._on_close()
            # The exception must be logged via the
            # standard logger.
            assert any(
                "welcome-dialog on_save_settings callback failed"
                in r.getMessage()
                and "simulated persistence failure" in r.getMessage()
                for r in handler.records
            ), (
                f"expected the exception to be logged "
                f"via the standard logger, got: "
                f"{[r.getMessage() for r in handler.records]}"
            )
        finally:
            _detach_logger(logger, handler, old_level)

    def test_on_close_silent_swallow_is_gone(self) -> None:
        """R24-1 source-shape: the silent
        ``except Exception: pass`` in
        ``_on_close`` is GONE, replaced by the
        R21/R23 ``logging.getLogger(__name__)
        .exception(...)`` fix-shape."""
        from steam_review_tool.ui import popup_welcome
        src = _strip_comments_and_docstrings(
            inspect.getsource(popup_welcome),
        )
        # Find the _on_close body
        idx = src.find("def _on_close")
        assert idx >= 0, "popup_welcome has no _on_close"
        body = src[idx:idx + 1000]
        # The old "except Exception: pass" pattern is
        # gone from the _on_close body.
        assert "except Exception:\n                pass" not in body, (
            "popup_welcome._on_close still has the R24 "
            "anti-pattern: a bare `except Exception: pass` "
            "wrapping _on_save_settings. Use the R23 "
            "fix-shape: `except Exception as exc: "
            "logging.getLogger(__name__).exception(...)` "
            "instead.\nBody:\n" + body
        )
        # The new fix-shape is in place.
        assert (
            'logging.getLogger(__name__).exception(\n'
            '                    "welcome-dialog on_save_settings '
            'callback failed: %s",\n'
            '                    exc,\n'
            '                )'
        ) in body, (
            "popup_welcome._on_close must use the R24 "
            "fix-shape: `logging.getLogger(__name__).exception(...)` "
            "to log the persistence-callback failure.\n"
            "Body:\n" + body
        )


# ---------------------------------------------------------------------------
# BUG-R24-2: popup_date_picker.py silent callback swallow
# ---------------------------------------------------------------------------
class TestDatePickerPopupLogsCallbackErrors:
    """``DatePickerPopup._apply`` calls the
    user-supplied ``on_change`` callback and used to
    silently swallow ANY exception with
    ``except Exception: pass``.

    A bug in the callback (a downstream string-parse
    that raises) would be invisible to both user and
    developer. R24 adds the same defense-in-depth
    logging at the popup-forwarding layer.
    """

    def test_apply_logs_callback_error(self, tk_root) -> None:
        """When ``on_change`` raises, the exception
        must be logged via the standard logger."""
        from steam_review_tool.ui.popup_date_picker import (
            DatePickerPopup,
        )

        logger, handler, old_level = _attach_logger(
            "steam_review_tool.ui.popup_date_picker",
        )
        try:
            entry = ctk.CTkEntry(tk_root)
            try:
                dp = DatePickerPopup(
                    target_entry=entry,
                    master=tk_root,
                    on_change=lambda _v: (_ for _ in ()).throw(
                        RuntimeError("simulated date-cb failure"),
                    ),
                )
                # _apply reads self._picked; set it so
                # the callback is called with a real arg.
                dp._picked = "2024-01-15"
                dp._apply()
                assert any(
                    "date-picker on_change callback failed"
                    in r.getMessage()
                    and "simulated date-cb failure"
                    in r.getMessage()
                    for r in handler.records
                ), (
                    f"expected the exception to be logged "
                    f"via the standard logger, got: "
                    f"{[r.getMessage() for r in handler.records]}"
                )
            finally:
                try:
                    entry.destroy()
                except Exception:
                    pass
        finally:
            _detach_logger(logger, handler, old_level)

    def test_apply_silent_swallow_is_gone(self) -> None:
        """R24-2 source-shape: the silent
        ``except Exception: pass`` in
        ``_apply`` is GONE."""
        from steam_review_tool.ui import popup_date_picker
        src = _strip_comments_and_docstrings(
            inspect.getsource(popup_date_picker),
        )
        idx = src.find("def _apply")
        assert idx >= 0, "popup_date_picker has no _apply"
        body = src[idx:idx + 1000]
        assert "except Exception:\n                pass" not in body, (
            "popup_date_picker._apply still has the R24 "
            "anti-pattern.\nBody:\n" + body
        )
        assert (
            'logging.getLogger(__name__).exception(\n'
            '                    "date-picker on_change '
            'callback failed: %s",\n'
            '                    exc,\n'
            '                )'
        ) in body, (
            "popup_date_picker._apply must use the R24 "
            "fix-shape.\nBody:\n" + body
        )


# ---------------------------------------------------------------------------
# BUG-R24-3 + R24-4: popup_time_picker.py silent callback swallow
# ---------------------------------------------------------------------------
class TestTimePickerPopupLogsCallbackErrors:
    """``TimePickerPopup._pick_clear`` and
    ``_apply`` both call the user-supplied
    ``on_change`` callback and used to silently
    swallow ANY exception with
    ``except Exception: pass``.

    Same anti-pattern as R24-2 (date picker).
    """

    def test_pick_clear_logs_callback_error(self, tk_root) -> None:
        """R24-3: ``_pick_clear`` logs the
        callback failure via the standard logger."""
        from steam_review_tool.ui.popup_time_picker import (
            TimePickerPopup,
        )

        logger, handler, old_level = _attach_logger(
            "steam_review_tool.ui.popup_time_picker",
        )
        try:
            entry = ctk.CTkEntry(tk_root)
            try:
                tp = TimePickerPopup(
                    target_entry=entry,
                    master=tk_root,
                    on_change=lambda _v: (_ for _ in ()).throw(
                        RuntimeError("simulated time-cb clear failure"),
                    ),
                )
                tp._pick_clear()
                assert any(
                    "time-picker on_change callback (clear) failed"
                    in r.getMessage()
                    and "simulated time-cb clear failure"
                    in r.getMessage()
                    for r in handler.records
                ), (
                    f"expected the exception to be logged, got: "
                    f"{[r.getMessage() for r in handler.records]}"
                )
            finally:
                try:
                    entry.destroy()
                except Exception:
                    pass
        finally:
            _detach_logger(logger, handler, old_level)

    def test_pick_clear_silent_swallow_is_gone(self) -> None:
        """R24-3 source-shape: the silent
        ``except Exception: pass`` in
        ``_pick_clear`` is GONE."""
        from steam_review_tool.ui import popup_time_picker
        src = _strip_comments_and_docstrings(
            inspect.getsource(popup_time_picker),
        )
        idx = src.find("def _pick_clear")
        assert idx >= 0, "popup_time_picker has no _pick_clear"
        body = src[idx:idx + 800]
        assert "except Exception:\n                pass" not in body, (
            "popup_time_picker._pick_clear still has the R24 "
            "anti-pattern.\nBody:\n" + body
        )
        assert (
            'logging.getLogger(__name__).exception(\n'
            '                    "time-picker on_change '
            'callback (clear) failed: %s",\n'
            '                    exc,\n'
            '                )'
        ) in body, (
            "popup_time_picker._pick_clear must use the R24 "
            "fix-shape.\nBody:\n" + body
        )

    def test_apply_logs_callback_error(self) -> None:
        """R24-4: ``_apply`` logs the callback
        failure via the standard logger."""
        from steam_review_tool.ui.popup_time_picker import (
            TimePickerPopup,
        )

    def test_apply_logs_callback_error(self, tk_root) -> None:
        """R24-4: ``_apply`` logs the callback
        failure via the standard logger."""
        from steam_review_tool.ui.popup_time_picker import (
            TimePickerPopup,
        )

        logger, handler, old_level = _attach_logger(
            "steam_review_tool.ui.popup_time_picker",
        )
        try:
            entry = ctk.CTkEntry(tk_root)
            try:
                tp = TimePickerPopup(
                    target_entry=entry,
                    master=tk_root,
                    on_change=lambda _v: (_ for _ in ()).throw(
                        RuntimeError("simulated time-cb apply failure"),
                    ),
                )
                # _apply reads self._hour_var and
                # self._min_var; set them so the
                # callback is reached.
                tp._hour_var = tk.IntVar(value=10)
                tp._min_var = tk.IntVar(value=30)
                tp._apply()
                assert any(
                    "time-picker on_change callback (apply) failed"
                    in r.getMessage()
                    and "simulated time-cb apply failure"
                    in r.getMessage()
                    for r in handler.records
                ), (
                    f"expected the exception to be logged, got: "
                    f"{[r.getMessage() for r in handler.records]}"
                )
            finally:
                try:
                    entry.destroy()
                except Exception:
                    pass
        finally:
            _detach_logger(logger, handler, old_level)

    def test_apply_silent_swallow_is_gone(self) -> None:
        """R24-4 source-shape: the silent
        ``except Exception: pass`` in
        ``_apply`` is GONE."""
        from steam_review_tool.ui import popup_time_picker
        src = _strip_comments_and_docstrings(
            inspect.getsource(popup_time_picker),
        )
        idx = src.find("def _apply")
        assert idx >= 0, "popup_time_picker has no _apply"
        body = src[idx:idx + 1000]
        assert "except Exception:\n                pass" not in body, (
            "popup_time_picker._apply still has the R24 "
            "anti-pattern.\nBody:\n" + body
        )
        assert (
            'logging.getLogger(__name__).exception(\n'
            '                    "time-picker on_change '
            'callback (apply) failed: %s",\n'
            '                    exc,\n'
            '                )'
        ) in body, (
            "popup_time_picker._apply must use the R24 "
            "fix-shape.\nBody:\n" + body
        )


# ---------------------------------------------------------------------------
# BUG-R24-5: _responsive.py silent on_reflow callback swallow
# ---------------------------------------------------------------------------
class TestResponsiveGridLogsCallbackErrors:
    """``ResponsiveGrid._relayout`` calls the
    caller-supplied ``on_reflow`` callback and used
    to silently swallow ANY exception with
    ``except Exception: pass``.

    The callback is typically a tab controller's
    ``_refresh_button_states`` or a label-update
    hook — bugs in those handlers would be
    invisible. R24 adds the same defense-in-depth
    logging.
    """

    def test_relayout_logs_callback_error(self) -> None:
        """When ``on_reflow`` raises, the exception
        must be logged via the standard logger."""
        from steam_review_tool.ui._responsive import (
            ResponsiveGrid,
        )

    def test_relayout_logs_callback_error(self, tk_root) -> None:
        """When ``on_reflow`` raises, the exception
        must be logged via the standard logger."""
        from steam_review_tool.ui._responsive import (
            ResponsiveGrid,
        )

        logger, handler, old_level = _attach_logger(
            "steam_review_tool.ui._responsive",
        )
        try:
            grid = ctk.CTkFrame(tk_root)
            try:
                g = ResponsiveGrid(grid, min_col_width=320)
                g.add_row("L1:", lambda p: ctk.CTkLabel(p, text="X"))
                g.add_row("L2:", lambda p: ctk.CTkLabel(p, text="Y"))
                g.on_reflow(
                    lambda: (_ for _ in ()).throw(
                        RuntimeError("simulated reflow failure"),
                    ),
                )
                # Patch winfo_width to return a large
                # value so _relayout doesn't early-return
                # on width < 50.
                with patch.object(
                    g.outer, "winfo_width", return_value=1000,
                ):
                    g.build()
                assert any(
                    "ResponsiveGrid on_reflow callback failed"
                    in r.getMessage()
                    and "simulated reflow failure" in r.getMessage()
                    for r in handler.records
                ), (
                    f"expected the exception to be logged, got: "
                    f"{[r.getMessage() for r in handler.records]}"
                )
            finally:
                try:
                    grid.destroy()
                except Exception:
                    pass
        finally:
            _detach_logger(logger, handler, old_level)

    def test_relayout_silent_swallow_is_gone(self) -> None:
        """R24-5 source-shape: the silent
        ``except Exception: pass`` in
        ``_relayout`` (wrapping ``self._reflow_cb()``)
        is GONE.

        Note: the SAME function also has OTHER
        ``except Exception: pass`` (or ``return``)
        blocks wrapping WIDGET ops (e.g. ``winfo_width``,
        ``child.destroy()``) — those are Category A
        (TclError guards) and are out of scope for R24.
        This test narrows the check to the
        ``self._reflow_cb()`` block specifically.
        """
        from steam_review_tool.ui import _responsive
        src = _strip_comments_and_docstrings(
            inspect.getsource(_responsive),
        )
        # Find the ``self._reflow_cb()`` call site and
        # extract the wrapping try/except.
        idx = src.find("self._reflow_cb()")
        assert idx >= 0, (
            "_responsive has no `self._reflow_cb()` call — "
            "did the callback wiring change?"
        )
        # Walk back to the `try:` immediately
        # preceding the call.
        before = src[max(0, idx - 400):idx]
        # Match the closest preceding `try:` line
        # (any indent). The R24 fix uses 16 spaces.
        try_matches = list(re.finditer(r"^[ \t]+try:\s*$", before, re.M))
        assert try_matches, (
            "could not locate a `try:` line before "
            "self._reflow_cb() in _responsive._relayout. "
            "Source before the call:\n" + before
        )
        try_start = try_matches[-1].start()
        # Read 600 chars forward from the `try:` line.
        abs_try = max(0, idx - 400) + try_start
        block = src[abs_try:abs_try + 600]
        # The old anti-pattern was:
        #     try:
        #         self._reflow_cb()
        #     except Exception:
        #         pass
        # Check the R24 fix is in place: the block
        # must contain `except Exception as exc:` and
        # `logging.getLogger(__name__).exception(`.
        assert "except Exception as exc:" in block, (
            "_responsive._relayout's `self._reflow_cb()` "
            "block must use `except Exception as exc:` "
            "(R24 fix-shape). Block:\n" + block
        )
        assert "logging.getLogger(__name__).exception(" in block, (
            "_responsive._relayout's `self._reflow_cb()` "
            "block must log via "
            "`logging.getLogger(__name__).exception(...)` "
            "(R24 fix-shape). Block:\n" + block
        )
        # Anti-pattern guard: the line right after
        # `except Exception as exc:` (skipping blank
        # + comment lines) must NOT be `pass`.
        body_lines = block.splitlines()
        for i, line in enumerate(body_lines):
            if line.strip() == "except Exception as exc:":
                for j in range(i + 1, min(i + 6, len(body_lines))):
                    nxt = body_lines[j].strip()
                    if not nxt or nxt.startswith("#"):
                        continue
                    assert nxt != "pass", (
                        "_responsive._relayout's "
                        "`self._reflow_cb()` block has the "
                        "R24 anti-pattern: "
                        "`except Exception as exc: pass`. "
                        "Block:\n" + block
                    )
                    break
                break


# ---------------------------------------------------------------------------
# BUG-R24-1..R24-5: project-wide silent-callback-swallow sweep
# ---------------------------------------------------------------------------
class TestNoSilentCallbackSwallowInUI:
    """R24 global sweep: walk every ``ui/popup_*.py``
    and ``ui/_responsive.py`` file and assert that
    no callback-forwarding site (``on_change`` /
    ``on_save_settings`` / ``on_reflow``) has a
    bare ``except Exception: pass`` wrapper.

    A "callback-forwarding site" is identified by
    the pattern: a callback call (``callback()``
    or ``self.callback()``) immediately wrapped in
    ``try: ... except Exception: pass``.

    This is the R22/R23 lesson applied at saturation
    phase: project-wide sweeps catch refactor-drift
    at boundaries the per-file site list missed.
    The R24 sweep walks the 4 files where the
    anti-pattern lived (popup_welcome, popup_date_picker,
    popup_time_picker, _responsive) and asserts
    every such site is now logged.
    """

    # Files where callback-forwarding anti-pattern
    # could appear. The R24 sweep walks all of them.
    _TARGET_FILES = (
        "ui/popup_welcome.py",
        "ui/popup_date_picker.py",
        "ui/popup_time_picker.py",
        "ui/_responsive.py",
    )

    # Callback name patterns (regex fragments). A
    # try/except wrapping any of these is the R24
    # anti-pattern target.
    _CALLBACK_PATTERNS = (
        r'on_change\s*\(',
        r'on_save_settings\s*\(',
        r'self\._on_save_settings\s*\(',
        r'self\._reflow_cb\s*\(',
    )

    def test_no_silent_callback_swallow_in_ui(self) -> None:
        """Project-wide anti-pattern guard.

        Walks every target ``ui/*.py`` file and
        asserts that no callback-forwarding site
        (any of the regex patterns in
        ``_CALLBACK_PATTERNS``) is wrapped in
        ``try: ... except Exception: pass``.

        The fix-shape (R23 / R24) is: every such
        site must use
        ``except Exception as exc: logging.getLogger
        (__name__).exception("X: %s", exc)``.
        """
        from steam_review_tool import __file__ as pkg_init
        root = Path(pkg_init).parent
        offenders: list[str] = []
        for rel in self._TARGET_FILES:
            path = root / rel
            if not path.exists():
                continue
            src = _strip_comments_and_docstrings(
                path.read_text(encoding="utf-8"),
            )
            for cb_pattern in self._CALLBACK_PATTERNS:
                # Find every callback call. The
                # corresponding try/except is the
                # IMMEDIATELY preceding try/except
                # block (within ~5 lines of the call).
                for m in re.finditer(cb_pattern, src):
                    cb_idx = m.start()
                    # Look at the 5 lines BEFORE the
                    # callback call. The wrapping
                    # try/except must be there.
                    pre_window = src[max(0, cb_idx - 500):cb_idx]
                    pre_lines = pre_window.splitlines()
                    # The last 5 non-empty, non-comment
                    # lines are the most relevant.
                    relevant = [
                        ln for ln in pre_lines[-8:]
                        if ln.strip() and not ln.lstrip().startswith("#")
                    ]
                    if not relevant:
                        continue
                    # Find the most recent `try:` line
                    # and the most recent `except`
                    # line in the window.
                    try_line_idx = None
                    exc_line_idx = None
                    for i, ln in enumerate(relevant):
                        stripped = ln.strip()
                        if stripped.endswith("try:"):
                            try_line_idx = i
                        if stripped.startswith("except "):
                            exc_line_idx = i
                    if try_line_idx is None or exc_line_idx is None:
                        continue
                    # The `try:` must come BEFORE the
                    # `except` in the window for this
                    # to be a valid try/except block.
                    if try_line_idx >= exc_line_idx:
                        continue
                    # Check the except line for the
                    # R24 anti-pattern: a bare
                    # `except Exception:` (no `as exc`)
                    # with the next non-blank, non-comment
                    # line being `pass`.
                    exc_line = relevant[exc_line_idx].strip()
                    # Find the lines AFTER the except.
                    after_exc = relevant[exc_line_idx + 1:]
                    if not after_exc:
                        continue
                    first_after = after_exc[0].strip()
                    # The R24 anti-pattern: bare
                    # `except Exception:` (no `as exc`)
                    # followed by `pass`.
                    if (
                        exc_line == "except Exception:"
                        and first_after == "pass"
                    ):
                        offenders.append(
                            f"{rel}: callback-forwarding "
                            f"site matching {cb_pattern!r} "
                            f"still has the R24 anti-pattern: "
                            f"`except Exception: pass`. Use "
                            f"the R23/R24 fix-shape: "
                            f"`except Exception as exc: "
                            f"logging.getLogger(__name__)"
                            f".exception(\"X: %s\", exc)` "
                            f"instead."
                        )
        assert not offenders, (
            "Project has the R24 anti-pattern "
            "(silent callback swallow) in the UI "
            "layer. Use the R23 fix-shape: "
            "`except Exception as exc: "
            "logging.getLogger(__name__).exception(...)` "
            "instead. Offenders:\n\n"
            + "\n\n".join(offenders)
        )
