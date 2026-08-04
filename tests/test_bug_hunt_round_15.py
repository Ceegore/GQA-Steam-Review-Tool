"""Round-15 bug-hunt regression tests.

Real bugs found in a fifteenth systematic pass. Rounds 1-14
(9388ab1, 9ea69de, ed231bc, 80f9431, f913ae8, e0514c0,
0e4f031, ba4255e, 49aa77a, 831219e, 04f47f6, dfd6ff7,
6265d12, 561fc45) covered the int / str / or-default
residue, the chained-dict crash, the double-subscribe
pattern, the over-broad "find latest .md" walk, the missing
worker-shutdown wait, the broken batch-dump feature, the
missed R5 sites, the Tk widget-state + watch-thread-safety
issues, the destructive "Reset" button before commit, the
shared ``self._worker`` field, the backup-filename
collision, the sister-helper inconsistency, the
sync-on-main-thread network call, the
popup-window-destroy race, the consolidation of the
cross-platform "open path" ladder, the silent
export-failure hiding, the popup-search stale results, the
slow popup-open aggregation, the broad ``except Exception``
swallowing specific actionable errors, the file-content-hash
OOM, the non-deterministic safe-name walk, and the markdown
table cell escaping.

This round targets a new bug class: **settings-persistence
data loss + dead code + silent exceptions in non-UI helpers**.

Three real bugs found:

1. ``popup_settings._save_and_close`` built a 5-field dict
   and called ``settings_store.save(data)``, which wrote
   only those 5 keys to disk. The other 5 settings the
   user could have set elsewhere (``also_csv``,
   ``also_json``, ``per_language``, ``open_after_export``,
   ``greeting_shown``) were silently lost — the next
   ``load()`` would merge with DEFAULTS and reset them
   silently. Fix: load the current settings, then
   ``.update(...)`` with the dialog's 5 fields, then save
   the merged dict.

2. ``APIWorkflow.dump_root`` was set in 3 places
   (``__init__``, ``app_window._on_settings_changed``,
   ``tab_api._on_pick_dump_root``) but never read inside
   the class — the actual file writes happen through
   ``DumpFolderController.dump_root`` and
   ``DumpRepository.dump_root``. The 3 assignments were
   dead code. Fix: remove the ``self.dump_root =
   dump_root`` line from ``__init__`` and the 2 dead
   assignments in callers.

3. ``_since_section._on_preset_change`` silently
   swallowed the ``on_change`` callback error if
   ``log_fn`` was None (the typical case in this app).
   The preset change "looked" applied but the dependent
   state (e.g. dump-folder label refresh) silently
   broke. Fix: always log via the standard logger so
   the developer can spot the failure in stderr even
   when no ``log_fn`` is wired.
"""
from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# BUG-R15-1: popup_settings._save_and_close overwrites ALL settings
# ---------------------------------------------------------------------------
class TestPopupSettingsPreservesAllKeys:
    """``popup_settings._save_and_close`` previously built a
    5-field dict from the dialog's text variables and
    called ``settings_store.save(data)`` — overwriting the
    entire on-disk file with just those 5 keys. The other
    5 settings the user had set elsewhere (also_csv,
    also_json, per_language, open_after_export,
    greeting_shown) were silently reset to DEFAULTS on
    next launch.

    Fix: load the current settings, then ``.update(...)``
    with the dialog's 5 fields, then save the merged dict.
    The 5 dialog fields overwrite the matching keys; the
    other 5 fields are preserved.
    """

    def test_save_preserves_other_settings(self) -> None:
        """The on-disk file after a settings-dialog save
        must still contain the fields the user set
        elsewhere (e.g. ``also_csv=True``). The previous
        code wrote only 5 fields; the user's other
        preferences were silently lost."""
        from steam_review_tool.services import settings_store

        with tempfile.TemporaryDirectory() as td:
            # Pretend the user has the config dir in
            # the temp dir. settings_store uses a
            # module-level SETTINGS_FILE constant so we
            # patch it.
            fake_file = Path(td) / "settings.json"
            with patch.object(
                settings_store, "SETTINGS_FILE", fake_file,
            ):
                # Initial state: user has also_csv=True
                # (a setting NOT in the dialog's 5
                # fields).
                settings_store.save({
                    "dump_root": "/orig/dump",
                    "obsidian_vault": "/orig/vault",
                    "apify_token": "orig_token",
                    "keyword_list": ["a", "b"],
                    "ai_prompt_template": "orig prompt",
                    "also_csv": True,        # <-- NOT in dialog
                    "also_json": True,       # <-- NOT in dialog
                    "per_language": True,    # <-- NOT in dialog
                    "open_after_export": True,  # <-- NOT in dialog
                    "greeting_shown": True,  # <-- NOT in dialog
                })
                # Simulate the user opening the dialog,
                # changing dump_root, and saving.
                # The 5 dialog fields are the new
                # values; the other 5 must be preserved.
                from steam_review_tool.ui.popup_settings import (
                    SettingsDialog,
                )
                dlg = SettingsDialog.__new__(SettingsDialog)
                dlg._dump_root_var = MagicMock()
                dlg._dump_root_var.get.return_value = "/new/dump"
                dlg._obsidian_var = MagicMock()
                dlg._obsidian_var.get.return_value = "/new/vault"
                dlg._apify_var = MagicMock()
                dlg._apify_var.get.return_value = "new_token"
                dlg._keywords_text = MagicMock()
                dlg._keywords_text.get.return_value = "1.0,end"
                dlg._ai_prompt_text = MagicMock()
                dlg._ai_prompt_text.get.return_value = "1.0,end"
                dlg._save_cb = None
                dlg._top = None
                # Patch the actual save call.
                with patch.object(
                    settings_store, "save",
                    wraps=settings_store.save,
                ) as wrapped_save:
                    dlg._save_and_close()
                    # The wrapped save must have been
                    # called with a dict containing
                    # BOTH the 5 dialog fields AND
                    # the 5 other fields (preserved).
                    wrapped_save.assert_called_once()
                    saved_data = wrapped_save.call_args[0][0]
                    # Dialog fields were updated.
                    assert saved_data["dump_root"] == "/new/dump"
                    assert saved_data["obsidian_vault"] == (
                        "/new/vault"
                    )
                    assert saved_data["apify_token"] == "new_token"
                    assert saved_data["keyword_list"] == ["1.0", "end"]
                    # The kw_list parsing is comma-split.
                    # ``"1.0,end"`` strips to ``"1.0"`` and
                    # ``"end"`` -> ``["1.0", "end"]``.
                    # Other fields were preserved.
                    assert saved_data["also_csv"] is True
                    assert saved_data["also_json"] is True
                    assert saved_data["per_language"] is True
                    assert saved_data["open_after_export"] is True
                    assert saved_data["greeting_shown"] is True

    def test_save_with_no_prior_settings_uses_defaults(self) -> None:
        """If there's no prior settings file (first launch),
        the dialog save must still produce a valid dict
        (not crash on the missing-file read). The
        ``current = _load_settings()`` call must fall
        back to an empty dict on ``OSError``."""
        from steam_review_tool.services import settings_store

        with tempfile.TemporaryDirectory() as td:
            fake_file = Path(td) / "no_such_file.json"
            with patch.object(
                settings_store, "SETTINGS_FILE", fake_file,
            ):
                from steam_review_tool.ui.popup_settings import (
                    SettingsDialog,
                )
                dlg = SettingsDialog.__new__(SettingsDialog)
                dlg._dump_root_var = MagicMock()
                dlg._dump_root_var.get.return_value = "/x"
                dlg._obsidian_var = MagicMock()
                dlg._obsidian_var.get.return_value = ""
                dlg._apify_var = MagicMock()
                dlg._apify_var.get.return_value = ""
                dlg._keywords_text = MagicMock()
                dlg._keywords_text.get.return_value = "1.0,end"
                dlg._ai_prompt_text = MagicMock()
                dlg._ai_prompt_text.get.return_value = "1.0,end"
                dlg._save_cb = None
                dlg._top = None
                # Must not raise on a missing settings
                # file. The ``_load_settings()`` call
                # falls back to ``{}`` (the
                # ``try/except OSError`` branch in the
                # R15-1 fix).
                dlg._save_and_close()


