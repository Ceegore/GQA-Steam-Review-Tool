"""Dump-folder controller.

Owns the "📁 Set dump folder…", "📂 Open dump folder",
"🎮 Open game folder" actions and the Obsidian-vault copy step.

Communicates only through the event bus, so any tab or controller can
ask it to do something without knowing who else is listening.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Optional

from ..core.event_bus import bus
from ..exporters.obsidian_copier import copy_to_obsidian_vault
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
        bus.publish("dump.root.changed", path=str(path))
        # Persist the new dump root to ``settings.json`` so
        # the choice survives an app restart. The previous
        # version only updated the in-memory ``self.dump_root``,
        # so a user who picked a new dump folder via the
        # "Set…" button (without opening the Settings dialog)
        # would find their choice reverted on next launch.
        # The Settings dialog is the only OTHER path that
        # touches ``settings.json.dump_root``; both paths
        # now converge to the same on-disk value.
        try:
            from ..services.settings_store import (
                load as _load_settings,
                save as _save_settings,
            )
            current = _load_settings()
        except OSError as exc:
            _log.warning(
                "could not load settings for dump_root persist: %s",
                exc,
            )
            return
        current["dump_root"] = str(path)
        try:
            _save_settings(current)
        except OSError as exc:
            _log.warning(
                "could not persist dump_root to settings: %s",
                exc,
            )

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
        except OSError as exc:
            _log.warning(
                "could not load settings for obsidian_vault persist: %s",
                exc,
            )
            return
        current["obsidian_vault"] = str(vault) if vault else ""
        try:
            _save_settings(current)
        except OSError as exc:
            _log.warning(
                "could not persist obsidian_vault to settings: %s",
                exc,
            )

    def open_dump_folder(self) -> Optional[str]:
        return self._open(self.dump_root)

    def open_game_folder(self, app_id: int, safe_name: str) -> Optional[str]:
        folder = self.dump_root / f"{app_id}_{safe_name}"
        return self._open(folder)

    # ---- obsidian sync -------------------------------------------------

    def sync_to_obsidian(self, exported_path: Path) -> Optional[str]:
        if not self.obsidian_vault:
            return None
        return copy_to_obsidian_vault(exported_path, self.obsidian_vault)


__all__ = ["DumpFolderController"]