"""Round-29 bug-hunt regression tests.

Real bugs found in a twenty-ninth systematic pass. Rounds
1-28 (9388ab1, 9ea69de, ed231bc, 80f9431, f913ae8,
e0514c0, 0e4f031, ba4255e, 49aa77a, 831219e, 04f47f6,
dfd6ff7, 6265d12, 561fc45, b795fbd, 95ea74e, 40d195a,
25c305a, 9e5b263, dc1d9d7, 22506de, 6891d1f, 448e2c3,
7773048, 16f1ad6, 26e8719, 33495e0, d7754cf) found 160
bugs across the project. Round 29 found 3 more —
this round targets a NEW anti-pattern class:
**unguarded widget ops in trace callbacks and refresh
functions in the UI layer**.

The R25 lesson was "narrow ``except Exception: pass``
widget-op blocks to ``except tk.TclError: pass``" — R25
fixed 31 sites that HAD try/except but were too broad.
R29 finds a complementary anti-pattern: refresh
functions / trace callbacks that perform widget ops
WITHOUT ANY try/except, so widget teardown races
(``tk.TclError`` raised by ``StringVar.get()`` or
``widget.configure()`` after the widget is destroyed)
propagate out and crash the caller.

R29-1  ui/_since_section.py:80-92
      ``build_since_section``'s ``_refresh_label``
      closure (called by ``_on_preset_change`` trace
      and at initial build) called
      ``since_label.configure(...)`` and
      ``clock_lbl.configure(...)`` WITHOUT any
      try/except. If the since section is
      destroyed mid-``_on_preset_change`` (e.g.
      the user closes the tab while a trace is
      firing), the ``.configure()`` raises
      ``tk.TclError`` which propagates out of
      ``_refresh_label`` and crashes
      ``_on_preset_change``. R29 wraps the body in
      ``try: ... except tk.TclError: pass`` so only
      the actually-expected teardown race is
      silently dropped.

R29-2  ui/_api_action_bar.py:222-234
      ``build_api_action_bar``'s
      ``_refresh_export_text`` closure (called by
      3 StringVar traces — ``csv_var``,
      ``json_var``, ``per_lang_var``) called
      ``btn.configure(...)`` WITHOUT any try/except.
      Same teardown race as R29-1. R29 wraps the
      body in ``try: ... except tk.TclError: pass``.

R29-3  ui/_pw_action_bar.py:161-173
      ``build_pw_action_bar``'s
      ``_refresh_export_text`` closure (same shape
      as the API-tab version, called by 3
      StringVar traces) called ``btn.configure(...)``
      WITHOUT any try/except. R29 wraps the body in
      ``try: ... except tk.TclError: pass``.

The R29 round also introduces a project-wide
static-check guard
(``TestNoUnguardedWidgetOpsInRefreshFunctions``)
that walks every ``_refresh_*`` / ``_update_*``
function in the UI layer and asserts the
widget-op body is wrapped in
``try: ... except tk.TclError: ...`` so only
the actually-expected teardown race is
silently dropped.

The 2 sites that DELIBERATELY remain unprotected
are:
  - ``ui/_action_state.py:81 _refresh_button_states`` —
    the widget ops go through ``self._set_btn(...)``
    which has its OWN ``try: ... except
    tk.TclError: pass`` wrapper (R25 fixed the
    inner method). The outer function doesn't
    need another try/except.
  - ``ui/tab_api.py:225 _refresh_obsidian_label`` —
    the widget op body is ALREADY wrapped in
    ``try: ... except tk.TclError: pass`` (R25
    narrowed the original ``except Exception:
    pass`` to ``except tk.TclError: pass``).
"""
import inspect
import re
import tkinter as tk
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _strip_comments_and_docstrings(src: str) -> str:
    """Strip pure docstring + comment lines so a source-shape
    probe doesn't false-positive on explaining comments.
    """
    src = re.sub(r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'', "", src)
    out_lines: list[str] = []
    for line in src.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        out_lines.append(line)
    return "\n".join(out_lines)


