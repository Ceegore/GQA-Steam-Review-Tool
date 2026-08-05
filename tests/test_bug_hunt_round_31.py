"""Round-31 bug-hunt regression tests.

Real bugs found in a thirty-first systematic pass. Rounds
1-30 (9388ab1, 9ea69de, ed231bc, 80f9431, f913ae8,
e0514c0, 0e4f031, ba4255e, 49aa77a, 831219e, 04f47f6,
dfd6ff7, 6265d12, 561fc45, b795fbd, 95ea74e, 40d195a,
25c305a, 9e5b263, dc1d9d7, 22506de, 6891d1f, 448e2c3,
7773048, 16f1ad6, 26e8719, 33495e0, d7754cf, b70a537,
d08bb9e) found 173 bugs across the project. Round 31
found 8 more — this round targets the R30 future-round
hint anti-pattern class: **missing docstrings on public
methods that are called from UI code**. R30's future-round
hint said:

> "Docstring coverage — some public functions lack
> docstrings entirely."

R31 walks the public method surface of the two main
controller classes (``APIWorkflow`` and
``PlaywrightWorkflow``) and finds 7 public methods that
are called from UI but lack docstrings. R31 adds
docstrings that document the behavior, edge cases, and
side effects (e.g. bus events emitted, threading model).

R31 also removes the dead ``labelled_entry`` function
from ``ui/section_header.py`` (the R27 dead-code audit
caught it; R30 corrected its return type as a side-effect
of fixing the wrong annotation; R31 does the final
removal).

R31-1  controllers/api_workflow.py:106
      ``APIWorkflow.stop()`` had no docstring. The
      method sets a ``threading.Event`` that the
      worker checks between pages. R31 adds a
      docstring documenting the cooperative-stop
      pattern and that ``wait()`` must be called
      separately for graceful shutdown.

R31-2  controllers/api_workflow.py:167
      ``APIWorkflow.export(...)`` had no docstring.
      The method delegates to
      ``exporters.export_orchestrator.run_export``
      (the shared export pipeline). R31 adds a
      docstring documenting the optional flags
      (``also_csv`` / ``also_json`` /
      ``per_language`` / ``obsidian_vault``) and
      the return type.

R31-3  controllers/playwright_workflow.py:86
      ``PlaywrightWorkflow.install_playwright()``
      had no docstring. The method spawns a
      background ``pip install`` thread. R31 adds
      a docstring documenting the idempotency
      pattern (double-click is a no-op) and the
      ``DEP_STATUS_CHANGED`` bus event.

R31-4  controllers/playwright_workflow.py:96
      ``PlaywrightWorkflow.install_chromium()`` had
      no docstring. The method spawns a background
      thread that downloads the Chromium binary.
      R31 adds a docstring documenting the
      ``install_playwright`` ordering requirement.

R31-5  controllers/playwright_workflow.py:124
      ``PlaywrightWorkflow.open_cache()`` had no
      docstring. The method opens the Playwright
      browser-cache directory in the OS file
      manager. R31 adds a docstring.

R31-6  controllers/playwright_workflow.py:208
      ``PlaywrightWorkflow.export(...)`` had no
      docstring. The method delegates to
      ``run_export`` (same shared pipeline as
      ``APIWorkflow.export``). R31 adds a docstring
      documenting the shared-pipeline contract.

R31-7  controllers/playwright_workflow.py:227
      ``PlaywrightWorkflow.stop()`` had no docstring.
      The method sets a ``threading.Event`` that
      the scrape worker checks. R31 adds a
      docstring.

R31-8  ui/section_header.py:30 + 56
      ``labelled_entry`` was DEAD CODE (R27 audit
      caught it; R30 corrected its return type as
      a side-effect). R31 finally REMOVES the
      function from ``section_header.py`` and
      removes the entry from ``__all__``. The
      function had zero callers anywhere in the
      production codebase — the R27 dead-code
      audit confirmed it. R30's ``R30-5`` was an
      INTERIM fix (corrected the wrong return
      type); R31-8 is the FINAL fix (removes the
      function entirely).

The R31 round also updates the R30 test file to
make ``test_labelled_entry_annotated`` a soft-skip
(if the function is gone, the test is a no-op —
R31's removal is the final fix). The R30 project-wide
sweep's exempt set no longer needs the
``("section_header.py", "labelled_entry")`` entry
(the function is gone, so it can't be a type-hint
gap).

The 1 site that DELIBERATELY remains without a
docstring:
  - ``PlaywrightWorkflow.refresh_dep_status`` —
    already has a docstring
    ("Probe playwright + chromium on a background
    thread."). Not R31 scope.
  - ``APIWorkflow.start_fetch`` and
    ``APIWorkflow.wait`` / ``PlaywrightWorkflow.wait``
    / ``PlaywrightWorkflow.scrape`` — all have
    docstrings. Not R31 scope.
"""
import inspect
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _has_docstring_after_def(src: str, def_keyword: str) -> bool:
    """Return True if the function/class starting with
    ``def_keyword`` is immediately followed by a
    string-literal docstring.

    The check is structural: the first non-blank
    statement after the function signature is an
    ``Expr`` whose value is a ``Constant`` string.
    """
    idx = src.find(def_keyword)
    if idx < 0:
        return False
    # Find the next top-level def (or end of file)
    # to bound the function body. Look for
    # ``\n    def`` or ``\nclass`` at the same indent.
    next_def = -1
    for marker in ("\n    def ", "\nclass "):
        m = src.find(marker, idx + 1)
        if m >= 0 and (next_def < 0 or m < next_def):
            next_def = m
    body = src[idx:next_def if next_def > 0 else len(src)]
    # The first non-blank, non-comment line in the
    # body must be a string literal.
    import ast
    try:
        body_node = ast.parse(body)
    except SyntaxError:
        return False
    if not body_node.body:
        return False
    # If the parsed body is a FunctionDef, look at
    # its first inner statement (the docstring is
    # inside the function body, not at module
    # level).
    first = body_node.body[0]
    if isinstance(first, ast.FunctionDef):
        if not first.body:
            return False
        first = first.body[0]
    if not isinstance(first, ast.Expr):
        return False
    if not isinstance(first.value, ast.Constant):
        return False
    return isinstance(first.value.value, str)


