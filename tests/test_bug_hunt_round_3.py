"""Round-3 bug-hunt regression tests.

Real bugs found in systematic Round-3 scan of the under-covered
modules (``services/``, ``core/``, ``exporters/``, ``controllers/``,
``ui/``). Each test class documents the bug it covers and what the
expected post-fix behaviour is. Tests intentionally avoid the GUI
layer so they run in any headless environment.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# BUG-R3-1: TrendsStore ``dump_root`` parameter was silently ignored
# ---------------------------------------------------------------------------
class TestTrendsStoreNoDumpRoot:
    """``TrendsStore.__init__`` used to accept a ``dump_root`` parameter
    but immediately overwrote ``self.path`` with the module-level
    ``TRENDS_FILE`` constant, so passing the parameter was a no-op
    (and worse, misleading — a caller might think the trends ledger
    was being scoped to a different directory).

    Fix: the constructor now takes no arguments. The test confirms
    the misleading parameter is gone and that ``self.path`` always
    points at the module-level ``TRENDS_FILE``.
    """

    def test_init_takes_no_arguments(self) -> None:
        from steam_review_tool.services.trends_store import TrendsStore
        import inspect

        sig = inspect.signature(TrendsStore.__init__)
        params = [
            p for p in sig.parameters.values()
            if p.name != "self"
        ]
        assert params == [], (
            f"TrendsStore.__init__ should take no args besides self; "
            f"got {[p.name for p in params]}"
        )

    def test_path_is_module_level_constant(self) -> None:
        from steam_review_tool.services import trends_store
        from steam_review_tool.services.trends_store import TRENDS_FILE, TrendsStore

        store = TrendsStore()
        assert store.path == TRENDS_FILE
        assert store.path is trends_store.TRENDS_FILE

    def test_dump_root_kwarg_now_raises(self) -> None:
        """Passing the removed kwarg must fail loudly, not silently
        ignore it. TypeError is the canonical Python error for an
        unexpected keyword argument."""
        from steam_review_tool.services.trends_store import TrendsStore

        with pytest.raises(TypeError):
            TrendsStore(dump_root=Path("/tmp/fake"))


# ---------------------------------------------------------------------------
# BUG-R3-2: filter_controller crashed on None / non-numeric timestamps
# ---------------------------------------------------------------------------
class TestFilterControllerSafeTimestamp:
    """``apply_window_filter`` used ``int(r.get("timestamp_created", 0))``
    in three list comprehensions. The default branch only fires when
    the key is missing — if a review has ``timestamp_created: None``
    (or a non-numeric string from the Apify normaliser), ``int()``
    raised and the whole export crashed.

    Fix: a ``_safe_ts`` helper coerces ``None`` and non-numeric values
    to ``0`` so the function keeps working on malformed rows.
    """

    def test_none_timestamp_does_not_crash_first_24h(self) -> None:
        """The "first 24h" window picks the earliest non-zero ts
        as the anchor and keeps everything within 24h of it. With
        a None row in the mix, the function used to crash on
        ``int(None)``. After the fix it must return a list."""
        from steam_review_tool.controllers.filter_controller import (
            apply_window_filter,
        )
        now = int(time.time())
        reviews = [
            {"timestamp_created": now - 60},
            {"timestamp_created": None},  # malformed row
            {"timestamp_created": now - 120},
        ]
        # Must not raise.
        out = apply_window_filter(reviews, "first 24h")
        assert isinstance(out, list)

    def test_none_timestamp_does_not_crash_last_7d(self) -> None:
        from steam_review_tool.controllers.filter_controller import (
            apply_window_filter,
        )
        now = int(time.time())
        reviews = [
            {"timestamp_created": now - 60},       # recent
            {"timestamp_created": None},            # malformed
            {"timestamp_created": now - 30 * 86400},  # too old
        ]
        out = apply_window_filter(reviews, "last 7d")
        # None → ts=0 < cutoff (now-7d), so the malformed row is
        # correctly excluded. The important guarantee: no crash.
        assert len(out) == 1
        assert out[0]["timestamp_created"] == now - 60

    def test_string_timestamp_does_not_crash(self) -> None:
        """A hand-rolled review with a string timestamp is coerced
        to 0 rather than raising ``ValueError`` from ``int("abc")``."""
        from steam_review_tool.controllers.filter_controller import (
            apply_window_filter,
        )
        now = int(time.time())
        reviews = [
            {"timestamp_created": str(now - 60)},   # valid numeric string
            {"timestamp_created": "not-a-number"},  # malformed string
            {"timestamp_created": now + 60},         # future-dated
        ]
        # Must not raise.
        out = apply_window_filter(reviews, "first 24h")
        assert isinstance(out, list)

    def test_all_passes_through_unchanged(self) -> None:
        """``"all"`` is the short-circuit branch; verify it's untouched."""
        from steam_review_tool.controllers.filter_controller import (
            apply_window_filter,
        )
        reviews = [{"timestamp_created": None}, {"timestamp_created": "x"}]
        assert apply_window_filter(reviews, "all") is reviews


