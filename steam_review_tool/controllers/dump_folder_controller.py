"""Dump-folder controller.

Owns the "📁 Set dump folder…", "📂 Open dump folder"
actions and the vault-persistence chokepoints.

The tabs call :meth:`set_dump_root` / :meth:`set_obsidian_vault`
directly (the R16-3 / R17-1 chokepoints) and re-render their labels
in the same handler. The controller used to publish a
``dump.root.changed`` bus event too, but a R19-2 audit found
zero subscribers — the event was dead and was removed.

R27 removed two more dead public methods:
  - :meth:`DumpFolderController.open_game_folder` (defined
    but never called from any UI / controller / test).
    The "open game folder" feature is documented in the
    help text but the wiring was never finished.
  - :meth:`DumpFolderController.sync_to_obsidian` (defined
    but never called). The actual Obsidian sync happens
    via the export flow's ``run_export(..., obsidian_vault=...)``
    parameter (see :mod:`exporters.export_orchestrator`),
    which passes the vault through to
    :func:`exporters.obsidian_copier.copy_to_obsidian_vault`
    directly. The wrapper method on
    :class:`DumpFolderController` was a leftover from an
    earlier design where the controller was the single
    chokepoint.

R27 also removed the now-unused
``from ..exporters.obsidian_copier import copy_to_obsidian_vault``
import (the function is still used by
:mod:`exporters.export_orchestrator`).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Optional

from ..utils.os_open import open_path_in_os


_log = get_logger = logging.getLogger(__name__)


class DumpFolderController:
    """Centralizes all file-system actions on the dump folder."""

    def __init__(
        self,
        dump_root: Path,
        obsidian_vault: Optional[Path] = None,
        open_external: Optional[Callable[[Path], Optional[str]]] = None,
    ) -> None:
        self.dump_root = dump_root
        self.obsidian_vault = obsidian_vault
        self._open = open_external or open_path_in_os

    # ---- folder actions ------------------------------------------------

    def set_dump_root(self, path: Path) -> None:
        self.dump_root = path
        # Persist the new dump root to ``settings.json`` so
        # the choice survives an app restart. The previous
        # version only updated the in-memory ``self.dump_root``,
        # so a user who picked a new dump folder via the
        # "Set…" button (without opening the Settings dialog)
        # would find their choice reverted on next launch.
        # The Settings dialog is the only OTHER path that
        # touches ``settings.json.dump_root``; both paths
        # now converge to the same on-disk value.
        #
        # The previous version of this method also
        # ``bus.publish("dump.root.changed", path=str(path))``
        # but a grep across the codebase (R19-2 audit)
        # found zero subscribers — the event was dead.
        # The tabs that react to a dump-root change
        # (recreate ``dump_repo``, refresh the label)
        # already do so directly in
        # ``_on_pick_dump_root`` after calling the
        # chokepoint. Removed in R19-2 to eliminate
        # the drift hazard (same R17-2 / R18-2
        # "no consumer" anti-pattern).
        try:
            from ..services.settings_store import (
                load as _load_settings,
                save as _save_settings,
            )
            current = _load_settings()
        except OSError:
            # ``_log.exception`` (not ``_log.warning``) so the
            # traceback is captured — a "could not load
            # settings" failure with only the exception
            # message hides the file path / permissions
            # error that the developer needs to debug.
            # Same R12-4 to R12-7 + R15-3 lesson applied
            # to the new dump_root chokepoint in R16-3.
            _log.exception("could not load settings for dump_root persist")
            return
        current["dump_root"] = str(path)
        try:
            _save_settings(current)
        except OSError:
            # Same R12-4 + R15-3 traceback-capture lesson:
            # a save failure with only the exception
            # message hides WHICH path failed and WHY.
            # ``_log.exception`` captures the traceback.
            _log.exception("could not persist dump_root to settings")

    def set_obsidian_vault(self, vault: Optional[Path]) -> None:
        """Update the in-memory vault + persist the change.

        Same R16-3 fix-shape as :meth:`set_dump_root`: a user
        who picked a new Obsidian vault via the "Pick vault"
        button (without opening the Settings dialog) used to
        find the choice reverted on next launch because only
        ``self.obsidian_vault`` was updated — ``settings.json``
        was never touched, so ``settings_store.load()`` on
        the next launch read the previous value and the
        DEFAULTS merge filled the new key with ``""``. The
        Settings dialog does persist the vault (it goes
        through ``save_cb`` → ``_on_saved`` → ``save``); the
        picker is the only path that bypasses the dialog and
        therefore needs explicit persistence.
        """
        self.obsidian_vault = vault
        try:
            from ..services.settings_store import (
                load as _load_settings,
                save as _save_settings,
            )
            current = _load_settings()
        except OSError:
            # Same R12-4 + R15-3 traceback-capture lesson
            # as ``set_dump_root`` above. ``_log.exception``
            # captures the traceback so a developer can
            # see WHICH settings file failed to load
            # (file path, permissions, etc.) — not just
            # the bare exception message.
            _log.exception("could not load settings for obsidian_vault persist")
            return
        current["obsidian_vault"] = str(vault) if vault else ""
        try:
            _save_settings(current)
        except OSError:
            # Same R12-4 + R15-3 traceback-capture lesson:
            # ``_log.exception`` captures the traceback
            # so a save failure surfaces the file path
            # + permissions error in the log.
            _log.exception("could not persist obsidian_vault to settings")

    def open_dump_folder(self) -> Optional[str]:
        return self._open(self.dump_root)


__all__ = ["DumpFolderController"]