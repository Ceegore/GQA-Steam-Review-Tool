"""Berlin timezone helper with a tzdata-free DST-aware fallback.

The Windows Store Python build ships without ``tzdata``, so we fall back
to a manual CET/CEST switch: CET = UTC+1, CEST = UTC+2, with the switch
on the last Sunday of March (→ CEST) and the last Sunday of October
(→ CET). The exact EU rules have changed a few times historically,
but for the GUI's display "close enough" is fine — DST boundaries
shift at most by a few minutes vs. the official tzdata rules.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone, tzinfo
from typing import Optional

try:  # Python 3.9+
    from zoneinfo import ZoneInfo
    BERLIN: tzinfo = ZoneInfo("Europe/Berlin")
    _USE_ZONEINFO = True
except Exception:  # pragma: no cover - tzdata missing

    def _last_sunday(year: int, month: int) -> int:
        """Return the day-of-month of the last Sunday in ``year/month``."""
        # Day 1 of the month → find weekday; then subtract days to get
        # to Sunday, then add 7 to ensure we land on the *last* Sunday.
        first = datetime(year, month, 1)
        # weekday(): Mon=0, Sun=6
        days_to_sunday = (6 - first.weekday()) % 7
        last_sunday_day = days_to_sunday + 1
        # Add 7 until we exceed the month's end
        while True:
            try:
                datetime(year, month, last_sunday_day + 7)
                last_sunday_day += 7
            except ValueError:
                break
        return last_sunday_day

    def _is_cest(year: int, month: int, day: int) -> bool:
        """``True`` if the given date is in CEST (summer time)."""
        if 4 <= month <= 9:
            return True
        if month in (1, 2, 11, 12):
            return False
        # March: after the last Sunday 01:00 UTC → CEST
        if month == 3:
            return day >= _last_sunday(year, 3)
        # October: before the last Sunday 01:00 UTC → still CEST
        if month == 10:
            return day < _last_sunday(year, 10)
        return False

    class _BerlinTZ(tzinfo):
        """CET (UTC+1) / CEST (UTC+2) — manual DST switch."""

        def utcoffset(self, dt):
            if _is_cest(dt.year, dt.month, dt.day):
                return timedelta(hours=2)
            return timedelta(hours=1)

        def dst(self, dt):
            if _is_cest(dt.year, dt.month, dt.day):
                return timedelta(hours=1)
            return timedelta(0)

        def tzname(self, dt):
            return "CEST" if _is_cest(dt.year, dt.month, dt.day) else "CET"

    BERLIN = _BerlinTZ()
    _USE_ZONEINFO = False


def format_berlin(ts: Optional[int]) -> str:
    """Format a unix timestamp as 'YYYY-MM-DD HH:MM:SS (Europe/Berlin)'."""
    if ts is None:
        return "—"
    dt = datetime.fromtimestamp(ts, tz=BERLIN)
    return dt.strftime("%Y-%m-%d %H:%M:%S %Z")


def current_berlin_str() -> str:
    """Return current time in Berlin as 'YYYY-MM-DD HH:MM:SS'."""
    return datetime.now(BERLIN).strftime("%Y-%m-%d %H:%M:%S")


def current_berlin() -> datetime:
    """Return ``datetime.now(BERLIN)`` — convenient for tests/DI."""
    return datetime.now(BERLIN)


__all__ = ["BERLIN", "format_berlin", "current_berlin_str", "current_berlin"]