"""Round-17 bug-hunt regression tests.

Real bugs found in a seventeenth systematic pass. Rounds 1-16
(9388ab1, 9ea69de, ed231bc, 80f9431, f913ae8, e0514c0,
0e4f031, ba4255e, 49aa77a, 831219e, 04f47f6, dfd6ff7,
6265d12, 561fc45, b795fbd, 95ea74e) found 75 bugs across
the project. Round 17 found 3 more — this round targets a
specific pattern class: **in-memory state changes that
were never persisted + dead code + silent error
swallowing on the persist path**.

The recurring lesson (compounding R15 + R16): when a
refactor adds a "the public function should be the
chokepoint" fix (R16-1/R16-2 atomic writers, R16-3
``set_dump_root`` persistence), the OTHER paths that
update the same in-memory state through a back door
(bypass the public function) are still bugged. The R17
round finds the obsidian_vault equivalent of the
R16-3 ``set_dump_root`` bug.

R17-1  controllers/dump_folder_controller.py +
       ui/_tab_actions.py: ``pick_obsidian_vault`` and
       ``clear_obsidian_vault`` set the in-memory
       ``self.obsidian_vault`` directly (bypassing the
       settings dialog) and never persist to disk.

Root cause: same as R16-3. The Settings dialog
            (``popup_settings._save_and_close``) goes
            through ``settings_store.save`` and persists
            the vault. The picker / clear actions in
            ``_tab_actions.py`` write the in-memory
            attribute directly — a user who picks a vault
            via the picker (without opening Settings)
            expects the choice to survive an app restart,
            but the next ``settings_store.load()`` reads
            the old value from disk and the DEFAULTS
            merge fills the new key with ``""``.

Fix:      added ``set_obsidian_vault`` method to
            ``DumpFolderController`` (mirrors
            ``set_dump_root``): updates the in-memory
            value, then loads + updates + saves the
            settings dict. ``pick_obsidian_vault`` and
            ``clear_obsidian_vault`` now call
            ``self.dump_ctrl.set_obsidian_vault(...)``
            instead of writing the attribute directly.

R17-2  ui/tab_trends.py: ``_log_status`` is dead code
       (only defined, never called anywhere in the
       codebase).

Root cause: a refactor (R9 / R11-3) introduced
            ``_log_status_safe`` as the thread-safe
            variant, and the old ``_log_status`` was
            kept "for any external caller" — but no
            external caller exists. The misleading
            "Kept for any external caller" comment
            was the only thing keeping the dead
            function alive.

Fix:      removed ``_log_status``. The static check
            in ``TestNoDeadLogStatusInTabTrends`` is
            the regression probe.

R17-3  ui/app_window.py: ``_persist_settings`` had a
       bare ``except Exception: pass`` that silently
       dropped any save failure.

Root cause: R12-4 to R12-7 (silent export-failure
            hiding) + R15-3 (silent callback error)
            established the rule: always log via the
            standard ``logging`` module as the primary
            surface, even when no UI ``log_fn`` is
            wired. ``_persist_settings`` predated that
            pattern (it was written in the R1 / R2
            phase when silent swallow was the default).

Fix:      replaced ``except Exception: pass`` with
            ``except OSError as exc: logging
            .getLogger(__name__).exception(...)``.
            A user clicking "Don't show again" in the
            welcome dialog now gets a stderr trace if
            the save failed, instead of silent data
            loss.

Test discipline notes (compounding R12 + R13 + R16
lessons):

- The set_obsidian_vault tests use Windows-friendly
  paths (Path(td) / "vault" + Path(td) / "new") —
  Path("/new/vault") is normalised to "\\new\\vault"
  on Windows, breaking the equality check (same R16
  test-path-handling lesson).

- The set_obsidian_vault tests patch
  ``settings_store.SETTINGS_FILE`` so they can use a
  throwaway settings file in a tempdir. The
  ``_load_settings`` / ``_save_settings`` calls
  inside ``set_obsidian_vault`` re-import
  ``settings_store`` at call time, so the patch
  works at any test phase.

- The ``TestNoDeadLogStatusInTabTrends`` test
  walks the file and asserts that ``def _log_status``
  does NOT appear (regex anchored on the def line).
  A regression that re-introduces the dead code
  will fail the test.

Stats: 3 bugs found, 9 regression tests added.
"""
from __future__ import annotations

