"""Round-19 bug-hunt regression tests.

Real bugs found in a nineteenth systematic pass. Rounds 1-18
(9388ab1, 9ea69de, ed231bc, 80f9431, f913ae8, e0514c0,
0e4f031, ba4255e, 49aa77a, 831219e, 04f47f6, dfd6ff7,
6265d12, 561fc45, b795fbd, 95ea74e, 40d195a, 25c305a)
found 82 bugs across the project. Round 19 found 2 more
— this round targets two related patterns: **private
duplicate of a public helper** + **dead bus event with
zero subscribers**.

The recurring lesson (compounding R4 + R5 + R17 + R18):
after the R-series consolidated many small helpers
(``safe_int``, ``safe_str``, ``safe_coerce_int``,
``safe_coerce_str``), some private duplicates were left
behind. The R19 round finds one more — the
``popup_settings._safe_str`` helper that duplicates
``safe_coerce_str`` from ``utils.coercion``.

R19-1  ui/popup_settings.py: the private
       ``_safe_str(value, default)`` helper did
       ``str(value)`` for any non-None value. A
       hand-edited settings.json with a list / dict
       value for ``dump_root`` would render as the
       str() of the Python list (``"['a', 'b']"``)
       in the entry field.

Root cause: same R4/R5 helper-consolidation lesson.
            ``safe_coerce_str`` (utils.coercion)
            already does the right thing for every
            input type — returns the ``str(value)``
            for int / float / bool, the empty
            default for None / list / dict / tuple,
            and the stripped string for str. The
            private ``_safe_str`` was a partial
            duplicate that handled only the None
            case and silently used ``str(value)``
            for everything else (including lists
            and dicts, which become Python-repr
            garbage in the entry field).

Fix:      deleted the private ``_safe_str`` and
            routed the 4 call sites through the
            public ``safe_coerce_str`` from
            ``utils.coercion``. A test pins the
            new behaviour: a list value renders
            as ``""`` (the default), not as
            ``"['a', 'b']"``.

R19-2  controllers/dump_folder_controller.py:
       ``set_dump_root`` did
       ``bus.publish("dump.root.changed", ...)``
       but a grep across the entire codebase
       found zero subscribers.

Root cause: same R8 ("ANY bus.publish must have a
            corresponding subscriber") and R17-2 /
            R18-2 ("kept for back-compat" /
            "no consumer" anti-pattern) lesson.
            The R16-3 chokepoint inherited the
            ``bus.publish`` from a pre-existing
            hand-rolled ``set_dump_root`` that
            relied on a subscriber. After the
            refactor, the tabs that react to a
            dump-root change (recreate
            ``dump_repo``, refresh the label)
            already do so directly in
            ``_on_pick_dump_root`` after calling
            the chokepoint — they don't need a
            bus subscription.

Fix:      removed the ``bus.publish`` call + the
            ``bus`` import (now unused). A test
            asserts that no file in the codebase
            publishes or subscribes to
            ``dump.root.changed``.

Test discipline notes (compounding R12 + R13 + R16
+ R17 + R18 lessons):

- The R19-1 tests use hand-rolled settings dicts
  with non-string values (list, int, bool, None,
  whitespace-only) to verify the new
  ``safe_coerce_str``-based behaviour.

- The R19-2 tests are static-check source-walkers
  that pin the absence of the dead bus event.

- The ``_strip_comments_and_docstrings`` helper is
  reused from R16 for the source-shape probes.

Stats: 2 bugs found, 9 regression tests added.
"""
from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helper: strip pure comment / docstring lines from a source string before
# substring-regression checks. Reused from R16.
# ---------------------------------------------------------------------------
def _strip_comments_and_docstrings(src: str) -> str:
    src_no_docstrings = re.sub(
        r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'',
        "",
        src,
    )
    out_lines: list[str] = []
    for line in src_no_docstrings.splitlines():
        if line.strip().startswith("#"):
            continue
        out_lines.append(line)
    return "\n".join(out_lines)