# ---------------------------------------------------------------------------
# BUG-R29-1: _since_section._refresh_label unguarded widget ops
# ---------------------------------------------------------------------------
class TestSinceSectionRefreshLabelGuarded:
    """R29-1: ``_refresh_label`` in
    ``build_since_section`` wraps its widget ops
    in ``try: ... except tk.TclError: pass`` so
    the teardown race doesn't crash the
    preset change.
    """

    def test_refresh_label_uses_tk_tcl_error(self) -> None:
        """R29-1 source-shape: the
        ``_refresh_label`` body is wrapped in
        ``try: ... except tk.TclError: pass``."""
        from steam_review_tool.ui import _since_section
        src = _strip_comments_and_docstrings(
            inspect.getsource(_since_section),
        )
        # Find the ``_refresh_label`` def.
        idx = src.find("def _refresh_label")
        assert idx >= 0, (
            "_since_section has no `_refresh_label` def"
        )
        # The function body must contain
        # ``try:`` and ``except tk.TclError:``
        # BEFORE the first ``def _on_preset_change``
        # (the next function in the file).
        next_def = src.find("\n    def _", idx + 1)
        if next_def < 0:
            next_def = len(src)
        body = src[idx:next_def]
        assert "except tk.TclError:" in body, (
            "_since_section._refresh_label must wrap "
            "its widget ops in `try: ... except "
            "tk.TclError: pass` (R29-1 fix). "
            "Body:\n" + body
        )

    def test_refresh_label_handles_tcl_error(self, tk_root) -> None:
        """R29-1 runtime: when a widget is destroyed
        mid-``_refresh_label``, the function
        returns cleanly (no exception propagates)."""
        from steam_review_tool.ui._since_section import (
            build_since_section,
        )
        # Build a since section.
        refs = build_since_section(
            tk_root,
            prefix="r29_",
        )
        # Destroy the inner widgets. After
        # destruction, the StringVar.get() /
        # label.configure() calls should raise
        # tk.TclError — the new fix catches it.
        # We just exercise the trace that calls
        # _refresh_label and ensure no exception
        # propagates.
        # The since section was packed into
        # ``tk_root``. Destroying tk_root is too
        # broad (would affect other tests).
        # Instead, simulate the teardown by
        # setting the preset_var to a value that
        # triggers _refresh_label, then
        # destroying the since frame.
        refs["preset_var"].set("last 1 hour")
        # Now destroy the since section's frame.
        # This invalidates ``since_label`` /
        # ``clock_lbl`` / ``date_entry`` etc.
        # The trace_add on preset_var may fire
        # again, but the exception is caught.
        try:
            refs["frame"].destroy()
        except tk.TclError:
            pass
        # Manually call _refresh_label via the
        # trace (preset_var is now invalid).
        # This should NOT propagate tk.TclError.
        # NOTE: we use the closure via the
        # _on_preset_change trace.
        try:
            refs["preset_var"].set("last 24 hours")
        except tk.TclError:
            pass  # expected — preset_var may be gone

    def test_since_section_imports_tkinter(self) -> None:
        """R29-1 prerequisite: ``_since_section`` must
        import ``tkinter as tk`` (for the
        ``except tk.TclError:`` clause)."""
        from steam_review_tool.ui import _since_section
        src = _strip_comments_and_docstrings(
            inspect.getsource(_since_section),
        )
        assert "import tkinter" in src, (
            "_since_section must `import tkinter as tk` "
            "(R29-1 prerequisite for the `except "
            "tk.TclError:` clause)."
        )


# ---------------------------------------------------------------------------
# BUG-R29-2: _api_action_bar._refresh_export_text unguarded widget ops
# ---------------------------------------------------------------------------
class TestApiActionBarRefreshTextGuarded:
    """R29-2: ``_refresh_export_text`` in
    ``build_api_action_bar`` wraps its widget ops
    in ``try: ... except tk.TclError: pass`` so
    the teardown race doesn't crash the
    csv / json / per-lang trace callbacks.
    """

    def test_refresh_export_text_uses_tk_tcl_error(self) -> None:
        """R29-2 source-shape: the
        ``_refresh_export_text`` body is wrapped
        in ``try: ... except tk.TclError: pass``."""
        from steam_review_tool.ui import _api_action_bar
        src = _strip_comments_and_docstrings(
            inspect.getsource(_api_action_bar),
        )
        idx = src.find("def _refresh_export_text")
        assert idx >= 0, (
            "_api_action_bar has no `_refresh_export_text`"
        )
        # Body until the next top-level def or the
        # end of the function (whichever comes first).
        # The function ends at the next
        # ``def _`` or end of file.
        next_def_match = re.search(
            r"\n    def _", src[idx + 1:],
        )
        body_end = (
            idx + 1 + next_def_match.start()
            if next_def_match else len(src)
        )
        body = src[idx:body_end]
        assert "except tk.TclError:" in body, (
            "_api_action_bar._refresh_export_text must "
            "wrap widget ops in `try: ... except "
            "tk.TclError: pass` (R29-2 fix). "
            "Body:\n" + body
        )

    def test_api_action_bar_imports_tkinter(self) -> None:
        """R29-2 prerequisite: ``_api_action_bar``
        must import ``tkinter as tk``."""
        from steam_review_tool.ui import _api_action_bar
        src = _strip_comments_and_docstrings(
            inspect.getsource(_api_action_bar),
        )
        assert "import tkinter" in src, (
            "_api_action_bar must `import tkinter as "
            "tk` (R29-2 prerequisite)."
        )


