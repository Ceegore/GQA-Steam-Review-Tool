"""Date/time helpers for the "When to include" filter."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from ..core.constants import SINCE_PRESETS
from ..core.timezone import BERLIN, current_berlin


def parse_since_preset(label: str) -> int:
    """Return the hours value for a preset label, or -1 for 'custom'.

    ``0`` means "all time" (no filter); ``-1`` means "custom" — the
    caller must then look at the date+time entries.
    """
    for lbl, hrs in SINCE_PRESETS:
        if lbl == label:
            return hrs
    return 0


def compute_since_timestamp(
    preset_label: str,
    custom_date_str: str = "",
    custom_time_str: str = "",
    now: Optional[datetime] = None,
) -> Optional[int]:
    """Translate (preset, date, time) into a UTC unix timestamp.

    Returns ``None`` if no filter is active (preset is "all time" or
    unknown, or both custom date+time are blank).
    """
    if now is None:
        now = current_berlin()

    hours = parse_since_preset(preset_label)
    if hours == 0:
        return None
    if hours > 0:
        since = now - timedelta(hours=hours)
        return int(since.timestamp())
    # hours == -1 → custom mode
    date_s = (custom_date_str or "").strip()
    time_s = (custom_time_str or "").strip()
    if not date_s and not time_s:
        return None
    if not date_s:
        date_s = now.strftime("%Y-%m-%d")
    if not time_s:
        time_s = "00:00"
    try:
        naive = datetime.strptime(f"{date_s} {time_s}", "%Y-%m-%d %H:%M")
    except ValueError:
        return None
    berlin_dt = naive.replace(tzinfo=BERLIN)
    return int(berlin_dt.timestamp())


__all__ = ["parse_since_preset", "compute_since_timestamp"]