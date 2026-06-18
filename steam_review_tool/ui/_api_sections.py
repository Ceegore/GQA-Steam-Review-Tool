"""Filter + game-section widget builders for the Steam API tab.

Extracted from ``tab_api.py`` to keep the controller file under the
500-line hard limit. Builds:

* the Game input + collapsible Dump-folder/Vault row
* the Filter section (now using :class:`ResponsiveGrid` so the
  filter widgets flow into 2-4 columns on wide windows and collapse
  to a single column on narrow ones)
* the Backend override row

The "Reset filters" button that sits in the Filters header is
returned separately so the controller can wire it to its
``_reset_filters`` handler.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

import customtkinter as ctk

from ..core.constants import REVIEW_FILTERS, REVIEW_TYPES, STEAM_LANGUAGES
from ._responsive import ResponsiveGrid
from .collapsible_group import CollapsibleGroup
from .section_header import make_section
from .tooltip import ToolTip


# Stable identifiers used by the grid reflow callback to locate the
# text-entry widgets after each layout pass. The factory closures
# tag each entry with one of these so ``_capture_entries`` can put
# the right handle on the right ``ApiFilterRefs`` slot.
_PLAYTIME_ID = "__playtime__"
_HELPFUL_ID = "__helpful__"
_APIFY_ID = "__apify__"


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
    playtime_min_entry: Optional[ctk.CTkEntry]
    helpful_entry: Optional[ctk.CTkEntry]
    apify_entry: Optional[ctk.CTkEntry]


@dataclass
class ApiGameRefs:
    """Public surface of the API-tab game / dump-folder widgets."""
    app_id_entry: ctk.CTkEntry
    dump_label: ctk.CTkLabel
    seen_label: ctk.CTkLabel
    obsidian_label: ctk.CTkLabel


def _make_entry(parent: ctk.CTkFrame, *, width: int,
                placeholder: str, tag_id: str) -> ctk.CTkEntry:
    """Build a CTkEntry and tag it with ``tag_id`` via ``._tag`` so
    the reflow callback can find it again after every re-flow."""
    entry = ctk.CTkEntry(parent, width=width, placeholder_text=placeholder)
    setattr(entry, "_tag", tag_id)
    return entry


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
    sec.pack(fill="x", padx=8, pady=(4, 2))
    ctk.CTkLabel(sec, text="Game", font=("", 13, "bold")).pack(
        anchor="w", padx=8, pady=(4, 2),
    )
    row = ctk.CTkFrame(sec, fg_color="transparent")
    row.pack(fill="x", padx=8, pady=(0, 4))
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
    df_group.outer.pack(fill="x", padx=4, pady=(2, 2))
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


def build_api_filters_section(
    parent: ctk.CTkBaseClass,
    *,
    on_reset: Callable[[], None],
) -> tuple[ApiFilterRefs, ctk.CTkButton]:
    """Build the filter section + the Apify-token backend row.

    Returns ``(refs, reset_btn)`` where ``refs`` is the
    :class:`ApiFilterRefs` and ``reset_btn`` is the "Reset filters"
    button (already wired to ``on_reset``).
    """
    # StringVars (state lives outside the widget tree, so it survives
    # every re-flow of the ResponsiveGrid).
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
        playtime_min_entry=None,  # set by _capture_entries
        helpful_entry=None,
        apify_entry=None,
    )

    # Filters section header + reset button.
    reset_btn = ctk.CTkButton(
        parent, text="Reset filters", width=110, height=26,
        command=on_reset, fg_color="#444",
    )
    ToolTip(reset_btn, "Reset all filters in this section to defaults.")
    sec_filt_body = make_section(
        parent, "Filters", right_widget=reset_btn,
    )

    # Collapsible filter-options group.
    filt_group = CollapsibleGroup(
        sec_filt_body, "Filter options", expanded=True, icon="🔍",
    )
    filt_group.outer.pack(fill="x", padx=2, pady=(2, 2))
    fbody = filt_group.body

    # Responsive grid: N columns based on container width.
    grid = ResponsiveGrid(fbody, min_col_width=280, label_width=120)
    grid.add_row(
        "Language:", lambda p: ctk.CTkOptionMenu(
            p, values=STEAM_LANGUAGES, variable=refs.lang_var, width=180,
        ),
        tip="'all' returns every available language.",
    )
    grid.add_row(
        "Sort by:", lambda p: ctk.CTkOptionMenu(
            p, values=REVIEW_FILTERS, variable=refs.filter_var, width=140,
        ),
        tip="recent / updated / all",
    )
    grid.add_row(
        "Sentiment:", lambda p: ctk.CTkOptionMenu(
            p, values=REVIEW_TYPES, variable=refs.type_var, width=140,
        ),
        tip="all / positive / negative",
    )
    grid.add_row(
        "Purchase type:", lambda p: ctk.CTkOptionMenu(
            p, values=["all", "steam", "non_steam"],
            variable=refs.purchase_var, width=140,
        ),
        tip="all / steam / non_steam",
    )
    grid.add_row(
        "Min playtime (hrs):",
        lambda p: _make_entry(p, width=160,
                              placeholder="blank = none",
                              tag_id=_PLAYTIME_ID),
        tip="Blank = no limit.",
    )
    grid.add_row(
        "Min helpful votes:",
        lambda p: _make_entry(p, width=160, placeholder="0",
                              tag_id=_HELPFUL_ID),
        tip="Quality threshold.",
    )
    grid.add_row(
        "Include off-topic:", lambda p: ctk.CTkOptionMenu(
            p, values=["false", "true"], variable=refs.offtopic_var, width=140,
        ),
        tip="false = hide memes/test/etc.",
    )
    grid.add_row(
        "Reviews per page:", lambda p: ctk.CTkOptionMenu(
            p, values=["20", "50", "100"], variable=refs.perpage_var, width=140,
        ),
        tip="Steam caps this at 100.",
    )
    grid.add_row(
        "Watch interval (min):", lambda p: ctk.CTkOptionMenu(
            p, values=["1", "2", "5", "10", "15", "30", "60"],
            variable=refs.interval_var, width=140,
        ),
        tip="Polling cadence.",
    )
    grid.add_row(
        "Window:", lambda p: ctk.CTkOptionMenu(
            p, values=["all", "first 24h", "last 7d"],
            variable=refs.first_24h_var, width=140,
        ),
        tip="all | first 24h | last 7d",
    )
    def _capture_entries() -> None:
        """Walk the freshly-built grid and assign entries by their tag."""
        for col in grid._col_frames:  # noqa: SLF001 - internal OK
            for row in col.winfo_children():
                for w in row.winfo_children():
                    tag = getattr(w, "_tag", None)
                    if tag == _PLAYTIME_ID:
                        refs.playtime_min_entry = w
                    elif tag == _HELPFUL_ID:
                        refs.helpful_entry = w

    grid.on_reflow(_capture_entries)
    grid.build()

    # Backend override row.
    sec_be = make_section(parent, "Backend (optional override)")
    brow = ctk.CTkFrame(sec_be, fg_color="transparent")
    brow.pack(fill="x", padx=4, pady=2)
    ctk.CTkLabel(brow, text="Engine:", width=120, anchor="e").pack(
        side="left", padx=(4, 4),
    )
    ctk.CTkOptionMenu(
        brow, values=["Steam API", "Apify (bypasses cache)"],
        variable=refs.backend_var, width=220,
    ).pack(side="left", padx=4)
    ctk.CTkLabel(brow, text="Apify token:", width=90, anchor="e").pack(
        side="left", padx=(20, 4),
    )
    apify_entry = _make_entry(
        brow, width=300, placeholder="apify_api_xxx…",
        tag_id=_APIFY_ID,
    )
    apify_entry.pack(side="left", padx=4, fill="x", expand=True)
    refs.apify_entry = apify_entry

    return refs, reset_btn


__all__ = [
    "ApiFilterRefs", "ApiGameRefs",
    "build_api_filters_section", "build_api_game_section",
]