# ---------------------------------------------------------------------------
# BUG-R3-3: per_language_exporter.build_summary stored None as a dict key
# ---------------------------------------------------------------------------
class TestPerLanguageExporterNoneLanguage:
    """``langs[r.get("language", "—")] = ...`` only supplied a default
    when the *key* was missing. Review dicts from some API paths
    include a present ``"language"`` key with value ``None``, which
    then became a ``dict`` key — invalid in JSON, and inconsistent
    with the sibling ``group_by_language`` function which already
    handled None via ``r.get("language") or "unknown"``.

    Fix: use ``r.get("language") or "—"`` so the present-but-None
    case is also covered.
    """

    def test_none_language_treated_as_placeholder(self) -> None:
        from steam_review_tool.exporters.per_language_exporter import (
            build_summary,
        )
        reviews = [
            {"voted_up": True, "language": "english"},
            {"voted_up": False, "language": None},       # malformed
            {"voted_up": True, "language": "german"},
            {"voted_up": False},                          # missing key
        ]
        out = build_summary(reviews)
        # The "—" placeholder (em-dash) appears once for both the
        # None row and the missing-key row. Most importantly, no
        # ``"None"`` literal leaked into the rendered Markdown.
        assert "None" not in out
        # The em-dash placeholder is used by the missing-key branch;
        # the None branch should also collapse into it.
        assert "—" in out

    def test_no_none_key_in_language_distribution_table(self) -> None:
        from steam_review_tool.exporters.per_language_exporter import (
            build_summary,
        )
        reviews = [{"voted_up": True, "language": None}]
        out = build_summary(reviews)
        # The Markdown table includes a "Language distribution"
        # section. We don't want the header value to be the Python
        # repr "None" — it should be a user-readable placeholder.
        assert "| None |" not in out

    def test_group_by_language_handles_none_too(self) -> None:
        """The sibling function must keep its existing None-safe
        behaviour after the build_summary fix."""
        from steam_review_tool.exporters.per_language_exporter import (
            group_by_language,
        )
        out = group_by_language([
            {"language": None},
            {"language": "english"},
            {},
        ])
        # Both None and missing-key collapse into "unknown".
        assert out.get("unknown") is not None
        assert out.get("english") is not None
        assert None not in out
        assert "None" not in out


