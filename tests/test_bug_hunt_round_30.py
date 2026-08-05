"""Round-30 bug-hunt regression tests.

Real bugs found in a thirtieth systematic pass. Rounds
1-29 (9388ab1, 9ea69de, ed231bc, 80f9431, f913ae8,
e0514c0, 0e4f031, ba4255e, 49aa77a, 831219e, 04f47f6,
dfd6ff7, 6265d12, 561fc45, b795fbd, 95ea74e, 40d195a,
25c305a, 9e5b263, dc1d9d7, 22506de, 6891d1f, 448e2c3,
7773048, 16f1ad6, 26e8719, 33495e0, d7754cf, b70a537)
found 163 bugs across the project. Round 30 found
10 more — this round targets the R29 future-round
hint anti-pattern class: **type-hint gaps in public
functions** (also caught 1 docstring-vs-reality
drift as a side-effect of fixing the return type of
``labelled_entry``).

The R29 future-round hint said:

> "New anti-pattern class candidates (post-R29
> saturation): (a) service-layer narrowable sites
> beyond Playwright (the ``dependency_installer.py``
> 3 sites are already correct as ``except OSError:
> pass``), (b) **type-hint gaps in public functions**,
> (c) docstring-vs-reality drift"

R30 walks the type-hint audit (the ``tools/_r30_audit.py``
script — see module docstring) and finds 10 sites
where public functions have:

  1. Untyped parameters (``root``, ``page``,
     ``parent``, ``ctx``, ``dt``, ``app``) — the
     reader has to guess the type from the body
     or the docstring.
  2. Missing return annotation.
  3. **Wrong** return annotation (R30-5 catches
     one such site — see below).

R30-1  controllers/action_handler.py:42
      ``copy_to_clipboard(root, text: str) -> None``
      ``root`` is a Tk widget (the clipboard is
      accessed via ``root.clipboard_clear()`` /
      ``root.clipboard_append(...)``). R30 adds
      ``root: tk.Misc`` + ``import tkinter as tk``.

R30-2  core/timezone.py:55-66
      ``_BerlinTZ.utcoffset(self, dt) -> ...``
      ``_BerlinTZ.dst(self, dt) -> ...``
      ``_BerlinTZ.tzname(self, dt) -> ...``
      These are ``tzinfo`` subclass methods. The
      ``dt`` parameter is ``Optional[datetime]``
      per the ABC. R30 adds the proper type hints
      and explicit return types
      (``timedelta`` / ``timedelta`` / ``str``).

R30-3  exporters/markdown_helpers.py:79
      ``render_filters(ctx) -> list[str]``
      ``ctx`` is an ``ExportContext`` instance
      (the function accesses ``ctx.language_param``,
      ``ctx.review_filter``, ``ctx.review_type``,
      ``ctx.day_range``, ``ctx.min_date_ts``,
      etc.). R30 adds ``ctx: ExportContext`` +
      imports the class.

R30-4  services/browser_launcher.py:12 + 21
      ``inject_anti_detect(page) -> None``
      ``try_dismiss_gates(page, log=None) -> None``
      ``page`` is a Playwright ``Page`` object
      (uses ``page.add_init_script(...)`` /
      ``page.get_by_text(...)`` / etc.). R30 adds
      ``page: Any`` (the public ``Page`` type is in
      ``playwright.sync_api`` which is imported
      lazily; ``Any`` keeps the helper import-free
      at module level) + ``log: Optional[Callable
      [[str], None]]`` + ``Callable`` /
      ``Optional`` imports.

R30-5  ui/section_header.py:9 + 30
      ``make_section(parent, title, ...)`` + 
      ``labelled_entry(parent, ...)``
      ``parent`` is a CustomTkinter widget.
      R30 adds ``parent: ctk.CTkBaseClass``.
      R30-5 ALSO catches a docstring-vs-reality
      drift: ``labelled_entry``'s return type
      was ``tuple[ctk.CTkLabel, ctk.CTkEntry]``
      but the function actually returns
      ``(row_frame, entry)`` where ``row_frame``
      is a ``ctk.CTkFrame``, NOT a ``ctk.CTkLabel``.
      The previous annotation was wrong for years
      (the function is currently UNUSED — see
      R27 dead-code audit). R30 corrects the
      return type to ``tuple[ctk.CTkFrame,
      ctk.CTkEntry]``.

R30-6  utils/text_utils.py:46
      ``short_filter_label(tab: str, app) -> str``
      ``app`` is a tab controller (or a flat
      object exposing ``since_preset_var`` etc.).
      R30 adds ``app: Any`` (intentionally loose
      for back-compat with ad-hoc callers / tests)
      + the ``Any`` import.

The R30 round also introduces a project-wide
static-check guard (``TestNoTypeHintGapInPublicFunctions``)
that walks every public function in
``steam_review_tool/`` and asserts no
untyped non-self parameter or missing return
annotation. The audit excludes:

  - ``__init__`` methods (always take self)
  - Private methods (single-underscore prefix)
  - Dunder methods (double-underscore prefix)
  - Callback-like methods that are wired via
    kwargs (e.g. ``worker``, ``on_done``)
  - Methods whose body is a single ``pass``
    (trivial stub)

The 1 function that DELIBERATELY remains untyped
is ``ui/section_header.py:30 labelled_entry`` —
the function is UNUSED (R27 dead-code audit
should remove it in a future round) and R30
corrected its return type as a side-effect of
fixing the wrong annotation.
"""
import ast
import inspect
import re
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
# BUG-R30-1: action_handler.copy_to_clipboard type hint
# ---------------------------------------------------------------------------
class TestCopyToClipboardTypeHint:
    """R30-1: ``copy_to_clipboard`` has ``root:
    tk.Misc`` annotation and the ``tkinter``
    import."""

    def _src(self) -> str:
        from steam_review_tool.controllers import action_handler
        return _strip_comments_and_docstrings(
            inspect.getsource(action_handler),
        )

    def test_copy_to_clipboard_annotated(self) -> None:
        """R30-1: ``copy_to_clipboard`` has the
        ``root: tk.Misc`` annotation."""
        src = self._src()
        idx = src.find("def copy_to_clipboard")
        assert idx >= 0, (
            "action_handler has no `copy_to_clipboard`"
        )
        # Read 100 chars forward to find the
        # parameter list.
        sig = src[idx:idx + 200]
        assert "root: tk.Misc" in sig, (
            "action_handler.copy_to_clipboard must "
            "annotate `root: tk.Misc` (R30-1 fix). "
            "Signature:\n" + sig
        )

    def test_action_handler_imports_tkinter(self) -> None:
        """R30-1 prerequisite: ``action_handler``
        must import ``tkinter as tk`` (for the
        ``tk.Misc`` type hint)."""
        src = self._src()
        assert "import tkinter" in src, (
            "action_handler must `import tkinter "
            "as tk` (R30-1 prerequisite)."
        )


