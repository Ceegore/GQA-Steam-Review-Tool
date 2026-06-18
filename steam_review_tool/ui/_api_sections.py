"""Filter + game-section widget builders for the Steam API tab.

Extracted from ``tab_api.py`` to keep the controller file under the
500-line hard limit. Builds the verbose CustomTkinter widget grids
and returns a small ``ApiFilterRefs`` namedtuple with the widget
handles the controller needs (entries, StringVars, etc.).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

import customtkinter as ctk

from ..core.constants import REVIEW_FILTERS, REVIEW_TYPES, STEAM_LANGUAGES
from .collapsible_group import CollapsibleGroup
from .tooltip import ToolTip


@dataclass
class ApiFilterRefs:
    """Public surface of the API-tab filter widgets."""
    lang_var: ctk.StringVar
    filter_var: ctk.StringVar
    type_var: ctk.StringVar
    purchase_var: ctk.StringVar
    offtopic_var: ctk.StringVar
    perpage_var: ctk.StringVar
    interval_var: ctk.StringVar
    first_24h_var: ctk.StringVar
    backend_var: ctk.StringVar
    playtime_min_entry: ctk.CTkEntry
    helpful_entry: ctk.CTkEntry
    apify_entry: ctk.CTkEntry


@dataclass
class ApiGameRefs:
    """Public surface of the API-tab game / dump-folder widgets."""
    app_id_entry: ctk.CTkEntry
    dump_label: ctk.CTkLabel
    seen_label: ctk.CTkLabel
    obsidian_label: ctk.CTkLabel


def build_api_game_section(
    parent: ctk.CTkBaseClass,
    *,
    on_load: Callable[[], None],
    on_pick_dump_root: Callable[[], None],
    on_open_dump_folder: Callable[[], None],
    on_pick_obsidian: Callable[[], None],
    on_clear_obsidian: Callable[[], None],
    initial_dump_label: str,
) -> ApiGameRefs:
    """Build the Game input + Dump-folder collapsible group."""
    sec = ctk.CTkFrame(parent)
    sec.pack(fill="x", padx=8, pady=(8, 4))
    ctk.CTkLabel(sec, text="Game", font=("", 13, "bold")).pack(
        anchor="w", padx=8, pady=(6, 2),
    )
    row = ctk.CTkFrame(sec, fg_color="transparent")
    row.pack(fill="x", padx=8, pady=(0, 6))
    ctk.CTkLabel(
        row, text="App ID / store URL:", width=140, anchor="w",
    ).pack(side="left", padx=(4, 6))
    entry = ctk.CTkEntry(
        row, placeholder_text="e.g. 4311090 or store URL",
    )
    entry.pack(side="left", padx=4, fill="x", expand=True)
    def _trigger_load(_e: object = None) -> None:
        on_load()
    entry.bind("<Return>", _trigger_load)
    ToolTip(entry, "Steam App ID or any store / community URL.")
    ctk.CTkButton(
        row, text="Load Game  ⏎", command=on_load, width=120,
    ).pack(side="left", padx=4)

    df_group = CollapsibleGroup(
        sec, "Dump folder & Vault", expanded=False, icon="📂",
    )
    df_group.outer.pack(fill="x", padx=4, pady=(2, 4))
    df_inner = ctk.CTkFrame(df_group.body, fg_color="transparent")
    df_inner.pack(fill="x", padx=4, pady=2)
    dump_label = ctk.CTkLabel(
        df_inner, text=initial_dump_label, anchor="w", text_color="gray",
    )
    dump_label.pack(side="left", padx=4, fill="x", expand=True)
    seen_label = ctk.CTkLabel(
        df_inner, text="Already exported: 0 reviews", anchor="e",
        text_color="gray",
    )
    seen_label.pack(side="right", padx=4)
    ctk.CTkButton(
        df_inner, text="📁 Set…", width=80, height=24,
        command=on_pick_dump_root,
    ).pack(side="right", padx=2)
    ctk.CTkButton(
        df_inner, text="📂 Open", width=80, height=24,
        command=on_open_dump_folder,
    ).pack(side="right", padx=2)
    vault_row = ctk.CTkFrame(df_group.body, fg_color="transparent")
    vault_row.pack(fill="x", padx=4, pady=2)
    ctk.CTkLabel(vault_row, text="📓 Vault:", width=80, anchor="e").pack(
        side="left", padx=(0, 4),
    )
    obsidian_label = ctk.CTkLabel(
        vault_row, text="(not set)", anchor="w", text_color="gray",
    )
    obsidian_label.pack(side="left", padx=4, fill="x", expand=True)
    ctk.CTkButton(
        vault_row, text="📓 Set…", width=80, height=24,
        command=on_pick_obsidian,
    ).pack(side="right", padx=2)
    ctk.CTkButton(
        vault_row, text="🧹 Clear", width=70, height=24,
        command=on_clear_obsidian,
    ).pack(side="right", padx=2)
    return ApiGameRefs(
        app_id_entry=entry, dump_label=dump_label, seen_label=seen_label,
        obsidian_label=obsidian_label,
    )


def build_api_filters_section(parent: ctk.CTkBaseClass) -> ApiFilterRefs:
    """Build the 6 filter rows + the Apify-token backend row."""
    sec_filt = ctk.CTkFrame(parent)
    sec_filt.pack(fill="x", padx=8, pady=(4, 4))
    ctk.CTkLabel(
        sec_filt, text="Filters", font=("", 13, "bold"),
    ).pack(anchor="w", padx=8, pady=(6, 2))
    filt_group = CollapsibleGroup(
        sec_filt, "Filter options", expanded=True, icon="🔍",
    )
    filt_group.outer.pack(fill="x", padx=2, pady=(2, 2))
    fbody = filt_group.body

    def _row() -> ctk.CTkFrame:
        r = ctk.CTkFrame(fbody, fg_color="transparent")
        r.pack(fill="x", padx=4, pady=2)
        return r

    def _label(parent_: ctk.CTkFrame, text: str, tip: str = "") -> None:
        l = ctk.CTkLabel(parent_, text=text, anchor="e", width=130)
        l.pack(side="left", padx=(10, 4), pady=5)
        if tip:
            ToolTip(l, tip)

    def _widget(parent_: ctk.CTkFrame, widget: ctk.CTkBaseClass,
                tip: str = "") -> ctk.CTkBaseClass:
        widget.pack(side="left", padx=4, pady=5)
        if tip:
            ToolTip(widget, tip)
        return widget

    refs = ApiFilterRefs(
        lang_var=ctk.StringVar(value="all"),
        filter_var=ctk.StringVar(value="recent"),
        type_var=ctk.StringVar(value="all"),
        purchase_var=ctk.StringVar(value="all"),
        offtopic_var=ctk.StringVar(value="false"),
        perpage_var=ctk.StringVar(value="100"),
        interval_var=ctk.StringVar(value="5"),
        first_24h_var=ctk.StringVar(value="all"),
        backend_var=ctk.StringVar(value="Steam API"),
        playtime_min_entry=ctk.CTkEntry(
            parent, width=140, placeholder_text="blank = none",
        ),
        helpful_entry=ctk.CTkEntry(
            parent, width=140, placeholder_text="0",
        ),
        apify_entry=ctk.CTkEntry(
            parent, width=300, placeholder_text="apify_api_xxx…",
        ),
    )

    r0 = _row()
    _label(r0, "Language:", tip="'all' returns every available language.")
    _widget(r0, ctk.CTkOptionMenu(
        r0, values=STEAM_LANGUAGES, variable=refs.lang_var, width=240,
    ), tip="Pick a language code or 'all'.")
    r1 = _row()
    _label(r1, "Sort by:", tip="recent / updated / all")
    _widget(r1, ctk.CTkOptionMenu(
        r1, values=REVIEW_FILTERS, variable=refs.filter_var, width=140,
    ))
    _label(r1, "Sentiment:")
    _widget(r1, ctk.CTkOptionMenu(
        r1, values=REVIEW_TYPES, variable=refs.type_var, width=140,
    ))
    r2 = _row()
    _label(r2, "Purchase type:", tip="all / steam / non_steam")
    _widget(r2, ctk.CTkOptionMenu(
        r2, values=["all", "steam", "non_steam"],
        variable=refs.purchase_var, width=140,
    ))
    _label(r2, "Min playtime (hrs):", tip="Blank = no limit.")
    refs.playtime_min_entry = _widget(r2, refs.playtime_min_entry)
    r3 = _row()
    _label(r3, "Min helpful votes:", tip="Quality threshold.")
    refs.helpful_entry = _widget(r3, refs.helpful_entry)
    _label(r3, "Include off-topic:", tip="false = hide memes/test/etc.")
    _widget(r3, ctk.CTkOptionMenu(
        r3, values=["false", "true"],
        variable=refs.offtopic_var, width=140,
    ))
    r4 = _row()
    _label(r4, "Reviews per page:", tip="Steam caps this at 100.")
    _widget(r4, ctk.CTkOptionMenu(
        r4, values=["20", "50", "100"], variable=refs.perpage_var, width=140,
    ))
    _label(r4, "Watch interval (min):", tip="Polling cadence.")
    _widget(r4, ctk.CTkOptionMenu(
        r4, values=["1", "2", "5", "10", "15", "30", "60"],
        variable=refs.interval_var, width=140,
    ))
    r5 = _row()
    _label(r5, "Window:", tip="all | first 24h | last 7d")
    _widget(r5, ctk.CTkOptionMenu(
        r5, values=["all", "first 24h", "last 7d"],
        variable=refs.first_24h_var, width=140,
    ))

    # Backend override row
    sec_be = ctk.CTkFrame(parent)
    sec_be.pack(fill="x", padx=8, pady=(4, 4))
    ctk.CTkLabel(
        sec_be, text="Backend (optional override)",
        font=("", 13, "bold"),
    ).pack(anchor="w", padx=8, pady=(6, 2))
    brow = ctk.CTkFrame(sec_be, fg_color="transparent")
    brow.pack(fill="x", padx=8, pady=(2, 6))
    ctk.CTkLabel(brow, text="Engine:", width=130, anchor="e").pack(
        side="left", padx=(10, 4),
    )
    ctk.CTkOptionMenu(
        brow, values=["Steam API", "Apify (bypasses cache)"],
        variable=refs.backend_var, width=220,
    ).pack(side="left", padx=4)
    ctk.CTkLabel(brow, text="Apify token:", width=90, anchor="e").pack(
        side="left", padx=(20, 4),
    )
    refs.apify_entry.pack(side="left", padx=4, fill="x", expand=True)
    return refs


__all__ = [
    "ApiFilterRefs", "ApiGameRefs",
    "build_api_filters_section", "build_api_game_section",
]