"""File hashing helpers used by the Obsidian-vault sync."""
from __future__ import annotations

import hashlib
from pathlib import Path

# 1 MiB read chunk — large enough that the per-call overhead of
# ``hashlib.sha1(...).update(...)`` is amortised, small enough that
# a 150 MB Chromium download doesn't blow the heap.
_HASH_CHUNK_BYTES = 1 << 20


def file_content_hash(path: Path) -> str:
    """Return a hex SHA-1 of a file's bytes, or ``""`` on any I/O error.

    Used by the Obsidian-vault sync to compare two files of the same
    name without copying them again. SHA-1 is fine here — Python's
    ``hashlib`` always ships it and collision risk for ``.md`` files is
    irrelevant.

    The previous implementation did ``f.read()`` which loaded the
    entire file into memory. For a 10 MB ``.md`` export this is
    fine, but the function is also used to compare any file the
    user copies to their vault — a user dragging a large video
    review (or a binary blob by mistake) would have OOM'd the
    process. Block-stream the file instead.
    """
    try:
        h = hashlib.sha1()
        with open(path, "rb") as f:
            while True:
                block = f.read(_HASH_CHUNK_BYTES)
                if not block:
                    break
                h.update(block)
        return h.hexdigest()
    except OSError:
        return ""


__all__ = ["file_content_hash"]