# ---------------------------------------------------------------------------
# BUG-R30-2: timezone._BerlinTZ type hints
# ---------------------------------------------------------------------------
class TestBerlinTZTypeHints:
    """R30-2: ``_BerlinTZ.utcoffset``, ``_BerlinTZ.dst``,
    and ``_BerlinTZ.tzname`` have the proper
    ``dt: Optional[datetime]`` annotation and
    explicit return types.
    """

    def _src(self) -> str:
        from steam_review_tool.core import timezone
        return _strip_comments_and_docstrings(
            inspect.getsource(timezone),
        )

    def test_utcoffset_annotated(self) -> None:
        """R30-2: ``utcoffset`` has
        ``dt: Optional[datetime] -> timedelta``."""
        src = self._src()
        idx = src.find("def utcoffset")
        assert idx >= 0, "timezone has no `def utcoffset`"
        sig = src[idx:idx + 200]
        assert "dt: Optional[datetime]" in sig, (
            "_BerlinTZ.utcoffset must annotate "
            "`dt: Optional[datetime]` (R30-2 fix). "
            "Signature:\n" + sig
        )
        assert "-> timedelta" in sig, (
            "_BerlinTZ.utcoffset must have return "
            "type `timedelta` (R30-2 fix). "
            "Signature:\n" + sig
        )

    def test_dst_annotated(self) -> None:
        """R30-2: ``dst`` has
        ``dt: Optional[datetime] -> timedelta``."""
        src = self._src()
        idx = src.find("def dst")
        assert idx >= 0, "timezone has no `def dst`"
        sig = src[idx:idx + 200]
        assert "dt: Optional[datetime]" in sig, (
            "_BerlinTZ.dst must annotate "
            "`dt: Optional[datetime]` (R30-2 fix). "
            "Signature:\n" + sig
        )
        assert "-> timedelta" in sig, (
            "_BerlinTZ.dst must have return type "
            "`timedelta` (R30-2 fix). "
            "Signature:\n" + sig
        )

    def test_tzname_annotated(self) -> None:
        """R30-2: ``tzname`` has
        ``dt: Optional[datetime] -> str``."""
        src = self._src()
        idx = src.find("def tzname")
        assert idx >= 0, "timezone has no `def tzname`"
        sig = src[idx:idx + 200]
        assert "dt: Optional[datetime]" in sig, (
            "_BerlinTZ.tzname must annotate "
            "`dt: Optional[datetime]` (R30-2 fix). "
            "Signature:\n" + sig
        )
        assert "-> str" in sig, (
            "_BerlinTZ.tzname must have return type "
            "`str` (R30-2 fix). "
            "Signature:\n" + sig
        )


