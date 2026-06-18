"""Action-bar widget builder for the Playwright tab.

Extracted from ``tab_playwright.py`` to keep the controller file
under the 500-line hard limit. Mirrors the layout of
``_api_action_bar.py`` minus the watch-mode widgets.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

import customtkinter as ctk

from .tooltip import ToolTip


@dataclass
class PwActionRefs:
    """Handles returned by :func:`build_pw_action_bar`."""
    scrape_btn: Optional[ctk.CTkButton] = None
    resume_btn: Optional[ctk.CTkButton] = None
    fetch_new_btn: Optional[ctk.CTkButton] = None
    stop_btn: Optional[ctk.CTkButton] = None
    export_btn: Optional[ctk.CTkButton] = None


def build_pw_action_bar(
    parent: ctk.CTkBaseClass,
    *,
    actions: Any,                          # TabActions instance
    on_scrape: Callable[[], None],
    on_stop: Callable[[], None],
    on_open_cache: Callable[[], None],
    on_resume: Callable[[], None],
    on_fetch_new: Callable[[], None],
    on_export: Callable[[], None],
    csv_var: ctk.StringVar,
    json_var: ctk.StringVar,
    per_lang_var: ctk.StringVar,
    split_var: ctk.StringVar,
) -> PwActionRefs:
    """Construct the two button rows. Returns refs to the key buttons."""
    sec_act = ctk.CTkFrame(parent, fg_color="transparent")
    sec_act.pack(fill="x", padx=8, pady=(4, 4))
    refs = PwActionRefs()

    refs.scrape_btn = ctk.CTkButton(
        sec_act, text="▶ Start Browser Scrape", fg_color="#8a5a00",
        command=on_scrape, width=210,
    )
    refs.scrape_btn.pack(side="left", padx=4, pady=4)
    ToolTip(refs.scrape_btn, "Launch Chromium and fetch reviews (Ctrl+P).")

    refs.resume_btn = ctk.CTkButton(
        sec_act, text="▶ Resume", command=on_resume,
        width=140, fg_color="#2d7a2d",
    )
    refs.resume_btn.pack(side="left", padx=4, pady=4)
    refs.resume_btn.configure(state="disabled")
    ToolTip(refs.resume_btn, "Continue a stopped scrape from the saved cursor.")

    refs.fetch_new_btn = ctk.CTkButton(
        sec_act, text="🆕 Fetch new", command=on_fetch_new,
        width=140, fg_color="#0f7a3a",
    )
    refs.fetch_new_btn.pack(side="left", padx=4, pady=4)
    refs.fetch_new_btn.configure(state="disabled")
    ToolTip(refs.fetch_new_btn, "Scrape + dedup + auto-export.")

    refs.stop_btn = ctk.CTkButton(
        sec_act, text="■ Stop", command=on_stop, width=80,
        fg_color="#a83232",
    )
    refs.stop_btn.pack(side="left", padx=4, pady=4)
    refs.stop_btn.configure(state="disabled")
    ToolTip(refs.stop_btn, "Stop the current scrape.")

    refs.export_btn = ctk.CTkButton(
        sec_act, text="Export to .md", command=on_export,
        width=130, fg_color="#2d7a2d",
    )
    refs.export_btn.pack(side="right", padx=4, pady=4)
    refs.export_btn.configure(state="disabled")
    ToolTip(refs.export_btn, "Save the scraped reviews as a Markdown file.")

    ctk.CTkButton(
        sec_act, text="Open cache", command=on_open_cache, width=120,
    ).pack(side="right", padx=4, pady=4)

    split_frame = ctk.CTkFrame(sec_act, fg_color="transparent")
    split_frame.pack(side="right", padx=(4, 12), pady=4)
    ctk.CTkLabel(split_frame, text="Split per N:").pack(
        side="left", padx=(0, 4),
    )
    ctk.CTkEntry(
        split_frame, textvariable=split_var, width=70,
        placeholder_text="0=off",
    ).pack(side="left")

    also_frame = ctk.CTkFrame(sec_act, fg_color="transparent")
    also_frame.pack(side="right", padx=4, pady=4)
    ctk.CTkCheckBox(
        also_frame, text="📊 CSV", variable=csv_var,
        onvalue="1", offvalue="0", width=70,
    ).pack(side="left", padx=2)
    ctk.CTkCheckBox(
        also_frame, text="🔧 JSON", variable=json_var,
        onvalue="1", offvalue="0", width=80,
    ).pack(side="left", padx=2)
    ctk.CTkCheckBox(
        also_frame, text="🌐 Per-lang", variable=per_lang_var,
        onvalue="1", offvalue="0", width=90,
    ).pack(side="left", padx=2)
    for label, fn, w in (
        ("📊 Summary", actions.write_summary, 110),
        ("🔍 Search", actions.search_dump, 110),
        ("📦 Batch", actions.batch_dump, 110),
    ):
        ctk.CTkButton(
            sec_act, text=label, width=w, command=fn,
        ).pack(side="right", padx=4, pady=4)

    # AI / analytics row
    ai_row = ctk.CTkFrame(sec_act, fg_color="transparent")
    ai_row.pack(fill="x", padx=4, pady=(0, 4))
    for label, fn, w in (
        ("🤖 Copy + AI prompt", actions.copy_with_ai_prompt, 170),
        ("💾 Save as prompt", actions.save_as_prompt, 140),
        ("🔴 Quick: negatives", actions.quick_view_negatives, 140),
        ("🔝 Top complaints", actions.top_complaints, 140),
        ("📂 Open latest .md", actions.open_latest_md, 140),
    ):
        ctk.CTkButton(
            ai_row, text=label, width=w, command=fn,
        ).pack(side="left", padx=2)
    ctk.CTkButton(
        ai_row, text="⚙ Settings", width=110,
        command=actions.open_settings, fg_color="#444",
    ).pack(side="right", padx=2)
    return refs


__all__ = ["PwActionRefs", "build_pw_action_bar"]