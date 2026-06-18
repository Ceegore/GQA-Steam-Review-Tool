"""Trends chart popup.

Uses the Python ``tkinter`` Canvas to draw a simple line/bar chart of
wishlist / follower / review counts over time. Pure-Python so we don't
add a matplotlib dependency.
"""
from __future__ import annotations

import tkinter as tk
from typing import Optional, Any

import customtkinter as ctk

from ..models.trends_snapshot import TrendsSnapshot


RANGE_DAYS = {
    "1d": 1, "1w": 7, "1m": 30, "3m": 90,
    "6m": 180, "1y": 365, "all": None,
}


class TrendsWindow:
    """Modal line/bar chart for one or more tracked apps."""

    def __init__(self, master, store, apps: list[dict[str, Any]]) -> None:
        self.master = master
        self.store = store
        self.apps = apps
        self._top: Optional[ctk.CTkToplevel] = None
        self._metric_var = tk.StringVar(value="wishlist")
        self._range_var = tk.StringVar(value="1w")
        self._chart_type_var = tk.StringVar(value="line")
        self._canvas: Optional[tk.Canvas] = None

    # ---- public --------------------------------------------------------

    def open(self) -> None:
        if self._top is not None and self._top.winfo_exists():
            self._top.focus()
            return
        self._top = ctk.CTkToplevel(self.master)
        self._top.title("Trends graph")
        self._top.geometry("900x600")
        self._top.transient(self.master)
        self._top.grab_set()
        self._build()

    # ---- internals -----------------------------------------------------

    def _build(self) -> None:
        top = self._top
        assert top is not None

        bar = ctk.CTkFrame(top, fg_color="transparent")
        bar.pack(fill="x", padx=10, pady=(10, 4))
        ctk.CTkLabel(bar, text="📈 Trends", font=("", 13, "bold")).pack(
            side="left", padx=4,
        )

        ctk.CTkLabel(bar, text="Metric:", width=60, anchor="e").pack(
            side="left", padx=(20, 4),
        )
        ctk.CTkOptionMenu(
            bar, values=["wishlist", "followers", "reviews", "positive %"],
            variable=self._metric_var, width=120,
            command=lambda _v: self._redraw(),
        ).pack(side="left", padx=4)

        ctk.CTkLabel(bar, text="Range:", width=50, anchor="e").pack(
            side="left", padx=(20, 4),
        )
        ctk.CTkOptionMenu(
            bar, values=list(RANGE_DAYS.keys()),
            variable=self._range_var, width=80,
            command=lambda _v: self._redraw(),
        ).pack(side="left", padx=4)

        ctk.CTkLabel(bar, text="Type:", width=40, anchor="e").pack(
            side="left", padx=(20, 4),
        )
        ctk.CTkOptionMenu(
            bar, values=["line", "bar"],
            variable=self._chart_type_var, width=80,
            command=lambda _v: self._redraw(),
        ).pack(side="left", padx=4)

        ctk.CTkButton(bar, text="Close", width=80, command=top.destroy).pack(
            side="right", padx=4,
        )

        ctk.CTkLabel(
            top, text="(tip: 'positive %' shows the share of positive reviews)",
            text_color="gray", anchor="w",
        ).pack(fill="x", padx=10)

        self._canvas = tk.Canvas(top, bg="#1a1a1a", highlightthickness=0)
        self._canvas.pack(fill="both", expand=True, padx=10, pady=(2, 10))

        self._redraw()

    def _redraw(self) -> None:
        if self._canvas is None:
            return
        self._canvas.delete("all")
        metric = self._metric_var.get()
        days = RANGE_DAYS.get(self._range_var.get())
        chart_type = self._chart_type_var.get()

        series_by_app: dict[int, list[TrendsSnapshot]] = {}
        for app in self.apps:
            snaps = self.store.series(app["app_id"], metric, days=days)
            series_by_app[app["app_id"]] = snaps

        all_vals: list[float] = []
        for snaps in series_by_app.values():
            for s in snaps:
                v = self._value(s, metric)
                if v is not None:
                    all_vals.append(float(v))
        if not all_vals:
            self._canvas.create_text(
                450, 280, text="No data for the selected range.",
                fill="#888", font=("Segoe UI", 12),
            )
            return

        # Aggregate by day (averaging)
        from collections import defaultdict
        agg: dict[int, dict[int, list[float]]] = {}
        for app_id, snaps in series_by_app.items():
            per_day: dict[int, list[float]] = defaultdict(list)
            for s in snaps:
                v = self._value(s, metric)
                if v is None:
                    continue
                day = s.ts // 86400
                per_day[day].append(float(v))
            for d, vs in per_day.items():
                agg.setdefault(app_id, {})[d] = [sum(vs) / len(vs)]

        w = self._canvas.winfo_width() or 880
        h = self._canvas.winfo_height() or 540
        pad_l, pad_r, pad_t, pad_b = 60, 160, 30, 40
        plot_w = max(w - pad_l - pad_r, 100)
        plot_h = max(h - pad_t - pad_b, 100)
        vmin, vmax = min(all_vals), max(all_vals)
        if vmax == vmin:
            vmax = vmin + 1

        # axes
        self._canvas.create_line(pad_l, pad_t, pad_l, pad_t + plot_h, fill="#666")
        self._canvas.create_line(
            pad_l, pad_t + plot_h, pad_l + plot_w, pad_t + plot_h, fill="#666",
        )
        for i in range(5):
            y = pad_t + plot_h * i / 4
            v = vmax - (vmax - vmin) * i / 4
            self._canvas.create_line(pad_l - 4, y, pad_l, y, fill="#666")
            self._canvas.create_text(
                pad_l - 6, y, text=f"{v:.0f}", anchor="e", fill="#888",
                font=("Segoe UI", 9),
            )

        # plot each app's series
        palette = ["#5dade6", "#e67e22", "#2ecc71", "#9b59b6", "#f1c40f"]
        from time import time as _now
        cutoff = int(_now()) - (days * 86400 if days else 0)
        all_days: set[int] = set()
        for _app_id, per_day in agg.items():
            all_days.update(per_day.keys())
        if not all_days:
            return
        d_min, d_max = min(all_days), max(all_days)
        if d_min == d_max:
            d_max = d_min + 1

        for idx, (app_id, per_day) in enumerate(agg.items()):
            color = palette[idx % len(palette)]
            days_sorted = sorted(per_day.keys())
            if not days_sorted:
                continue
            pts = []
            for d in days_sorted:
                if d < cutoff and days:
                    continue
                x = pad_l + (d - d_min) / max(d_max - d_min, 1) * plot_w
                v = per_day[d][0]
                y = pad_t + (vmax - v) / max(vmax - vmin, 1) * plot_h
                pts.append((x, y, d, v))
            if chart_type == "line" and len(pts) >= 2:
                for i in range(len(pts) - 1):
                    self._canvas.create_line(
                        pts[i][0], pts[i][1], pts[i+1][0], pts[i+1][1],
                        fill=color, width=2,
                    )
            elif chart_type == "bar":
                bar_w = max(plot_w / max(len(pts), 1) - 2, 2)
                for x, y, _, _ in pts:
                    self._canvas.create_rectangle(
                        x, y, x + bar_w, pad_t + plot_h,
                        fill=color, outline="",
                    )
            for x, y, _, _ in pts:
                self._canvas.create_oval(
                    x - 3, y - 3, x + 3, y + 3, fill=color, outline="",
                )

            # legend entry
            name = next((a["name"] for a in self.apps if a["app_id"] == app_id),
                        str(app_id))
            ly = pad_t + 20 + idx * 18
            self._canvas.create_rectangle(
                w - pad_r + 8, ly - 6, w - pad_r + 20, ly + 6,
                fill=color, outline="",
            )
            self._canvas.create_text(
                w - pad_r + 26, ly, text=name, anchor="w",
                fill="#e0e0e0", font=("Segoe UI", 9),
            )

    @staticmethod
    def _value(s: TrendsSnapshot, metric: str) -> Optional[float]:
        if metric == "wishlist":
            return s.wishlist
        if metric == "followers":
            return s.followers
        if metric == "reviews":
            return s.reviews
        if metric == "positive %":
            return s.positive_pct
        return None


__all__ = ["TrendsWindow", "RANGE_DAYS"]