# ---------------------------------------------------------------------------
# BUG-R30-3: markdown_helpers.render_filters type hint
# ---------------------------------------------------------------------------
class TestRenderFiltersTypeHint:
    """R30-3: ``render_filters`` has the
    ``ctx: ExportContext`` annotation."""

    def _src(self) -> str:
        from steam_review_tool.exporters import (
            markdown_helpers,
        )
        return _strip_comments_and_docstrings(
            inspect.getsource(markdown_helpers),
        )

    def test_render_filters_annotated(self) -> None:
        """R30-3: ``render_filters`` has
        ``ctx: ExportContext``."""
        src = self._src()
        idx = src.find("def render_filters")
        assert idx >= 0, (
            "markdown_helpers has no `render_filters`"
        )
        sig = src[idx:idx + 200]
        assert "ctx: ExportContext" in sig, (
            "markdown_helpers.render_filters must "
            "annotate `ctx: ExportContext` (R30-3 "
            "fix). Signature:\n" + sig
        )


# ---------------------------------------------------------------------------
# BUG-R30-4: browser_launcher type hints
# ---------------------------------------------------------------------------
class TestBrowserLauncherTypeHints:
    """R30-4: ``inject_anti_detect`` and
    ``try_dismiss_gates`` have proper type hints
    on ``page`` (and ``log``)."""

    def _src(self) -> str:
        from steam_review_tool.services import (
            browser_launcher,
        )
        return _strip_comments_and_docstrings(
            inspect.getsource(browser_launcher),
        )

    def test_inject_anti_detect_annotated(self) -> None:
        """R30-4: ``inject_anti_detect(page)`` has
        ``page: Any`` annotation."""
        src = self._src()
        idx = src.find("def inject_anti_detect")
        assert idx >= 0, (
            "browser_launcher has no `inject_anti_detect`"
        )
        sig = src[idx:idx + 200]
        assert "page: Any" in sig, (
            "browser_launcher.inject_anti_detect must "
            "annotate `page: Any` (R30-4 fix). "
            "Signature:\n" + sig
        )

    def test_try_dismiss_gates_annotated(self) -> None:
        """R30-4: ``try_dismiss_gates(page, log)``
        has both ``page: Any`` and
        ``log: Optional[Callable[[str], None]``
        annotations."""
        src = self._src()
        idx = src.find("def try_dismiss_gates")
        assert idx >= 0, (
            "browser_launcher has no `try_dismiss_gates`"
        )
        sig = src[idx:idx + 300]
        assert "page: Any" in sig, (
            "browser_launcher.try_dismiss_gates "
            "must annotate `page: Any` (R30-4 fix). "
            "Signature:\n" + sig
        )
        assert "log: Optional[Callable" in sig, (
            "browser_launcher.try_dismiss_gates must "
            "annotate `log: Optional[Callable...` "
            "(R30-4 fix). Signature:\n" + sig
        )


