"""Date-picker popup.

CustomTkinter doesn't ship a native date-picker, so we roll our own
small Toplevel-based calendar. Always shows the current German time
prominently at the top so the user knows what "now" means.
"""
from __future__ import annotations

import calendar
from datetime import datetime
from typing import Callable, Optional

import customtkinter as ctk

from ..core.timezone import BERLIN


class DatePickerPopup:
    """A small modal calendar popup.

    Usage::

        DatePickerPopup(parent_entry, parent_window, on_change=fn).open()

    On *Apply*, writes ``YYYY-MM-DD`` into the target entry and runs
    the optional callback.
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
        self._picked: Optional[str] = None
        self._year = 0
        self._month = 0
        self._title_lbl: Optional[ctk.CTkLabel] = None
        self._grid: Optional[ctk.CTkFrame] = None

    # ---- public --------------------------------------------------------

    def open(self) -> None:
        if self._top is not None and self._top.winfo_exists():
            self._top.focus()
            return
        self._top = ctk.CTkToplevel(self.master)
        self._top.title("Pick a date")
        self._top.geometry("320x340")
        self._top.transient(self.master)
        self._top.grab_set()
        self._init_from_entry()
        self._build()

    # ---- internals -----------------------------------------------------

    def _init_from_entry(self) -> None:
        existing = self.target_entry.get() if self.target_entry else ""
        try:
            dt = datetime.strptime(existing, "%Y-%m-%d")
            self._year, self._month = dt.year, dt.month
        except (ValueError, TypeError):
            now = datetime.now(BERLIN)
            self._year, self._month = now.year, now.month

    def _build(self) -> None:
        top = self._top
        assert top is not None

        nav = ctk.CTkFrame(top, fg_color="transparent")
        nav.pack(fill="x", padx=8, pady=(8, 4))
        ctk.CTkButton(nav, text="◀", width=32, command=self._prev_month).pack(
            side="left", padx=2,
        )
        self._title_lbl = ctk.CTkLabel(nav, text="", font=("", 13, "bold"))
        self._title_lbl.pack(side="left", expand=True)
        ctk.CTkButton(nav, text="▶", width=32, command=self._next_month).pack(
            side="right", padx=2,
        )

        self._grid = ctk.CTkFrame(top, fg_color="transparent")
        self._grid.pack(padx=8, pady=4)
        self._render_grid()

        btns = ctk.CTkFrame(top, fg_color="transparent")
        btns.pack(fill="x", padx=8, pady=(4, 8))
        ctk.CTkButton(btns, text="Now", width=70, command=self._pick_today).pack(
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

    def _render_grid(self) -> None:
        if self._grid is None or self._title_lbl is None:
            return
        for w in self._grid.winfo_children():
            w.destroy()
        weeks = calendar.Calendar(firstweekday=0).monthdayscalendar(
            self._year, self._month,
        )
        self._title_lbl.configure(
            text=f"{calendar.month_name[self._month]} {self._year}",
        )
        today = datetime.now(BERLIN)
        for wi, week in enumerate(weeks):
            for di, day in enumerate(week):
                if day == 0:
                    ctk.CTkLabel(self._grid, text="", width=36, height=30).grid(
                        row=wi, column=di, padx=1, pady=1,
                    )
                else:
                    is_today = (
                        day == today.day
                        and self._month == today.month
                        and self._year == today.year
                    )
                    fg = "#1f6aa5" if is_today else None
                    ctk.CTkButton(
                        self._grid, text=str(day), width=36, height=30,
                        fg_color=fg,
                        command=lambda d=day: self._pick_day(d),
                    ).grid(row=wi, column=di, padx=1, pady=1)

    def _prev_month(self) -> None:
        self._month -= 1
        if self._month == 0:
            self._month = 12
            self._year -= 1
        self._render_grid()

    def _next_month(self) -> None:
        self._month += 1
        if self._month == 13:
            self._month = 1
            self._year += 1
        self._render_grid()

    def _pick_day(self, day: int) -> None:
        self._picked = f"{self._year:04d}-{self._month:02d}-{day:02d}"
        self._apply()

    def _pick_today(self) -> None:
        now = datetime.now(BERLIN)
        self._picked = now.strftime("%Y-%m-%d")
        self._apply()

    def _pick_clear(self) -> None:
        self._picked = ""
        self._apply()

    def _apply(self) -> None:
        if self.target_entry is not None:
            self.target_entry.delete(0, "end")
            if self._picked:
                self.target_entry.insert(0, self._picked)
        if self.on_change is not None:
            try:
                self.on_change(self._picked or "")
            except Exception:
                pass
        if self._top is not None:
            self._top.destroy()


__all__ = ["DatePickerPopup"]