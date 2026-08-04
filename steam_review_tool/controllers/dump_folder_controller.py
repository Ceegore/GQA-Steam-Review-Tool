"""Dump-folder controller.

Owns the "📁 Set dump folder…", "📂 Open dump folder",
"🎮 Open game folder" actions and the Obsidian-vault copy step.

Communicates only through the event bus, so any tab or controller can
ask it to do something without knowing who else is listening.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from ..core.event_bus import bus
from ..exporters.obsidian_copier import copy_to_obsidian_vault
from ..utils.os_open import open_path_in_os


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