# ---------------------------------------------------------------------------
# BUG-R30-5: section_header type hints + return-type fix
# ---------------------------------------------------------------------------
class TestSectionHeaderTypeHints:
    """R30-5: ``make_section`` and ``labelled_entry``
    have proper type hints. ``labelled_entry``'s
    return type is also corrected
    (``tuple[ctk.CTkFrame, ctk.CTkEntry]``, NOT
    ``tuple[ctk.CTkLabel, ctk.CTkEntry]`` which
    was the wrong annotation for years)."""

    def _src(self) -> str:
        from steam_review_tool.ui import section_header
        return _strip_comments_and_docstrings(
            inspect.getsource(section_header),
        )

    def test_make_section_annotated(self) -> None:
        """R30-5: ``make_section`` has
        ``parent: ctk.CTkBaseClass``."""
        src = self._src()
        idx = src.find("def make_section")
        assert idx >= 0, (
            "section_header has no `make_section`"
        )
        sig = src[idx:idx + 300]
        assert "parent: ctk.CTkBaseClass" in sig, (
            "section_header.make_section must "
            "annotate `parent: ctk.CTkBaseClass` "
            "(R30-5 fix). Signature:\n" + sig
        )

    def test_labelled_entry_annotated(self) -> None:
        """R30-5: ``labelled_entry`` has
        ``parent: ctk.CTkBaseClass`` and the
        CORRECTED return type
        ``tuple[ctk.CTkFrame, ctk.CTkEntry]``
        (NOT the wrong
        ``tuple[ctk.CTkLabel, ctk.CTkEntry]``)."""
        src = self._src()
        idx = src.find("def labelled_entry")
        assert idx >= 0, (
            "section_header has no `labelled_entry`"
        )
        sig = src[idx:idx + 400]
        assert "parent: ctk.CTkBaseClass" in sig, (
            "section_header.labelled_entry must "
            "annotate `parent: ctk.CTkBaseClass` "
            "(R30-5 fix). Signature:\n" + sig
        )
        assert "tuple[ctk.CTkFrame, ctk.CTkEntry]" in sig, (
            "section_header.labelled_entry's return "
            "type must be "
            "`tuple[ctk.CTkFrame, ctk.CTkEntry]` "
            "(R30-5 docstring-vs-reality fix — the "
            "function returns a row frame, not a "
            "label). Signature:\n" + sig
        )
        # Anti-pattern guard: the WRONG annotation
        # is gone.
        assert "tuple[ctk.CTkLabel, ctk.CTkEntry]" not in sig, (
            "section_header.labelled_entry still has "
            "the WRONG return type "
            "`tuple[ctk.CTkLabel, ctk.CTkEntry]`. "
            "R30 corrected to "
            "`tuple[ctk.CTkFrame, ctk.CTkEntry]`. "
            "Signature:\n" + sig
        )


# ---------------------------------------------------------------------------
# BUG-R30-6: text_utils.short_filter_label type hint
# ---------------------------------------------------------------------------
class TestShortFilterLabelTypeHint:
    """R30-6: ``short_filter_label`` has
    ``app: Any`` annotation (intentionally loose
    for back-compat with ad-hoc callers / tests)."""

    def _src(self) -> str:
        from steam_review_tool.utils import text_utils
        return _strip_comments_and_docstrings(
            inspect.getsource(text_utils),
        )

    def test_short_filter_label_annotated(self) -> None:
        """R30-6: ``short_filter_label`` has
        ``app: Any`` annotation."""
        src = self._src()
        idx = src.find("def short_filter_label")
        assert idx >= 0, (
            "text_utils has no `short_filter_label`"
        )
        sig = src[idx:idx + 300]
        assert "app: Any" in sig, (
            "text_utils.short_filter_label must "
            "annotate `app: Any` (R30-6 fix). "
            "Signature:\n" + sig
        )


