"""Atomic file write helper.

Wraps ``Path.write_text()`` so the write is **atomic**:
write to a temp file in the same directory, then ``os.replace()`` to
the final name. This protects against partial-write corruption when
the process is killed (Ctrl+C, OOM, power loss) mid-write.

Also provides a corruption-recovery helper that, on a ``JSONDecodeError``,
moves the broken file to ``<name>.corrupt-<timestamp>-<n>`` so the next
load falls back to defaults instead of silently wiping user data.
"""
from __future__ import annotations

import itertools
import json
import os
from typing import Any, Callable
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Union


# Process-unique counter for the corrupt-backup filename. The first
# 6 hex chars of ``uuid4`` are the secondary tie-breaker; the counter
# is the tertiary tie-breaker (in case the user clears their UUID seed
# for some reason). Two corrupt reads in the same microsecond on the
# same process would otherwise collide on the previous
# ``int(datetime.now(...).timestamp())`` second-precision suffix — on
# Windows the second ``os.replace`` would fail with ``FileExistsError``
# (leaving the new corrupt file in place un-renamed), and on POSIX it
# would silently overwrite the first backup with the second.
_BACKUP_COUNTER = itertools.count()


def atomic_write_text(path: Path, content: str,
                       encoding: str = "utf-8") -> None:
    """Write ``content`` to ``path`` atomically.

    Writes to a temp file in the same directory (so ``os.replace`` is
    a single rename on the same filesystem, not a copy), then renames
    it over the target. The rename is atomic on POSIX and Windows
    NTFS for files on the same volume.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=path.name + ".",
        suffix=".tmp",
        dir=str(path.parent),
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding=encoding) as f:
            f.write(content)
        os.replace(tmp_path, path)
    except Exception:
        # Clean up the temp file on any error
        try:
            tmp_path.unlink()
        except OSError:
            pass
        raise


def atomic_write_json(path: Path, data: Any,
                       *, indent: int = 2,
                       ensure_ascii: bool = False) -> None:
    """Atomic JSON write."""
    text = json.dumps(data, indent=indent, ensure_ascii=ensure_ascii)
    atomic_write_text(path, text)


def load_json_with_recovery(
    path: Path,
    *,
    default: Any = None,
    on_corrupt: Optional["Callable[[Path, Exception], None]"] = None,
) -> Any:
    """Load JSON from ``path`` with graceful corruption recovery.

    On ``JSONDecodeError`` or any other parse error, the broken file
    is moved aside to ``<name>.corrupt-<micro-ts>-<n>`` so the user can
    inspect it later. Returns ``default`` (which itself defaults to
    ``None``).

    The backup filename uses microsecond precision + a process-unique
    counter so two corruption events in the same second (e.g. a CI
    test that writes a broken file twice, or a system crash that
    re-corrupts the same file) don't collide. The previous
    second-precision suffix caused the second ``os.replace`` to fail
    on Windows (``FileExistsError`` → second backup silently dropped)
    or to silently overwrite the first backup on POSIX.
    """
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        # Microsecond precision + monotonic counter — the counter
        # alone would be enough, but a human-readable timestamp in
        # the filename is a real help when the user is digging
        # through a folder of "settings.json.corrupt-…" backups.
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%f")
        n = next(_BACKUP_COUNTER)
        backup = path.with_suffix(f"{path.suffix}.corrupt-{ts}-{n}")
        try:
            os.replace(path, backup)
        except OSError:
            # If we can't even rename it, just leave it alone and
            # return the default.
            pass
        if on_corrupt is not None:
            try:
                on_corrupt(backup, exc)
            except Exception:
                pass
        return default


__all__ = [
    "atomic_write_text",
    "atomic_write_json",
    "load_json_with_recovery",
]