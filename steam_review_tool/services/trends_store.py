"""Per-app time-series store for the Trends tab.

Backed by a single JSON file under the config dir. Appends snapshots
each time the user "refreshes" a tracked app; queries return a
filtered series for a chosen metric + time range.

All writes are atomic; all R-M-W sequences are serialised by a lock
to prevent concurrent writes from corrupting the JSON.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Optional, Any

from ..core.atomic_write import atomic_write_json, load_json_with_recovery
from ..core.logger import get_logger
from ..core.paths import ensure_config_dir
from ..models.trends_snapshot import TrendsSnapshot

_log = get_logger(__name__)

TRENDS_FILE = ensure_config_dir() / "trends.json"

# All R-M-W goes through this lock so the on-disk file stays consistent
# even if multiple API workers record snapshots concurrently.
_write_lock = threading.Lock()


class TrendsStore:
    """Persistent time-series of popularity metrics per tracked app.

    Backed by a single JSON file under the config dir
    (see :data:`TRENDS_FILE`). The store is intentionally global —
    the trends ledger is not per-game, so a ``dump_root`` parameter
    (as the dump repository has) would be misleading. The constructor
    takes no arguments for that reason.
    """

    def __init__(self) -> None:
        self.path = TRENDS_FILE

    # ---- low-level ----------------------------------------------------

    def _load(self) -> dict[str, Any]:
        return load_json_with_recovery(
            self.path, default={"tracked": [], "snapshots": []},
            on_corrupt=lambda backup, exc: _log.warning(
                "trends.json was corrupt (%s); moved to %s — "
                "starting with empty trend history.", exc, backup,
            ),
        )

    def save(self, data: dict[str, Any]) -> None:
        with _write_lock:
            atomic_write_json(self.path, data)

    # ---- tracked apps --------------------------------------------------

    def tracked_apps(self) -> list[dict[str, Any]]:
        return list(self._load().get("tracked", []))

    def is_tracked(self, app_id: int) -> bool:
        return any(t.get("app_id") == app_id for t in self.tracked_apps())

    def add(self, app_id: int, name: str) -> None:
        with _write_lock:
            data = self._load()
            if any(t.get("app_id") == app_id
                   for t in data.get("tracked", [])):
                return
            data.setdefault("tracked", []).append(
                {"app_id": app_id, "name": name},
            )
            atomic_write_json(self.path, data)

    def remove(self, app_id: int) -> None:
        with _write_lock:
            data = self._load()
            data["tracked"] = [
                t for t in data.get("tracked", [])
                if t.get("app_id") != app_id
            ]
            atomic_write_json(self.path, data)

    # ---- snapshots ----------------------------------------------------

    def record(self, snapshot: TrendsSnapshot) -> None:
        with _write_lock:
            data = self._load()
            data.setdefault("snapshots", []).append({
                "app_id": snapshot.app_id,
                "ts": snapshot.ts,
                "wishlist": snapshot.wishlist,
                "followers": snapshot.followers,
                "reviews": snapshot.reviews,
                "positive_pct": snapshot.positive_pct,
            })
            atomic_write_json(self.path, data)

    def series(
        self, app_id: int, metric: str, days: Optional[int] = None
    ) -> list[TrendsSnapshot]:
        """Return snapshots for ``app_id``, filtered to ``metric`` and the
        last ``days`` (or all if ``days`` is None).
        """
        data = self._load()
        snaps = data.get("snapshots", [])
        out: list[TrendsSnapshot] = []
        for s in snaps:
            if s.get("app_id") != app_id:
                continue
            if metric not in s:
                continue
            out.append(TrendsSnapshot(
                app_id=app_id,
                ts=int(s.get("ts", 0)),
                wishlist=s.get("wishlist"),
                followers=s.get("followers"),
                reviews=s.get("reviews"),
                positive_pct=s.get("positive_pct"),
            ))
        if days:
            from time import time as _now
            cutoff = int(_now()) - days * 86400
            out = [s for s in out if s.ts >= cutoff]
        out.sort(key=lambda s: s.ts)
        return out


__all__ = ["TrendsStore"]