"""String utilities: filename sanitization and filter labels."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from ..core.timezone import current_berlin


def sanitize_for_filename(s: str, max_len: int = 30) -> str:
    """Make ``s`` safe to embed in a filename.

    Strips path separators, Windows-reserved characters, collapses
    whitespace, and truncates to ``max_len``. Returns ``"app"`` if the
    input is empty or only contains forbidden characters.
    """
    if not s:
        return "app"
    bad = '<>:"/\\|?*'
    out = "".join("_" if c in bad else c for c in s)
    out = "_".join(out.split())
    out = out.strip(" ._") or "app"
    if len(out) > max_len:
        out = out[:max_len].rstrip("._")
    return out


def make_export_basename(
    game_name: str,
    filter_label: str,
    now: Optional[datetime] = None,
) -> str:
    """Build the short export filename.

    Format: ``GQA Reviewdump_<game_short>_<filter>_<YYYYMMDD-HHMM>.md``
    Example: ``GQA Reviewdump_BusSim27_last3h_20260617-1430.md``
    """
    if now is None:
        now = current_berlin()
    game_short = sanitize_for_filename(game_name, max_len=25)
    filt = sanitize_for_filename(filter_label or "all", max_len=20)
    ts = now.strftime("%Y%m%d-%H%M")
    return f"GQA Reviewdump_{game_short}_{filt}_{ts}.md"


def short_filter_label(tab: str, app) -> str:
    """Human-readable filter mode label for the export filename.

    Reads the appropriate GUI widgets via ``app`` and returns something
    like ``"last3h"``, ``"last24h"``, ``"all"``, or
    ``"custom2026-06-10T14h"``.
    """
    prefix = "pw_" if tab == "pw" else ""
    try:
        preset = getattr(app, f"{prefix}since_preset_var").get()
    except AttributeError:
        return "all"
    if not preset.startswith("custom"):
        parts = preset.split()
        if len(parts) >= 2 and parts[0] == "last":
            unit = parts[2].rstrip("s")
            return f"last{parts[1]}{unit[0]}"
        return "all"
    try:
        d = getattr(app, f"{prefix}since_date_entry").get()
        t = getattr(app, f"{prefix}since_time_entry").get()
    except AttributeError:
        return "custom"
    if d and t:
        return f"custom{d.replace('-', '')}T{t.replace(':', '')}"
    if d:
        return f"custom{d.replace('-', '')}"
    return "custom"


__all__ = ["sanitize_for_filename", "make_export_basename", "short_filter_label"]