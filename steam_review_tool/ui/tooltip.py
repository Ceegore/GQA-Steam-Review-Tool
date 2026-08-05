"""Lightweight hover-tooltip for CustomTkinter widgets.

Why not just use tkinter's ``tooltip`` package? Adding a dependency
for one tooltip would be silly. This implementation has no external
deps, supports multi-line wrapping, and uses ``after`` for clean
show/hide scheduling.
"""
from __future__ import annotations

import tkinter as tk
from typing import Optional

import customtkinter as ctk


class ToolTip:
    """Hover tooltip. Usage: ``ToolTip(my_widget, "Click to fetch reviews")``."""

    def __init__(
        self,
        widget: tk.Misc,
        text: str,
        delay_ms: int = 400,
    ) -> None:
        self.widget = widget
        self.text = text
        self.delay_ms = delay_ms
        self._after_id: Optional[str] = None
        self._tip_window: Optional[tk.Toplevel] = None
        widget.bind("<Enter>", self._schedule)
        widget.bind("<Leave>", self._cancel)
        widget.bind("<ButtonPress>", self._cancel)

    def _schedule(self, _event=None) -> None:
        self._after_id = self.widget.after(self.delay_ms, self._show)

    def _cancel(self, _event=None) -> None:
        if self._after_id is not None:
            try:
                self.widget.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None
        if self._tip_window is not None:
            try:
                self._tip_window.destroy()
            except tk.TclError:
                pass
            self._tip_window = None

    def _show(self) -> None:
        if self._tip_window is not None:
            return
        try:
            x = self.widget.winfo_pointerx() + 12
            y = self.widget.winfo_pointery() + 18
        except tk.TclError:
            return
        self._tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(
            tw,
            text=self.text,
            justify="left",
            background="#1a1a1a",
            foreground="#e0e0e0",
            relief="solid",
            borderwidth=1,
            padx=6,
            pady=3,
            font=("Segoe UI", 9),
        )
        label.pack()


__all__ = ["ToolTip"]