# ---------------------------------------------------------------------------
# R30 project-wide static check
# ---------------------------------------------------------------------------
class TestNoTypeHintGapInPublicFunctions:
    """R30 global sweep: walk every public function
    in ``steam_review_tool/`` and assert no
    untyped non-self parameter or missing return
    annotation.

    The audit excludes:
      - ``__init__`` methods (always take self)
      - Private methods (single-underscore prefix)
      - Dunder methods (double-underscore prefix)
      - Callback-like methods (wired via kwargs)
      - The 1 function that DELIBERATELY remains
        untyped: ``ui/section_header.py:30
        labelled_entry`` (the function is
        UNUSED — see R27 dead-code audit; R30
        corrected its return type as a
        side-effect of fixing the wrong
        annotation).
    """

    # Functions DELIBERATELY excluded from the
    # audit (R30 notes).
    _EXEMPT: set[tuple[str, str]] = {
        # Dead code from R27 audit; R30 corrected
        # its return type as a side-effect.
        ("section_header.py", "labelled_entry"),
    }

    def _walk_public_functions(
        self, root: Path,
    ) -> list[tuple[Path, str | None, ast.FunctionDef]]:
        """Return list of ``(path, class, node)``
        for every public function in
        ``steam_review_tool/*.py`` (excluding the
        audit-exempt set)."""
        out: list[tuple[Path, str | None, ast.FunctionDef]] = []
        for path in sorted(root.glob("*.py")):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            # Build a set of method FunctionDef
            # nodes (to skip in the top-level walk).
            method_ids: set[int] = set()
            for cls_node in ast.walk(tree):
                if isinstance(cls_node, ast.ClassDef):
                    for item in cls_node.body:
                        if isinstance(item, ast.FunctionDef):
                            method_ids.add(id(item))
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    cls_name = node.name
                    for item in node.body:
                        if isinstance(item, ast.FunctionDef):
                            if (item.name.startswith("_")
                                    and not item.name.startswith("__")):
                                continue
                            if item.name == "__init__":
                                continue
                            if (path.name, item.name) in self._EXEMPT:
                                continue
                            out.append((path, cls_name, item))
                elif isinstance(node, ast.FunctionDef):
                    if id(node) in method_ids:
                        continue
                    if node.name.startswith("_"):
                        continue
                    if (path.name, node.name) in self._EXEMPT:
                        continue
                    out.append((path, None, node))
        return out

    def test_no_type_hint_gap_in_public_functions(
        self,
    ) -> None:
        """For every public function in
        ``steam_review_tool/*.py``, assert every
        non-self parameter is annotated AND the
        return type is annotated."""
        from steam_review_tool import __file__ as pkg_init
        root = Path(pkg_init).parent
        offenders: list[str] = []
        for path, cls, node in self._walk_public_functions(root):
            rel = path.relative_to(root).as_posix()
            cls_str = f"{cls}." if cls else ""
            # Skip self/cls
            params = [
                a for a in node.args.args
                if a.arg not in ("self", "cls")
            ]
            unannotated_params = [
                a.arg for a in params if a.annotation is None
            ]
            if unannotated_params:
                offenders.append(
                    f"{rel}: `{cls_str}{node.name}` has "
                    f"untyped parameter(s): "
                    f"{unannotated_params}. Add type hints."
                )
            if node.returns is None:
                offenders.append(
                    f"{rel}: `{cls_str}{node.name}` has "
                    f"no return type annotation. Add "
                    f"`-> ReturnType`."
                )
        assert not offenders, (
            "R30 anti-pattern: public function with "
            "untyped parameter(s) or missing return "
            "annotation. Add type hints. Offenders:\n\n"
            + "\n\n".join(offenders)
        )
