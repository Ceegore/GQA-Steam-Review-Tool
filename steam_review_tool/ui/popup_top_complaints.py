"""Top-Complaints / Top-Praise popup.

Shows the most-mentioned themes (with sample quotes) for the loaded
review set. Mirrors the original TopComplaintsDialog.
"""
from __future__ import annotations

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

    def open(self) -> None:
        if self._top is not None and self._top.winfo_exists():
            self._top.focus()
            return
        self._top = ctk.CTkToplevel(self.master)
        self._top.title("Top complaints & praise")
        self._top.geometry("780x580")
        self._top.transient(self.master)
        self._build()

    def _build(self) -> None:
        top = self._top
        assert top is not None

        ctk.CTkLabel(
            top, text="Top complaints & praise",
            font=("", 14, "bold"),
        ).pack(pady=(10, 4))

        for section, mode in (
            ("Top complaints (negative themes)", "negative"),
            ("Top praise (positive themes)", "positive"),
        ):
            ctk.CTkLabel(top, text=section, font=("", 12, "bold")).pack(
                pady=(8, 2), anchor="w", padx=12,
            )
            themes = aggregate_top_themes(
                self.reviews, top_n=10, mode=mode,
                keyword_list=self.keyword_list,
            )
            if not themes:
                ctk.CTkLabel(
                    top, text="(no themes detected)",
                    text_color="gray",
                ).pack(anchor="w", padx=24)
                continue
            box = ctk.CTkTextbox(top, height=120)
            box.pack(fill="x", padx=12, pady=2)
            lines = []
            for t in themes:
                lines.append(
                    f"• {t['theme']} ({t['count']}×) — \"{t['sample_quote']}\""
                )
            box.insert("1.0", "\n".join(lines))
            box.configure(state="disabled")

        # Playtime histogram
        ctk.CTkLabel(top, text="Playtime distribution", font=("", 12, "bold")).pack(
            pady=(12, 2), anchor="w", padx=12,
        )
        hist = compute_playtime_histogram(self.reviews, buckets=5)
        if hist:
            box = ctk.CTkTextbox(top, height=100)
            box.pack(fill="x", padx=12, pady=2)
            box.insert("1.0", "\n".join(
                f"  {label}: {vals['pos']} positive / {vals['neg']} negative"
                for label, vals in hist.items()
            ))
            box.configure(state="disabled")

        ctk.CTkButton(top, text="Close", command=top.destroy).pack(pady=(10, 8))


__all__ = ["TopComplaintsDialog"]