"""Filter configuration passed to a review source."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class FilterConfig:
    """The full set of filters the user has selected.

    Used by both the API tab and the Playwright tab. ``min_date_ts``
    is the absolute UTC unix timestamp below which reviews are dropped.
    """
    language: str = "all"
    review_filter: str = "all"
    review_type: str = "all"
    day_range: Optional[int] = None
    min_date_ts: Optional[int] = None
    min_helpful: int = 0
    num_per_page: int = 100


__all__ = ["FilterConfig"]