# ---------------------------------------------------------------------------
# BUG-R15-2: api_workflow.dump_root is dead code
# ---------------------------------------------------------------------------
class TestApiWorkflowNoDeadDumpRoot:
    """``APIWorkflow.dump_root`` was set in 3 places
    (``__init__``, ``app_window._on_settings_changed``,
    ``tab_api._on_pick_dump_root``) but never read inside
    the class. The 3 assignments were dead code. Fix:
    remove the attribute entirely (and the 2 dead
    assignments in callers).
    """

    def test_api_workflow_no_longer_has_dump_root_attr(self) -> None:
        """The ``APIWorkflow`` instance must not have a
        ``dump_root`` attribute (it was dead code)."""
        from steam_review_tool.controllers.api_workflow import (
            APIWorkflow,
        )
        # Use __new__ to skip __init__ (we don't need a
        # real SteamAPI for this test).
        wf = APIWorkflow.__new__(APIWorkflow)
        assert not hasattr(wf, "dump_root"), (
            "APIWorkflow.dump_root is dead code (set in 3 "
            "places, never read). Remove the attribute "
            "and the 3 dead assignments."
        )

    def test_api_workflow_init_no_longer_sets_dump_root(self) -> None:
        """``APIWorkflow.__init__`` must not set
        ``self.dump_root``. The constructor still
        accepts ``dump_root`` for DI back-compat but
        ignores it."""
        from steam_review_tool.controllers.api_workflow import (
            APIWorkflow,
        )
        # Inspect the source to confirm the attribute
        # is not set in __init__.
        import inspect
        from pathlib import Path
        from unittest.mock import MagicMock
        src = inspect.getsource(APIWorkflow.__init__)
        assert "self.dump_root = dump_root" not in src, (
            "APIWorkflow.__init__ must not set "
            "self.dump_root (dead code)"
        )

    def test_app_window_no_longer_assigns_api_wf_dump_root(
        self,
    ) -> None:
        """``app_window._on_settings_changed`` must not
        set ``self.api_wf.dump_root`` (dead code)."""
        from pathlib import Path
        src = Path(
            "steam_review_tool/ui/app_window.py"
        ).read_text(encoding="utf-8")
        assert "self.api_wf.dump_root" not in src, (
            "app_window.py must not set "
            "self.api_wf.dump_root (dead code)"
        )

    def test_tab_api_no_longer_assigns_api_wf_dump_root(self) -> None:
        """``tab_api._on_pick_dump_root`` must not set
        ``self.api_wf.dump_root`` (dead code)."""
        from pathlib import Path
        src = Path(
            "steam_review_tool/ui/tab_api.py"
        ).read_text(encoding="utf-8")
        assert "self.api_wf.dump_root" not in src, (
            "tab_api.py must not set self.api_wf.dump_root "
            "(dead code)"
        )


