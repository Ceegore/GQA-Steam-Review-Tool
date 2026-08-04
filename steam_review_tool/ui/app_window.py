"""Slim App window — lifecycle + tab wiring only.

The actual tab layouts live in ``ui/tab_api.py``, ``ui/tab_playwright.py``,
and ``ui/tab_trends.py``. Heavy business logic lives in the controllers
(``controllers/*``). Communication runs through ``core.event_bus.bus``.
"""
from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from typing import Callable, Optional, Any

import customtkinter as ctk

from ..core.event_bus import bus
from ..core.logger import configure_logging
from ..core.timezone import current_berlin_str
from ..controllers.action_handler import (
    copy_to_clipboard, find_latest_dump_md, open_in_editor, open_store_page,
)
from ..controllers.api_workflow import APIWorkflow
from ..controllers.dump_folder_controller import DumpFolderController
from ..controllers.filter_controller import build_filter_config
from ..controllers.playwright_workflow import PlaywrightWorkflow
from ..controllers.settings_controller import SettingsController
from ..controllers.trends_workflow import TrendsWorkflow
from ..services.dump_repository import DumpRepository
from ..services.steam_api_service import SteamAPI
from ..services.trends_store import TrendsStore
from .info_panel import InfoPanel
from .popup_help import HelpDialog
from .popup_welcome import WelcomeDialog
from .tab_api import ApiTabController
from .tab_playwright import PlaywrightTabController
from .tab_trends import TrendsTabController


