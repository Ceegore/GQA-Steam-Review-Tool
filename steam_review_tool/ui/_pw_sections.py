"""Filter-section widget builder for the Playwright tab.

Extracted from ``tab_playwright.py`` to keep the controller file under
the 500-line hard limit. Returns a ``PwFilterRefs`` dataclass with the
StringVars + entries the controller needs to read.
"""
from __future__ import annotations

from dataclasses import dataclass

import customtkinter as ctk

from ..core.constants import STEAM_LANGUAGES
from .collapsible_group import CollapsibleGroup
from .tooltip import ToolTip


@dataclass
class PwFilterRefs:
    """Public surface of the Playwright-tab filter widgets."""
    sort_var: ctk.StringVar
    max_var: ctk.StringVar
    lang_var: ctk.StringVar
    purchase_var: ctk.StringVar
    offtopic_var: ctk.StringVar
    playtime_min_entry: ctk.CTkEntry


def build_pw_filters_section(parent: ctk.CTkBaseClass) -> PwFilterRefs:
    """Build the 3 filter rows shared between Steam API and PW tabs."""
    sec_filt = ctk.CTkFrame(parent)
    sec_filt.pack(fill="x", padx=8, pady=(4, 4))
    ctk.CTkLabel(
        sec_filt, text="Filters", font=("", 12, "bold"),
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

    refs = PwFilterRefs(
        sort_var=ctk.StringVar(value="recent"),
        max_var=ctk.StringVar(value="100"),
        lang_var=ctk.StringVar(value="all"),
        purchase_var=ctk.StringVar(value="all"),
        offtopic_var=ctk.StringVar(value="false"),
        playtime_min_entry=ctk.CTkEntry(
            parent, width=140, placeholder_text="blank = none",
        ),
    )

    r0 = _row()
    _label(r0, "Sort by:", tip="recent / helpful / positive / negative")
    _widget(r0, ctk.CTkOptionMenu(
        r0, values=["recent", "helpful", "positive", "negative"],
        variable=refs.sort_var, width=140,
    ))
    _label(r0, "Max reviews:", tip="Hard cap on how many to scrape.")
    _widget(r0, ctk.CTkOptionMenu(
        r0, values=["20", "50", "100", "200", "500"],
        variable=refs.max_var, width=140,
    ))

    r1 = _row()
    _label(r1, "Language:", tip="'all' returns all of them.")
    _widget(r1, ctk.CTkOptionMenu(
        r1, values=STEAM_LANGUAGES, variable=refs.lang_var, width=240,
    ))

    r2 = _row()
    _label(r2, "Purchase type:", tip="all / steam / non_steam")
    _widget(r2, ctk.CTkOptionMenu(
        r2, values=["all", "steam", "non_steam"],
        variable=refs.purchase_var, width=140,
    ))
    _label(r2, "Min playtime (hrs):", tip="Lower bound on reviewer playtime.")
    refs.playtime_min_entry = _widget(r2, refs.playtime_min_entry)

    r3 = _row()
    _label(r3, "Include off-topic:", tip="false = filter out off-topic reviews.")
    _widget(r3, ctk.CTkOptionMenu(
        r3, values=["false", "true"],
        variable=refs.offtopic_var, width=140,
    ))
    return refs


__all__ = ["PwFilterRefs", "build_pw_filters_section"]