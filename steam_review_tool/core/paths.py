"""Filesystem path helpers for the per-game dump tree.

All path computations live here so we can swap the on-disk layout
without hunting through business logic.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from .constants import CONFIG_DIR, DEFAULT_DUMP_ROOT


def ensure_config_dir() -> Path:
    """Create and return the hidden config dir (~/.steam_review_tool/)."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return CONFIG_DIR


def game_dump_folder(dump_root: Path, app_id: Optional[int], safe_name: str) -> Path:
    """Return ``<dump_root>/<app_id>_<safe_name>/`` for a given game.

    ``app_id`` may be ``None`` (no game loaded yet) — in that case the
    parent ``dump_root`` is returned without creating a sub-folder.
    """
    if app_id is None:
        return dump_root
    folder = dump_root / f"{app_id}_{safe_name}"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def seen_ids_path(dump_root: Path, app_id: Optional[int], safe_name: str) -> Path:
    """Path to the per-app ``seen_ids.json`` dedup ledger."""
    return game_dump_folder(dump_root, app_id, safe_name) / "seen_ids.json"


def progress_file(app_id: int) -> Path:
    """Path used by the Playwright subprocess to checkpoint its cursor.

    Deterministic per ``app_id`` so the worker can resume without
    knowing the GUI's PID.
    """
    return ensure_config_dir() / f"_pw_progress_{app_id}.json"


def default_dump_root() -> Path:
    """Return the user's default dump root, creating it if necessary."""
    DEFAULT_DUMP_ROOT.mkdir(parents=True, exist_ok=True)
    return DEFAULT_DUMP_ROOT


__all__ = [
    "ensure_config_dir",
    "game_dump_folder",
    "seen_ids_path",
    "progress_file",
    "default_dump_root",
]