"""Steam-API tab — controller.

Owns widget state + handlers (load, fetch, stop, resume, fetch-new,
export, watch-toggle, reset-filters) and the log/progress/clock for
the "Steam API (cached)" tab. Content is hosted inside a
:class:`CTkScrollableFrame` (``self.body``) so every control stays
reachable on small screens. See ``_api_sections.py`` for the
responsive filter grid, ``_api_action_bar.py`` for the action bar,
``_tab_hint.py`` for the "When to use this tab" hint card, and
``_since_section.py`` for the German-time section.
"""
from __future__ import annotations

import threading
from pathlib import Path
from tkinter import filedialog
from typing import Any, Callable, Optional

import customtkinter as ctk

from ..controllers.api_workflow import APIWorkflow
from ..controllers.dump_folder_controller import DumpFolderController
from ..controllers.filter_controller import (
    apply_window_filter, build_filter_config,
)
from ..core.event_bus import bus
from ..models.export_context import ExportContext
from ..services.dump_repository import DumpRepository
from ..ui._api_action_bar import ApiActionRefs, build_api_action_bar
from ..ui._api_sections import (
    ApiFilterRefs, ApiGameRefs, build_api_filters_section,
    build_api_game_section,
)
from ..ui._action_state import ActionStateMixin
from ..ui._since_section import build_since_section
from ..ui._tab_actions import TabActions
from ..ui._tab_hint import API_HINT, build_tab_hint
from ..utils.text_utils import make_export_basename, short_filter_label
from ..utils.url_utils import resolve_app_id


