"""URL/ID parsing utilities for Steam app identifiers."""
from __future__ import annotations

import re
from typing import Optional


# Steam App IDs are positive 32-bit integers (per Steamworks docs).
# We reject anything outside the valid range as a defence against
# malformed input from the URL field.
MAX_STEAM_APP_ID = 2_147_483_647  # int32 max


def resolve_app_id(query: str) -> Optional[int]:
    """Extract a Steam ``App ID`` from various input formats.

    Accepts:
      - bare App ID: ``"4311090"``
      - store URL:    ``"https://store.steampowered.com/app/4311090/..."``
      - sub URL:      ``"steam://run/4311090"``

    Returns the integer App ID or ``None`` if it can't be parsed or
    falls outside the valid Steam App-ID range.
    """
    q = (query or "").strip()
    if not q:
        return None
    if q.isdigit():
        return _validate(int(q))
    m = re.search(r"/app/(\d+)", q)
    if m:
        return _validate(int(m.group(1)))
    m = re.search(r"/(?:run|subs)/(\d+)", q)
    if m:
        return _validate(int(m.group(1)))
    return None


def _validate(app_id: int) -> Optional[int]:
    """Return ``app_id`` if it's a plausible Steam App ID, else ``None``."""
    if app_id <= 0 or app_id > MAX_STEAM_APP_ID:
        return None
    return app_id


__all__ = ["resolve_app_id", "MAX_STEAM_APP_ID"]