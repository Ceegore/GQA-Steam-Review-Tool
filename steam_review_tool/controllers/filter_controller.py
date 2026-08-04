"""Filter controller — shared between the API tab and the PW tab.

Translates the user's "When to include" combo + date + time entries
into a FilterConfig and a UTC timestamp, ready to feed to either
review source.
"""
from __future__ import annotations

from time import time as _now
from typing import Optional, Any

from ..models.filter_config import FilterConfig
from ..utils.datetime_utils import compute_since_timestamp


def build_filter_config(
    *,
    language: str = "all",
    review_filter: str = "all",
    review_type: str = "all",
    day_range: Optional[int] = None,
    min_helpful: int = 0,
    num_per_page: int = 100,
    preset_label: str = "all time",
    custom_date: str = "",
    custom_time: str = "",
) -> FilterConfig:
    """Compose a FilterConfig + the derived ``min_date_ts`` lower bound."""
    min_date_ts = compute_since_timestamp(preset_label, custom_date, custom_time)
    return FilterConfig(
        language=language,
        review_filter=review_filter,
        review_type=review_type,
        day_range=day_range,
        min_date_ts=min_date_ts,
        min_helpful=min_helpful,
        num_per_page=num_per_page,
    )


def _safe_ts(r: dict[str, Any]) -> int:
    """Coerce a review's ``timestamp_created`` into a plain int.

    The Steam API normally returns an int, but normalised review
    dicts (e.g. from the Apify client or a hand-rolled test) can
    carry ``None`` or a non-numeric string. Treating those as
    ``timestamp = 0`` keeps ``apply_window_filter`` from crashing
    the whole export just because one review row is malformed.
    """
    raw = r.get("timestamp_created")
    if raw is None:
        return 0
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def apply_window_filter(
    reviews: list[dict[str, Any]], window: str,
) -> list[dict[str, Any]]:
    """Drop reviews that fall outside the chosen "Window".

    ``window`` is one of:
      - ``"all"``         — keep everything
      - ``"first 24h"``   — keep only reviews within 24 h of the earliest
      - ``"last 7d"``     — keep only reviews in the last 7 days
    """
    if not reviews or window == "all":
        return reviews
    ts = [_safe_ts(r) for r in reviews]
    if window == "first 24h":
        t0 = min(ts) if ts else 0
        return [r for r in reviews if _safe_ts(r) < t0 + 86400]
    if window == "last 7d":
        cutoff = int(_now()) - 7 * 86400
        return [r for r in reviews if _safe_ts(r) >= cutoff]
    return reviews


__all__ = ["build_filter_config", "apply_window_filter"]