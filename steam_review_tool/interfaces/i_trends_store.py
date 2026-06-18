"""Trends store interface."""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

from ..models.trends_snapshot import TrackedApp, TrendsSnapshot


class ITrendsStore(Protocol):
    """Tracks per-app time-series snapshots (wishlist / followers / reviews)."""

    def tracked_apps(self) -> list[TrackedApp]: ...

    def is_tracked(self, app_id: int) -> bool: ...

    def add(self, app_id: int, name: str) -> None: ...

    def remove(self, app_id: int) -> None: ...

    def record(self, snapshot: TrendsSnapshot) -> None: ...

    def series(
        self, app_id: int, metric: str, days: int | None = None
    ) -> list[TrendsSnapshot]: ...


__all__ = ["ITrendsStore"]