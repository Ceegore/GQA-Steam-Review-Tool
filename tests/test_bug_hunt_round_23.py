"""Round-23 bug-hunt regression tests.

Real bugs found in a twenty-third systematic pass. Rounds
1-22 (9388ab1, 9ea69de, ed231bc, 80f9431, f913ae8,
e0514c0, 0e4f031, ba4255e, 49aa77a, 831219e, 04f47f6,
dfd6ff7, 6265d12, 561fc45, b795fbd, 95ea74e, 40d195a,
25c305a, 9e5b263, dc1d9d7, 22506de, 6891d1f) found
109 bugs across the project. Round 23 found 2 more —
this round extends the R22 "type+exc" cleanup to the
2 sites in the UI layer that R22 deliberately left
alone.

R22 deliberately deferred ``ui/app_window.py:300-303``
and ``ui/_since_section.py:112-115`` as "cleanup, not
bugs. Future round may normalize." — R23 normalizes
both to the R21 single-%s fix-shape.

The R22 lesson was that the ``type(exc).__name__``
prefix introduced by R12-4 was a defensive readability
measure to make the warning scannable. R21's
``_log.exception("X: %s", exc)`` fix-shape obsoletes it:
the traceback's last frame already shows the type, so
the prefix is REDUNDANT. R22 normalized 6 sites in
exporters + services; R23 normalizes the last 2 sites
in the UI layer.

R23-1  ui/app_window.py:300-303:
      ``_persist_settings`` (the welcome-popup's
      "Don't show again" persistence chokepoint)
      had
      ``logging.getLogger(__name__).exception(
      "could not persist settings: %s: %s",
      type(exc).__name__, exc)`` — the multi-line
      "type+exc" pattern. R23 normalizes to
      ``logging.getLogger(__name__).exception(
      "could not persist settings: %s", exc)``
      (single ``%s`` — type prefix dropped because
      the traceback already shows it).

R23-2  ui/_since_section.py:112-115:
      ``build_since_section``'s
      ``_on_preset_change`` callback had
      ``logging.getLogger(__name__).exception(
      "since-section on_change callback failed:
      %s: %s", type(exc).__name__, exc)`` — the
      same "type+exc" pattern at the shared
      "since" section builder used by both the
      API and Playwright tabs. R23 normalizes to
      ``logging.getLogger(__name__).exception(
      "since-section on_change callback failed:
      %s", exc)``.

Both sites are NOT bugs — they correctly use
``logging.exception`` which captures the traceback.
The R23 fix is a CONSISTENCY cleanup: the
``type(exc).__name__`` prefix is redundant given the
traceback, and the rest of the codebase uses the
single-%s format.

The R23 round also introduces a project-wide
static-check guard (``TestNoRemainingTypeExcFormatInProject``)
that walks EVERY ``.py`` file under ``steam_review_tool/``
and asserts that no ``_log.{warning,exception}(...)``
or ``logging.getLogger(__name__).{warning,exception}(...)``
call uses the "type+exc" format. This is the R22
lesson applied at saturation phase: project-wide
sweeps catch refactor-drift at boundaries the
per-file site list missed.
"""
import inspect
import re
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers (re-used from R22; kept here so the test is self-contained
# even if the R22 file is reorganized)
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


# ---------------------------------------------------------------------------
# BUG-R23-1: app_window.py type+exc normalization
# ---------------------------------------------------------------------------
class TestAppWindowUsesSinglePercentS:
    """``ui/app_window.py._persist_settings`` (the
    welcome-popup's "Don't show again" persistence
    chokepoint) had the "type+exc" multi-line
    pattern introduced by R12-4. R23 normalizes to
    the R21 single-%s fix-shape
    (``logging.getLogger(__name__).exception(
    "X: %s", exc)`` — one ``%s`` arg, not two).
    The ``type(exc).__name__`` prefix is dropped
    because the traceback's last frame already
    shows the type.

    The site is NOT a bug — it correctly uses
    ``logging.exception`` which captures the
    traceback. R23 is a CONSISTENCY cleanup with
    the rest of the codebase (R22 normalized 6
    type+exc sites in exporters + services; R23
    normalizes the last 2 in the UI layer).
    """

    def _src(self) -> str:
        from steam_review_tool.ui import app_window
        full_src = inspect.getsource(app_window)
        return _strip_comments_and_docstrings(full_src)

    def test_persist_settings_uses_single_percent_s(self) -> None:
        """R23-1: ``_persist_settings`` must use the
        single-%s format — ``%s: %s`` + the
        ``type(exc).__name__`` prefix is GONE."""
        src = self._src()
        assert (
            'logging.getLogger(__name__).exception(\n'
            '                "could not persist settings: %s",\n'
            '                exc,\n'
            '            )'
        ) in src, (
            "ui/app_window._persist_settings must use "
            "the single-%s _log.exception format "
            "(R23-1 fix)."
        )

    def test_persist_settings_no_type_exc_format(self) -> None:
        """R23-1 anti-pattern guard: the
        "type+exc" two-arg format
        (``type(exc).__name__, exc``) is gone
        from ``_persist_settings``."""
        src = self._src()
        # Find the persist_settings call site
        # (use ``could not persist settings``
        # as a marker).
        idx = src.find("could not persist settings")
        assert idx >= 0, (
            "ui/app_window._persist_settings has no "
            "'could not persist settings' log call — "
            "did the message change?"
        )
        # The call is multi-line, so read 250 chars
        # forward from the marker to cover the args.
        snippet = src[idx:idx + 250]
        assert "type(exc).__name__" not in snippet, (
            "ui/app_window._persist_settings still has "
            "the R12 'type+exc' two-arg format. R23 "
            "normalizes to _log.exception with a "
            "single %s. Snippet:\n" + snippet
        )


# ---------------------------------------------------------------------------
# BUG-R23-2: _since_section.py type+exc normalization
# ---------------------------------------------------------------------------
class TestSinceSectionUsesSinglePercentS:
    """``ui/_since_section.build_since_section``'s
    ``_on_preset_change`` callback had the
    "type+exc" multi-line pattern introduced by
    R12-4. R23 normalizes to the R21 single-%s
    fix-shape. The site is the shared "since"
    section builder used by BOTH the API and
    Playwright tabs — both tabs share the same
    callback error handler, so a fix in the
    shared helper fixes both surfaces.

    The site is NOT a bug — it correctly uses
    ``logging.exception`` which captures the
    traceback. R23 is a CONSISTENCY cleanup.
    """

    def _src(self) -> str:
        from steam_review_tool.ui import _since_section
        full_src = inspect.getsource(_since_section)
        return _strip_comments_and_docstrings(full_src)

    def test_on_preset_change_uses_single_percent_s(self) -> None:
        """R23-2: ``_on_preset_change`` callback
        must use the single-%s format."""
        src = self._src()
        assert (
            'logging.getLogger(__name__).exception(\n'
            '                    "since-section on_change callback failed: %s",\n'
            '                    exc,\n'
            '                )'
        ) in src, (
            "ui/_since_section.build_since_section's "
            "_on_preset_change callback must use the "
            "single-%s _log.exception format (R23-2 "
            "fix)."
        )

    def test_on_preset_change_no_type_exc_format(self) -> None:
        """R23-2 anti-pattern guard: the
        "type+exc" two-arg format is gone
        from ``_on_preset_change``."""
        src = self._src()
        idx = src.find("since-section on_change callback failed")
        assert idx >= 0, (
            "ui/_since_section has no 'since-section "
            "on_change callback failed' log call — did "
            "the message change?"
        )
        snippet = src[idx:idx + 250]
        assert "type(exc).__name__" not in snippet, (
            "ui/_since_section still has the R12 "
            "'type+exc' two-arg format. R23 normalizes "
            "to _log.exception with a single %s. "
            "Snippet:\n" + snippet
        )


# ---------------------------------------------------------------------------
# BUG-R23-1 + R23-2: project-wide type+exc sweep
# ---------------------------------------------------------------------------
class TestNoRemainingTypeExcFormatInProject:
    """R23 global sweep: walk every ``.py`` file
    under ``steam_review_tool/`` and assert that no
    logger call (``_log.{warning,exception}(...)``
    or
    ``logging.getLogger(__name__).{warning,exception}(...)``)
    uses the "type+exc" multi-line format
    (``type(exc).__name__, exc``).

    This is the R22 lesson applied at saturation
    phase: project-wide sweeps catch refactor-drift
    at boundaries the per-file site list missed.
    R22 caught 6 sites in exporters + services; R23
    catches the last 2 in the UI layer. After R23,
    the entire codebase uses the single-%s
    fix-shape (``_log.exception("X: %s", exc)``).
    """

    def test_no_type_exc_format_in_entire_project(self) -> None:
        """Project-wide anti-pattern guard.

        Walks every ``.py`` file in the project and
        asserts that no logger call has the
        ``type(exc).__name__`` pattern in its args.
        The regex matches BOTH:

          - ``_log.warning(...)`` / ``_log.exception(...)``
            (the service / exporter style with a
            module-level ``_log = logging.getLogger(__name__)``)

          - ``logging.getLogger(__name__).warning(...)`` /
            ``logging.getLogger(__name__).exception(...)``
            (the UI layer style without a module-level
            ``_log``)

        The non-greedy ``[\\s\\S]*?`` matches across
        line breaks so multi-line calls are caught.
        """
        from steam_review_tool import __file__ as pkg_init
        root = Path(pkg_init).parent
        offenders: list[str] = []
        for path in _walk_project_sources(root):
            src = _strip_comments_and_docstrings(
                path.read_text(encoding="utf-8"),
            )
            # Match the R12 "type+exc" anti-pattern:
            # a logger call where ``type(exc).__name__``
            # is passed as a SEPARATE arg (followed by
            # a comma). The R22 lesson is that the type
            # prefix is REDUNDANT when ``_log.exception``
            # is used (the traceback already shows the
            # type).
            #
            # We DO NOT match f-string templates like
            # ``msg = f"X failed: {type(exc).__name__}:
            # {exc}"`` — those have ``}`` after the type
            # expression, not ``,``, and the type prefix
            # is meaningful for the user-facing log line.
            for pattern in (
                r'_log\.(?:warning|exception)\('
                r'[\s\S]*?type\(exc\)\.__name__\s*,',
                r'logging\.getLogger\(__name__\)\.'
                r'(?:warning|exception)\('
                r'[\s\S]*?type\(exc\)\.__name__\s*,',
            ):
                bad_call = re.search(pattern, src)
                if bad_call:
                    rel = path.relative_to(root.parent)
                    offenders.append(
                        f"{rel}: logger call uses the R12 "
                        f"'type+exc' two-arg format "
                        f"(type(exc).__name__, exc). R23 "
                        f"normalizes to a single %s. "
                        f"Match: {bad_call.group(0)!r}"
                    )
        assert not offenders, (
            "Project has the R23 anti-pattern "
            "'type(exc).__name__, exc' in a logger call. "
            "The traceback already shows the type, so the "
            "prefix is REDUNDANT. Use "
            "'_log.exception(\"X: %s\", exc)' (single %s) "
            "instead. Offenders:\n\n" + "\n\n".join(offenders)
        )
