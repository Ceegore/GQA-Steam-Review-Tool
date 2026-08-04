"""Date/time helpers for the "When to include" filter."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from ..core.constants import SINCE_PRESETS
from ..core.logger import get_logger
from ..core.timezone import BERLIN, current_berlin


_log = get_logger(__name__)


def parse_since_preset(label: str) -> int:
    """Return the hours value for a preset label, or 0 for unknown.

    ``0`` means "all time" (no filter) AND is the fallback for an
    unknown label; ``-1`` means "custom" — the caller must then look
    at the date+time entries. Callers that need to distinguish
    "all time" from "unknown" should check whether ``label`` appears
    in :data:`SINCE_PRESETS` first.
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

    Returns ``None`` if no filter is active (preset is "all time",
    both custom date+time are blank, or the input is otherwise empty).

    Unknown preset labels are logged at WARNING level and also yield
    ``None`` — but the caller's UI should be checked separately. A
    silently-dropped filter on an unknown label is the worst
    outcome (a user thinks they applied "last 3 days" and gets all
    reviews) so we surface the misconfiguration in the log.
    """
    if now is None:
        now = current_berlin()

    # Detect "unknown preset" so we can warn instead of silently
    # treating it like "all time". ``parse_since_preset`` returns 0
    # for both the real "all time" label and for any unknown label.
    if preset_label and not any(
        lbl == preset_label for lbl, _hrs in SINCE_PRESETS
    ):
        _log.warning(
            "compute_since_timestamp: unknown preset label %r — "
            "treating as 'all time' (no filter applied).",
            preset_label,
        )
        return None

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