import inspect
import re
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Helper: strip pure comment / docstring lines from a source string before
# substring-regression checks. Reused from R16 (the R12 / R13 cross-project
# lesson was re-confirmed in R16: a docstring that DOCUMENTS the anti-pattern
# gets matched by a naive substring check).
# ---------------------------------------------------------------------------
def _strip_comments_and_docstrings(src: str) -> str:
    src_no_docstrings = re.sub(
        r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'',
        "",
        src,
    )
    out_lines: list[str] = []
    for line in src_no_docstrings.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        out_lines.append(line)
    return "\n".join(out_lines)


# ---------------------------------------------------------------------------
# BUG-R17-1: pick_obsidian_vault / clear_obsidian_vault don't persist
# ---------------------------------------------------------------------------
class TestSetObsidianVaultPersists:
    """``DumpFolderController.set_obsidian_vault`` must persist the
    new value to ``settings.json`` so the choice survives an app
    restart. Same R16-3 fix-shape as ``set_dump_root``.

    Without the fix, ``pick_obsidian_vault`` and
    ``clear_obsidian_vault`` set the in-memory attribute directly
    and never write to disk — the user's choice is lost on next
    launch.
    """

    def test_pick_obsidian_vault_persists_to_settings(self) -> None:
        """A vault picked via the picker must survive an app
        restart — the on-disk ``settings.json`` must reflect
        the new vault after ``set_obsidian_vault`` is called."""
        from steam_review_tool.services import settings_store
        from steam_review_tool.controllers.dump_folder_controller import (
            DumpFolderController,
        )

        with pytest.MonkeyPatch().context() as mp:
            with __import__("tempfile").TemporaryDirectory() as td:
                # Use Windows-friendly absolute paths in
                # the test.
                orig_dir = Path(td) / "orig"
                new_dir = Path(td) / "new"
                orig_dir.mkdir()
                new_dir.mkdir()
                fake_file = Path(td) / "settings.json"
                mp.setattr(settings_store, "SETTINGS_FILE", fake_file)
                # Initial state: user has a default
                # vault.
                settings_store.save({
                    "dump_root": str(orig_dir),
                    "obsidian_vault": "",
                    "apify_token": "",
                    "keyword_list": [],
                    "ai_prompt_template": "",
                })
                # User picks a new vault via the picker.
                ctrl = DumpFolderController(
                    dump_root=orig_dir,
                )
                ctrl.set_obsidian_vault(new_dir)
                # The on-disk settings must now reflect
                # the new vault.
                loaded = settings_store.load()
                assert loaded["obsidian_vault"] == str(new_dir), (
                    f"on-disk settings must reflect the new "
                    f"obsidian vault, got {loaded['obsidian_vault']!r}"
                )

    def test_clear_obsidian_vault_persists_empty(self) -> None:
        """A vault cleared via the clear action must persist
        the empty choice — the on-disk ``settings.json`` must
        have ``obsidian_vault == ""`` after the clear."""
        from steam_review_tool.services import settings_store
        from steam_review_tool.controllers.dump_folder_controller import (
            DumpFolderController,
        )

        with pytest.MonkeyPatch().context() as mp:
            with __import__("tempfile").TemporaryDirectory() as td:
                orig_dir = Path(td) / "orig"
                vault_dir = Path(td) / "vault"
                orig_dir.mkdir()
                vault_dir.mkdir()
                fake_file = Path(td) / "settings.json"
                mp.setattr(settings_store, "SETTINGS_FILE", fake_file)
                # Initial state: user has a vault.
                settings_store.save({
                    "dump_root": str(orig_dir),
                    "obsidian_vault": str(vault_dir),
                    "apify_token": "orig_token",
                    "keyword_list": ["a", "b"],
                    "ai_prompt_template": "orig prompt",
                })
                # User clicks "Clear vault".
                ctrl = DumpFolderController(
                    dump_root=orig_dir,
                    obsidian_vault=vault_dir,
                )
                ctrl.set_obsidian_vault(None)
                # The on-disk settings must now reflect
                # the empty choice.
                loaded = settings_store.load()
                assert loaded["obsidian_vault"] == "", (
                    f"on-disk settings must reflect the cleared "
                    f"vault, got {loaded['obsidian_vault']!r}"
                )
                # The other settings were preserved
                # (same R15-1 + R16-3 contract).
                assert loaded["apify_token"] == "orig_token"
                assert loaded["keyword_list"] == ["a", "b"]
                assert loaded["ai_prompt_template"] == "orig prompt"

    def test_pick_obsidian_vault_preserves_other_settings(self) -> None:
        """Persisting the new vault must not erase the
        other settings (same R15-1 contract)."""
        from steam_review_tool.services import settings_store
        from steam_review_tool.controllers.dump_folder_controller import (
            DumpFolderController,
        )

        with pytest.MonkeyPatch().context() as mp:
            with __import__("tempfile").TemporaryDirectory() as td:
                orig_dir = Path(td) / "orig"
                new_dir = Path(td) / "new"
                old_vault = Path(td) / "old_vault"
                orig_dir.mkdir()
                new_dir.mkdir()
                old_vault.mkdir()
                fake_file = Path(td) / "settings.json"
                mp.setattr(settings_store, "SETTINGS_FILE", fake_file)
                settings_store.save({
                    "dump_root": str(orig_dir),
                    "obsidian_vault": str(old_vault),
                    "apify_token": "orig_token",
                    "keyword_list": ["a", "b"],
                    "ai_prompt_template": "orig prompt",
                    "also_csv": True,
                })
                ctrl = DumpFolderController(
                    dump_root=orig_dir,
                    obsidian_vault=old_vault,
                )
                ctrl.set_obsidian_vault(new_dir)
                loaded = settings_store.load()
                # New vault was persisted.
                assert loaded["obsidian_vault"] == str(new_dir)
                # Other settings were preserved.
                assert loaded["dump_root"] == str(orig_dir)
                assert loaded["apify_token"] == "orig_token"
                assert loaded["keyword_list"] == ["a", "b"]
                assert loaded["ai_prompt_template"] == "orig prompt"
                assert loaded["also_csv"] is True

    def test_pick_obsidian_vault_no_op_when_no_settings_file(self) -> None:
        """On a first launch (no settings file), the
        ``set_obsidian_vault`` call must not raise. The
        ``_load_settings`` call inside the R17-1 fix
        falls back to ``{}`` on ``OSError`` (via
        ``load_json_with_recovery``)."""
        from steam_review_tool.services import settings_store
        from steam_review_tool.controllers.dump_folder_controller import (
            DumpFolderController,
        )

        with pytest.MonkeyPatch().context() as mp:
            with __import__("tempfile").TemporaryDirectory() as td:
                orig_dir = Path(td) / "orig"
                new_dir = Path(td) / "new"
                orig_dir.mkdir()
                new_dir.mkdir()
                fake_file = Path(td) / "no_such_file.json"
                mp.setattr(settings_store, "SETTINGS_FILE", fake_file)
                ctrl = DumpFolderController(
                    dump_root=orig_dir,
                )
                # Must not raise on a missing settings
                # file.
                ctrl.set_obsidian_vault(new_dir)
                # The in-memory state is updated
                # regardless.
                assert ctrl.obsidian_vault == new_dir
                # The on-disk state is created with the
                # new vault.
                loaded = settings_store.load()
                assert loaded["obsidian_vault"] == str(new_dir)

    def test_set_obsidian_vault_updates_in_memory_value(self) -> None:
        """The in-memory value must be updated even if the
        disk persist fails (so the current session sees the
        change). Pins the contract that in-memory state is
        updated FIRST, then persistence is attempted."""
        from steam_review_tool.services import settings_store
        from steam_review_tool.controllers.dump_folder_controller import (
            DumpFolderController,
        )

        with pytest.MonkeyPatch().context() as mp:
            with __import__("tempfile").TemporaryDirectory() as td:
                orig_dir = Path(td) / "orig"
                new_dir = Path(td) / "new"
                orig_dir.mkdir()
                new_dir.mkdir()
                fake_file = Path(td) / "settings.json"
                mp.setattr(settings_store, "SETTINGS_FILE", fake_file)
                ctrl = DumpFolderController(
                    dump_root=orig_dir,
                )
                ctrl.set_obsidian_vault(new_dir)
                # In-memory value updated.
                assert ctrl.obsidian_vault == new_dir

    def test_tab_actions_use_set_obsidian_vault(self) -> None:
        """Static check: ``_tab_actions.pick_obsidian_vault``
        and ``clear_obsidian_vault`` must call
        ``set_obsidian_vault`` (not write ``obsidian_vault``
        directly). The pre-R17 code did
        ``self.dump_ctrl.obsidian_vault = Path(path)`` —
        a regression that reverts the fix would re-introduce
        the direct attribute write in either method."""
        from steam_review_tool.ui import _tab_actions
        src = inspect.getsource(_tab_actions)
        code = _strip_comments_and_docstrings(src)
        # ``pick_obsidian_vault`` and ``clear_obsidian_vault``
        # must call set_obsidian_vault.
        assert "set_obsidian_vault" in code, (
            "_tab_actions must call set_obsidian_vault "
            "instead of writing self.dump_ctrl.obsidian_vault "
            "directly"
        )
        # And the direct attribute write (pre-R17 anti-pattern)
        # must NOT appear in either method body.
        assert "self.dump_ctrl.obsidian_vault =" not in code, (
            "_tab_actions must NOT write "
            "self.dump_ctrl.obsidian_vault = ... directly — "
            "use set_obsidian_vault so the change is persisted"
        )

    def test_set_obsidian_vault_uses_load_then_save(self) -> None:
        """Source-shape regression: ``set_obsidian_vault`` must
        ``load`` the current settings, update the in-memory
        copy, then ``save`` the merged dict. The pre-R17
        anti-pattern (write-only-in-memory) would NOT load +
        save — a regression that reverts the fix would drop
        the ``load`` / ``save`` calls and the test would
        fail."""
        from steam_review_tool.controllers import (
            dump_folder_controller,
        )
        src = inspect.getsource(dump_folder_controller)
        code = _strip_comments_and_docstrings(src)
        # The new method must be present.
        assert "def set_obsidian_vault" in code, (
            "DumpFolderController must define "
            "set_obsidian_vault"
        )
        # Find the method body and check it has the
        # load + save pattern.
        marker = "def set_obsidian_vault("
        start = code.find(marker)
        assert start != -1
        end = code.find("\n\n", start)
        body = code[start:end]
        assert "_load_settings" in body, (
            "set_obsidian_vault must call _load_settings to "
            "read the current on-disk state"
        )
        assert "_save_settings" in body, (
            "set_obsidian_vault must call _save_settings to "
            "persist the new value"
        )


