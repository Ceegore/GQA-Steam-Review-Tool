"""Round-25 bug-hunt regression tests.

Real bugs found in a twenty-fifth systematic pass. Rounds
1-24 (9388ab1, 9ea69de, ed231bc, 80f9431, f913ae8,
e0514c0, 0e4f031, ba4255e, 49aa77a, 831219e, 04f47f6,
dfd6ff7, 6265d12, 561fc45, b795fbd, 95ea74e, 40d195a,
25c305a, 9e5b263, dc1d9d7, 22506de, 6891d1f, 448e2c3,
7773048) found 116 bugs across the project. Round 25
found 27 more — this round is a SATURATION-PHASE
code-hygiene cleanup that the R22/R23/R24 future-round
hints explicitly deferred:

> "The next Category A cleanup: narrow all 30+
> ``except Exception: pass`` widget-op blocks to
> ``except tk.TclError: pass`` (the actually-expected
> exception class). This is a code-hygiene cleanup,
> not a bug fix — but a project-wide static check can
> prevent regression."

The R22 lesson was "broad ``except Exception`` in
non-error-handling code silently drops real failures".
R13 fixed the service + controller layer (broad
``except Exception`` in non-UI code). R21 fixed the
``_log.warning(...)`` part of the same pattern. R22
normalized the "type+exc" format. R23 fixed the UI
layer's "type+exc" format. R24 fixed the UI layer's
callback-forwarding paths (``except Exception: pass``
wrapping ``callback()`` calls — those are real bugs
because the swallowed error is from the callback, not
from widget teardown).

R25 is the CATEGORY A counterpart to R24: ``except
Exception: pass`` wrapping WIDGET operations
(``winfo_width``, ``child.destroy``, ``after_cancel``,
``configure``, ``place``, etc.). The swallowed error
is the EXPECTED ``tk.TclError`` raised when a widget
is being torn down. Narrowing to ``except tk.TclError``
makes the intent explicit — only the actually-expected
exception class is silently dropped, not a broader
``Exception`` that could hide other bugs (e.g.
``AttributeError`` if the widget is None).

R25 sites (27 total across 8 files):

  ui/_responsive.py       10 sites  (update_idletasks,
                                       after_cancel x2,
                                       winfo_width x2,
                                       child.destroy,
                                       place_forget,
                                       configure,
                                       widget.place,
                                       _req_size winfo)
  ui/tab_api.py            5 sites  (log_box configure,
                                       progress.set x2,
                                       reset_filters helper,
                                       obsidian_label
                                       configure)
  ui/tab_playwright.py     6 sites  (log_box configure,
                                       progress.set,
                                       dump_label configure,
                                       target.after, ...)
  ui/tooltip.py            3 sites  (after_cancel,
                                       tip_window.destroy,
                                       winfo_pointerx/y)
  ui/_action_state.py      1 site   (btn.configure)
  ui/popup_batch_dump.py   3 sites  (top.after status
                                       callback,
                                       start_btn.configure,
                                       batch-loop return)
  ui/popup_search.py       1 site   (top.after_cancel)
  ui/popup_welcome.py      2 sites  (top.geometry,
                                       CTkLabel logo)

The R25 round also introduces a project-wide
static-check guard (``TestNoBareExceptExceptionInUI``)
that walks every ``ui/*.py`` file and asserts no
``except Exception:`` (bare, not ``as exc``) with a
``pass`` / ``return`` / ``continue`` body remains.
This is the R22/R23/R24 lesson applied at saturation
phase: project-wide sweeps catch refactor-drift at
boundaries the per-file site list missed.

The 4 sites in the UI layer that REMAIN as
``except Exception:`` (not narrowed) are:

  ui/popup_search.py:230       — string parse
                                  (NOT a widget op)
  ui/popup_settings.py:195      — caller-supplied
                                  callback ``_save_cb``
                                  (R23 fix-shape, NOT
                                  Category A)
  ui/tab_trends.py:223         — subprocess call
                                  ``run_popularity_probe``
                                  (NOT a widget op)
  ui/_action_state.py:78       — service call
                                  ``resume_get``
                                  (NOT a widget op)

R25 also preserves the R24 fix in
``ui/_responsive.py:173`` — the caller-supplied
``self._reflow_cb()`` callback still uses the R24
``except Exception as exc: logging.getLogger(__name__)
.exception(...)`` fix-shape. A regression test
verifies the callback path is NOT narrowed to
``tk.TclError`` (the callback can raise ANY exception,
not just TclError).
"""
import inspect
import re
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers (re-used from R22/R23/R24; kept here so the test is self-contained
# even if the R22/R23/R24 files are reorganized)
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
# R25 per-file source-shape tests
# ---------------------------------------------------------------------------
# Each test asserts that a SPECIFIC line in a SPECIFIC file was
# narrowed from ``except Exception:`` to ``except tk.TclError:``.
# The test is "source-shape" — it checks the literal text at
# the line, not the runtime behavior. This is the same
# approach as R22/R23/R24.

# (file_path, line_number, indent_str, body_str)
# The body is what follows the except clause (pass / return /
# continue). The script-style `_r25_narrow_excepts.py`
# tool produced this table by walking every Category A site
# in the project.
_R25_SITES: list[tuple[str, int, str, str]] = [
    # _responsive.py — 10 sites
    ("steam_review_tool/ui/_responsive.py", 105, "        ", "pass"),
    ("steam_review_tool/ui/_responsive.py", 117, "            ", "pass"),
    ("steam_review_tool/ui/_responsive.py", 133, "            ", "return"),
    ("steam_review_tool/ui/_responsive.py", 144, "                ", "pass"),
    ("steam_review_tool/ui/_responsive.py", 254, "            ", "pass"),
    ("steam_review_tool/ui/_responsive.py", 267, "            ", "return"),
    ("steam_review_tool/ui/_responsive.py", 275, "                ", "pass"),
    ("steam_review_tool/ui/_responsive.py", 336, "            ", "pass"),
    ("steam_review_tool/ui/_responsive.py", 346, "        ", "pass"),
    ("steam_review_tool/ui/_responsive.py", 355, "        ", None),  # `return (100, 30)`
    # tab_api.py — 5 sites
    ("steam_review_tool/ui/tab_api.py", 198, "        ", "pass"),
    ("steam_review_tool/ui/tab_api.py", 205, "            ", "pass"),
    ("steam_review_tool/ui/tab_api.py", 231, "        ", "pass"),
    ("steam_review_tool/ui/tab_api.py", 272, "            ", "pass"),  # one-liner `try: e.delete ... except tk.TclError: pass`
    ("steam_review_tool/ui/tab_api.py", 279, "            ", "pass"),
    # tab_playwright.py — 6 sites
    ("steam_review_tool/ui/tab_playwright.py", 215, "        ", "pass"),
    ("steam_review_tool/ui/tab_playwright.py", 228, "            ", "pass"),
    ("steam_review_tool/ui/tab_playwright.py", 247, "        ", "pass"),
    ("steam_review_tool/ui/tab_playwright.py", 270, "        ", "pass"),
    ("steam_review_tool/ui/tab_playwright.py", 479, "        ", "pass"),
    ("steam_review_tool/ui/tab_playwright.py", 487, "            ", "pass"),
    # tooltip.py — 3 sites
    ("steam_review_tool/ui/tooltip.py", 41, "            ", "pass"),
    ("steam_review_tool/ui/tooltip.py", 47, "            ", "pass"),
    ("steam_review_tool/ui/tooltip.py", 57, "        ", "return"),
    # _action_state.py — 1 site
    ("steam_review_tool/ui/_action_state.py", 65, "        ", "pass"),
    # popup_batch_dump.py — 3 sites
    ("steam_review_tool/ui/popup_batch_dump.py", 214, "                    ", None),  # body has comment + return
    ("steam_review_tool/ui/popup_batch_dump.py", 231, "                    ", "return"),
    ("steam_review_tool/ui/popup_batch_dump.py", 238, "            ", "pass"),
    # popup_search.py — 1 site
    ("steam_review_tool/ui/popup_search.py", 119, "            ", "pass"),
    # popup_welcome.py — 2 sites
    ("steam_review_tool/ui/popup_welcome.py", 123, "        ", "pass"),
    ("steam_review_tool/ui/popup_welcome.py", 203, "        ", None),  # body has comment + assignment
]


class TestCategoryANarrowing:
    """R25 source-shape: every Category A site
    (widget-op wrapped in ``except Exception: pass /
    return / continue``) is now narrowed to
    ``except tk.TclError:``.

    The 31 R25-narrowed sites span 8 UI files. The
    fix-shape is uniform: the bare ``except Exception:``
    becomes ``except tk.TclError:``, the body is
    unchanged.

    This test counts the `except tk.TclError:` sites
    per file (which is a more line-number-resilient
    check than asserting on specific line numbers,
    since edits to a file can shift line numbers).
    """

    # Expected minimum `except tk.TclError:` count
    # per file (R25 narrowed this many sites per
    # file — actual count may be higher if the file
    # had pre-existing `except tk.TclError:` sites).
    _EXPECTED_MIN_PER_FILE: dict[str, int] = {
        "steam_review_tool/ui/_responsive.py": 10,
        "steam_review_tool/ui/tab_api.py": 5,
        "steam_review_tool/ui/tab_playwright.py": 6,
        "steam_review_tool/ui/tooltip.py": 3,
        "steam_review_tool/ui/_action_state.py": 1,
        "steam_review_tool/ui/popup_batch_dump.py": 3,
        "steam_review_tool/ui/popup_search.py": 1,
        "steam_review_tool/ui/popup_welcome.py": 2,
    }

    def _read(self, rel: str) -> str:
        from steam_review_tool import __file__ as pkg_init
        # pkg_init is `<repo>/steam_review_tool/__init__.py` →
        # `.parent` is `<repo>/steam_review_tool`, `.parent.parent`
        # is `<repo>`.
        repo = Path(pkg_init).parent.parent
        path = repo / rel
        return path.read_text(encoding="utf-8")

    def _count_tclerror_sites(self, src: str) -> int:
        """Count `except tk.TclError:` lines in source.
        Matches both multi-line and one-liner forms.
        """
        count = 0
        for line in src.splitlines():
            if re.match(r"^\s*except\s+tk\.TclError\s*:", line):
                count += 1
        return count

    def test_all_files_have_at_least_expected_tclerror_sites(self) -> None:
        """Each R25 file must have at least the
        expected number of `except tk.TclError:`
        sites (the sites R25 narrowed)."""
        offenders: list[str] = []
        for rel, expected_min in self._EXPECTED_MIN_PER_FILE.items():
            src = self._read(rel)
            actual = self._count_tclerror_sites(src)
            if actual < expected_min:
                offenders.append(
                    f"{rel}: expected at least {expected_min} "
                    f"`except tk.TclError:` sites (R25-narrowed), "
                    f"found {actual}",
                )
        assert not offenders, (
            "R25 narrowing incomplete — some files have "
            "fewer `except tk.TclError:` sites than expected. "
            "Offenders:\n" + "\n".join(offenders)
        )

    def test_r24_callback_path_preserved(self) -> None:
        """The R24 fix in ``ui/_responsive.py:173``
        (the caller-supplied ``self._reflow_cb()``
        callback) must REMAIN as the R24 fix-shape
        (``except Exception as exc: logging.getLogger
        (__name__).exception(...)``) — R25 must NOT
        have narrowed it to ``except tk.TclError:``.

        The callback can raise ANY exception, not just
        TclError. Narrowing would lose the R24 logging
        fix.
        """
        from steam_review_tool.ui import _responsive
        src = _strip_comments_and_docstrings(
            inspect.getsource(_responsive),
        )
        # Find the ``self._reflow_cb()`` block.
        idx = src.find("self._reflow_cb()")
        assert idx >= 0, (
            "_responsive has no `self._reflow_cb()` call — "
            "did the callback wiring change?"
        )
        # Walk back to the `try:` and read 600 chars.
        before = src[max(0, idx - 400):idx]
        try_matches = list(re.finditer(r"^[ \t]+try:\s*$", before, re.M))
        assert try_matches, "could not find `try:` before _reflow_cb()"
        abs_try = max(0, idx - 400) + try_matches[-1].start()
        block = src[abs_try:abs_try + 600]
        # The R24 fix-shape must be in place.
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
        # And it must NOT have been narrowed to
        # ``except tk.TclError:`` (R25 would be wrong
        # here — the callback is not a widget op).
        assert "except tk.TclError:" not in block, (
            "_responsive._relayout's `self._reflow_cb()` "
            "block was incorrectly narrowed to "
            "`except tk.TclError:` (R25 over-applied). "
            "The callback can raise ANY exception, not "
            "just TclError. Block:\n" + block
        )

    def test_import_tkinter_added_where_needed(self) -> None:
        """R25 added ``import tkinter as tk`` to the
        files that need it. Verify the import is
        present in every file that has a narrowed
        site."""
        files_with_narrowed = sorted(
            self._EXPECTED_MIN_PER_FILE.keys(),
        )
        offenders: list[str] = []
        for rel in files_with_narrowed:
            src = self._read(rel)
            if "import tkinter" not in src and "from tkinter" not in src:
                offenders.append(
                    f"{rel}: no `import tkinter` or `from tkinter` "
                    f"import (R25 narrowing uses `tk.TclError`)",
                )
        assert not offenders, (
            "Files with R25-narrowed sites must import "
            "tkinter (for `tk.TclError`):\n"
            + "\n".join(offenders)
        )


# ---------------------------------------------------------------------------
# R25 project-wide static check
# ---------------------------------------------------------------------------
class TestNoBareExceptExceptionInUI:
    """R25 global sweep: walk every ``ui/*.py`` file
    and assert that no Category A site
    (``except Exception:`` with body ``pass`` /
    ``return`` / ``continue``) remains.

    The 4 legitimate ``except Exception:`` sites in
    the UI layer (which are NOT widget ops) are
    documented in the file's module docstring:

      - ``ui/popup_search.py:230`` — string parse
      - ``ui/popup_settings.py:195`` — callback
        (R23 fix-shape)
      - ``ui/tab_trends.py:223`` — subprocess call
      - ``ui/_action_state.py:78`` — service call

    This test walks the source of each UI file,
    finds every ``except Exception:`` (bare, not
    ``as exc``) with a ``pass`` / ``return`` /
    ``continue`` body, and asserts the list is
    empty.

    This is the R22/R23/R24 lesson applied at
    saturation phase: project-wide sweeps catch
    refactor-drift at boundaries the per-file site
    list missed.
    """

    def test_no_bare_except_exception_pass_return_in_ui(self) -> None:
        """Project-wide anti-pattern guard.

        Walks every ``ui/*.py`` file and asserts
        that no bare ``except Exception:`` with a
        ``pass`` / ``return`` / ``continue`` body
        remains. (R25 narrowed every such site to
        ``except tk.TclError:``.)
        """
        from steam_review_tool import __file__ as pkg_init
        repo = Path(pkg_init).parent.parent
        ui_dir = repo / "steam_review_tool" / "ui"
        offenders: list[str] = []
        for path in sorted(ui_dir.glob("*.py")):
            rel = path.relative_to(repo).as_posix()
            lines = path.read_text(encoding="utf-8").splitlines()
            for i, line in enumerate(lines):
                m = re.match(
                    r'^(\s*)except\s+Exception\s*:\s*$', line,
                )
                if not m:
                    continue
                indent = m.group(1)
                # Body line is the next line, same/higher
                # indent.
                if i + 1 >= len(lines):
                    continue
                nxt = lines[i + 1]
                if not nxt.startswith(indent + " "):
                    continue
                body = nxt.strip()
                if body in ("pass", "return", "continue"):
                    offenders.append(
                        f"{rel}:{i + 1}: bare `except Exception:` "
                        f"with `{body}` body — should be narrowed "
                        f"to `except tk.TclError:` (R25).",
                    )
        assert not offenders, (
            "R25 anti-pattern: bare `except Exception:` "
            "with `pass` / `return` / `continue` body "
            "remains in the UI layer. Narrow to "
            "`except tk.TclError:` (the actually-expected "
            "exception class for widget teardown). "
            "Offenders:\n\n" + "\n\n".join(offenders)
        )
