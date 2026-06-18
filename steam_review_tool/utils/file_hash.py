"""File hashing helpers used by the Obsidian-vault sync."""
from __future__ import annotations

import hashlib
from pathlib import Path


def file_content_hash(path: Path) -> str:
    """Return a hex SHA-1 of a file's bytes, or ``""`` on any I/O error.

    Used by the Obsidian-vault sync to compare two files of the same
    name without copying them again. SHA-1 is fine here — Python's
    ``hashlib`` always ships it and collision risk for ``.md`` files is
    irrelevant.
    """
    try:
        with open(path, "rb") as f:
            return hashlib.sha1(f.read()).hexdigest()
    except OSError:
        return ""


__all__ = ["file_content_hash"]