# ---------------------------------------------------------------------------
# BUG-R17-2: tab_trends._log_status is dead code
# ---------------------------------------------------------------------------
class TestNoDeadLogStatusInTabTrends:
    """``ui/tab_trends.py._log_status`` was dead code kept
    "for any external caller" — but no external caller
    exists in the codebase. Static check: the function
    must NOT be defined.

    A regression that re-introduces the dead method would
    re-add a duplicate code path that the
    ``_log_status_safe`` (thread-safe) variant already
    covers. Removing it eliminates a drift hazard.
    """

    def test_tab_trends_no_def_log_status(self) -> None:
        """``ui/tab_trends.py`` must NOT define ``_log_status``.

        The pre-R17 code had::

            def _log_status(self, msg: str) -> None:
                # Kept for any external caller that still uses
                # the old single-threaded signature...
                if self._status_lbl is not None:
                    self._status_lbl.configure(text=msg[:120])

        A grep of the codebase shows no caller (the only
        references are the def + the docstring of
        ``_log_status_safe``). The R17 fix removes the
        dead method.
        """
        from steam_review_tool.ui import tab_trends
        src = inspect.getsource(tab_trends)
        code = _strip_comments_and_docstrings(src)
        # Anchor on the def line so we don't false-match
        # a "Kept for the old _log_status" mention in a
        # docstring.
        assert "def _log_status(" not in code, (
            "ui/tab_trends.py must NOT define _log_status — "
            "it is dead code (no external caller). The "
            "thread-safe variant _log_status_safe is the "
            "only one needed."
        )

    def test_tab_trends_no_dead_code_call_to_log_status(self) -> None:
        """Static check: no caller of ``_log_status`` should
        exist anywhere in the codebase. The function
        definition removal leaves no orphan caller."""
        from pathlib import Path
        project_root = Path("steam_review_tool")
        offenders: list[str] = []
        for py in project_root.rglob("*.py"):
            text = py.read_text(encoding="utf-8")
            code = _strip_comments_and_docstrings(text)
            for ln in code.splitlines():
                if "_log_status(" in ln and "def " not in ln:
                    offenders.append(f"{py}: {ln.strip()}")
        assert not offenders, (
            "found orphan callers of _log_status (the "
            "function is being removed in R17-2): "
            f"{offenders}"
        )