class ApiTabController(ActionStateMixin):
    """Owns the "Steam API (cached)" tab widgets + handlers."""

    def __init__(
        self,
        parent: ctk.CTkBaseClass,
        *,
        master: Any,
        dump_ctrl: DumpFolderController,
        api_wf: APIWorkflow,
        log_fn: Callable[[str], None],
        open_settings_fn: Callable[[], None],
    ) -> None:
        self.parent = parent
        self.master = master
        self.dump_ctrl = dump_ctrl
        self.api_wf = api_wf
        self._log = log_fn
        self._actions = TabActions(
            master=master, dump_ctrl=dump_ctrl, log_fn=log_fn,
            open_settings_fn=open_settings_fn,
        )
        # Widget refs (filled in _build)
        self._app_id_entry: Optional[ctk.CTkEntry] = None
        self._progress: Optional[ctk.CTkProgressBar] = None
        self._progress_lbl: Optional[ctk.CTkLabel] = None
        self._review_count_lbl: Optional[ctk.CTkLabel] = None
        self._log_box: Optional[ctk.CTkTextbox] = None
        self._clock_lbl: Optional[ctk.CTkLabel] = None
        self._seen_label: Optional[ctk.CTkLabel] = None
        self._dump_label: Optional[ctk.CTkLabel] = None
        self._obsidian_label: Optional[ctk.CTkLabel] = None
        self._action_refs = ApiActionRefs()
        self.game_refs: Optional[ApiGameRefs] = None
        self.filter_refs: Optional[ApiFilterRefs] = None
        # Also-export option vars (used by the action bar at build time)
        self.also_export_csv_var = ctk.StringVar(value="0")
        self.also_export_json_var = ctk.StringVar(value="0")
        self.per_language_var = ctk.StringVar(value="0")
        self.auto_incr_var = ctk.StringVar(value="0")
        self.api_split_var = ctk.StringVar(value="0")
        # Watch-mode worker state
        self._watch_thread: Optional[threading.Thread] = None
        self._watch_stop = threading.Event()
        self._watching = False
        self._since: dict[str, Any] = {}
        # Wire button-state management to the workflow's bus events.
        # This is the single source of truth that toggles the
        # Export / Fetch-new / Resume / Stop / Watch buttons in
        # response to FETCH_STARTED / FETCH_COMPLETED / FETCH_FAILED.
        # An older in-line subscription block was removed — it called
        # ``self._on_fetch_completed(**kw)`` against the mixin's
        # ``(kw: dict, *, source: str)`` signature and silently raised
        # TypeError, so the Export button was never enabled.
        self.install_action_state_bus(
            started_event=self.api_wf.FETCH_STARTED,
            completed_event=self.api_wf.FETCH_COMPLETED,
            failed_event=self.api_wf.FETCH_FAILED,
            source="api",
        )
        self._build()

    # ---- build -------------------------------------------------------

    def _build(self) -> None:
        # Scrollable body — every control stays reachable on small windows.
        self.body = ctk.CTkScrollableFrame(self.parent, fg_color="transparent")
        self.body.pack(fill="both", expand=True, padx=4, pady=4)
        # 1. Tab-purpose hint (collapsed by default).
        build_tab_hint(self.body, hint_text=API_HINT, expanded=False)
        # 2. Game + Dump-folder section.
        self.game_refs = build_api_game_section(
            self.body, on_load=self._on_load,
            on_pick_dump_root=self._on_pick_dump_root,
            on_open_dump_folder=self._actions.open_dump_folder,
            on_pick_obsidian=self._actions.pick_obsidian_vault,
            on_clear_obsidian=self._actions.clear_obsidian_vault,
            initial_dump_label=f"📂 {self.dump_ctrl.dump_root}",
        )
        self._app_id_entry = self.game_refs.app_id_entry
        self._dump_label = self.game_refs.dump_label
        self._seen_label = self.game_refs.seen_label
        self._obsidian_label = self.game_refs.obsidian_label
        # 3. Filters section (responsive + reset button).
        self.filter_refs, _ = build_api_filters_section(
            self.body, on_reset=self._reset_filters,
        )
        # 4. When to include (German time).
        self._since = build_since_section(
            self.body, prefix="api_", log_fn=self._log,
        )
        # 5. Action bar.
        self._action_refs = build_api_action_bar(
            self.body, actions=self._actions,
            on_fetch=self._on_fetch, on_resume=self._on_resume,
            on_fetch_new=self._on_fetch_new, on_stop=self._on_stop,
            on_watch_toggle=self._on_watch_toggle, on_export=self._on_export,
            csv_var=self.also_export_csv_var,
            json_var=self.also_export_json_var,
            per_lang_var=self.per_language_var,
            auto_incr_var=self.auto_incr_var, split_var=self.api_split_var,
        )
        # 6. Progress + clock + Log (bottom of scrollable body).
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
        self._clock_lbl = ctk.CTkLabel(self.body, text="", text_color="gray")
        self._clock_lbl.pack(anchor="w", padx=12, pady=(0, 2))
        log_hdr = ctk.CTkFrame(self.body, fg_color="transparent")
        log_hdr.pack(fill="x", padx=12, pady=(4, 0))
        ctk.CTkLabel(log_hdr, text="Log", font=("", 12, "bold")).pack(side="left")
        ctk.CTkButton(log_hdr, text="Clear", width=70, height=24,
                      command=self._clear_log).pack(side="right")
        self._log_box = ctk.CTkTextbox(self.body, height=160)
        self._log_box.pack(fill="x", padx=8, pady=(0, 8))
        self._log_box.configure(state="disabled")

    def _bind_shortcuts(self) -> None:
        self.master.bind_all("<Control-f>", lambda _e: self._on_fetch())
        self.master.bind_all("<Control-Shift-f>", lambda _e: self._on_fetch_new())
        self.master.bind_all("<Control-s>", lambda _e: self._on_stop())
        self.master.bind_all("<Control-e>", lambda _e: self._on_export())
        self.master.bind_all("<Control-w>", lambda _e: self._on_watch_toggle())

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
        except Exception:
            pass

    def update_progress(self, page: int, fetched: int, total: int) -> None:
        if self._progress is not None and total:
            try:
                self._progress.set(min(fetched / total, 1.0))
            except Exception:
                pass
        if self._progress_lbl is not None:
            self._progress_lbl.configure(text=f"Page {page} · {fetched}/{total}")

    def update_review_count(self, n: int) -> None:
        if self._review_count_lbl is not None:
            self._review_count_lbl.configure(text=f"{n} reviews")

    def update_clock(self, now_str: str) -> None:
        if self._clock_lbl is not None:
            self._clock_lbl.configure(text=f"🕒 Now: {now_str} (Berlin)")
        if self._since:
            self._since["refresh"]()

    def refresh_seen_count(self, n: int) -> None:
        if self._seen_label is not None:
            self._seen_label.configure(text=f"Already exported: {n} reviews")

    def _refresh_obsidian_label(self) -> None:
        try:
            if self._obsidian_label is not None:
                v = self.dump_ctrl.obsidian_vault
                self._obsidian_label.configure(
                    text=str(v) if v else "(not set)",
                )
        except Exception:
            pass

    # ---- filter helpers ---------------------------------------------

    def _filter(self) -> Any:
        if self.filter_refs is None:
            return build_filter_config()
        helpful_raw = self.filter_refs.helpful_entry.get() or "0"
        try:
            helpful = int(helpful_raw or 0)
        except ValueError:
            helpful = 0
        return build_filter_config(
            language=self.filter_refs.lang_var.get(),
            review_filter=self.filter_refs.filter_var.get(),
            review_type=self.filter_refs.type_var.get(),
            day_range=None,
            min_helpful=helpful,
            num_per_page=int(self.filter_refs.perpage_var.get()),
            preset_label=self._since["preset_var"].get(),
            custom_date=self._since["date_entry"].get(),
            custom_time=self._since["time_entry"].get(),
        )

    def _first_24h_keep(self, reviews: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if self.filter_refs is None:
            return reviews
        return apply_window_filter(reviews, self.filter_refs.first_24h_var.get())

    def _reset_filters(self) -> None:
        """Reset every filter widget (and since section) to defaults."""
        if self.filter_refs is None:
            return
        f = self.filter_refs
        f.lang_var.set("all"); f.filter_var.set("recent"); f.type_var.set("all")
        f.purchase_var.set("all"); f.offtopic_var.set("false")
        f.perpage_var.set("100"); f.interval_var.set("5")
        f.first_24h_var.set("all"); f.backend_var.set("Steam API")
        for e in (f.helpful_entry, f.playtime_min_entry):
            try: e.delete(0, "end")
            except Exception: pass
        if self._since:
            try:
                self._since["preset_var"].set("all time")
                self._since["date_entry"].delete(0, "end")
                self._since["time_entry"].delete(0, "end")
                self._since["refresh"]()
            except Exception:
                pass
        self._log("Filters reset to defaults.")

    # ---- load / fetch / stop / resume / fetch-new -------------------

    def _on_load(self) -> None:
        raw = self._app_id_entry.get() if self._app_id_entry else ""
        app_id = resolve_app_id(raw)
        if app_id is None:
            self._log("Invalid App ID / URL."); return
        self.master.app_id = app_id
        self._log(f"Fetching app details for {app_id}…")
        details = self.api_wf.api.get_app_details(app_id)
        if not details:
            self._log("App details fetch failed."); return
        self.master.app_details = details
        self._log(f"Loaded: {details.get('name')}")
        bus.publish("app.loaded", app_id=app_id, app_details=details)
        # A new game id invalidates any prior state — refresh the
        # button enable/disable set.
        self._refresh_button_states(source="api")

    def _on_fetch(self) -> None:
        if self.master.app_id is None:
            self._log("Load a game first."); return
        cfg = self._filter()
        self.api_wf.start_fetch(
            self.master.app_id, language=cfg.language,
            review_filter=cfg.review_filter, review_type=cfg.review_type,
            day_range=cfg.day_range, min_date_ts=cfg.min_date_ts,
            min_helpful=cfg.min_helpful, num_per_page=cfg.num_per_page,
        )

    def _on_stop(self) -> None:
        self.api_wf.stop(); self._stop_watch(); self._log("Stop requested.")

    def _on_resume(self) -> None:
        if self.master.app_id is None: return
        cfg = self._filter()
        self.api_wf.start_fetch(
            self.master.app_id, language=cfg.language,
            review_filter=cfg.review_filter, review_type=cfg.review_type,
            day_range=cfg.day_range, min_date_ts=cfg.min_date_ts,
            min_helpful=cfg.min_helpful, num_per_page=cfg.num_per_page,
            resume=True,
        )

    def _on_fetch_new(self) -> None:
        if self.master.app_id is None:
            self._log("Load a game first."); return
        cfg = self._filter()
        self.api_wf.start_fetch(
            self.master.app_id, language=cfg.language,
            review_filter=cfg.review_filter, review_type=cfg.review_type,
            day_range=cfg.day_range, min_date_ts=cfg.min_date_ts,
            min_helpful=cfg.min_helpful, num_per_page=cfg.num_per_page,
        )
        bus.subscribe_once(self.api_wf.FETCH_COMPLETED,
                           self._auto_export_after_fetch)

    # ---- export ------------------------------------------------------

    def _build_export_context(
        self, *, reviews: list[dict[str, Any]], min_date_ts: Optional[int],
    ) -> ExportContext:
        f = self.filter_refs
        return ExportContext(
            app_id=self.master.app_id or 0,
            app_details=self.master.app_details,
            reviews=reviews,
            language_param=(f.lang_var.get() if f else "all"),
            review_filter=(f.filter_var.get() if f else "all"),
            review_type=(f.type_var.get() if f else "all"),
            day_range=None, min_date_ts=min_date_ts,
        )

    def _auto_export_after_fetch(self, **kw: Any) -> None:
        reviews = kw.get("reviews") or []
        if not reviews:
            self._log("Fetch-new: no reviews fetched."); return
        repo = DumpRepository(self.dump_ctrl.dump_root)
        seen = set(repo.load_seen_ids(self.master.app_id))
        new = [r for r in reviews if r.get("recommendationid") not in seen]
        if not new:
            self._log("Fetch-new: all reviews already exported."); return
        kept = self._first_24h_keep(new)
        base = make_export_basename(
            (self.master.app_details or {}).get("name", "app"),
            short_filter_label("api", self) + "_new",
        )
        dest = self.dump_ctrl.dump_root / base
        ctx = self._build_export_context(reviews=kept,
                                          min_date_ts=kw.get("min_date_ts"))
        result = self.api_wf.export(
            ctx, dest,
            also_csv=self.also_export_csv_var.get() == "1",
            also_json=self.also_export_json_var.get() == "1",
            per_language=self.per_language_var.get() == "1",
            obsidian_vault=self.dump_ctrl.obsidian_vault,
        )
        new_ids = seen | {rid for r in kept if (rid := r.get("recommendationid"))}
        repo.save_seen_ids(self.master.app_id, sorted(new_ids))
        self.refresh_seen_count(len(new_ids))
        self._log(f"Fetch-new: exported {len(kept)} reviews → {dest.name}")
        if result.get("obsidian"):
            self._log(f"  ✓ Synced to Obsidian: {result['obsidian']}")

    def _on_export(self) -> None:
        if not self.master.reviews:
            self._log("Nothing to export."); return
        kept = self._first_24h_keep(self.master.reviews)
        default_name = make_export_basename(
            (self.master.app_details or {}).get("name", "app"),
            short_filter_label("api", self),
        )
        dest = filedialog.asksaveasfilename(
            defaultextension=".md", initialfile=default_name,
            filetypes=[("Markdown", "*.md"), ("All", "*.*")],
        )
        if not dest: return
        ctx = self._build_export_context(reviews=kept, min_date_ts=None)
        result = self.api_wf.export(
            ctx, Path(dest),
            also_csv=self.also_export_csv_var.get() == "1",
            also_json=self.also_export_json_var.get() == "1",
            per_language=self.per_language_var.get() == "1",
            obsidian_vault=self.dump_ctrl.obsidian_vault,
        )
        self._log(f"Exported → {result.get('md')}")
        if result.get("obsidian"):
            self._log(f"  ✓ Synced to Obsidian: {result['obsidian']}")
        if self.master.settings.get("open_after_export", True):
            from ..controllers.action_handler import open_in_editor
            err = open_in_editor(Path(dest))
            if err: self._log(f"  Could not open in editor: {err}")

    # ---- watch mode --------------------------------------------------

    def _on_watch_toggle(self) -> None:
        if self._watch_thread and self._watch_thread.is_alive():
            self._stop_watch(); self._log("Watch mode stopped.")
            self._watching = False
            if self._action_refs.watch_btn is not None:
                self._action_refs.watch_btn.configure(text="▶ Start Watching")
            self._refresh_button_states(source="api")
            return
        if self.master.app_id is None:
            self._log("Load a game first."); return
        self._watch_stop.clear()
        try:
            minutes = int(self.filter_refs.interval_var.get()) if self.filter_refs else 5
        except ValueError:
            minutes = 5
        self._watching = True
        if self._action_refs.watch_btn is not None:
            self._action_refs.watch_btn.configure(text="■ Stop Watching")
        self._log(f"Watching every {minutes} min…")
        def _worker() -> None:
            while not self._watch_stop.is_set():
                new_reviews = self.api_wf.api.poll_recent_reviews(
                    self.master.app_id, max_pages=2, page_size=100,
                    language=(self.filter_refs.lang_var.get()
                              if self.filter_refs else "all"),
                )
                if new_reviews:
                    self._log(f"[watch] +{len(new_reviews)} new review(s).")
                    if self.auto_incr_var.get() == "1":
                        bus.publish(self.api_wf.FETCH_COMPLETED,
                                    app_id=self.master.app_id,
                                    reviews=new_reviews)
                if self._watch_stop.wait(timeout=minutes * 60): return
        self._watch_thread = threading.Thread(target=_worker, daemon=True)
        self._watch_thread.start()
        self._refresh_button_states(source="api")

    def _stop_watch(self) -> None:
        self._watch_stop.set()

    # ---- dump folder -------------------------------------------------

    def _on_pick_dump_root(self) -> None:
        new_root = self._actions.pick_dump_root()
        if new_root is None: return
        if self._dump_label is not None:
            self._dump_label.configure(text=f"📂 {new_root}")
        cls = type(self.master.dump_repo)
        self.master.dump_repo = cls(new_root)
        self.api_wf.dump_root = new_root


__all__ = ["ApiTabController"]
