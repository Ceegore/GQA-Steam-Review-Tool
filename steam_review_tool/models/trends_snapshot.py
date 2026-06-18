"""Per-app time-series snapshots for the Trends tab."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class TrackedApp:
    """An app the user is tracking for trend metrics."""
    app_id: int
    name: str


@dataclass
class TrendsSnapshot:
    """One observation for one app at one moment in time."""
    app_id: int
    ts: int  # UTC unix seconds
    wishlist: Optional[int] = None
    followers: Optional[int] = None
    reviews: Optional[int] = None
    positive_pct: Optional[float] = None


__all__ = ["TrackedApp", "TrendsSnapshot"]