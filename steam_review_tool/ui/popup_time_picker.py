"""Time-picker popup. Counter-style selectors for HH and MM."""
from __future__ import annotations

import tkinter as tk
from datetime import datetime
from typing import Callable, Optional

import customtkinter as ctk

from ..core.timezone import BERLIN


class TimePickerPopup:
    """A small modal HH:MM picker.

    Usage::

        TimePickerPopup(parent_entry, parent_window, on_change=fn).open()
    """

    def __init__(
        self,
        target_entry,
        master,
        on_change: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.target_entry = target_entry
        self.master = master
        self.on_change = on_change
        self._top: Optional[ctk.CTkToplevel] = None
        self._hour_var: Optional[tk.IntVar] = None
        self._min_var: Optional[tk.IntVar] = None

    # ---- public --------------------------------------------------------

    def open(self) -> None:
        if self._top is not None and self._top.winfo_exists():
            self._top.focus()
            return
        self._top = ctk.CTkToplevel(self.master)
        self._top.title("Pick a time")
        self._top.geometry("240x220")
        self._top.transient(self.master)
        self._top.grab_set()
        self._init_from_entry()
        self._build()

    # ---- internals -----------------------------------------------------

    def _init_from_entry(self) -> None:
        existing = self.target_entry.get() if self.target_entry else ""
        try:
            dt = datetime.strptime(existing, "%H:%M")
            h, m = dt.hour, dt.minute
        except (ValueError, TypeError):
            now = datetime.now(BERLIN)
            h, m = now.hour, now.minute
        self._hour_var = tk.IntVar(value=h)
        self._min_var = tk.IntVar(value=m)

    def _build(self) -> None:
        top = self._top
        assert top is not None and self._hour_var and self._min_var

        ctk.CTkLabel(top, text="Time (Berlin)", font=("", 12, "bold")).pack(
            pady=(8, 4),
        )

        spinbox_frame = ctk.CTkFrame(top, fg_color="transparent")
        spinbox_frame.pack(pady=8)
        for label, var, lo, hi in (
            ("Hour",   self._hour_var, 0, 23),
            ("Minute", self._min_var,  0, 59),
        ):
            col = ctk.CTkFrame(spinbox_frame, fg_color="transparent")
            col.pack(side="left", padx=8)
            ctk.CTkLabel(col, text=label).pack()
            ctk.CTkButton(
                col, text="▲", width=40, height=24,
                command=lambda v=var, hi=hi: v.set((v.get() + 1) % (hi + 1)),
            ).pack()
            ctk.CTkLabel(col, textvariable=var, font=("", 18, "bold")).pack(pady=2)
            ctk.CTkButton(
                col, text="▼", width=40, height=24,
                command=lambda v=var, hi=hi: v.set((v.get() - 1) % (hi + 1)),
            ).pack()

        btns = ctk.CTkFrame(top, fg_color="transparent")
        btns.pack(fill="x", padx=8, pady=8)
        ctk.CTkButton(btns, text="Now", width=70, command=self._pick_now).pack(
            side="left", padx=2,
        )
        ctk.CTkButton(btns, text="Clear", width=70, command=self._pick_clear).pack(
            side="left", padx=2,
        )
        ctk.CTkButton(btns, text="Cancel", width=80, command=top.destroy).pack(
            side="right", padx=2,
        )
        ctk.CTkButton(
            btns, text="Apply", width=80, fg_color="#1f6aa5",
            command=self._apply,
        ).pack(side="right", padx=2)

    def _set(self, h: int, m: int) -> None:
        if self._hour_var is not None:
            self._hour_var.set(h)
        if self._min_var is not None:
            self._min_var.set(m)

    def _pick_now(self) -> None:
        now = datetime.now(BERLIN)
        self._set(now.hour, now.minute)
        self._apply()

    def _pick_clear(self) -> None:
        if self.target_entry is not None:
            self.target_entry.delete(0, "end")
        if self.on_change is not None:
            try:
                self.on_change("")
            except Exception as exc:
                # R24: the previous ``except Exception: pass`` silently
                # dropped any failure from the user-supplied callback.
                # Always log so the failure is at least visible in
                # stderr (mirrors the R23 fix-shape in
                # ``_since_section._on_preset_change``).
                import logging
                logging.getLogger(__name__).exception(
                    "time-picker on_change callback (clear) failed: %s",
                    exc,
                )
        if self._top is not None:
            self._top.destroy()

    def _apply(self) -> None:
        if self._hour_var is None or self._min_var is None:
            return
        hh = int(self._hour_var.get())
        mm = int(self._min_var.get())
        value = f"{hh:02d}:{mm:02d}"
        if self.target_entry is not None:
            self.target_entry.delete(0, "end")
            self.target_entry.insert(0, value)
        if self.on_change is not None:
            try:
                self.on_change(value)
            except Exception as exc:
                # R24: the previous ``except Exception: pass`` silently
                # dropped any failure from the user-supplied callback.
                # Always log so the failure is at least visible in
                # stderr (mirrors the R23 fix-shape in
                # ``_since_section._on_preset_change``).
                import logging
                logging.getLogger(__name__).exception(
                    "time-picker on_change callback (apply) failed: %s",
                    exc,
                )
        if self._top is not None:
            self._top.destroy()


__all__ = ["TimePickerPopup"]