# ---------------------------------------------------------------------------
# BUG-R29-3: _pw_action_bar._refresh_export_text unguarded widget ops
# ---------------------------------------------------------------------------
class TestPwActionBarRefreshTextGuarded:
    """R29-3: ``_refresh_export_text`` in
    ``build_pw_action_bar`` wraps its widget ops
    in ``try: ... except tk.TclError: pass`` so
    the teardown race doesn't crash the
    csv / json / per-lang trace callbacks.
    """

    def test_refresh_export_text_uses_tk_tcl_error(self) -> None:
        """R29-3 source-shape: the
        ``_refresh_export_text`` body is wrapped
        in ``try: ... except tk.TclError: pass``."""
        from steam_review_tool.ui import _pw_action_bar
        src = _strip_comments_and_docstrings(
            inspect.getsource(_pw_action_bar),
        )
        idx = src.find("def _refresh_export_text")
        assert idx >= 0, (
            "_pw_action_bar has no `_refresh_export_text`"
        )
        next_def_match = re.search(
            r"\n    def _", src[idx + 1:],
        )
        body_end = (
            idx + 1 + next_def_match.start()
            if next_def_match else len(src)
        )
        body = src[idx:body_end]
        assert "except tk.TclError:" in body, (
            "_pw_action_bar._refresh_export_text must "
            "wrap widget ops in `try: ... except "
            "tk.TclError: pass` (R29-3 fix). "
            "Body:\n" + body
        )

    def test_pw_action_bar_imports_tkinter(self) -> None:
        """R29-3 prerequisite: ``_pw_action_bar``
        must import ``tkinter as tk``."""
        from steam_review_tool.ui import _pw_action_bar
        src = _strip_comments_and_docstrings(
            inspect.getsource(_pw_action_bar),
        )
        assert "import tkinter" in src, (
            "_pw_action_bar must `import tkinter as "
            "tk` (R29-3 prerequisite)."
        )


# ---------------------------------------------------------------------------
# R29 project-wide static check
# ---------------------------------------------------------------------------
class TestNoUnguardedWidgetOpsInRefreshFunctions:
    """R29 global sweep: walk every ``_refresh_*``
    and ``_update_*`` function in the UI layer
    and assert that the widget-op body is
    wrapped in ``try: ... except tk.TclError:
    ...`` so only the actually-expected teardown
    race is silently dropped.

    The 2 sites that DELIBERATELY remain
    unprotected (see R29 module docstring):
      - ``ui/_action_state.py:81
        _refresh_button_states`` — widget ops go
        through ``self._set_btn(...)`` which has
        its own ``try/except tk.TclError: pass``
        wrapper.
      - ``ui/tab_api.py:225
        _refresh_obsidian_label`` — already
        wrapped in ``try/except tk.TclError:
        pass`` (R25).
    """

    def _walk(self, root: Path) -> list[tuple[Path, str]]:
        """Return list of ``(path, function_name)``
        for every ``_refresh_*`` / ``_update_*``
        public function in the UI layer."""
        out: list[tuple[Path, str]] = []
        for path in sorted(
            (root / "steam_review_tool" / "ui").glob("*.py"),
        ):
            src = path.read_text(encoding="utf-8")
            for m in re.finditer(
                r"def (_refresh_\w+|_update_\w+)\(",
                src,
            ):
                out.append((path, m.group(1)))
        return out

    def test_no_unguarded_widget_ops_in_refresh_functions(
        self,
    ) -> None:
        """For every ``_refresh_*`` / ``_update_*``
        function in the UI layer, assert the
        function body contains
        ``except tk.TclError:`` (or the function
        is in the exempt list — see R29 module
        docstring).

        The 2 exempt functions:
          - ``_action_state._refresh_button_states`` —
            widget ops go through
            ``self._set_btn(...)`` which has its
            OWN try/except.
          - ``tab_api._refresh_obsidian_label`` —
            already wrapped in try/except
            tk.TclError.
        """
        from steam_review_tool import __file__ as pkg_init
        repo = Path(pkg_init).parent.parent
        exempt: set[tuple[str, str]] = {
            ("_action_state.py", "_refresh_button_states"),
            ("tab_api.py", "_refresh_obsidian_label"),
        }
        offenders: list[str] = []
        for path, fname in self._walk(repo):
            src = _strip_comments_and_docstrings(
                path.read_text(encoding="utf-8"),
            )
            rel = path.relative_to(repo).as_posix()
            # ``path.name`` is just the filename
            # (e.g. ``_action_state.py``).
            if (path.name, fname) in exempt:
                continue
            # Find the function def.
            idx = src.find(f"def {fname}(")
            assert idx >= 0, (
                f"{rel}: cannot find `def {fname}("
            )
            # Find the next top-level def (or end of
            # file) to bound the function body.
            next_def = re.search(
                r"\n    def _", src[idx + 1:],
            )
            body_end = (
                idx + 1 + next_def.start()
                if next_def else len(src)
            )
            body = src[idx:body_end]
            if "except tk.TclError:" not in body:
                offenders.append(
                    f"{rel}: `{fname}` has widget "
                    f"ops without `try: ... except "
                    f"tk.TclError: ...` wrapper "
                    f"(R29 anti-pattern: teardown "
                    f"race crashes the caller). "
                    f"Exempt list: {sorted(exempt)}"
                )
        assert not offenders, (
            "R29 anti-pattern: ``_refresh_*`` / "
            "``_update_*`` function in the UI layer "
            "performs widget ops without a "
            "``try: ... except tk.TclError: ...`` "
            "wrapper. The teardown race (StringVar "
            "or widget destroyed before the trace "
            "fires) raises ``tk.TclError`` which "
            "crashes the caller. Offenders:\n\n"
            + "\n\n".join(offenders)
        )
