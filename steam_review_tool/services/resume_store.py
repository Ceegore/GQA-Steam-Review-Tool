"""Resume-cursor persistence for fetch workflows.

Both the API and Playwright tabs can save and resume a fetch. We
store cursors keyed by ``(source, app_id)``.

All write paths go through ``atomic_write_json`` so a crash mid-write
cannot corrupt the file (which would wipe all resume state).
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Optional

from ..core.atomic_write import atomic_write_json, load_json_with_recovery
from ..core.logger import get_logger
from ..core.paths import ensure_config_dir

_log = get_logger(__name__)

CONFIG_FILE = ensure_config_dir() / "resume.json"

# Serialise R-M-W access from multiple workers. Only one writer at a
# time; readers can proceed in parallel but may see slightly stale
# state, which is acceptable for resume cursors.
_write_lock = threading.Lock()


def load_all() -> dict[str, Any]:
    """Load the full resume blob. Returns ``{}`` on I/O or parse errors."""
    return load_json_with_recovery(
        CONFIG_FILE, default={},
        on_corrupt=lambda backup, exc: _log.warning(
            "resume.json was corrupt (%s); moved to %s — "
            "resume cursors have been lost.", exc, backup,
        ),
    )


def save_all(data: dict[str, Any]) -> None:
    """Persist the entire resume blob atomically."""
    with _write_lock:
        atomic_write_json(CONFIG_FILE, data)


def get(source: str, app_id: int) -> Optional[dict[str, Any]]:
    """Return the resume-cursor entry for ``(source, app_id)`` or ``None``."""
    # ``or {}`` collapses a present-but-None ``source`` (e.g. from
    # a hand-edited resume.json) into an empty dict so the chained
    # ``.get(str(app_id))`` doesn't crash on ``None.get``.
    return (load_all().get(source) or {}).get(str(app_id))


def set_(source: str, app_id: int, **fields: Any) -> None:
    """Merge ``fields`` into the entry for ``(source, app_id)`` and persist."""
    with _write_lock:
        data = load_all()
        src = data.setdefault(source, {})
        entry = src.setdefault(str(app_id), {})
        entry.update(fields)
        atomic_write_json(CONFIG_FILE, data)


def clear(source: str, app_id: int) -> None:
    """Remove the entry for ``(source, app_id)`` if it exists."""
    with _write_lock:
        data = load_all()
        if source in data and str(app_id) in data[source]:
            del data[source][str(app_id)]
            atomic_write_json(CONFIG_FILE, data)


__all__ = ["load_all", "save_all", "get", "set_", "clear"]