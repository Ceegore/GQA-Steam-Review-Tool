"""Filter-section widget builder for the Playwright tab.

Extracted from ``tab_playwright.py`` to keep the controller file under
the 500-line hard limit. Builds the Game input row, the Dependencies
section (Playwright pkg / Chromium) and the Filter section.

The filter widgets are now laid out via :class:`ResponsiveGrid` so
they re-flow into 2-4 columns on wide windows and collapse to a
single column on narrow ones.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import customtkinter as ctk

from ..core.constants import STEAM_LANGUAGES
from ._responsive import ResponsiveGrid
from .collapsible_group import CollapsibleGroup
from .section_header import make_section
from .tooltip import ToolTip


@dataclass
class PwFilterRefs:
    """Public surface of the Playwright-tab filter widgets."""
    sort_var: ctk.StringVar
    max_var: ctk.StringVar
    lang_var: ctk.StringVar
    purchase_var: ctk.StringVar
    offtopic_var: ctk.StringVar
    playtime_min_entry: Optional[ctk.CTkEntry]


_PLAYTIME_ID = "__pw_playtime__"


def build_pw_game_section(
    parent: ctk.CTkBaseClass,
    *,
    on_load: Callable[[], None],
    on_pick_dump_root: Callable[[], None],
    on_open_dump_folder: Callable[[], None],
    initial_dump_label: str,
) -> dict:
    """Build the Game input row + dump-folder row.

    Returns a dict of widget refs the caller needs to wire up
    (game_label, dump_label, seen_label).
    """
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
    app_id_entry = ctk.CTkEntry(
        row, placeholder_text="e.g. 4311090 or store URL",
    )
    app_id_entry.pack(side="left", padx=4, fill="x", expand=True)
    app_id_entry.bind("<Return>", lambda _e: on_load())
    ToolTip(app_id_entry, "Steam App ID or any store / community URL.")
    ctk.CTkButton(
        row, text="Load Game  ⏎", command=on_load, width=120,
    ).pack(side="left", padx=4)

    det = ctk.CTkFrame(sec, fg_color="transparent")
    det.pack(fill="x", padx=8, pady=(0, 4))
    ctk.CTkLabel(det, text="Current game:", width=130, anchor="e").pack(
        side="left", padx=(0, 6),
    )
    game_label = ctk.CTkLabel(
        det, text="(load a game above or in the Steam API tab)",
        anchor="w", text_color="gray",
    )
    game_label.pack(side="left", padx=4, fill="x", expand=True)

    df_row = ctk.CTkFrame(sec, fg_color="transparent")
    df_row.pack(fill="x", padx=8, pady=(2, 4))
    dump_label = ctk.CTkLabel(
        df_row, text=initial_dump_label, anchor="w", text_color="gray",
    )
    dump_label.pack(side="left", padx=4, fill="x", expand=True)
    seen_label = ctk.CTkLabel(
        df_row, text="Already exported: 0 reviews", anchor="e",
        text_color="gray",
    )
    seen_label.pack(side="right", padx=4)
    ctk.CTkButton(
        df_row, text="📁 Set…", width=80, height=24,
        command=on_pick_dump_root,
    ).pack(side="right", padx=2)
    ctk.CTkButton(
        df_row, text="📂 Open", width=80, height=24,
        command=on_open_dump_folder,
    ).pack(side="right", padx=2)

    return {
        "app_id_entry": app_id_entry,
        "game_label": game_label,
        "dump_label": dump_label,
        "seen_label": seen_label,
    }


def build_pw_dependencies_section(
    parent: ctk.CTkBaseClass,
    *,
    on_install_pkg: Callable[[], None],
    on_install_chrome: Callable[[], None],
    on_open_cache: Callable[[], None],
) -> dict:
    """Build the Playwright / Chromium dependency status section."""
    sec_dep = ctk.CTkFrame(parent)
    sec_dep.pack(fill="x", padx=8, pady=(4, 2))
    ctk.CTkLabel(
        sec_dep, text="Dependencies", font=("", 13, "bold"),
    ).pack(anchor="w", padx=8, pady=(4, 2))
    dgrid = ctk.CTkFrame(sec_dep, fg_color="transparent")
    dgrid.pack(fill="x", padx=8, pady=(0, 4))
    ctk.CTkLabel(dgrid, text="playwright pkg:", width=140, anchor="e").grid(
        row=0, column=0, sticky="e", padx=(10, 4), pady=5,
    )
    pkg_status = ctk.CTkLabel(
        dgrid, text="checking…", anchor="w", text_color="gray",
    )
    pkg_status.grid(row=0, column=1, sticky="w", padx=4, pady=5)
    ctk.CTkButton(
        dgrid, text="Install", command=on_install_pkg, width=100,
    ).grid(row=0, column=2, padx=4, pady=5)
    ctk.CTkButton(
        dgrid, text="Open cache", command=on_open_cache, width=120,
    ).grid(row=0, column=3, padx=4, pady=5)

    ctk.CTkLabel(
        dgrid, text="chromium:", width=140, anchor="e",
    ).grid(row=1, column=0, sticky="e", padx=(10, 4), pady=5)
    chrome_status = ctk.CTkLabel(
        dgrid, text="—", anchor="w", text_color="gray",
    )
    chrome_status.grid(row=1, column=1, sticky="w", padx=4, pady=5)
    ctk.CTkButton(
        dgrid, text="Install", command=on_install_chrome, width=100,
    ).grid(row=1, column=2, padx=4, pady=5)

    return {"pkg_status": pkg_status, "chrome_status": chrome_status}


def build_pw_filters_section(
    parent: ctk.CTkBaseClass,
    *,
    on_reset: Callable[[], None],
) -> tuple[PwFilterRefs, ctk.CTkButton]:
    """Build the filter section for the Playwright tab.

    Returns ``(refs, reset_btn)``.
    """
    refs = PwFilterRefs(
        sort_var=ctk.StringVar(value="recent"),
        max_var=ctk.StringVar(value="100"),
        lang_var=ctk.StringVar(value="all"),
        purchase_var=ctk.StringVar(value="all"),
        offtopic_var=ctk.StringVar(value="false"),
        playtime_min_entry=None,  # filled by _capture_playtime
    )

    # ---- Section header + reset button ------------------------------
    reset_btn = ctk.CTkButton(
        parent, text="Reset filters", width=110, height=26,
        command=on_reset, fg_color="#444",
    )
    ToolTip(reset_btn, "Reset all filters in this section to defaults.")
    sec_filt_body = make_section(parent, "Filters", right_widget=reset_btn)

    # ---- Collapsible filter-options group ---------------------------
    filt_group = CollapsibleGroup(
        sec_filt_body, "Filter options", expanded=True, icon="🔍",
    )
    filt_group.outer.pack(fill="x", padx=2, pady=(2, 2))
    fbody = filt_group.body

    # ---- Responsive grid --------------------------------------------
    grid = ResponsiveGrid(fbody, min_col_width=280, label_width=130)
    grid.add_row(
        "Sort by:", lambda p: ctk.CTkOptionMenu(
            p, values=["recent", "helpful", "positive", "negative"],
            variable=refs.sort_var, width=140,
        ),
        tip="recent / helpful / positive / negative",
    )
    grid.add_row(
        "Max reviews:", lambda p: ctk.CTkOptionMenu(
            p, values=["20", "50", "100", "200", "500"],
            variable=refs.max_var, width=140,
        ),
        tip="Hard cap on how many to scrape.",
    )
    grid.add_row(
        "Language:", lambda p: ctk.CTkOptionMenu(
            p, values=STEAM_LANGUAGES, variable=refs.lang_var, width=180,
        ),
        tip="'all' returns all of them.",
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
        lambda p: _make_pw_entry(p, refs),
        tip="Lower bound on reviewer playtime.",
    )
    grid.add_row(
        "Include off-topic:", lambda p: ctk.CTkOptionMenu(
            p, values=["false", "true"],
            variable=refs.offtopic_var, width=140,
        ),
        tip="false = filter out off-topic reviews.",
    )

    def _capture_playtime() -> None:
        for col in grid._col_frames:  # noqa: SLF001
            for row in col.winfo_children():
                for w in row.winfo_children():
                    if getattr(w, "_tag", None) == _PLAYTIME_ID:
                        refs.playtime_min_entry = w

    grid.on_reflow(_capture_playtime)
    grid.build()

    return refs, reset_btn


def _make_pw_entry(parent: ctk.CTkFrame, refs: PwFilterRefs) -> ctk.CTkEntry:
    """Build the Playwright playtime entry and tag it for reflow lookup."""
    entry = ctk.CTkEntry(parent, width=160, placeholder_text="blank = none")
    setattr(entry, "_tag", _PLAYTIME_ID)
    return entry


__all__ = [
    "PwFilterRefs",
    "build_pw_filters_section",
    "build_pw_game_section",
    "build_pw_dependencies_section",
]
