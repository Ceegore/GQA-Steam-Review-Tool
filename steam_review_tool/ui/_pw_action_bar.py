"""Action-bar widget builder for the Playwright tab.

Extracted from ``tab_playwright.py`` to keep the controller file
under the 500-line hard limit. Builds the action-bar buttons inside
a :class:`WrapFrame` so the bar wraps to a new row when the current
window is too narrow — no element ever runs off the visible tab
area.

The Export button text toggles between **"Export to .md"** (only
the markdown export will be produced) and **"Generate all"** (any
of CSV / JSON / Per-lang is enabled, so the user should know the
button now produces multiple files).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

import customtkinter as ctk
import tkinter as tk

from ._responsive import WrapFrame
from .tooltip import ToolTip


# Shared text labels for the Export button (mirrors _api_action_bar).
_EXPORT_BASE_TEXT = "Export to .md"
_EXPORT_GENERATE_ALL_TEXT = "Generate all"


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
    actions: Any,
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
    """Construct the Playwright tab action bar with auto-wrapping rows."""
    sec_act = ctk.CTkFrame(parent, fg_color="transparent")
    sec_act.pack(fill="x", padx=8, pady=(4, 4))
    wrap = WrapFrame(sec_act, padx=4, pady=4, row_gap=2)
    wrap.pack(fill="x")
    refs = PwActionRefs()

    refs.scrape_btn = ctk.CTkButton(
        wrap, text="▶ Start Browser Scrape", fg_color="#8a5a00",
        command=on_scrape, width=210,
    )
    wrap.add(refs.scrape_btn)
    ToolTip(refs.scrape_btn, "Launch Chromium and fetch reviews (Ctrl+P).")

    refs.resume_btn = ctk.CTkButton(
        wrap, text="▶ Resume", command=on_resume,
        width=140, fg_color="#2d7a2d",
    )
    wrap.add(refs.resume_btn)
    refs.resume_btn.configure(state="disabled")
    ToolTip(refs.resume_btn, "Continue a stopped scrape from the saved cursor.")

    refs.fetch_new_btn = ctk.CTkButton(
        wrap, text="🆕 Fetch new", command=on_fetch_new,
        width=140, fg_color="#0f7a3a",
    )
    wrap.add(refs.fetch_new_btn)
    refs.fetch_new_btn.configure(state="disabled")
    ToolTip(refs.fetch_new_btn, "Scrape + dedup + auto-export (Ctrl+Shift+P).")

    refs.stop_btn = ctk.CTkButton(
        wrap, text="■ Stop", command=on_stop, width=80,
        fg_color="#a83232",
    )
    wrap.add(refs.stop_btn)
    refs.stop_btn.configure(state="disabled")
    ToolTip(refs.stop_btn, "Stop the current scrape.")

    refs.export_btn = ctk.CTkButton(
        wrap, text=_EXPORT_BASE_TEXT, command=on_export,
        width=130, fg_color="#2d7a2d",
    )
    wrap.add(refs.export_btn)
    refs.export_btn.configure(state="disabled")
    ToolTip(refs.export_btn,
            "Save scraped reviews as Markdown (Ctrl+E). Generates .md always; "
            "also CSV / JSON / per-language files when those checkboxes are on.")

    open_cache = ctk.CTkButton(
        wrap, text="📂 Open cache", command=on_open_cache, width=120,
    )
    wrap.add(open_cache)

    also_frame = ctk.CTkFrame(wrap, fg_color="transparent")
    ctk.CTkCheckBox(
        also_frame, text="📊 CSV", variable=csv_var,
        onvalue="1", offvalue="0", width=70,
    ).pack(side="left", padx=2, pady=4)
    ctk.CTkCheckBox(
        also_frame, text="🔧 JSON", variable=json_var,
        onvalue="1", offvalue="0", width=80,
    ).pack(side="left", padx=2, pady=4)
    ctk.CTkCheckBox(
        also_frame, text="🌐 Per-lang", variable=per_lang_var,
        onvalue="1", offvalue="0", width=90,
    ).pack(side="left", padx=2, pady=4)
    wrap.add(also_frame)

    split_entry = ctk.CTkEntry(
        wrap, textvariable=split_var, width=80,
        placeholder_text="Split N (0=off)",
    )
    wrap.add(split_entry)
    ToolTip(split_entry, "Split exports every N reviews (0 = no split).")

    for label, fn, w in (
        ("📊 Summary", actions.write_summary, 110),
        ("🔍 Search", actions.search_dump, 110),
        ("📦 Batch", actions.batch_dump, 110),
    ):
        btn = ctk.CTkButton(wrap, text=label, width=w, command=fn)
        wrap.add(btn)

    for label, fn, w in (
        ("🤖 Copy + AI prompt", actions.copy_with_ai_prompt, 170),
        ("💾 Save as prompt", actions.save_as_prompt, 140),
        ("🔴 Quick: negatives", actions.quick_view_negatives, 150),
        ("🔝 Top complaints", actions.top_complaints, 140),
        ("📂 Open latest .md", actions.open_latest_md, 150),
    ):
        btn = ctk.CTkButton(wrap, text=label, width=w, command=fn)
        wrap.add(btn)

    settings = ctk.CTkButton(
        wrap, text="⚙ Settings", width=110,
        command=actions.open_settings, fg_color="#444",
    )
    wrap.add(settings, side="right")

    # ---- Live button-text sync (Export <-> Generate all) ----------
    # Mirrors the API tab: when any of CSV / JSON / Per-lang is on,
    # the Export button text changes from "Export to .md" to
    # "Generate all" so the user knows they're getting more than the
    # .md. ``trace_add`` fires on the Tk event loop so this is
    # thread-safe.

    def _refresh_export_text(*_args: Any) -> None:
        btn = refs.export_btn
        if btn is None:
            return
        try:
            wants_extra = (
                csv_var.get() == "1"
                or json_var.get() == "1"
                or per_lang_var.get() == "1"
            )
            btn.configure(
                text=_EXPORT_GENERATE_ALL_TEXT
                if wants_extra else _EXPORT_BASE_TEXT,
            )
        except tk.TclError:
            # R29: widget teardown race. Same
            # pattern as ``_api_action_bar``
            # ``_refresh_export_text`` — the
            # ``csv_var`` / ``json_var`` /
            # ``per_lang_var`` StringVars and the
            # ``export_btn`` CTkButton can be
            # destroyed before the trace fires.
            # The previous version had NO
            # try/except. R29 wraps in
            # ``try: ... except tk.TclError: pass``
            # so only the actually-expected
            # teardown race is silently dropped.
            pass

    csv_var.trace_add("write", _refresh_export_text)
    json_var.trace_add("write", _refresh_export_text)
    per_lang_var.trace_add("write", _refresh_export_text)
    _refresh_export_text()

    return refs


__all__ = ["PwActionRefs", "build_pw_action_bar"]
