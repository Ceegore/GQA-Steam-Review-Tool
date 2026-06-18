"""User-preferences JSON store.

Persists the user's choices (dump root, Obsidian vault, Apify token,
keyword list[Any], AI prompt, last-fetch filters) under the config dir.

Writes are atomic; reads recover from a corrupt JSON by moving the
broken file aside and returning DEFAULTS (instead of silently
overwriting user settings).
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from ..core.atomic_write import atomic_write_json, load_json_with_recovery
from ..core.logger import get_logger
from ..core.paths import ensure_config_dir

_log = get_logger(__name__)

SETTINGS_FILE = ensure_config_dir() / "settings.json"

DEFAULTS: dict[str, Any] = {
    "dump_root": str(Path.home() / "Documents" / "SteamReviewDumps"),
    "obsidian_vault": "",
    "apify_token": "",
    "keyword_list": [],
    "ai_prompt_template": "",
    "open_after_export": True,
    "also_csv": False,
    "also_json": False,
    "per_language": False,
    # First-launch greeting is shown once; ticking "Don't show
    # again" in the welcome popup flips this to ``True``.
    "greeting_shown": False,
}

# Serialise save + reload cycles. Without this, two rapid save calls
# can race and lose a field. With it, both writers see the same
# baseline data.
_write_lock = threading.Lock()


def load() -> dict[str, Any]:
    """Load the user's settings, merged with DEFAULTS for missing keys."""
    data = load_json_with_recovery(
        SETTINGS_FILE, default=dict(DEFAULTS),
        on_corrupt=lambda backup, exc: _log.warning(
            "settings.json was corrupt (%s); moved to %s — "
            "loading built-in defaults.", exc, backup,
        ),
    )
    merged = dict(DEFAULTS)
    merged.update(data or {})
    return merged


def save(data: dict[str, Any]) -> None:
    """Persist the user's settings atomically."""
    with _write_lock:
        atomic_write_json(SETTINGS_FILE, data)


def reset_defaults() -> dict[str, Any]:
    """Delete the on-disk settings file (if any) and return DEFAULTS."""
    try:
        SETTINGS_FILE.unlink()
    except FileNotFoundError:
        pass
    except OSError as exc:
        _log.warning("could not remove settings.json: %s", exc)
    return dict(DEFAULTS)


__all__ = ["DEFAULTS", "load", "save", "reset_defaults"]