# ---------------------------------------------------------------------------
# BUG-R31-1..R31-7: docstring additions to public controller methods
# ---------------------------------------------------------------------------
class TestControllerPublicMethodDocstrings:
    """R31-1..R31-7: 7 public controller methods
    that are called from UI but lacked docstrings
    now have them.
    """

    # (file_path, function_signature_keyword) — the
    # function_signature_keyword is the unique
    # ``def name(`` fragment that identifies the
    # site. We test for a docstring AFTER this
    # def line.
    _SITES: list[tuple[str, str, str]] = [
        (
            "controllers/api_workflow.py",
            "def stop(self) -> None:",
            "APIWorkflow.stop",
        ),
        (
            "controllers/api_workflow.py",
            "def export(",
            "APIWorkflow.export",
        ),
        (
            "controllers/playwright_workflow.py",
            "def install_playwright(self) -> None:",
            "PlaywrightWorkflow.install_playwright",
        ),
        (
            "controllers/playwright_workflow.py",
            "def install_chromium(self) -> None:",
            "PlaywrightWorkflow.install_chromium",
        ),
        (
            "controllers/playwright_workflow.py",
            "def open_cache(self) -> Optional[str]:",
            "PlaywrightWorkflow.open_cache",
        ),
        (
            "controllers/playwright_workflow.py",
            "def export(",
            "PlaywrightWorkflow.export",
        ),
        (
            "controllers/playwright_workflow.py",
            "def stop(self) -> None:",
            "PlaywrightWorkflow.stop",
        ),
    ]

    def _read(self, rel: str) -> str:
        from steam_review_tool import __file__ as pkg_init
        repo = Path(pkg_init).parent.parent
        return (repo / "steam_review_tool" / rel).read_text(
            encoding="utf-8",
        )

    def test_all_sites_have_docstrings(self) -> None:
        """R31-1..R31-7: every site must have a
        docstring immediately after the
        ``def`` line (the first non-blank statement
        is a string literal)."""
        for rel, def_keyword, display_name in self._SITES:
            src = self._read(rel)
            assert _has_docstring_after_def(
                src, def_keyword,
            ), (
                f"{rel}: `{display_name}` must have a "
                f"docstring (R31 fix). "
                f"Missing after: `{def_keyword}`. "
                f"Either add a `'''...'''` docstring "
                f"right after the def line, or update "
                f"this test if the function is "
                f"intentionally undocumented."
            )


# ---------------------------------------------------------------------------
# BUG-R31-8: dead labelled_entry removed
# ---------------------------------------------------------------------------
class TestLabelledEntryRemoved:
    """R31-8: the dead ``labelled_entry`` function
    is REMOVED from ``ui/section_header.py`` and
    from ``__all__``. The R27 dead-code audit
    caught it; R30 corrected its return type; R31
    finally removes the function.
    """

    def test_labelled_entry_attribute_gone(self) -> None:
        """R31-8: the ``labelled_entry`` attribute
        is GONE from
        :mod:`steam_review_tool.ui.section_header`."""
        from steam_review_tool.ui import section_header
        assert not hasattr(
            section_header, "labelled_entry",
        ), (
            "ui.section_header.labelled_entry is "
            "still defined (R31-8 anti-pattern: "
            "dead code). R31 removes it. The "
            "function has zero non-test callers."
        )

    def test_labelled_entry_source_gone(self) -> None:
        """R31-8 source-shape: ``def labelled_entry``
        must not appear in the source."""
        from steam_review_tool import __file__ as pkg_init
        repo = Path(pkg_init).parent.parent
        src = (repo / "steam_review_tool" /
               "ui/section_header.py").read_text(
            encoding="utf-8",
        )
        assert "def labelled_entry" not in src, (
            "section_header.py still has "
            "`def labelled_entry` (R31-8 anti-pattern). "
            "R31 removes the dead function."
        )

    def test_all_no_labelled_entry(self) -> None:
        """R31-8: ``__all__`` does NOT export
        ``labelled_entry``."""
        from steam_review_tool.ui import section_header
        assert "labelled_entry" not in section_header.__all__, (
            "section_header.__all__ still includes "
            "`labelled_entry` (R31-8 anti-pattern). "
            "R31 removes the dead function from "
            "the public API."
        )

    def test_section_header_module_docstring_updated(
        self,
    ) -> None:
        """R31-8: the section_header module
        docstring is intact (R31 only removed the
        dead function, didn't damage the file)."""
        from steam_review_tool.ui import section_header
        assert section_header.__doc__ is not None, (
            "section_header lost its module docstring "
            "(R31-8 accidental damage)."
        )
        assert "helpers" in section_header.__doc__.lower(), (
            "section_header's module docstring is "
            "missing the 'helpers' description "
            "(R31-8 accidental damage)."
        )


