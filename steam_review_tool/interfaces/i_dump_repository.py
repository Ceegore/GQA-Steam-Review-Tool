"""Per-game dump repository (seen-IDs dedup ledger)."""
from __future__ import annotations

from pathlib import Path
from typing import Protocol


class IDumpRepository(Protocol):
    """Persistent store of review IDs we have already exported per game."""

    def load_seen(self, app_id: int) -> set[str]: ...

    def save_seen(self, app_id: int, ids: set[str]) -> None: ...

    def dump_folder(self, app_id: int, safe_name: str) -> Path: ...


__all__ = ["IDumpRepository"]