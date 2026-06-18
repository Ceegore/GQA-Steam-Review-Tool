"""Right-hand "info panel" widget shown next to each tab.

Shows the loaded game's metadata + a live "now in Berlin" clock. The
``update`` method is called whenever a new game is loaded; the clock
is updated via a separate ``tick_clock`` callback (every second).
"""
from __future__ import annotations

from typing import Optional, Any

import customtkinter as ctk

from ..core.timezone import current_berlin_str


class InfoPanel(ctk.CTkFrame):
    """A side panel showing loaded-game info and a clock."""

    def __init__(self, master) -> None:
        super().__init__(master, width=240)
        self._name_lbl = ctk.CTkLabel(
            self, text="(no game loaded)", font=("", 13, "bold"),
            anchor="w", justify="left", wraplength=220,
        )
        self._name_lbl.pack(fill="x", padx=8, pady=(10, 4))
        self._app_id_lbl = ctk.CTkLabel(
            self, text="", text_color="gray", anchor="w",
        )
        self._app_id_lbl.pack(fill="x", padx=8, pady=2)
        self._dev_lbl = ctk.CTkLabel(self, text="", anchor="w", wraplength=220)
        self._dev_lbl.pack(fill="x", padx=8, pady=2)
        self._pub_lbl = ctk.CTkLabel(self, text="", anchor="w", wraplength=220)
        self._pub_lbl.pack(fill="x", padx=8, pady=2)
        self._plat_lbl = ctk.CTkLabel(self, text="", anchor="w", wraplength=220)
        self._plat_lbl.pack(fill="x", padx=8, pady=2)
        self._clock_lbl = ctk.CTkLabel(
            self, text="", text_color="gray", anchor="w",
        )
        self._clock_lbl.pack(fill="x", padx=8, pady=(12, 2))

    # ---- API -----------------------------------------------------------

    def update(self, app_id: Optional[int], app_details: Optional[dict[str, Any]]) -> None:
        if not app_details:
            self._name_lbl.configure(text="(no game loaded)")
            self._app_id_lbl.configure(text="")
            self._dev_lbl.configure(text="")
            self._pub_lbl.configure(text="")
            self._plat_lbl.configure(text="")
            return
        self._name_lbl.configure(text=app_details.get("name", "(unnamed)"))
        self._app_id_lbl.configure(text=f"App ID: {app_id}")
        devs = ", ".join(app_details.get("developers", []) or []) or "—"
        pubs = ", ".join(app_details.get("publishers", []) or []) or "—"
        platforms = app_details.get("platforms", {}) or {}
        plat_str = ", ".join(k for k, v in platforms.items() if v) or "—"
        self._dev_lbl.configure(text=f"Developer: {devs}")
        self._pub_lbl.configure(text=f"Publisher: {pubs}")
        self._plat_lbl.configure(text=f"Platforms: {plat_str}")

    def set_clock(self, text: str) -> None:
        self._clock_lbl.configure(text=text)

    def tick_clock(self) -> None:
        self.set_clock(f"🕒 Now: {current_berlin_str()} (Berlin)")


__all__ = ["InfoPanel"]