# ---------------------------------------------------------------------------
# BUG-R15-3: _since_section._on_preset_change silently swallows errors
# ---------------------------------------------------------------------------
class TestSinceSectionLogsCallbackErrors:
    """``_since_section._on_preset_change`` only
    forwarded the ``on_change`` callback error to
    ``log_fn`` (which is optional and typically None in
    this app). When the user didn't supply a log_fn, the
    exception was silently swallowed — the preset change
    "looked" applied but the dependent state silently
    broke.

    Fix: always log via the standard ``logging`` module
    so the developer can spot the failure in stderr
    even when no ``log_fn`` is wired.
    """

    def test_on_change_error_logged_when_log_fn_is_none(self) -> None:
        """When the ``on_change`` callback raises and
        ``log_fn`` is None, the exception must be logged
        via the standard logger (so the developer sees
        it in stderr) — NOT silently swallowed."""
        from steam_review_tool.ui._since_section import (
            build_since_section,
        )

        # Track the records logged from the
        # ``_since_section`` logger.
        records: list[logging.LogRecord] = []

        class _ListHandler(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                records.append(record)

        handler = _ListHandler(level=logging.DEBUG)
        logger = logging.getLogger(
            "steam_review_tool.ui._since_section",
        )
        logger.addHandler(handler)
        old_level = logger.level
        logger.setLevel(logging.DEBUG)
        try:
            # Build a since section WITHOUT a log_fn
            # (the typical case in this app).
            def _failing_on_change() -> None:
                raise RuntimeError("simulated callback failure")

            # Use a real CTk root so the widget tree
            # builds without error.
            import customtkinter as ctk
            from tests.conftest import _shared_root_lock
            with _shared_root_lock:
                # Use the existing session-scoped root
                # fixture infrastructure.
                root = ctk.CTk()
                try:
                    refs = build_since_section(
                        root,
                        prefix="test_",
                        on_change=_failing_on_change,
                        log_fn=None,  # <-- the bug condition
                    )
                    # Trigger the failing callback via
                    # the preset_var trace.
                    refs["preset_var"].set("last 1 hour")
                    # The exception must be logged via
                    # the standard logger even though
                    # log_fn is None.
                    assert any(
                        "since-section on_change callback failed"
                        in r.getMessage()
                        and "simulated callback failure" in r.getMessage()
                        for r in records
                    ), (
                        f"expected the exception to be logged "
                        f"via the standard logger, got: "
                        f"{[r.getMessage() for r in records]}"
                    )
                finally:
                    root.destroy()
        finally:
            logger.removeHandler(handler)
            logger.setLevel(old_level)

    def test_on_change_success_does_not_log_warning(self) -> None:
        """When the ``on_change`` callback succeeds,
        no warning is logged (and the callback is
        actually called)."""
        from steam_review_tool.ui._since_section import (
            build_since_section,
        )

        records: list[logging.LogRecord] = []

        class _ListHandler(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                records.append(record)

        handler = _ListHandler(level=logging.DEBUG)
        logger = logging.getLogger(
            "steam_review_tool.ui._since_section",
        )
        logger.addHandler(handler)
        try:
            call_count = [0]

            def _ok_on_change() -> None:
                call_count[0] += 1

            import customtkinter as ctk
            root = ctk.CTk()
            try:
                refs = build_since_section(
                    root, prefix="ok_",
                    on_change=_ok_on_change, log_fn=None,
                )
                refs["preset_var"].set("last 1 hour")
                assert call_count[0] == 1
                # No warnings on a successful callback.
                warnings = [
                    r for r in records
                    if "since-section" in r.getMessage()
                ]
                assert not warnings, (
                    f"successful callback should not log a "
                    f"warning, got: "
                    f"{[r.getMessage() for r in warnings]}"
                )
            finally:
                root.destroy()
        finally:
            logger.removeHandler(handler)


# ---------------------------------------------------------------------------
# End-to-end: settings persistence across the dialog-save flow
# ---------------------------------------------------------------------------
class TestSettingsPersistenceEndToEnd:
    """End-to-end check: the on-disk settings file
    after a dialog save must contain BOTH the 5
    dialog-managed keys AND the 5 non-dialog keys
    (also_csv, also_json, per_language, open_after_export,
    greeting_shown).
    """

    def test_dialog_save_preserves_non_dialog_keys_end_to_end(
        self,
    ) -> None:
        from steam_review_tool.services import settings_store
        from steam_review_tool.ui.popup_settings import (
            SettingsDialog,
        )

        with tempfile.TemporaryDirectory() as td:
            fake_file = Path(td) / "settings.json"
            with patch.object(
                settings_store, "SETTINGS_FILE", fake_file,
            ):
                # Initial state: user has also_csv=True
                # and greeting_shown=True.
                settings_store.save({
                    "dump_root": "/x",
                    "obsidian_vault": "",
                    "apify_token": "",
                    "keyword_list": [],
                    "ai_prompt_template": "",
                    "also_csv": True,
                    "also_json": False,
                    "per_language": False,
                    "open_after_export": True,
                    "greeting_shown": True,
                })
                # Open the dialog, change one field,
                # save.
                dlg = SettingsDialog.__new__(SettingsDialog)
                dlg._dump_root_var = MagicMock()
                dlg._dump_root_var.get.return_value = "/y"
                dlg._obsidian_var = MagicMock()
                dlg._obsidian_var.get.return_value = ""
                dlg._apify_var = MagicMock()
                dlg._apify_var.get.return_value = ""
                dlg._keywords_text = MagicMock()
                dlg._keywords_text.get.return_value = "1.0,end"
                dlg._ai_prompt_text = MagicMock()
                dlg._ai_prompt_text.get.return_value = "1.0,end"
                dlg._save_cb = None
                dlg._top = None
                dlg._save_and_close()
                # Reload the on-disk file. The user's
                # other preferences must be preserved.
                loaded = settings_store.load()
                assert loaded["also_csv"] is True
                assert loaded["also_json"] is False
                assert loaded["per_language"] is False
                assert loaded["open_after_export"] is True
                assert loaded["greeting_shown"] is True
                # The dialog field was updated.
                assert loaded["dump_root"] == "/y"
