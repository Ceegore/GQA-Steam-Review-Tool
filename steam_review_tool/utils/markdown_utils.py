"""Small Markdown escaping helpers used by the exporters."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional


def md_escape(s: Optional[str]) -> str:
    """Escape characters that would break Markdown tables / code blocks."""
    if s is None:
        return ""
    return s.replace("|", "\\|").replace("\r", "")


def ts_to_iso(ts: Optional[int]) -> str:
    """Format ``ts`` as ``'YYYY-MM-DD HH:MM:SS UTC'`` or ``'—'`` if absent."""
    if not ts:
        return "—"
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S UTC"
        )
    except (OverflowError, OSError, ValueError):
        return "—"


def yesno(b: Optional[bool]) -> str:
    """Render a bool flag as ``✓`` / ``✗`` / ``—``."""
    if b is True:
        return "✓"
    if b is False:
        return "✗"
    return "—"


__all__ = ["md_escape", "ts_to_iso", "yesno"]