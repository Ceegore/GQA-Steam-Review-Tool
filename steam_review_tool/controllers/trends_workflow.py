"""Trends workflow — manage tracked apps, refresh snapshots, open chart."""
from __future__ import annotations

import threading
from typing import Callable, Optional, Any

from ..services.trends_store import TrendsStore
from ..models.trends_snapshot import TrendsSnapshot


class TrendsWorkflow:
    """Owns the Trends-tab state machine."""

    # The previous version of this class published two bus
    # events: ``TRACKED_CHANGED`` (3 publishes) and
    # ``SNAPSHOT_RECORDED`` (1 publish). A R20-2 audit
    # found zero subscribers for either event — the
    # ``TrendsWindow`` and ``tab_trends`` re-render via
    # direct method calls (the workflow calls back into
    # the tab through closures passed at construction
    # time) rather than through the bus. The bus
    # publishes were dead code. Removed in R20-2 to
    # eliminate the drift hazard.

    def __init__(
        self,
        store: TrendsStore,
        log_cb: Callable[[str], None],
    ) -> None:
        self.store = store
        self.log = log_cb
        self._refresh_worker: Optional[threading.Thread] = None
        self._refresh_lock = threading.Lock()

    # ---- tracked apps --------------------------------------------------

    def add(self, app_id: int, name: str) -> None:
        if self.store.is_tracked(app_id):
            return
        self.store.add(app_id, name)
        self.log(f"Added {name} ({app_id}) to trends.")

    def remove(self, app_id: int) -> None:
        self.store.remove(app_id)
        self.log(f"Removed {app_id} from trends.")

    def remove_all(self) -> None:
        for app in list(self.store.tracked_apps()):
            self.store.remove(app["app_id"])

    def list_tracked(self) -> list[dict[str, Any]]:
        return self.store.tracked_apps()

    # ---- snapshots -----------------------------------------------------

    def refresh_one(self, app_id: int, snapshot: TrendsSnapshot) -> None:
        self.store.record(snapshot)

    def refresh_all_async(
        self,
        fetch_metrics: Callable[[int], Optional[TrendsSnapshot]],
    ) -> bool:
        # Only one refresh pass at a time; if the user clicks again
        # we skip rather than spawning concurrent workers that race
        # on the trends.json file. Returns ``True`` if a new worker
        # was started, ``False`` if a previous one is still running.
        with self._refresh_lock:
            if (self._refresh_worker
                    and self._refresh_worker.is_alive()):
                self.log("A refresh is already running; ignored.")
                return False
            def worker():
                for app in self.list_tracked():
                    snap = fetch_metrics(app["app_id"])
                    if snap is not None:
                        self.refresh_one(app["app_id"], snap)

            self._refresh_worker = threading.Thread(
                target=worker, daemon=True,
            )
            self._refresh_worker.start()
            return True


__all__ = ["TrendsWorkflow"]