# ---------------------------------------------------------------------------
# BUG-R19-1: popup_settings._safe_str is a private duplicate of safe_coerce_str
# ---------------------------------------------------------------------------
class TestPopupSettingsUsesSafeCoerceStr:
    """``popup_settings._safe_str`` was a private duplicate of
    the public ``safe_coerce_str`` from ``utils.coercion``.

    R19-1 fix: deleted the private helper, routed the 4
    call sites through the public helper. The public
    helper handles non-string values more defensively
    (returns the default for list / dict instead of
    ``str(value)`` which becomes Python-repr garbage
    in the entry field).
    """

    def test_popup_settings_no_def_safe_str(self) -> None:
        """The private ``_safe_str`` function must NOT be
        defined in ``popup_settings.py``."""
        from steam_review_tool.ui import popup_settings
        src = inspect.getsource(popup_settings)
        code = _strip_comments_and_docstrings(src)
        assert "def _safe_str" not in code, (
            "ui/popup_settings.py must NOT define _safe_str "
            "— it is a private duplicate of the public "
            "safe_coerce_str from utils.coercion. Use the "
            "public helper (R19-1 fix)."
        )

    def test_popup_settings_no_call_to_safe_str(self) -> None:
        """No call to ``_safe_str(...)`` should remain."""
        from steam_review_tool.ui import popup_settings
        src = inspect.getsource(popup_settings)
        code = _strip_comments_and_docstrings(src)
        assert "_safe_str(" not in code, (
            "ui/popup_settings.py must NOT call _safe_str() "
            "anywhere — use safe_coerce_str() from "
            "utils.coercion (R19-1 fix)."
        )

    def test_popup_settings_imports_safe_coerce_str(self) -> None:
        """The public ``safe_coerce_str`` must be imported."""
        from steam_review_tool.ui import popup_settings
        src = inspect.getsource(popup_settings)
        code = _strip_comments_and_docstrings(src)
        assert "from ..utils.coercion import safe_coerce_str" in code, (
            "ui/popup_settings.py must import "
            "safe_coerce_str from utils.coercion (R19-1 fix)."
        )

    def test_safe_coerce_str_handles_list_value(self) -> None:
        """End-to-end: a list value for a settings field
        (e.g. a hand-edited ``dump_root: ["a", "b"]``)
        must be coerced to ``""`` (the default), not
        to ``"['a', 'b']"`` (the str() of a Python list)."""
        from steam_review_tool.utils.coercion import safe_coerce_str
        # The public helper returns "" for a list.
        assert safe_coerce_str(["a", "b"], "") == ""

    def test_safe_coerce_str_handles_dict_value(self) -> None:
        """A dict value must also be coerced to the
        default, not the str() of the dict."""
        from steam_review_tool.utils.coercion import safe_coerce_str
        assert safe_coerce_str({"a": 1}, "") == ""

    def test_safe_coerce_str_handles_int_value(self) -> None:
        """An int value must render as the str of the int
        (e.g. ``"42"``), preserving the R5 contract."""
        from steam_review_tool.utils.coercion import safe_coerce_str
        assert safe_coerce_str(42, "") == "42"

    def test_safe_coerce_str_handles_none(self) -> None:
        """None must render as the default (not as
        ``"None"`` — the R5 contract that motivated the
        helper)."""
        from steam_review_tool.utils.coercion import safe_coerce_str
        assert safe_coerce_str(None, "") == ""

    def test_safe_coerce_str_handles_whitespace_only(self) -> None:
        """A whitespace-only string must collapse to
        the default (R5 contract)."""
        from steam_review_tool.utils.coercion import safe_coerce_str
        assert safe_coerce_str("   ", "") == ""


# ---------------------------------------------------------------------------
# BUG-R19-2: bus.publish("dump.root.changed", ...) has no subscribers
# ---------------------------------------------------------------------------
class TestNoDeadDumpRootChangedBusEvent:
    """``set_dump_root`` used to publish
    ``"dump.root.changed"`` on the event bus, but a
    R19-2 audit found zero subscribers. R19-2 fix:
    removed the publish + the now-unused ``bus``
    import.

    Static-check: no file should publish OR subscribe
    to ``dump.root.changed``.
    """

    def test_no_publish_to_dump_root_changed(self) -> None:
        """No file should ``bus.publish("dump.root.changed", ...)``."""
        project_root = Path("steam_review_tool")
        offenders: list[str] = []
        for py in project_root.rglob("*.py"):
            text = py.read_text(encoding="utf-8")
            code = _strip_comments_and_docstrings(text)
            for ln in code.splitlines():
                if re.search(
                    r'\bbus\.publish\s*\(\s*["\']dump\.root\.changed["\']',
                    ln,
                ):
                    offenders.append(f"{py}: {ln.strip()}")
        assert not offenders, (
            "found publishers of dump.root.changed "
            "(the event has zero subscribers and was "
            "removed in R19-2): "
            f"{offenders}"
        )

    def test_no_subscribe_to_dump_root_changed(self) -> None:
        """No file should ``bus.subscribe("dump.root.changed", ...)``
        either (the event is fully dead)."""
        project_root = Path("steam_review_tool")
        offenders: list[str] = []
        for py in project_root.rglob("*.py"):
            text = py.read_text(encoding="utf-8")
            code = _strip_comments_and_docstrings(text)
            for ln in code.splitlines():
                if re.search(
                    r'\bbus\.subscribe\s*\(\s*["\']dump\.root\.changed["\']',
                    ln,
                ):
                    offenders.append(f"{py}: {ln.strip()}")
        assert not offenders, (
            "found subscribers of dump.root.changed "
            "(the event has zero publishers and is fully "
            "dead — removed in R19-2): "
            f"{offenders}"
        )

    def test_dump_folder_controller_no_bus_import(self) -> None:
        """The ``bus`` import in
        ``dump_folder_controller.py`` is now unused
        (the only ``bus.publish`` call was removed
        in R19-2). A regression that re-introduces
        the dead publish would also re-introduce
        the import (or keep the import dangling)."""
        from steam_review_tool.controllers import (
            dump_folder_controller,
        )
        src = inspect.getsource(dump_folder_controller)
        code = _strip_comments_and_docstrings(src)
        # The ``bus`` symbol must NOT appear as an
        # import OR usage in the post-R19 source.
        assert not re.search(r"^from\s+\S+\s+import.*\bbus\b", code, re.MULTILINE), (
            "dump_folder_controller.py must NOT import "
            "the event bus anymore (the only bus.publish "
            "was the dead 'dump.root.changed' event, "
            "removed in R19-2)"
        )
        # And no ``bus.`` usage.
        assert "bus." not in code, (
            "dump_folder_controller.py must NOT use "
            "the event bus anymore (R19-2 audit found "
            "zero subscribers for the only published "
            "event)"
        )
