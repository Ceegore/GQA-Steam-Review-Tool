"""Action-bar widget builder for the Steam API tab.

Extracted from ``tab_api.py`` to keep that file under the 500-line
hard limit. Builds the two horizontal button rows (primary + AI) and
returns a small ``ApiActionRefs`` namedtuple with the button handles
the controller needs to enable / disable / rewire.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

import customtkinter as ctk

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
    """Construct the two button rows. Returns refs to the key buttons."""
    sec_act = ctk.CTkFrame(parent, fg_color="transparent")
    sec_act.pack(fill="x", padx=8, pady=(4, 4))
    refs = ApiActionRefs()

    refs.fetch_btn = ctk.CTkButton(
        sec_act, text="Fetch Reviews", fg_color="#1f6aa5",
        command=on_fetch, width=140,
    )
    refs.fetch_btn.pack(side="left", padx=4, pady=4)
    ToolTip(refs.fetch_btn, "Start a paginated fetch (Ctrl+F).")

    refs.resume_btn = ctk.CTkButton(
        sec_act, text="▶ Resume", command=on_resume,
        width=110, fg_color="#2d7a2d",
    )
    refs.resume_btn.pack(side="left", padx=4, pady=4)
    refs.resume_btn.configure(state="disabled")
    ToolTip(refs.resume_btn, "Continue from the saved cursor.")

    refs.fetch_new_btn = ctk.CTkButton(
        sec_act, text="🆕 Fetch new", command=on_fetch_new,
        width=130, fg_color="#0f7a3a",
    )
    refs.fetch_new_btn.pack(side="left", padx=4, pady=4)
    refs.fetch_new_btn.configure(state="disabled")
    ToolTip(refs.fetch_new_btn, "Fetch + dedup + auto-export.")

    refs.stop_btn = ctk.CTkButton(
        sec_act, text="■ Stop", command=on_stop, width=80,
        fg_color="#a83232",
    )
    refs.stop_btn.pack(side="left", padx=4, pady=4)
    refs.stop_btn.configure(state="disabled")
    ToolTip(refs.stop_btn, "Stop the current fetch (Ctrl+S).")

    refs.watch_btn = ctk.CTkButton(
        sec_act, text="▶ Start Watching", command=on_watch_toggle,
        width=170, fg_color="#8a5a00",
    )
    refs.watch_btn.pack(side="left", padx=(20, 4), pady=4)
    refs.watch_btn.configure(state="disabled")
    ToolTip(refs.watch_btn, "Poll Steam for new reviews.")

    ctk.CTkCheckBox(
        sec_act, text="🔁 Auto-incr", variable=auto_incr_var,
        onvalue="1", offvalue="0", width=110,
    ).pack(side="left", padx=2)

    refs.export_btn = ctk.CTkButton(
        sec_act, text="Export to .md", command=on_export,
        width=130, fg_color="#2d7a2d",
    )
    refs.export_btn.pack(side="right", padx=4, pady=4)
    refs.export_btn.configure(state="disabled")
    ToolTip(refs.export_btn, "Save fetched reviews (Ctrl+E).")

    ctk.CTkButton(
        sec_act, text="Open store page", command=actions.open_store,
        width=130,
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
    ctk.CTkButton(
        sec_act, text="📊 Summary", width=110,
        command=actions.write_summary,
    ).pack(side="right", padx=4, pady=4)
    ctk.CTkButton(
        sec_act, text="🔍 Search", width=110,
        command=actions.search_dump,
    ).pack(side="right", padx=4, pady=4)
    ctk.CTkButton(
        sec_act, text="📦 Batch", width=110,
        command=actions.batch_dump,
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


__all__ = ["build_api_action_bar", "ApiActionRefs"]