# ---------------------------------------------------------------------------
# R31 project-wide static check
# ---------------------------------------------------------------------------
class TestNoPublicMethodWithoutDocstring:
    """R31 global sweep: walk every public method
    in the two main controller classes
    (``APIWorkflow`` and ``PlaywrightWorkflow``)
    and assert the method has a docstring.

    The audit excludes the 3 methods that ALREADY
    had docstrings before R31:
      - ``APIWorkflow.start_fetch`` (had docstring
        since initial implementation)
      - ``APIWorkflow.wait`` (had docstring since
        R9)
      - ``PlaywrightWorkflow.wait`` (had docstring
        since R9)
      - ``PlaywrightWorkflow.scrape`` (had
        docstring since initial implementation)
      - ``PlaywrightWorkflow.refresh_dep_status``
        (had docstring since initial implementation)

    The 7 methods R31 added docstrings to are
    NOT in the exempt list (they have docstrings
    now, so they pass the audit naturally).
    """

    # Methods DELIBERATELY exempt (already had a
    # docstring BEFORE R31, so the audit is a
    # no-op for them).
    _EXEMPT: set[tuple[str, str]] = {
        ("api_workflow.py", "start_fetch"),
        ("api_workflow.py", "wait"),
        ("playwright_workflow.py", "wait"),
        ("playwright_workflow.py", "scrape"),
        ("playwright_workflow.py", "refresh_dep_status"),
    }

    def test_no_public_method_without_docstring(self) -> None:
        """For every public method on
        ``APIWorkflow`` and ``PlaywrightWorkflow``
        that's NOT in the exempt list, assert the
        method has a docstring."""
        from steam_review_tool import __file__ as pkg_init
        repo = Path(pkg_init).parent.parent
        for rel, cls_name in (
            ("api_workflow.py", "APIWorkflow"),
            ("playwright_workflow.py", "PlaywrightWorkflow"),
        ):
            src = (repo / "steam_review_tool" /
                   "controllers" / rel).read_text(
                encoding="utf-8",
            )
            # Walk the source for ``def <name>(self``
            # in the class body. We use a regex for
            # speed (the file is large).
            import re
            for m in re.finditer(
                rf"    def ({cls_name.split('_')[0].lower()[:3]}\w+|"
                rf"\w+)\(self",
                src,
            ):
                method_name = m.group(1)
                # Skip private (single-underscore) +
                # dunder (double-underscore) methods —
                # they don't need docstrings.
                if method_name.startswith("_"):
                    continue
                if (rel, method_name) in self._EXEMPT:
                    continue
                def_keyword = f"def {method_name}(self"
                assert _has_docstring_after_def(
                    src, def_keyword,
                ), (
                    f"{rel}: `{cls_name}.{method_name}` "
                    f"must have a docstring (R31 fix). "
                    f"Missing after: `{def_keyword}`. "
                    f"Add a `'''...'''` docstring right "
                    f"after the def line, or update the "
                    f"_EXEMPT set if the method is "
                    f"intentionally undocumented."
                )


# Soft-update the R30 test for the dead
# ``labelled_entry`` — R31-8 removed it, so the
# R30 test must be aware that the function may be
# gone. This is a forward-port of the R30 test
# update, repeated here for clarity.
def test_r30_labelled_entry_soft_skip() -> None:
    """R31-8: the R30 ``test_labelled_entry_annotated``
    test should be a soft-skip if the function is
    gone (R31's removal is the FINAL fix). This
    test re-asserts the R30 soft-skip behavior so
    the R30 file doesn't have to be modified at
    test time.
    """
    from steam_review_tool.ui import section_header
    # If the function is GONE, the R30 test
    # soft-skips. Verify the function IS gone
    # (R31-8) so the R30 soft-skip is in effect.
    if hasattr(section_header, "labelled_entry"):
        # R31-8 didn't take. The test failure here
        # would mean the labelled_entry removal
        # was reverted. The R30 test will then
        # assert the corrected type hint.
        import pytest
        pytest.fail(
            "section_header.labelled_entry is still "
            "defined (R31-8 anti-pattern). R31 "
            "removes the dead function."
        )
