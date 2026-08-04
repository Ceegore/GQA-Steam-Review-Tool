"""Playwright workflow — manages dependency install, browser launch, and scrape.

Communicates with the UI through the event bus so the tab can render
logs / progress / dep status without polling. The actual scraping is
delegated to ``services/playwright_scraper.py`` (Phase-7 real
browser-driven scrape that bypasses Steam's JSON review cache).
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Callable, Optional

from ..core.event_bus import bus
from ..exporters.export_orchestrator import run as run_export
from ..models.export_context import ExportContext
from ..services import dependency_checker, dependency_installer, playwright_scraper


class PlaywrightWorkflow:
    """Owns the Playwright-tab state machine."""

    DEP_STATUS_CHANGED = "pw.dep.status.changed"
    SCRAPE_STARTED = "pw.scrape.started"
    SCRAPE_PROGRESS = "pw.scrape.progress"
    SCRAPE_COMPLETED = "pw.scrape.completed"
    SCRAPE_FAILED = "pw.scrape.failed"

    def __init__(self, log_cb: Callable[[str], None]) -> None:
        self.log = log_cb
        self._stop = threading.Event()
        # Two distinct worker slots: a scrape worker and an install
        # worker. They previously shared ``self._worker`` which meant
        # an in-flight scrape silently swallowed a click on "Install
        # Playwright" (and vice versa) — a confusing no-op UX bug
        # because the user would see the spinner but no progress.
        self._worker: Optional[threading.Thread] = None
        self._install_worker: Optional[threading.Thread] = None

    # ---- dep status ----------------------------------------------------

    def refresh_dep_status(self) -> None:
        """Probe playwright + chromium on a background thread."""
        def worker() -> None:
            pkg_ok = dependency_checker.is_playwright_available()
            chrome_ok = dependency_checker.is_chromium_installed()
            bus.publish(self.DEP_STATUS_CHANGED,
                        pkg=pkg_ok, chromium=chrome_ok)
        threading.Thread(target=worker, daemon=True).start()

    # ---- installers ----------------------------------------------------

    def install_playwright(self) -> None:
        # Separate ``_install_worker`` slot so an in-flight scrape
        # doesn't silently swallow the install click (and vice versa).
        if self._install_worker and self._install_worker.is_alive():
            return
        self._install_worker = threading.Thread(
            target=self._install_pw_worker, daemon=True,
        )
        self._install_worker.start()

    def install_chromium(self) -> None:
        if self._install_worker and self._install_worker.is_alive():
            return
        self._install_worker = threading.Thread(
            target=self._install_chrome_worker, daemon=True,
        )
        self._install_worker.start()

    def _install_pw_worker(self) -> None:
        self.log("Installing playwright package via pip (1-2 min)…")

        def on_done(ok: bool, msg: str) -> None:
            self.log(("✓ " if ok else "❌ ") + msg)
            bus.publish(self.DEP_STATUS_CHANGED, pkg=ok, chromium=None)

        dependency_installer.install_playwright(self.log, on_done)

    def _install_chrome_worker(self) -> None:
        self.log("Downloading Chromium (~150 MB, 1-3 min)…")

        def on_done(ok: bool, msg: str) -> None:
            self.log(("✓ " if ok else "❌ ") + msg)
            bus.publish(self.DEP_STATUS_CHANGED, pkg=None, chromium=ok)

        dependency_installer.install_chromium(self.log, on_done)

    # ---- cache ---------------------------------------------------------

    def open_cache(self) -> Optional[str]:
        return dependency_installer.open_pw_cache()

    # ---- scrape (Phase 7) ----------------------------------------------

    def scrape(
        self,
        app_id: int,
        *,
        language: str = "all",
        sort: str = "recent",
        max_reviews: int = 100,
        resume: bool = False,
    ) -> bool:
        """Launch a headless Chromium and scrape reviews. Returns
        ``True`` if a new worker was started, ``False`` if a previous
        one is still running.

        The boolean return lets the tab controller avoid subscribing
        an auto-export callback for a click that was a no-op (a
        duplicate "Fetch new" click mid-scrape would otherwise
        double the auto-export when the first scrape completes).
        """
        if self._worker and self._worker.is_alive():
            self.log("A scrape is already running; ignored.")
            return False
        self._stop.clear()
        bus.publish(self.SCRAPE_STARTED, app_id=app_id)
        self._worker = threading.Thread(
            target=self._scrape_worker,
            kwargs=dict(
                app_id=app_id, language=language, sort=sort,
                max_reviews=max_reviews, resume=resume,
            ),
            daemon=True,
        )
        self._worker.start()
        return True

    def _scrape_worker(
        self, *, app_id: int, language: str, sort: str,
        max_reviews: int, resume: bool,
    ) -> None:
        def progress_cb(page: int, fetched: int, total: int) -> None:
            bus.publish(self.SCRAPE_PROGRESS,
                        page=page, fetched=fetched, total=total)

        try:
            reviews = playwright_scraper.scrape_reviews(
                app_id,
                language=language,
                sort=sort,
                max_reviews=max_reviews,
                log_cb=self.log,
                stop_flag=self._stop.is_set,
                progress_cb=progress_cb,
                resume=resume,
            )
            bus.publish(self.SCRAPE_COMPLETED,
                        app_id=app_id, reviews=reviews)
        except Exception as exc:
            self.log(f"Scrape failed: {exc}")
            bus.publish(self.SCRAPE_FAILED,
                        app_id=app_id, error=str(exc))

    # ---- export (uses the shared Markdown pipeline) --------------------

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
        return run_export(
            ctx, dest,
            also_csv=also_csv, also_json=also_json,
            per_language=per_language, obsidian_vault=obsidian_vault,
            log_cb=self.log,
        )

    # ---- control --------------------------------------------------------

    def stop(self) -> None:
        self._stop.set()

    def wait(self, timeout: float = 5.0) -> bool:
        # Wait for BOTH the scrape worker and the install worker so a
        # pending install subprocess doesn't outlive the main window.
        # The shared ``_stop`` event is set by ``stop()`` and is
        # honoured by the scrape worker; the install worker doesn't
        # read it (the pip subprocess is its own thing), so we just
        # give it the timeout window to finish naturally.
        scrape = self._worker
        install = self._install_worker
        if scrape is None and install is None:
            return True
        if scrape is not None:
            scrape.join(timeout=timeout)
        if install is not None:
            install.join(timeout=timeout)
        still_alive = (
            (scrape is not None and scrape.is_alive())
            or (install is not None and install.is_alive())
        )
        return not still_alive


__all__ = ["PlaywrightWorkflow"]