class App(ctk.CTk):
    """Main window — composes services, controllers, and tab views."""

    def __init__(
        self,
        *,
        steam_api: Optional[SteamAPI] = None,
        dump_repository: Optional[DumpRepository] = None,
        trends_store: Optional[TrendsStore] = None,
        settings: Optional[dict[str, Any]] = None,
    ) -> None:
        configure_logging()
        super().__init__()

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        self.title("GQA Steam Review Tool")
        self.geometry("1180x880")
        self.minsize(1000, 780)

        # ---- DI: services -------------------------------------------
        self.api = steam_api or SteamAPI()
        dump_root_str = (settings or {}).get("dump_root") or ""
        self.dump_repo = dump_repository or DumpRepository(
            Path(dump_root_str) if dump_root_str else self._safe_default_root(),
        )
        self.trends_store = trends_store or TrendsStore()
        self.settings = settings or {}

        # ---- App-level state ----------------------------------------
        self.app_id: Optional[int] = None
        self.app_details: Optional[dict[str, Any]] = None
        self.reviews: list[dict[str, Any]] = []
        # NOTE: workers (api_wf, pw_wf) have their own stop events;
        # the App doesn't need a top-level one.

        # ---- Controllers (one per workflow) --------------------------
        self.dump_ctrl = DumpFolderController(
            dump_root=self.dump_repo.dump_root,
            obsidian_vault=self._obsidian_path(),
        )
        self.api_wf = APIWorkflow(
            self.api, self.dump_repo.dump_root, log_cb=self._log,
        )
        self.pw_wf = PlaywrightWorkflow(log_cb=self._pw_log)
        self.trends_wf = TrendsWorkflow(self.trends_store, log_cb=self._log)
        self.settings_ctrl = SettingsController(self)

        # ---- Tabs ----------------------------------------------------
        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(fill="both", expand=True, padx=8, pady=8)
        tab_api = self.tabview.add("Steam API (cached)")
        tab_pw = self.tabview.add("Playwright (real-time)")
        tab_trends = self.tabview.add("📈 Trends")

        # One InfoPanel per tab, kept in sync via the bus.
        self.info_panels: list[InfoPanel] = []
        for _name, frame in (
            ("api", tab_api), ("pw", tab_pw), ("trends", tab_trends),
        ):
            panel = InfoPanel(frame)
            panel.pack(side="right", fill="y", padx=(4, 8), pady=4)
            panel.update(self.app_id, self.app_details)
            self.info_panels.append(panel)

        # Each tab controller subscribes to the event bus it cares about.
        self.tab_api_ctrl = ApiTabController(
            tab_api, master=self,
            dump_ctrl=self.dump_ctrl,
            api_wf=self.api_wf,
            log_fn=self._log,
            open_settings_fn=self._on_open_settings,
        )
        self.tab_pw_ctrl = PlaywrightTabController(
            tab_pw, master=self,
            dump_ctrl=self.dump_ctrl,
            pw_wf=self.pw_wf,
            log_fn=self._pw_log,
            open_settings_fn=self._on_open_settings,
        )
        self.tab_trends_ctrl = TrendsTabController(
            tab_trends, master=self,
            trends_wf=self.trends_wf,
            trends_store=self.trends_store,
        )

        # Status bar
        self._status_var = tk.StringVar(value="Ready.")
        status = ctk.CTkLabel(
            self, textvariable=self._status_var, anchor="w",
            text_color="gray",
        )
        status.pack(fill="x", padx=8, pady=(0, 4))

        # Help / About
        self._help_dialog: Optional[HelpDialog] = None
        self._welcome_dialog: Optional[WelcomeDialog] = None
        try:
            menubar = tk.Menu(self)
            helpmenu = tk.Menu(menubar, tearoff=0)
            helpmenu.add_command(label="How to use…", command=self._on_show_help)
            helpmenu.add_command(
                label="Show welcome…", command=self._on_show_welcome,
            )
            menubar.add_cascade(label="Help", menu=helpmenu)
            self.configure(menu=menubar)
        except tk.TclError:
            # Some CTk versions on Linux/macOS don't support a top-level
            # menu via configure(); silently skip rather than crash.
            pass

        # Close handler — Tk must support WM_DELETE_WINDOW; if not, the
        # user simply has no X button, which we tolerate.
        try:
            self.protocol("WM_DELETE_WINDOW", self._on_close)
        except tk.TclError:
            pass

        # Kick off Playwright availability probe and clock
        self.pw_wf.refresh_dep_status()
        self.after(1000, self._tick_clock)

        # Show the welcome popup on first launch (or when re-opened
        # via Help → Show welcome…). 300 ms gives the main window
        # time to render and ``winfo_*`` queries to return real
        # coordinates, so we can centre the popup.
        self.after(300, self._show_welcome_if_first_launch)

        # Bus subscriptions: keep references so we can unsubscribe on
        # close. Previously these were bare lambdas — a memory leak
        # because the bus kept them alive after the App was destroyed.
        self._bus_subs: list[tuple[str, Callable[..., None]]] = [
            (self.api_wf.FETCH_COMPLETED,
             lambda **kw: self._on_reviews_loaded(**kw)),
            (self.api_wf.FETCH_PROGRESS,
             lambda **kw: self._on_progress(**kw)),
            ("app.loaded",
             lambda **kw: self._on_app_loaded(**kw)),
            ("settings.changed",
             lambda **kw: self._on_settings_changed(**kw)),
        ]
        for event, cb in self._bus_subs:
            bus.subscribe(event, cb)

    # ---- small helpers -----------------------------------------------

    @staticmethod
    def _safe_default_root() -> Path:
        from ..core.paths import default_dump_root
        return default_dump_root()

    @staticmethod
    def _resolve_dump_root(settings: Optional[dict[str, Any]]) -> Path:
        """Pick a valid dump root from settings or fall back to the default.

        Robust against: ``settings is None``, ``settings == {}``, missing
        key, empty string, or a path that doesn't exist.
        """
        from ..core.paths import default_dump_root
        if settings:
            raw = settings.get("dump_root")
            if isinstance(raw, str) and raw.strip():
                return Path(raw)
        return default_dump_root()

    def _obsidian_path(self) -> Optional[Path]:
        # ``or ""`` collapses a present-but-None vault value
        # (e.g. a hand-edited settings.json) into the missing-key
        # default so ``Path(None)`` doesn't raise below.
        v = self.settings.get("obsidian_vault") or ""
        return Path(v) if v else None

    # ---- logging -----------------------------------------------------

    def _log(self, msg: str) -> None:
        self.tab_api_ctrl.log(msg)

    def _pw_log(self, msg: str) -> None:
        self.tab_pw_ctrl.log(msg)

    # ---- bus events ---------------------------------------------------

    def _on_reviews_loaded(self, *, app_id: int, reviews: list[dict[str, Any]]) -> None:
        self.app_id = app_id
        self.reviews = reviews
        self.tab_api_ctrl.update_review_count(len(reviews))

    def _on_progress(self, *, page: int, fetched: int, total: int) -> None:
        self.tab_api_ctrl.update_progress(page, fetched, total)

    def _on_app_loaded(self, *, app_id: int, app_details: Optional[dict[str, Any]]) -> None:
        self.app_id = app_id
        self.app_details = app_details
        for panel in self.info_panels:
            panel.update(app_id, app_details)

    def _on_settings_changed(self, *, data: dict[str, Any]) -> None:
        # Re-bind dump root. ``Path(None)`` raises TypeError, so use
        # the ``or ""`` short-circuit to collapse a present-but-None
        # value (e.g. a hand-edited or migrated settings.json) into
        # the missing-key default.
        new_root_str = data.get("dump_root") or ""
        new_root = Path(new_root_str)
        if new_root_str:
            self.dump_repo = DumpRepository(new_root)
            self.dump_ctrl.set_dump_root(new_root)
            self.api_wf.dump_root = new_root
        vault = data.get("obsidian_vault") or ""
        self.dump_ctrl.obsidian_vault = Path(vault) if vault else None

    # ---- menu / close ------------------------------------------------

    def _on_show_help(self) -> None:
        if self._help_dialog is None:
            self._help_dialog = HelpDialog(self)
        self._help_dialog.open()

    def _show_welcome_if_first_launch(self) -> None:
        """Open the welcome popup if the user hasn't dismissed it.

        Persisted in ``settings.json`` under ``greeting_shown``.
        """
        if self.settings.get("greeting_shown"):
            return
        self._on_show_welcome()

    def _on_show_welcome(self) -> None:
        if self._welcome_dialog is None:
            self._welcome_dialog = WelcomeDialog(
                self,
                settings=self.settings,
                on_save_settings=self._persist_settings,
            )
        self._welcome_dialog.open()

    def _persist_settings(self, data: dict[str, Any]) -> None:
        """Best-effort save used by the welcome popup's
        ``Don't show again`` checkbox.
        """
        from ..services.settings_store import save as _save
        self.settings.update(data)
        try:
            _save(self.settings)
        except Exception:
            # Persisting is best-effort; don't crash the UI for it.
            pass

    def _on_open_settings(self) -> None:
        """Open the Settings popup. Tab controllers wire their
        AI-row "⚙ Settings" button to this.
        """
        self.settings_ctrl.open()

    def _on_close(self) -> None:
        # Unsubscribe from the bus so the closures (which keep `self`
        # alive via captured ``self``) don't outlive the window.
        for event, cb in getattr(self, "_bus_subs", []):
            bus.unsubscribe(event, cb)
        # Signal workers to stop first, then wait briefly for any
        # in-flight worker to flush its current page to disk.
        # Without this we could quit mid-write and leave a partial
        # cursor in resume.json. The Playwright tab has its own
        # worker that was previously NOT awaited on close — a real
        # partial-write risk for the playwright helper script
        # (subprocess temp file) and any in-flight export.
        self.api_wf.stop()
        self.pw_wf.stop()
        if hasattr(self.api_wf, "wait"):
            self.api_wf.wait(timeout=3.0)
        if hasattr(self.pw_wf, "wait"):
            self.pw_wf.wait(timeout=3.0)
        # Also wait for the API tab's watch-mode thread if it's
        # still running — the daemon=True flag would let the
        # process exit mid-iteration otherwise, potentially
        # leaving the watch loop to write a stale "0 / 0"
        # progress line after the main window is destroyed.
        watch = getattr(self.tab_api_ctrl, "_watch_thread", None)
        if watch is not None and watch.is_alive():
            watch.join(timeout=2.0)
        self.destroy()

    # ---- clock -------------------------------------------------------

    def _tick_clock(self) -> None:
        now_str = current_berlin_str()
        self.tab_api_ctrl.update_clock(now_str)
        self.tab_pw_ctrl.update_clock(now_str)
        self.after(1000, self._tick_clock)


__all__ = ["App"]