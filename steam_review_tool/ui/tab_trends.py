"""Trends tab — list[Any] + add/remove tracked apps, open chart, refresh now.

Matches the original monolith: each row shows the tracked app name +
App ID + a per-row Remove button. A separate input row accepts a
custom App ID to add. A "Refresh all" worker hits the Playwright
scraper (or Apify) for each tracked app and records a snapshot.

Heavy lifting lives in ``controllers/trends_workflow.py``. The
chart popup lives in ``popup_trends_chart.py``.
"""
from __future__ import annotations

from time import time as _now
from typing import Any, Callable, Optional

import customtkinter as ctk

from ..controllers.trends_workflow import TrendsWorkflow
from ..models.trends_snapshot import TrendsSnapshot
from ..services.trends_store import TrendsStore


class TrendsTabController:
    """Owns the "📈 Trends" tab widgets."""

    def __init__(
        self,
        parent: ctk.CTkBaseClass,
        *,
        master: Any,
        trends_wf: TrendsWorkflow,
        trends_store: TrendsStore,
    ) -> None:
        self.parent = parent
        self.master = master
        self.trends_wf = trends_wf
        self.trends_store = trends_store
        self._body: Optional[ctk.CTkScrollableFrame] = None
        self._input_entry: Optional[ctk.CTkEntry] = None
        self._lang_var = ctk.StringVar(value="all")
        self._status_lbl: Optional[ctk.CTkLabel] = None
        self._build()
        self._refresh()

    # ---- build -------------------------------------------------------

    def _build(self) -> None:
        # Explanation header
        ctk.CTkLabel(
            self.parent,
            text=(
                "📈 Wishlist / follower / review trends\n\n"
                "Each time you click 'Refresh all' (or when the app "
                "starts), the current wishlist / follower / review "
                "counts are scraped from the Steam storefront and "
                "saved to a local time-series DB."
            ),
            anchor="w", justify="left",
        ).pack(fill="x", padx=10, pady=(10, 4))

        # Add-app row
        add_row = ctk.CTkFrame(self.parent, fg_color="transparent")
        add_row.pack(fill="x", padx=10, pady=(0, 4))
        ctk.CTkLabel(add_row, text="Add App ID:", width=90, anchor="e").pack(
            side="left", padx=(0, 4),
        )
        self._input_entry = ctk.CTkEntry(
            add_row, width=200, placeholder_text="e.g. 4311090",
        )
        self._input_entry.pack(side="left", padx=4)
        ctk.CTkButton(
            add_row, text="➕ Add to trends", width=130,
            command=self._on_add_custom,
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            add_row, text="➕ Add currently loaded", width=200,
            command=self._on_add_current,
        ).pack(side="left", padx=4)

        # Tracked apps list[Any] (scrollable, one row per app with its own Remove)
        ctk.CTkLabel(
            self.parent, text="Tracked apps:", anchor="w",
            font=("", 12, "bold"),
        ).pack(fill="x", padx=10, pady=(8, 0))
        self._body = ctk.CTkScrollableFrame(self.parent, height=180)
        self._body.pack(fill="both", expand=True, padx=8, pady=(0, 6))

        # Action row
        action_row = ctk.CTkFrame(self.parent, fg_color="transparent")
        action_row.pack(fill="x", padx=10, pady=4)
        ctk.CTkButton(
            action_row, text="🔄 Refresh all", width=130,
            command=self._on_refresh_all,
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            action_row, text="📈 View graph", width=130,
            command=self._on_view_graph,
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            action_row, text="🧹 Remove all", width=130,
            command=self._on_remove_all,
        ).pack(side="left", padx=4)
        ctk.CTkLabel(action_row, text="Language:", width=80, anchor="e").pack(
            side="left", padx=(20, 4),
        )
        ctk.CTkOptionMenu(
            action_row,
            values=["all", "english", "german", "russian",
                    "schinese", "french", "spanish", "japanese"],
            variable=self._lang_var, width=110,
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            action_row, text="🔍 Per-language review count", width=210,
            command=self._on_per_language_count,
        ).pack(side="left", padx=4)
        self._status_lbl = ctk.CTkLabel(
            action_row, text="", anchor="w", text_color="gray",
        )
        self._status_lbl.pack(side="right", padx=4)

    # ---- handlers ----------------------------------------------------

    def _refresh(self) -> None:
        if self._body is None:
            return
        for w in self._body.winfo_children():
            w.destroy()
        tracked = self.trends_wf.list_tracked()
        if not tracked:
            ctk.CTkLabel(
                self._body, text="(no apps tracked yet)", text_color="gray",
            ).pack(pady=8)
            return
        for a in tracked:
            row = ctk.CTkFrame(self._body, fg_color="transparent")
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(
                row, text=f"• {a['name']} (App {a['app_id']})",
                anchor="w",
            ).pack(side="left", padx=4, fill="x", expand=True)
            ctk.CTkButton(
                row, text="Remove", width=80,
                command=lambda aid=a["app_id"]: self._on_remove_one(aid),
            ).pack(side="right", padx=4)

    def _on_add_current(self) -> None:
        if self.master.app_id is None:
            return
        name = (
            (self.master.app_details or {}).get("name")
            or f"App {self.master.app_id}"
        )
        self.trends_wf.add(self.master.app_id, name)
        self._refresh()

    def _on_add_custom(self) -> None:
        if self._input_entry is None:
            return
        raw = self._input_entry.get().strip()
        try:
            app_id = int(raw)
        except ValueError:
            if self._status_lbl is not None:
                self._status_lbl.configure(text="Invalid App ID.")
            return
        name = f"App {app_id}"
        try:
            from ..utils.url_utils import resolve_app_id
            parsed = resolve_app_id(raw)
            if parsed is not None:
                app_id = parsed
        except Exception:
            pass
        self.trends_wf.add(app_id, name)
        self._input_entry.delete(0, "end")
        self._refresh()

    def _on_remove_one(self, app_id: int) -> None:
        self.trends_wf.remove(app_id)
        self._refresh()

    def _on_remove_all(self) -> None:
        for a in self.trends_wf.list_tracked():
            self.trends_wf.remove(a["app_id"])
        self._refresh()

    def _on_refresh_all(self) -> None:
        """Snapshot wishlist/follower/reviews for every tracked app.

        We use a lightweight ``fetch_metrics`` that records wishlist
        / followers / reviews = None for now (the storefront DOM
        probe lives in ``services/playwright_subprocess.py``); the
        workflow's per-snapshot store is the integration point.
        """
        def fetch_metrics(app_id: int) -> TrendsSnapshot:
            try:
                from ..services.playwright_subprocess import (
                    run_popularity_probe,
                )
                metrics = run_popularity_probe(app_id, timeout=30)
            except Exception:
                metrics = {
                    "wishlist": None, "followers": None, "reviews": None,
                }
            return TrendsSnapshot(
                app_id=app_id,
                ts=int(_now()),
                wishlist=metrics.get("wishlist"),
                followers=metrics.get("followers"),
                reviews=metrics.get("reviews"),
            )
        self.trends_wf.refresh_all_async(fetch_metrics)
        if self._status_lbl is not None:
            self._status_lbl.configure(text="Refresh started…")

    def _on_per_language_count(self) -> None:
        if self.master.app_id is None:
            if self._status_lbl is not None:
                self._status_lbl.configure(text="Load a game first.")
            return
        from ..services.steam_api_service import SteamAPI
        api = SteamAPI()
        lang = self._lang_var.get()
        if lang == "all":
            reviews = api.fetch_all_reviews(
                self.master.app_id, language="all",
                review_filter="all", review_type="all",
                num_per_page=100, log_cb=self._log_status,
            )
        else:
            reviews = api.fetch_all_reviews(
                self.master.app_id, language=lang,
                review_filter="all", review_type="all",
                num_per_page=100, log_cb=self._log_status,
            )
        if self._status_lbl is not None:
            self._status_lbl.configure(
                text=f"{lang}: {len(reviews)} reviews",
            )

    def _log_status(self, msg: str) -> None:
        if self._status_lbl is not None:
            self._status_lbl.configure(text=msg[:120])

    def _on_view_graph(self) -> None:
        from .popup_trends_chart import TrendsWindow
        win = TrendsWindow(
            self.master, self.trends_store,
            self.trends_wf.list_tracked(),
        )
        win.open()


__all__ = ["TrendsTabController"]