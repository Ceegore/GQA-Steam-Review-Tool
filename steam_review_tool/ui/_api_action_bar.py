"""Action-bar widget builder for the Steam API tab.

Extracted from ``tab_api.py`` to keep that file under the 500-line
hard limit. Builds the action-bar buttons inside a
:class:`WrapFrame` so the bar **wraps to a new row** when the
current window is too narrow for all buttons — no element ever
runs off the visible tab area.

Returned are the key button handles (:class:`ApiActionRefs`) so the
controller can enable / disable / rewire them in response to bus
events (fetch started, completed, failed, ...).
"""
from __future__ import annotations

from typing import Any, Callable, Optional

import customtkinter as ctk

from ._responsive import WrapFrame
from .tooltip import ToolTip


class ApiActionRefs:
    """Handles returned by :func:`build_api_action_bar`."""

    def __init__(self) -> None:
        self.fetch_btn: Optional[ctk.CTkButton] = None
        self.resume_btn: Optional[ctk.CTkButton] = None
        self.fetch_new_btn: Optional[ctk.CTkButton] = None
        self.stop_btn: Optional[ctk.CTkButton] = None
        self.watch_btn: Optional[ctk.CTkButton] = None
        self.export_btn: Optional[ctk.CTkButton] = None


def build_api_action_bar(
    parent: ctk.CTkBaseClass,
    *,
    actions: Any,                          # TabActions instance
    on_fetch: Callable[[], None],
    on_resume: Callable[[], None],
    on_fetch_new: Callable[[], None],
    on_stop: Callable[[], None],
    on_watch_toggle: Callable[[], None],
    on_export: Callable[[], None],
    csv_var: ctk.StringVar,
    json_var: ctk.StringVar,
    per_lang_var: ctk.StringVar,
    auto_incr_var: ctk.StringVar,
    split_var: ctk.StringVar,
) -> ApiActionRefs:
    """Construct the action bar with auto-wrapping rows.

    Every button is registered with a :class:`WrapFrame` that
    reflows on resize. When the tab is narrow, right-most buttons
    wrap to a new row automatically — nothing falls off-screen.
    """
    sec_act = ctk.CTkFrame(parent, fg_color="transparent")
    sec_act.pack(fill="x", padx=8, pady=(4, 4))
    wrap = WrapFrame(sec_act, padx=4, pady=4, row_gap=2)
    wrap.pack(fill="x")
    refs = ApiActionRefs()

    # ---- Primary fetch / stop row ------------------------------------
    refs.fetch_btn = ctk.CTkButton(
        wrap, text="Fetch Reviews", fg_color="#1f6aa5",
        command=on_fetch, width=140,
    )
    wrap.add(refs.fetch_btn)
    ToolTip(refs.fetch_btn, "Start a paginated fetch (Ctrl+F).")

    refs.resume_btn = ctk.CTkButton(
        wrap, text="▶ Resume", command=on_resume,
        width=110, fg_color="#2d7a2d",
    )
    wrap.add(refs.resume_btn)
    refs.resume_btn.configure(state="disabled")
    ToolTip(refs.resume_btn, "Continue from the saved cursor.")

    refs.fetch_new_btn = ctk.CTkButton(
        wrap, text="🆕 Fetch new", command=on_fetch_new,
        width=130, fg_color="#0f7a3a",
    )
    wrap.add(refs.fetch_new_btn)
    refs.fetch_new_btn.configure(state="disabled")
    ToolTip(refs.fetch_new_btn, "Fetch + dedup + auto-export.")

    refs.stop_btn = ctk.CTkButton(
        wrap, text="■ Stop", command=on_stop, width=80,
        fg_color="#a83232",
    )
    wrap.add(refs.stop_btn)
    refs.stop_btn.configure(state="disabled")
    ToolTip(refs.stop_btn, "Stop the current fetch (Ctrl+S).")

    refs.watch_btn = ctk.CTkButton(
        wrap, text="▶ Start Watching", command=on_watch_toggle,
        width=170, fg_color="#8a5a00",
    )
    wrap.add(refs.watch_btn)
    refs.watch_btn.configure(state="disabled")
    ToolTip(refs.watch_btn, "Poll Steam for new reviews.")

    auto_incr = ctk.CTkCheckBox(
        wrap, text="🔁 Auto-incr", variable=auto_incr_var,
        onvalue="1", offvalue="0", width=110,
    )
    wrap.add(auto_incr)

    # ---- Also-export checkboxes + split ------------------------------
    also_frame = ctk.CTkFrame(wrap, fg_color="transparent")
    csv_cb = ctk.CTkCheckBox(
        also_frame, text="📊 CSV", variable=csv_var,
        onvalue="1", offvalue="0", width=70,
    )
    csv_cb.pack(side="left", padx=2, pady=4)
    json_cb = ctk.CTkCheckBox(
        also_frame, text="🔧 JSON", variable=json_var,
        onvalue="1", offvalue="0", width=80,
    )
    json_cb.pack(side="left", padx=2, pady=4)
    per_lang_cb = ctk.CTkCheckBox(
        also_frame, text="🌐 Per-lang", variable=per_lang_var,
        onvalue="1", offvalue="0", width=90,
    )
    per_lang_cb.pack(side="left", padx=2, pady=4)
    wrap.add(also_frame)

    split_entry = ctk.CTkEntry(
        wrap, textvariable=split_var, width=80,
        placeholder_text="Split N (0=off)",
    )
    wrap.add(split_entry)
    ToolTip(split_entry, "Split exports every N reviews (0 = no split).")

    # ---- Output + analytics row --------------------------------------
    refs.export_btn = ctk.CTkButton(
        wrap, text="Export to .md", command=on_export,
        width=130, fg_color="#2d7a2d",
    )
    wrap.add(refs.export_btn)
    refs.export_btn.configure(state="disabled")
    ToolTip(refs.export_btn, "Save fetched reviews (Ctrl+E).")

    open_store = ctk.CTkButton(
        wrap, text="Open store page", command=actions.open_store, width=140,
    )
    wrap.add(open_store)

    summary = ctk.CTkButton(
        wrap, text="📊 Summary", width=110, command=actions.write_summary,
    )
    wrap.add(summary)

    search = ctk.CTkButton(
        wrap, text="🔍 Search", width=110, command=actions.search_dump,
    )
    wrap.add(search)

    batch = ctk.CTkButton(
        wrap, text="📦 Batch", width=110, command=actions.batch_dump,
    )
    wrap.add(batch)

    # ---- AI / analytics row (right-pinned Settings) -----------------
    copy_ai = ctk.CTkButton(
        wrap, text="🤖 Copy + AI prompt",
        width=170, command=actions.copy_with_ai_prompt,
    )
    wrap.add(copy_ai)

    save_prompt = ctk.CTkButton(
        wrap, text="💾 Save as prompt",
        width=140, command=actions.save_as_prompt,
    )
    wrap.add(save_prompt)

    quick_neg = ctk.CTkButton(
        wrap, text="🔴 Quick: negatives",
        width=150, command=actions.quick_view_negatives,
    )
    wrap.add(quick_neg)

    top_complaints = ctk.CTkButton(
        wrap, text="🔝 Top complaints",
        width=140, command=actions.top_complaints,
    )
    wrap.add(top_complaints)

    open_latest = ctk.CTkButton(
        wrap, text="📂 Open latest .md",
        width=150, command=actions.open_latest_md,
    )
    wrap.add(open_latest)

    settings = ctk.CTkButton(
        wrap, text="⚙ Settings", width=110,
        command=actions.open_settings, fg_color="#444",
    )
    # Right-pinned: appears on the right of the last row.
    wrap.add(settings, side="right")

    return refs


__all__ = ["build_api_action_bar", "ApiActionRefs"]
