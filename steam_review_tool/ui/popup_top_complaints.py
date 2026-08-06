"""Top-Complaints / Top-Praise popup.

Shows the most-mentioned themes (with sample quotes) for the loaded
review set. Mirrors the original TopComplaintsDialog.
"""
from __future__ import annotations

import threading
from typing import Callable, Optional, Any

import customtkinter as ctk

from ..services.review_analyzer import (
    aggregate_top_themes, compute_playtime_histogram,
)


class TopComplaintsDialog:
    """A modal that shows top-N complaint + praise themes + a playtime histogram."""

    def __init__(self, master, reviews: list[dict[str, Any]], keyword_list) -> None:
        self.master = master
        self.reviews = reviews
        self.keyword_list = keyword_list
        self._top: Optional[ctk.CTkToplevel] = None
        # Track the analysis worker so a re-entry (e.g. the
        # user reopens the popup before the previous worker
        # finished) doesn't spawn a second concurrent worker
        # racing on the same widgets.
        self._worker: Optional[threading.Thread] = None

    def open(self) -> None:
        if self._top is not None and self._top.winfo_exists():
            self._top.focus()
            return
        self._top = ctk.CTkToplevel(self.master)
        self._top.title("Top complaints & praise")
        self._top.geometry("780x580")
        self._top.transient(self.master)
        # Build the static frame (title + "Computing…" placeholder)
        # synchronously so the popup appears immediately, then
        # offload the (potentially slow) aggregation to a
        # worker thread. The old code did the whole build on the
        # Tk main thread — for a 5 000-review set, that's 1-2 s
        # of GUI freeze while the popup is empty.
        self._build_skeleton()
        self._start_worker()

    def _build_skeleton(self) -> None:
        """Build the static title + placeholders. The dynamic
        sections (theme boxes + playtime histogram) are filled
        in by :meth:`_populate` once the worker thread finishes.
        """
        # R32-7: replace the type-narrowing ``assert top is not None``
        # with an early-return guard (see popup_batch_dump for the
        # full reasoning — ``assert`` is stripped under ``python -O``).
        top = self._top
        if top is None:
            return
        ctk.CTkLabel(
            top, text="Top complaints & praise",
            font=("", 14, "bold"),
        ).pack(pady=(10, 4))
        # Two placeholder rows (one for negative, one for positive)
        # that the worker will replace with the real theme textboxes.
        self._neg_frame = ctk.CTkFrame(top, fg_color="transparent")
        self._neg_frame.pack(fill="x", padx=12, pady=(8, 2))
        self._pos_frame = ctk.CTkFrame(top, fg_color="transparent")
        self._pos_frame.pack(fill="x", padx=12, pady=(8, 2))
        # Histogram placeholder frame
        self._hist_frame = ctk.CTkFrame(top, fg_color="transparent")
        self._hist_frame.pack(fill="x", padx=12, pady=(12, 2))
        self._status_lbl = ctk.CTkLabel(
            top, text="Computing…", anchor="w", text_color="gray",
        )
        self._status_lbl.pack(fill="x", padx=12, pady=(4, 2))
        ctk.CTkButton(top, text="Close", command=top.destroy).pack(pady=(10, 8))

    def _start_worker(self) -> None:
        """Spawn the daemon thread that runs the aggregation."""
        if (self._worker is not None and self._worker.is_alive()):
            return  # already running
        reviews = self.reviews
        keyword_list = self.keyword_list
        top = self._top

        def worker() -> None:
            try:
                neg = aggregate_top_themes(
                    reviews, top_n=10, mode="negative",
                    keyword_list=keyword_list,
                )
                pos = aggregate_top_themes(
                    reviews, top_n=10, mode="positive",
                    keyword_list=keyword_list,
                )
                hist = compute_playtime_histogram(reviews, buckets=5)
            except Exception as exc:
                if top is not None:
                    top.after(
                        0, lambda: self._show_error(
                            f"Analysis failed: {exc}",
                        ),
                    )
                return
            if top is not None:
                top.after(
                    0, lambda: self._populate(neg, pos, hist),
                )

        self._worker = threading.Thread(target=worker, daemon=True)
        self._worker.start()

    def _show_error(self, msg: str) -> None:
        if self._status_lbl is not None:
            self._status_lbl.configure(text=msg, text_color="red")

    def _populate(
        self,
        neg_themes: list[dict[str, Any]],
        pos_themes: list[dict[str, Any]],
        hist: dict[str, Any],
    ) -> None:
        """Fill the placeholder frames with the real data. Runs
        on the Tk main thread via ``after(0, …)``."""
        top = self._top
        if top is None:
            return
        # The popup might have been closed while the worker was
        # running. ``winfo_exists`` is the cheap pre-check; the
        # per-widget calls below would otherwise raise ``TclError``
        # on a destroyed frame.
        if not top.winfo_exists():
            return

        for frame, themes, section in (
            (self._neg_frame, neg_themes, "Top complaints (negative themes)"),
            (self._pos_frame, pos_themes, "Top praise (positive themes)"),
        ):
            ctk.CTkLabel(
                frame, text=section, font=("", 12, "bold"),
            ).pack(pady=(0, 2), anchor="w")
            if not themes:
                ctk.CTkLabel(
                    frame, text="(no themes detected)",
                    text_color="gray",
                ).pack(anchor="w", padx=12)
                continue
            box = ctk.CTkTextbox(frame, height=120)
            box.pack(fill="x", pady=2)
            lines = [
                f"• {t['theme']} ({t['count']}×) — \"{t['sample_quote']}\""
                for t in themes
            ]
            box.insert("1.0", "\n".join(lines))
            box.configure(state="readonly")

        ctk.CTkLabel(
            self._hist_frame, text="Playtime distribution",
            font=("", 12, "bold"),
        ).pack(pady=(0, 2), anchor="w")
        if hist:
            box = ctk.CTkTextbox(self._hist_frame, height=100)
            box.pack(fill="x", pady=2)
            box.insert("1.0", "\n".join(
                f"  {label}: {vals['pos']} positive / {vals['neg']} negative"
                for label, vals in hist.items()
            ))
            box.configure(state="readonly")
        else:
            ctk.CTkLabel(
                self._hist_frame, text="(no playtime data)",
                text_color="gray",
            ).pack(anchor="w", padx=12)
        if self._status_lbl is not None:
            self._status_lbl.configure(text="")


__all__ = ["TopComplaintsDialog"]