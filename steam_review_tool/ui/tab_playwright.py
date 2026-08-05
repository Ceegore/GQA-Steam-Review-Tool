"""Playwright tab — widget layout + handler wiring.

Mirrors the layout of the Steam API tab (scrollable body, hint,
filter grid, action bar, log) so the two tabs feel like siblings.
Cross-cutting handlers live in ``ui/_tab_actions.py``; the action-bar
widget grid lives in ``ui/_pw_action_bar.py``.

Heavy lifting lives in ``controllers/playwright_workflow.py`` and
``services/playwright_scraper.py`` (the real Phase-7 JS-driven
scraper that bypasses Steam's JSON cache).
"""
from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from typing import Any, Callable, Optional

import customtkinter as ctk

from ..controllers.dump_folder_controller import DumpFolderController
from ..controllers.filter_controller import (
    apply_window_filter, build_filter_config,
)
from ..core.event_bus import bus
from ..models.export_context import ExportContext
from ..services.dump_repository import DumpRepository
from ..ui._pw_action_bar import PwActionRefs, build_pw_action_bar
from ..ui._pw_sections import (
    PwFilterRefs, build_pw_dependencies_section,
    build_pw_filters_section, build_pw_game_section,
)
from ..ui._action_state import ActionStateMixin
from ..ui._since_section import build_since_section
from ..ui._tab_actions import TabActions
from ..ui._tab_hint import PLAYWRIGHT_HINT, build_tab_hint
from ..utils.text_utils import make_export_basename, short_filter_label
from ..utils.url_utils import resolve_app_id