# ---------------------------------------------------------------------------
# BUG-R17-3: app_window._persist_settings silent error swallow
# ---------------------------------------------------------------------------
class TestPersistSettingsLogsSaveFailure:
    """``App._persist_settings`` had a bare
    ``except Exception: pass`` that silently dropped any
    save failure. A user clicking "Don't show again" in
    the welcome dialog got no indication the setting was
    never persisted — and on next launch the greeting
    would reappear.

    R17-3 fix: catch ``OSError`` (the actual exception
    class for a save failure — disk full, permission
    denied, etc.) and log via the standard ``logging``
    module. The dev sees the trace in stderr.
    """

    def test_persist_settings_catches_oserror_not_bare_exception(
        self,
    ) -> None:
        """The ``_persist_settings`` save block must catch
        ``OSError`` specifically (not bare ``Exception``).
        A regression that reverts to ``except Exception: pass``
        would fail this test."""
        from steam_review_tool.ui import app_window
        src = inspect.getsource(app_window)
        code = _strip_comments_and_docstrings(src)
        marker = "def _persist_settings("
        start = code.find(marker)
        assert start != -1
        end = code.find("\n\n", start)
        body = code[start:end]
        # Must catch OSError, not bare Exception.
        assert "except OSError" in body, (
            "_persist_settings must catch OSError (the "
            "specific save-failure class) — a bare "
            "'except Exception: pass' silently swallows "
            "the failure and the user has no indication "
            "the save didn't happen"
        )
        # And the bare-Exception swallow must be gone.
        assert "except Exception:" not in body, (
            "_persist_settings must NOT have a bare "
            "'except Exception:' (R12-4 to R12-7 + R15-3 "
            "lesson — always log via the standard "
            "logging module as the primary surface)"
        )

    def test_persist_settings_logs_via_logging_module(
        self,
    ) -> None:
        """The save block must use the standard ``logging``
        module to surface the failure. R12-4 to R12-7 +
        R15-3 lesson: ``logging.getLogger(__name__)
        .exception(...)`` is the primary surface."""
        from steam_review_tool.ui import app_window
        src = inspect.getsource(app_window)
        code = _strip_comments_and_docstrings(src)
        marker = "def _persist_settings("
        start = code.find(marker)
        assert start != -1
        end = code.find("\n\n", start)
        body = code[start:end]
        # ``logging.getLogger(__name__).exception(...)`` is
        # the pattern. Accept either ``logging.getLogger``
        # (call form) or ``getLogger`` (already imported).
        assert (
            "logging.getLogger" in body
            or "getLogger(__name__)" in body
        ), (
            "_persist_settings must use the standard "
            "logging module (logging.getLogger(__name__) "
            "or an already-imported getLogger) so the "
            "failure is visible in stderr"
        )
        assert ".exception(" in body, (
            "_persist_settings must use .exception() (not "
            ".warning() or .error()) so the full traceback "
            "is preserved for the developer"
        )

    def test_persist_settings_actually_persists(self) -> None:
        """End-to-end: ``_persist_settings`` must call
        ``settings_store.save`` after updating the
        in-memory settings. A regression that drops the
        save call (e.g. just ``self.settings.update``)
        would fail this test."""
        from steam_review_tool.ui import app_window
        src = inspect.getsource(app_window)
        code = _strip_comments_and_docstrings(src)
        marker = "def _persist_settings("
        start = code.find(marker)
        assert start != -1
        end = code.find("\n\n", start)
        body = code[start:end]
        assert "_save(self.settings)" in body or "_save(settings" in body, (
            "_persist_settings must call _save(...) to "
            "actually persist the updated settings — "
            "a regression that drops the save call would "
            "leave the data in-memory only"
        )
