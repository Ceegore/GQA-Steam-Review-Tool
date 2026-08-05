"""Steam-API fetch + export workflow.

Runs the heavy work (HTTP fetch, dedup, export) in worker threads so the
GUI stays responsive. Publishes events on the bus so the UI can react
without being directly coupled to this controller.
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable, Optional, Any

from ..core.event_bus import bus
from ..core.logger import get_logger
from ..exporters.export_orchestrator import run as run_export
from ..models.export_context import ExportContext
from ..services.resume_store import get as resume_get
from ..services.resume_store import set_ as resume_set
from ..services.steam_api_service import SteamAPI
from ..utils.coercion import safe_int

_log = get_logger(__name__)


class APIWorkflow:
    """Coordinates Steam-API fetches + the resulting Markdown export."""

    FETCH_STARTED = "api.fetch.started"
    FETCH_PROGRESS = "api.fetch.progress"
    FETCH_COMPLETED = "api.fetch.completed"
    FETCH_FAILED = "api.fetch.failed"

    def __init__(
        self,
        api: SteamAPI,
        dump_root: Path,
        log_cb: Callable[[str], None],
    ) -> None:
        self.api = api
        # ``dump_root`` is accepted for DI / back-compat with the
        # factory wiring in ``app_factory.build_app`` but the
        # workflow itself never reads it — the actual file
        # writes (seen_ids ledger, .md export) happen through
        # ``DumpFolderController.dump_root`` / ``dump_repo``,
        # not through this attribute. Keeping the parameter
        # avoids breaking the constructor signature for any
        # external caller.
        self.log = log_cb
        self._stop = threading.Event()
        self._worker: Optional[threading.Thread] = None
        # Per-start ``threading.Event`` — each fetch gets its own so a
        # late ``stop()`` from a previous fetch can't poison the next
        # one. The shared ``self._stop`` would also have this problem
        # when the user clicks Stop → Fetch quickly.
        self._worker_lock = threading.Lock()

    # ---- fetch ---------------------------------------------------------

    def start_fetch(
        self,
        app_id: int,
        *,
        language: str = "all",
        review_filter: str = "all",
        review_type: str = "all",
        day_range: Optional[int] = None,
        min_date_ts: Optional[int] = None,
        min_helpful: int = 0,
        num_per_page: int = 100,
        resume: bool = False,
    ) -> bool:
        """Start a fetch worker. Returns ``True`` if a new worker was
        started, ``False`` if a previous one is still running.

        The boolean return lets the tab controller avoid subscribing
        an auto-export callback for a click that was a no-op
        (a duplicate "Fetch new" click mid-fetch would otherwise
        double the auto-export when the first fetch completes).
        """
        with self._worker_lock:
            if self._worker and self._worker.is_alive():
                self.log("Fetch already running; ignored.")
                return False
            # Reset the *shared* stop event for this new run.
            self._stop.clear()
            start_cursor = "*"
            if resume:
                saved = resume_get("api", app_id) or {}
                start_cursor = saved.get("cursor", "*")
                self.log(f"Resuming from cursor={start_cursor!r}")
            bus.publish(self.FETCH_STARTED, app_id=app_id)
            self._worker = threading.Thread(
                target=self._fetch_worker,
                kwargs=dict(
                    app_id=app_id, language=language,
                    review_filter=review_filter, review_type=review_type,
                    day_range=day_range, min_date_ts=min_date_ts,
                    min_helpful=min_helpful, num_per_page=num_per_page,
                    start_cursor=start_cursor,
                ),
                daemon=True,
            )
            self._worker.start()
            return True

    def stop(self) -> None:
        """Signal the current fetch worker to stop.

        Cooperative: the worker checks ``self._stop`` between
        pages and exits cleanly. Does NOT block — call
        :meth:`wait` separately to wait for the worker to
        finish (e.g. on app shutdown so we don't kill the
        worker mid-write).
        """
        self._stop.set()

    def wait(self, timeout: float = 5.0) -> bool:
        """Block until the current worker exits (or ``timeout`` s).

        Returns ``True`` if the worker finished, ``False`` on timeout.
        Useful for graceful shutdown so we don't kill the worker
        mid-write.
        """
        worker = self._worker
        if worker is None:
            return True
        worker.join(timeout=timeout)
        return not worker.is_alive()

    def _fetch_worker(
        self,
        *,
        app_id: int,
        language: str,
        review_filter: str,
        review_type: str,
        day_range: Optional[int],
        min_date_ts: Optional[int],
        min_helpful: int,
        num_per_page: int,
        start_cursor: str,
    ) -> None:
        def progress_cb(page: int, fetched: int, total: int) -> None:
            bus.publish(self.FETCH_PROGRESS, page=page, fetched=fetched, total=total)

        def cursor_cb(cursor: str) -> None:
            resume_set("api", app_id, cursor=cursor)

        try:
            reviews = self.api.fetch_all_reviews(
                app_id,
                language=language,
                review_filter=review_filter,
                review_type=review_type,
                day_range=day_range,
                min_date_ts=min_date_ts,
                num_per_page=num_per_page,
                progress_cb=progress_cb,
                log_cb=self.log,
                stop_flag=self._stop.is_set,
                start_cursor=start_cursor,
                cursor_cb=cursor_cb,
            )
            if min_helpful > 0:
                before = len(reviews)
                reviews = [r for r in reviews if safe_int(r, "votes_up", 0) >= min_helpful]
                self.log(f"min_helpful filter: kept {len(reviews)}/{before}")
            bus.publish(self.FETCH_COMPLETED, app_id=app_id, reviews=reviews)
        except Exception as exc:
            self.log(f"Fetch failed: {exc}")
            bus.publish(self.FETCH_FAILED, app_id=app_id, error=str(exc))

    # ---- export --------------------------------------------------------

    def export(
        self,
        ctx: ExportContext,
        dest: Path,
        *,
        also_csv: bool = False,
        also_json: bool = False,
        per_language: bool = False,
        obsidian_vault: Optional[Path] = None,
    ) -> dict[str, Any]:
        """Render the current reviews to ``dest`` (markdown + optional
        CSV / JSON / per-language splits + optional Obsidian copy).

        Delegates to :func:`exporters.export_orchestrator.run_export`
        which is the shared export pipeline (also used by the
        Playwright tab). The ``obsidian_vault`` parameter triggers
        the post-export copy into the user's Obsidian vault (if set
        in settings).

        Returns the export summary dict from ``run_export`` (file
        paths + counts). Errors are caught and reported via the log
        callback; partial outputs are preserved.
        """
        return run_export(
            ctx, dest,
            also_csv=also_csv, also_json=also_json,
            per_language=per_language, obsidian_vault=obsidian_vault,
            log_cb=self.log,
        )


__all__ = ["APIWorkflow"]