class PlaywrightTabController(ActionStateMixin):
    """Owns the "Playwright (real-time)" tab widgets + handlers."""

    def __init__(
        self,
        parent: ctk.CTkBaseClass,
        *,
        master: Any,
        dump_ctrl: DumpFolderController,
        pw_wf: Any,
        log_fn: Callable[[str], None],
        open_settings_fn: Callable[[], None],
    ) -> None:
        self.parent = parent
        self.master = master
        self.dump_ctrl = dump_ctrl
        self.pw_wf = pw_wf
        self._log = log_fn
        self._actions = TabActions(
            master=master, dump_ctrl=dump_ctrl, log_fn=log_fn,
            open_settings_fn=open_settings_fn,
            fetch_item=self._fetch_item,
        )

        # ---- Widget state --------------------------------------------
        self._app_id_entry: Optional[ctk.CTkEntry] = None
        self._game_label: Optional[ctk.CTkLabel] = None
        self._pkg_status: Optional[ctk.CTkLabel] = None
        self._chrome_status: Optional[ctk.CTkLabel] = None
        self._log_box: Optional[ctk.CTkTextbox] = None
        self._clock_lbl: Optional[ctk.CTkLabel] = None
        self._dump_label: Optional[ctk.CTkLabel] = None
        self._seen_label: Optional[ctk.CTkLabel] = None
        self._progress: Optional[ctk.CTkProgressBar] = None
        self._progress_lbl: Optional[ctk.CTkLabel] = None
        self._review_count_lbl: Optional[ctk.CTkLabel] = None
        self._action_refs = PwActionRefs()
        self.filter_refs: Optional[PwFilterRefs] = None
        self.also_export_csv_var = ctk.StringVar(value="0")
        self.also_export_json_var = ctk.StringVar(value="0")
        self.per_language_var = ctk.StringVar(value="0")
        self.pw_split_var = ctk.StringVar(value="0")

        self._since: dict[str, Any] = {}
        self._scrape_running = False
        # Wire button-state management to the workflow's bus events
        # (shared mixin; same logic as the API tab).
        self.install_action_state_bus(
            started_event=self.pw_wf.SCRAPE_STARTED,
            completed_event=self.pw_wf.SCRAPE_COMPLETED,
            failed_event=self.pw_wf.SCRAPE_FAILED,
            source="pw",
        )
        self._build()
        bus.subscribe(self.pw_wf.DEP_STATUS_CHANGED, self._on_dep_status)

    # ---- build -------------------------------------------------------

    def _build(self) -> None:
        # Scrollable container — every control is reachable on small
        # windows.
        self.body = ctk.CTkScrollableFrame(self.parent, fg_color="transparent")
        self.body.pack(fill="both", expand=True, padx=4, pady=4)

        # 1. Tab-purpose hint (collapsed by default)
        build_tab_hint(self.body, hint_text=PLAYWRIGHT_HINT, expanded=False)

        # 2. Game section
        game = build_pw_game_section(
            self.body,
            on_load=self._on_load,
            on_pick_dump_root=self._on_pick_dump_root,
            on_open_dump_folder=self._actions.open_dump_folder,
            initial_dump_label=f"📂 {self.dump_ctrl.dump_root}",
        )
        self._app_id_entry = game["app_id_entry"]
        self._game_label = game["game_label"]
        self._dump_label = game["dump_label"]
        self._seen_label = game["seen_label"]

        # 3. Dependencies (Playwright pkg / Chromium)
        deps = build_pw_dependencies_section(
            self.body,
            on_install_pkg=self._on_install_pkg,
            on_install_chrome=self._on_install_chrome,
            on_open_cache=self._on_open_cache,
        )
        self._pkg_status = deps["pkg_status"]
        self._chrome_status = deps["chrome_status"]

        # 4. Filter section (responsive + reset button)
        self.filter_refs, _reset_btn = build_pw_filters_section(
            self.body, on_reset=self._reset_filters,
        )

        # 5. When to include (German time)
        self._since = build_since_section(
            self.body, prefix="pw_", log_fn=self._log,
        )

        # 6. Action bar
        self._action_refs = build_pw_action_bar(
            self.body,
            actions=self._actions,
            on_scrape=self._on_scrape,
            on_stop=self._on_stop,
            on_open_cache=self._on_open_cache,
            on_resume=self._on_resume,
            on_fetch_new=self._on_fetch_new,
            on_export=self._on_export,
            csv_var=self.also_export_csv_var,
            json_var=self.also_export_json_var,
            per_lang_var=self.per_language_var,
            split_var=self.pw_split_var,
        )

        # 7. Progress + clock + Log
        self._build_progress_and_log()
        self._bind_shortcuts()

    def _build_progress_and_log(self) -> None:
        prog = ctk.CTkFrame(self.body, fg_color="transparent")
        prog.pack(fill="x", padx=8, pady=(4, 2))
        self._progress = ctk.CTkProgressBar(prog)
        self._progress.pack(side="left", fill="x", expand=True, padx=4)
        self._progress.set(0)
        self._progress_lbl = ctk.CTkLabel(prog, text="Idle.")
        self._progress_lbl.pack(side="left", padx=4)
        self._review_count_lbl = ctk.CTkLabel(prog, text="0 reviews")
        self._review_count_lbl.pack(side="left", padx=4)

        self._clock_lbl = ctk.CTkLabel(
            self.body, text="", text_color="gray",
        )
        self._clock_lbl.pack(anchor="w", padx=12, pady=(0, 2))

        log_hdr = ctk.CTkFrame(self.body, fg_color="transparent")
        log_hdr.pack(fill="x", padx=12, pady=(4, 0))
        ctk.CTkLabel(
            log_hdr, text="Log", font=("", 12, "bold"),
        ).pack(side="left")
        ctk.CTkButton(
            log_hdr, text="Clear", width=70, height=24,
            command=self._clear_log,
        ).pack(side="right")
        self._log_box = ctk.CTkTextbox(self.body, height=160)
        self._log_box.pack(fill="x", padx=8, pady=(0, 8))
        self._log_box.configure(state="disabled")

    def _bind_shortcuts(self) -> None:
        self.master.bind_all("<Control-p>", lambda _e: self._on_scrape())
        self.master.bind_all("<Control-Shift-p>", lambda _e: self._on_fetch_new())
        self.master.bind_all("<Control-r>", lambda _e: self._on_resume())

    # ---- log / progress / clock -------------------------------------

    def log(self, msg: str) -> None:
        if self._log_box is None:
            return
        try:
            self._log_box.configure(state="normal")
            self._log_box.insert("end", msg + "\n")
            self._log_box.see("end")
            self._log_box.configure(state="disabled")
        except Exception as exc:
            if "invalid command name" not in str(exc):
                raise

    def _clear_log(self) -> None:
        if self._log_box is None:
            return
        try:
            self._log_box.configure(state="normal")
            self._log_box.delete("1.0", "end")
            self._log_box.configure(state="disabled")
        except tk.TclError:
            pass

    def update_clock(self, now_str: str) -> None:
        if self._clock_lbl is not None:
            self._clock_lbl.configure(text=f"🕒 Now: {now_str} (Berlin)")
        if self._since:
            self._since["refresh"]()

    def update_progress(self, page: int, fetched: int, total: int) -> None:
        if self._progress is not None and total:
            try:
                self._progress.set(min(fetched / total, 1.0))
            except tk.TclError:
                pass
        if self._progress_lbl is not None:
            self._progress_lbl.configure(text=f"Page {page} · {fetched}/{total}")

    def update_review_count(self, n: int) -> None:
        if self._review_count_lbl is not None:
            self._review_count_lbl.configure(text=f"{n} reviews")

    def refresh_seen_count(self, n: int) -> None:
        if self._seen_label is not None:
            self._seen_label.configure(text=f"Already exported: {n} reviews")

    def _refresh_dump_label(self) -> None:
        try:
            if self._dump_label is not None:
                self._dump_label.configure(
                    text=f"📂 {self.dump_ctrl.dump_root}",
                )
        except tk.TclError:
            pass

    # ---- bus events --------------------------------------------------

    def _on_dep_status(self, *, pkg: Optional[bool] = None,
                       chromium: Optional[bool] = None) -> None:
        target = self.parent

        def apply() -> None:
            if pkg is not None and self._pkg_status is not None:
                self._pkg_status.configure(
                    text="✓ installed" if pkg else "❌ missing",
                    text_color="#2ecc71" if pkg else "#e74c3c",
                )
            if chromium is not None and self._chrome_status is not None:
                self._chrome_status.configure(
                    text="✓ installed" if chromium else "❌ missing",
                    text_color="#2ecc71" if chromium else "#e74c3c",
                )

        try:
            target.after(0, apply)
        except tk.TclError:
            pass

    # ---- handlers ----------------------------------------------------

    def _on_load(self) -> None:
        raw = self._app_id_entry.get() if self._app_id_entry else ""
        app_id = resolve_app_id(raw)
        if app_id is None:
            self._log("Invalid App ID / URL.")
            return
        self.master.app_id = app_id
        self._log(f"Loaded app {app_id}.")
        if self._game_label is not None:
            self._game_label.configure(text=f"App {app_id}")

    def _on_install_pkg(self) -> None:
        self.pw_wf.install_playwright()

    def _on_install_chrome(self) -> None:
        self.pw_wf.install_chromium()

    def _on_scrape(self) -> None:
        if self.master.app_id is None:
            self._log("Load a game first.")
            return
        self._log(
            f"Playwright scrape requested for app {self.master.app_id}…",
        )
        self.pw_wf.scrape(
            self.master.app_id,
            language=(self.filter_refs.lang_var.get()
                      if self.filter_refs else "all"),
            sort=(self.filter_refs.sort_var.get()
                  if self.filter_refs else "recent"),
            max_reviews=(int(self.filter_refs.max_var.get())
                         if self.filter_refs else 100),
        )

    def _on_stop(self) -> None:
        self.pw_wf.stop()
        self._log("Stop requested.")

    def _on_resume(self) -> None:
        if self.master.app_id is None:
            return
        self.pw_wf.scrape(self.master.app_id, resume=True)

    def _on_fetch_new(self) -> None:
        if self.master.app_id is None:
            self._log("Load a game first.")
            return
        # Only subscribe the auto-export callback if the workflow
        # actually started a new scrape. The old code subscribed
        # unconditionally, so a second "Fetch new" click mid-scrape
        # would double-subscribe — when the first scrape completed,
        # both auto-export callbacks fired and the user got TWO
        # exports.
        if not self.pw_wf.scrape(
            self.master.app_id,
            language=(self.filter_refs.lang_var.get()
                      if self.filter_refs else "all"),
            sort=(self.filter_refs.sort_var.get()
                  if self.filter_refs else "recent"),
            max_reviews=(int(self.filter_refs.max_var.get())
                         if self.filter_refs else 100),
        ):
            return
        bus.subscribe_once(
            "pw.scrape.completed",
            self._auto_export_after_scrape,
        )

    def _fetch_item(self, app_id: int) -> None:
        """Per-item fetch callback for the batch-dump dialog.

        Re-uses the same scrape + auto-export wiring as
        ``_on_fetch_new`` so the batch dialog iterates over
        queued app IDs and each one triggers a real scrape +
        auto-export. Previously the batch dialog published
        ``batch.run_item`` to the bus but no one subscribed —
        the batch feature was completely non-functional.
        """
        if not self.pw_wf.scrape(
            app_id,
            language=(self.filter_refs.lang_var.get()
                      if self.filter_refs else "all"),
            sort=(self.filter_refs.sort_var.get()
                  if self.filter_refs else "recent"),
            max_reviews=(int(self.filter_refs.max_var.get())
                         if self.filter_refs else 100),
        ):
            return
        bus.subscribe_once(
            "pw.scrape.completed",
            self._auto_export_after_scrape,
        )

    def _auto_export_after_scrape(self, **kw: Any) -> None:
        reviews = kw.get("reviews") or []
        if not reviews:
            self._log("Fetch-new: no reviews scraped.")
            return
        repo = DumpRepository(self.dump_ctrl.dump_root)
        seen = set(repo.load_seen_ids(self.master.app_id))
        new = [r for r in reviews
               if r.get("recommendationid") not in seen]
        if not new:
            self._log("Fetch-new: all reviews already exported.")
            return
        kept = self._first_24h_keep(new)
        base = make_export_basename(
            (self.master.app_details or {}).get("name", "app"),
            short_filter_label("pw", self) + "_new",
        )
        dest = self.dump_ctrl.dump_root / base
        ctx = ExportContext(
            app_id=self.master.app_id,
            app_details=self.master.app_details,
            reviews=kept,
            language_param=(self.filter_refs.lang_var.get()
                            if self.filter_refs else "all"),
            review_filter="all",
            review_type="all",
            day_range=None, min_date_ts=None,
        )
        result = self.pw_wf.export(
            ctx, dest,
            also_csv=self.also_export_csv_var.get() == "1",
            also_json=self.also_export_json_var.get() == "1",
            per_language=self.per_language_var.get() == "1",
            obsidian_vault=self.dump_ctrl.obsidian_vault,
        )
        new_ids = seen | {
            rid for r in kept if (rid := r.get("recommendationid"))
        }
        repo.save_seen_ids(self.master.app_id, sorted(new_ids))
        self.refresh_seen_count(len(new_ids))
        self._log(f"Fetch-new: exported {len(kept)} reviews → {dest.name}")
        if result.get("obsidian"):
            self._log(f"  ✓ Synced to Obsidian: {result['obsidian']}")

    def _on_export(self) -> None:
        if not self.master.reviews:
            self._log("Nothing to export.")
            return
        from tkinter import filedialog
        default_name = make_export_basename(
            (self.master.app_details or {}).get("name", "app"),
            short_filter_label("pw", self),
        )
        dest = filedialog.asksaveasfilename(
            defaultextension=".md", initialfile=default_name,
            filetypes=[("Markdown", "*.md"), ("All", "*.*")],
        )
        if not dest:
            return
        kept = self._first_24h_keep(self.master.reviews)
        ctx = ExportContext(
            app_id=self.master.app_id or 0,
            app_details=self.master.app_details,
            reviews=kept,
            language_param=(self.filter_refs.lang_var.get()
                            if self.filter_refs else "all"),
            review_filter="all",
            review_type="all",
            day_range=None, min_date_ts=None,
        )
        result = self.pw_wf.export(
            ctx, Path(dest),
            also_csv=self.also_export_csv_var.get() == "1",
            also_json=self.also_export_json_var.get() == "1",
            per_language=self.per_language_var.get() == "1",
            obsidian_vault=self.dump_ctrl.obsidian_vault,
        )
        self._log(f"Exported → {result.get('md')}")
        if result.get("obsidian"):
            self._log(f"  ✓ Synced to Obsidian: {result['obsidian']}")

    def _on_open_cache(self) -> None:
        err = self.pw_wf.open_cache()
        if err:
            self._log(err)

    def _on_pick_dump_root(self) -> None:
        new_root = self._actions.pick_dump_root()
        if new_root is None:
            return
        self._refresh_dump_label()
        cls = type(self.master.dump_repo)
        self.master.dump_repo = cls(new_root)

    def _first_24h_keep(self, reviews: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if self.filter_refs is None:
            return reviews
        return apply_window_filter(reviews, "all")  # PW tab has no window filter

    def _reset_filters(self) -> None:
        """Reset every Playwright-tab filter to its default."""
        if self.filter_refs is None:
            return
        f = self.filter_refs
        f.sort_var.set("recent")
        f.max_var.set("100")
        f.lang_var.set("all")
        f.purchase_var.set("all")
        f.offtopic_var.set("false")
        try:
            f.playtime_min_entry.delete(0, "end")
        except tk.TclError:
            pass
        if self._since:
            try:
                self._since["preset_var"].set("all time")
                self._since["date_entry"].delete(0, "end")
                self._since["time_entry"].delete(0, "end")
                self._since["refresh"]()
            except tk.TclError:
                pass
        self._log("Filters reset to defaults.")


__all__ = ["PlaywrightTabController"]
