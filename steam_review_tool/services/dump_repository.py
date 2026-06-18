"""Per-game dump repository (seen-IDs dedup ledger + folders).

We do NOT want a full database of every review Steam has ever shown
us. We only need to know "have I dumped this review_id before?" for
each game, so the "Fetch new" button can skip already-exported ones.

Format on disk::

    <dump_root>/<app_id>_<safe_name>/seen_ids.json
    {
      "app_id": 4311090,
      "name": "Bus Simulator 27 Demo",
      "seen_ids": ["abc123", "def456", ...],
      "last_export_at": "2026-06-17T14:30:00",
      "total_exported": 42
    }
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..core.atomic_write import atomic_write_json, load_json_with_recovery
from ..core.logger import get_logger
from ..core.paths import game_dump_folder, seen_ids_path
from ..utils.text_utils import sanitize_for_filename

_log = get_logger(__name__)

# Reject anything that isn't a single safe-name component. Prevents
# path traversal when ``safe_name`` is built from untrusted input
# (e.g., a game name from the Steam API).
_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,100}$")


class DumpRepository:
    """File-backed dedup ledger of already-exported review IDs."""

    def __init__(self, dump_root: Path) -> None:
        self.dump_root = dump_root

    def folder_for(
        self, app_id: Optional[int], safe_name: str
    ) -> Path:
        return game_dump_folder(
            self.dump_root, app_id, self._sanitize(safe_name),
        )

    def _path(self, app_id: int, safe_name: str) -> Path:
        return seen_ids_path(
            self.dump_root, app_id, self._sanitize(safe_name),
        )

    @staticmethod
    def _sanitize(safe_name: str) -> str:
        """Defence-in-depth: enforce the safe-name regex after the
        caller has already sanitized. Rejects any path-traversal
        payload (e.g., ``..\\..\\evil``).
        """
        # First normalise through the standard helper so callers
        # passing raw game names (which may contain spaces) still work.
        cleaned = sanitize_for_filename(safe_name, max_len=80)
        if not _SAFE_NAME_RE.match(cleaned):
            raise ValueError(
                f"unsafe safe_name after sanitisation: {cleaned!r} "
                f"(must match {_SAFE_NAME_RE.pattern})"
            )
        return cleaned

    def load_seen(self, app_id: int, safe_name: str) -> set[str]:
        path = self._path(app_id, safe_name)
        data = load_json_with_recovery(
            path, default={"seen_ids": []},
            on_corrupt=lambda backup, exc: _log.warning(
                "seen_ids.json was corrupt (%s); moved to %s — "
                "re-running this game will re-export its reviews.",
                exc, backup,
            ),
        )
        return set(data.get("seen_ids", []))

    def save_seen(
        self,
        app_id: int,
        safe_name: str,
        ids: set[str],
        name: str = "",
    ) -> None:
        path = self._path(app_id, safe_name)
        payload = {
            "app_id": app_id,
            "name": name or safe_name,
            "seen_ids": sorted(ids),
            "last_export_at": datetime.now(timezone.utc).isoformat(),
            "total_exported": len(ids),
        }
        atomic_write_json(path, payload)

    # ---- simplified 1-arg API used by the tab controllers ----------------

    def _guess_safe_name(self, app_id: int) -> str:
        """Find the per-game folder for ``app_id`` and reuse its safe_name.
        Falls back to ``str(app_id)`` if the folder doesn't exist yet.
        """
        if self.dump_root is None or not self.dump_root.exists():
            return str(app_id)
        prefix = f"{app_id}_"
        try:
            with os.scandir(self.dump_root) as it:
                for entry in it:
                    if entry.is_dir() and entry.name.startswith(prefix):
                        return entry.name[len(prefix):]
        except OSError:
            pass
        return str(app_id)

    def load_seen_ids(self, app_id: int) -> list[str]:
        """Back-compat 1-arg wrapper used by the tab controllers."""
        safe_name = self._guess_safe_name(app_id)
        return sorted(self.load_seen(app_id, safe_name))

    def save_seen_ids(
        self, app_id: int, ids: list[str], name: str = "",
    ) -> None:
        """Back-compat 1-arg wrapper used by the tab controllers."""
        safe_name = self._guess_safe_name(app_id)
        self.save_seen(app_id, safe_name, set(ids), name=name)


__all__ = ["DumpRepository"]