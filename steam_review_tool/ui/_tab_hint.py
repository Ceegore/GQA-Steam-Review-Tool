"""Tab-specific "When to use this tab" hint cards.

Each tab gets a small collapsible info card that explains *when* a user
should pick it (vs. the other tabs). The default state is collapsed —
it's a hint, not a daily-use widget, so we don't waste vertical real
estate on it.

Hint copy lives here (not in the controllers) so the wording stays
consistent across the app and is easy to tweak in one place.
"""
from __future__ import annotations

import customtkinter as ctk

from .collapsible_group import CollapsibleGroup
from .tooltip import ToolTip


# Hint copy. Plain text with explicit ``\\n`` because CTkLabel wraps
# embedded newlines correctly. Keep each bullet short — the card sits
# at the top of the tab and must not push everything else off-screen
# when expanded.
API_HINT = (
    "📌 When to use the Steam API tab:\n"
    "• FASTEST and CHEAPEST way to dump reviews — Steam's cached JSON\n"
    "  feed, usually with no cache-miss delay.\n"
    "• Best for ESTABLISHED games where Steam's review index is\n"
    "  already populated.\n"
    "• For NEW releases (last 24-72 h) where the cache is still empty,\n"
    "  switch to the Playwright tab — it bypasses the cache."
)

PLAYWRIGHT_HINT = (
    "📌 When to use the Playwright tab:\n"
    "• Launches a real headless Chromium browser and talks to Steam's\n"
    "  un-cached ajax endpoint, so it sees reviews the JSON API has\n"
    "  not yet indexed.\n"
    "• Best for NEW releases (last 24-72 h) where the JSON API\n"
    "  returns 0 reviews due to cache lag.\n"
    "• Slower than the API tab (one browser launch per scrape) — use\n"
    "  only when needed."
)

TRENDS_HINT = (
    "📌 When to use the Trends tab:\n"
    "• Each click of 'Refresh all' (or app startup) scrapes the\n"
    "  current wishlist / follower / review counts from the Steam\n"
    "  storefront and saves them to a local time-series DB.\n"
    "• Use 'View graph' to plot the recorded series for any tracked\n"
    "  app and spot popularity trends over time.\n"
    "• Use 'Per-language review count' to verify language coverage\n"
    "  for the currently loaded game."
)


def build_tab_hint(
    parent: ctk.CTkBaseClass,
    *,
    hint_text: str,
    expanded: bool = False,
    icon: str = "📌",
) -> CollapsibleGroup:
    """Build a collapsible 'When to use this tab' hint card.

    Returns the :class:`CollapsibleGroup` so the caller can tweak it
    (collapse / expand programmatically, etc.).
    """
    group = CollapsibleGroup(
        parent, "When to use this tab",
        expanded=expanded, icon=icon,
    )
    group.outer.pack(fill="x", padx=4, pady=(4, 2))

    lbl = ctk.CTkLabel(
        group.body,
        text=hint_text,
        anchor="w", justify="left",
        text_color=("#1f6aa5", "#5da9d6"),
        fg_color=("#eef5fb", "#1e2a35"),
        corner_radius=6,
    )
    lbl.pack(fill="x", padx=4, pady=4)

    ToolTip(
        lbl,
        "Click the header to collapse this hint when not needed.",
    )
    return group


__all__ = ["build_tab_hint", "API_HINT", "PLAYWRIGHT_HINT", "TRENDS_HINT"]
