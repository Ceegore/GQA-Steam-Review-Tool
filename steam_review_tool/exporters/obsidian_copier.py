"""Obsidian-vault sync: copy exported .md files into a chosen vault folder.

Skips copies when the destination already has a file with the same
SHA-1 (saves IO and avoids needless writes).
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

from ..utils.file_hash import file_content_hash


def copy_to_obsidian_vault(src_path: Path, vault_root: Path) -> Optional[str]:
    """Copy ``src_path`` to ``vault_root``.

    Returns ``None`` on success, an error string on failure.
    No-ops (returns ``None``) if the vault is empty.
    """
    if not vault_root:
        return None
    if not src_path.exists():
        return f"Source file does not exist: {src_path}"
    try:
        vault_root.mkdir(parents=True, exist_ok=True)
        dest = vault_root / src_path.name
        # Skip if identical (same content hash)
        if dest.exists():
            if file_content_hash(src_path) == file_content_hash(dest):
                return None
        shutil.copy2(src_path, dest)
        return None
    except OSError as exc:
        return str(exc)


__all__ = ["copy_to_obsidian_vault"]