# ---------------------------------------------------------------------------
# BUG-R3-4: dependency_installer triggered get-pip.py on any "pip" mention
# ---------------------------------------------------------------------------
class TestDependencyInstallerPipDetection:
    """The old check ``"pip" in stderr.lower()`` matched any error
    that mentioned pip, including legitimate install errors like
    ``"Could not install requirement pip-23.0.1"`` — a needless
    download of ``get-pip.py`` on every transient failure.

    Fix: only the specific CPython "No module named pip" signals
    trigger the bootstrap path. A real install error mentioning
    pip no longer triggers it.
    """

    def test_real_install_error_does_not_trigger_bootstrap(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When the first install attempt fails with a real error
        (e.g. a network error from pip itself), the bootstrap path
        should NOT run."""
        from steam_review_tool.services import dependency_installer

        # Patch find_external_python so we don't actually try to
        # invoke a real interpreter.
        monkeypatch.setattr(
            dependency_installer, "_find_python", lambda: sys.executable,
        )
        # Patch urlretrieve so the bootstrap path is observably
        # different from the non-bootstrap path.
        urlretrieve_called = {"n": 0}

        def fake_urlretrieve(*_a: Any, **_kw: Any) -> None:
            urlretrieve_called["n"] += 1

        monkeypatch.setattr(
            dependency_installer.urllib.request, "urlretrieve",
            fake_urlretrieve,
        )

        # Subprocess returns non-zero with a stderr that mentions
        # pip but is NOT a "module not found" error.
        class _Result:
            returncode = 1
            stderr = (
                "ERROR: Could not install requirement pip-23.0.1 "
                "because of a network error."
            )
            stdout = ""

        monkeypatch.setattr(
            dependency_installer.subprocess, "run",
            lambda *a, **kw: _Result(),
        )

        outcome: dict[str, Any] = {}

        def on_done(ok: bool, msg: str) -> None:
            outcome["ok"] = ok
            outcome["msg"] = msg

        dependency_installer.install_playwright(
            lambda _m: None, on_done,
        )

        assert urlretrieve_called["n"] == 0, (
            "get-pip.py was downloaded even though the error was "
            "NOT 'No module named pip'"
        )
        assert outcome.get("ok") is False

    def test_real_pip_missing_signal_does_trigger_bootstrap(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The actual CPython 'No module named pip' error must still
        trigger the bootstrap path."""
        from steam_review_tool.services import dependency_installer

        monkeypatch.setattr(
            dependency_installer, "_find_python", lambda: sys.executable,
        )

        class _Result:
            returncode = 1
            stderr = (
                "C:\\Python312\\python.exe: No module named pip"
            )
            stdout = ""

        run_calls: list[tuple[Any, ...]] = []

        def fake_run(*args: Any, **kw: Any) -> Any:
            run_calls.append((args, kw))
            return _Result()

        # We need urlretrieve to NOT actually download — but we want
        # to verify the bootstrap path was *entered* (i.e. the
        # ``urlretrieve`` line was reached). Patch it to return a
        # non-existent path so the followup ``subprocess.run`` raises
        # and the bootstrap is recorded as failed.
        bootstrap_reached = {"n": 0}

        def fake_urlretrieve(url: str, dest: str, *_a: Any) -> None:
            bootstrap_reached["n"] += 1
            # Write a tiny placeholder so the followup ``subprocess.run``
            # doesn't fail on a missing file.
            Path(dest).write_text("# fake get-pip\n", encoding="utf-8")

        monkeypatch.setattr(
            dependency_installer.urllib.request, "urlretrieve",
            fake_urlretrieve,
        )
        monkeypatch.setattr(
            dependency_installer.subprocess, "run", fake_run,
        )

        dependency_installer.install_playwright(
            lambda _m: None, lambda _ok, _msg: None,
        )

        assert bootstrap_reached["n"] == 1, (
            "Expected get-pip.py download to be attempted for the "
            "real 'No module named pip' signal."
        )

    def test_pip_missing_signal_uses_specific_phrases(self) -> None:
        """Static check: the source uses one of the specific
        'No module named pip' signals and not a bare ``"pip"`` in
        check. Strip comment lines first to avoid matching the
        explanatory comment that *describes* the fix."""
        src = Path(
            "steam_review_tool/services/dependency_installer.py"
        ).read_text(encoding="utf-8")
        code_lines = [
            ln for ln in src.splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")
        ]
        code = "\n".join(code_lines)
        # The specific signal must be there:
        assert "No module named pip" in code
        # The old, too-broad pattern must be gone.
        # Note: the substring ``"pip"`` appears many times in the
        # file (as a literal in subprocess args, comments, etc.).
        # What we want to assert is the absence of the exact
        # pattern that caused the bug: a bare membership-test of
        # the word "pip" against the lowercase stderr.
        assert '"pip" in stderr.lower()' not in code, (
            "Found the old, too-broad pip check. Use a specific "
            "'No module named pip' signal instead."
        )


# ---------------------------------------------------------------------------
# BUG-R3-5: dead code in dump_repository._guess_safe_name
# ---------------------------------------------------------------------------
class TestDumpRepositoryNoDeadNoneCheck:
    """The old code was
    ``if self.dump_root is None or not self.dump_root.exists():`` —
    but the constructor type-annotates ``dump_root: Path`` (not
    Optional), so the ``is None`` branch was unreachable. A static
    check on the source confirms it's gone, and a runtime check
    confirms the back-compat 1-arg API still works.
    """

    def test_source_no_longer_checks_dump_root_is_none(self) -> None:
        src = Path(
            "steam_review_tool/services/dump_repository.py"
        ).read_text(encoding="utf-8")
        code_lines = [
            ln for ln in src.splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")
        ]
        code = "\n".join(code_lines)
        assert "self.dump_root is None" not in code

    def test_load_seen_ids_still_works(self, tmp_path: Path) -> None:
        from steam_review_tool.services.dump_repository import DumpRepository
        # Create a folder with the per-game pattern so _guess_safe_name
        # finds a real folder.
        game_dir = tmp_path / "4311090_BusSim27"
        game_dir.mkdir()
        repo = DumpRepository(tmp_path)
        ids = repo.load_seen_ids(4311090)
        assert ids == []


# ---------------------------------------------------------------------------
# BUG-R3-6: dead code in review_analyzer.split_first_24h
# ---------------------------------------------------------------------------
class TestReviewAnalyzerSplitFirst24h:
    """The old ``if not timestamps: return {...}`` branch was
    dead code — a list comprehension over a non-empty iterable
    always produces a non-empty list. The fix replaces the redundant
    guard with explicit None / non-numeric handling, matching the
    R3-2 pattern in filter_controller.
    """

    def test_no_dead_if_not_timestamps_branch(self) -> None:
        src = Path(
            "steam_review_tool/services/review_analyzer.py"
        ).read_text(encoding="utf-8")
        code_lines = [
            ln for ln in src.splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")
        ]
        code = "\n".join(code_lines)
        assert "if not timestamps:" not in code, (
            "The 'if not timestamps' branch is dead after a list "
            "comprehension; remove it."
        )

    def test_split_handles_none_timestamps(self) -> None:
        from steam_review_tool.services.review_analyzer import split_first_24h
        now = int(time.time())
        reviews = [
            {"timestamp_created": now - 60},
            {"timestamp_created": None},       # malformed
            {"timestamp_created": "not-a-num"},
        ]
        out = split_first_24h(reviews)
        # Must not crash. The 60-seconds-ago row is within the first
        # 24h; the malformed rows (ts=0) are also "before" the
        # earliest valid review if earliest > 0, or fall into
        # "after" if all timestamps are 0. Either way, the function
        # returns a dict with the expected keys.
        assert "first_24h" in out
        assert "after" in out
        assert "earliest_ts" in out
        assert isinstance(out["first_24h"], list)
        assert isinstance(out["after"], list)

    def test_split_with_only_malformed_rows(self) -> None:
        from steam_review_tool.services.review_analyzer import split_first_24h
        reviews = [
            {"timestamp_created": None},
            {"timestamp_created": "x"},
        ]
        out = split_first_24h(reviews)
        # All timestamps coerce to 0; earliest is 0; the function
        # returns the full reviews list under "after".
        assert out["first_24h"] == []
        assert out["after"] == reviews


# ---------------------------------------------------------------------------
# BUG-R3-7: settings_controller published a string-literal event
# ---------------------------------------------------------------------------
class TestSettingsControllerEventConstants:
    """The old ``_on_saved`` published
    ``bus.publish("settings.applied", data=data)`` using a string
    literal — inconsistent with the class constant
    ``SETTINGS_CHANGED`` used on the line above. Renaming the
    event by accident would silently break any subscribers.

    Fix: both events are class constants; the publish calls use
    them. The test asserts the constants are present and the
    publish call uses the constant (not the literal).

    R20-1 update: ``SETTINGS_APPLIED`` was a dead bus event
    (zero subscribers). The R20-1 fix removed the constant
    + the publish call + the now-unused ``bus`` import.
    The tests below were updated to pin the new (cleaner)
    contract: only ``SETTINGS_CHANGED`` exists; only that
    one event is published.
    """

    def test_both_events_have_class_constants(self) -> None:
        from steam_review_tool.controllers.settings_controller import (
            SettingsController,
        )
        # R20-1: only ``SETTINGS_CHANGED`` exists; the
        # dead ``SETTINGS_APPLIED`` was removed.
        assert hasattr(SettingsController, "SETTINGS_CHANGED")
        assert not hasattr(SettingsController, "SETTINGS_APPLIED"), (
            "SettingsController.SETTINGS_APPLIED is a dead bus "
            "event (zero subscribers) — removed in R20-1"
        )
        assert isinstance(SettingsController.SETTINGS_CHANGED, str)

    def test_event_values_preserved(self) -> None:
        """The string value must not change — it's a public API
        consumed by any subscriber that listens on the bus."""
        from steam_review_tool.controllers.settings_controller import (
            SettingsController,
        )
        assert SettingsController.SETTINGS_CHANGED == "settings.changed"

    def test_publish_uses_constants(self) -> None:
        """The publish call must reference the class constant, not
        the bare string literal — a static substring check
        confirms this."""
        src = Path(
            "steam_review_tool/controllers/settings_controller.py"
        ).read_text(encoding="utf-8")
        # Strip comments / docstrings to avoid matching the
        # explanatory ``"settings.applied"`` in the docstring.
        code_lines = [
            ln for ln in src.splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")
        ]
        code = "\n".join(code_lines)
        # The publish call should use ``self.SETTINGS_CHANGED``,
        # not the bare string literal.
        assert 'bus.publish(self.SETTINGS_CHANGED' in code
        # And the old bare literal must be gone from code lines.
        bad_call = 'bus.publish("settings.changed"'
        assert bad_call not in code, (
            f"Found bare string literal in publish call: {bad_call}"
        )
        # R20-1: the dead ``SETTINGS_APPLIED`` publish must
        # NOT appear either.
        assert 'bus.publish(self.SETTINGS_APPLIED' not in code
        assert 'bus.publish("settings.applied"' not in code

    def test_saved_event_is_published(self) -> None:
        """Behavioural check: ``_on_saved`` publishes the
        ``SETTINGS_CHANGED`` event on the bus with the saved
        data. The R20-1 fix removed the dead
        ``SETTINGS_APPLIED`` publish."""
        from steam_review_tool.controllers.settings_controller import (
            SettingsController,
        )
        # Use a stub master; we never call .open() so the dialog
        # is never instantiated.
        ctrl = SettingsController.__new__(SettingsController)
        ctrl.master = None
        captured: list[tuple[str, dict[str, Any]]] = []

        from steam_review_tool.core import event_bus
        # We patch the module-level ``bus`` to capture publishes.
        original_publish = event_bus.bus.publish

        def fake_publish(event: str, **kw: Any) -> None:
            captured.append((event, kw))
        event_bus.bus.publish = fake_publish  # type: ignore[assignment]
        try:
            ctrl._on_saved({"dump_root": "/tmp/x"})
        finally:
            event_bus.bus.publish = original_publish  # type: ignore[assignment]

        events = [e for e, _ in captured]
        # R20-1: only ``SETTINGS_CHANGED`` is published now.
        assert "settings.changed" in events
        assert "settings.applied" not in events, (
            "SETTINGS_APPLIED is a dead bus event — "
            "the publish should have been removed in R20-1"
        )
        for _event, kw in captured:
            assert kw.get("data") == {"dump_root": "/tmp/x"}


# ---------------------------------------------------------------------------
# Cross-cutting: ensure the export orchestrator still works after the fixes
# ---------------------------------------------------------------------------
class TestExportPipelineAfterFixes:
    """Sanity-check that none of the R3 fixes broke the end-to-end
    export path. We build a tiny in-memory ExportContext and write
    it to a temp dir, then read it back and verify the rendered
    Markdown contains the expected review."""

    def test_export_with_none_language_and_none_timestamp(
        self, tmp_path: Path,
    ) -> None:
        from datetime import datetime, timezone
        from steam_review_tool.exporters.export_orchestrator import run
        from steam_review_tool.models.export_context import ExportContext

        now_iso = datetime.now(timezone.utc).isoformat()
        ctx = ExportContext(
            app_id=4311090,
            app_details={"name": "TestGame"},
            reviews=[
                {
                    "recommendationid": "rec-1",
                    "language": None,           # exercises R3-3
                    "voted_up": True,
                    "review": "Looks fine",
                    "timestamp_created": None,  # exercises R3-2/3-6
                    "author": {"steamid": "12345", "playtime_forever": 0},
                },
            ],
            language_param="all",
            review_filter="all",
            review_type="all",
            day_range=None,
            min_date_ts=None,
        )
        dest = tmp_path / "out.md"
        result = run(ctx, dest, log_cb=lambda _m: None)
        assert result["md"] == dest
        text = dest.read_text(encoding="utf-8")
        # The None language must not become the literal "None" in
        # the language-distribution table.
        assert "| None |" not in text
        # The review body must still appear.
        assert "Looks fine" in text
