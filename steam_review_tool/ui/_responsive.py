"""Responsive filter-grid layout.

The Steam API and Playwright tabs each have ~6 filter controls. Laying
them out one-per-row eats a lot of vertical space; on a 1200 px window
we can easily show 3 or even 4 columns side-by-side and reclaim the
space.

This module provides :class:`ResponsiveGrid` — a flow-style container
that adds a configurable number of ``(label, widget)`` rows and, on
``<Configure>``, re-flows them into as many columns as fit the current
container width.

Design notes
------------
* Widgets are passed as **factories** (``Callable[[parent], Widget]``)
  rather than pre-built widgets. The factory runs against the column
  frame every time we re-flow so the same logical widget ends up
  in the right column without us having to reparent live Tk widgets.
* We re-flow **only** when the column count changes, not on every
  pixel of resize — otherwise typing in an entry box is a laggy
  disaster (Tk fires ``<Configure>`` many times during a single drag).
* Re-flowing means the old widget is destroyed and replaced with a
  fresh one. Any *state* we want to preserve across re-flows (e.g.
  ``StringVar`` values) must live outside the widget — the caller
  owns the StringVars and binds them after each re-flow via the
  ``on_reflow`` callback.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

import customtkinter as ctk

from .tooltip import ToolTip


WidgetFactory = Callable[[ctk.CTkFrame], ctk.CTkBaseClass]


@dataclass
class _RowSpec:
    """One logical filter row (label + widget)."""
    label_text: str
    factory: WidgetFactory
    label_width: int
    tip: str


class ResponsiveGrid:
    """Flow-style filter grid that uses N columns based on available width.

    Usage::

        g = ResponsiveGrid(parent, min_col_width=320)
        g.add_row("Language:", lambda p: ctk.CTkOptionMenu(p, ...))
        g.add_row("Sort by:",  lambda p: ctk.CTkOptionMenu(p, ...))
        g.build()                    # call once after all rows are added
        # ``g.outer`` is the CTkFrame to pack into a parent.
    """

    def __init__(
        self,
        parent: ctk.CTkBaseClass,
        *,
        min_col_width: int = 320,
        label_width: int = 120,
        outer_padx: int = 4,
        outer_pady: int = 2,
    ) -> None:
        self.parent = parent
        self.min_col_width = max(120, int(min_col_width))
        self.label_width = max(60, int(label_width))
        self.outer = ctk.CTkFrame(parent, fg_color="transparent")
        self.outer.pack(fill="x", padx=outer_padx, pady=outer_pady)
        self._rows: list[_RowSpec] = []
        self._col_frames: list[ctk.CTkFrame] = []
        self._reflow_cb: Optional[Callable[[], None]] = None
        # Bind to <Configure> so resizes trigger a re-flow.
        self.outer.bind("<Configure>", self._on_configure)

    # ---- public API --------------------------------------------------

    def add_row(
        self,
        label_text: str,
        factory: WidgetFactory,
        *,
        tip: str = "",
        label_width: Optional[int] = None,
    ) -> None:
        """Append a (label, widget) pair. The factory builds the widget."""
        self._rows.append(_RowSpec(
            label_text=label_text,
            factory=factory,
            label_width=label_width if label_width is not None else self.label_width,
            tip=tip,
        ))

    def on_reflow(self, cb: Callable[[], None]) -> None:
        """Register a callback to run after every re-flow.

        Use this to re-bind ``StringVar``s to the freshly-built widgets.
        """
        self._reflow_cb = cb

    def build(self) -> None:
        """Trigger an initial layout pass.

        Runs the relayout synchronously so callers (e.g. the section
        builders) can read freshly-created widget handles out of
        ``_col_frames`` immediately after ``build()`` returns.
        Subsequent re-flows triggered by ``<Configure>`` still happen
        on the Tk event loop, which is fine because they're driven by
        actual user interaction (resize).
        """
        # ``update_idletasks`` forces the outer frame to compute its
        # real width so we don't compute 0 columns on first paint.
        try:
            self.outer.update_idletasks()
        except Exception:
            pass
        self._relayout()

    # ---- layout ------------------------------------------------------

    def _on_configure(self, event) -> None:
        # Only re-flow if our width has materially changed (10 px slack).
        new_w = event.width
        cur_w = getattr(self, "_last_w", -1)
        if abs(new_w - cur_w) < 10:
            return
        self._last_w = new_w
        self._relayout()

    def _relayout(self) -> None:
        try:
            width = self.outer.winfo_width()
        except Exception:
            return
        if width < 50 or not self._rows:
            return
        n_cols = max(1, min(len(self._rows), width // self.min_col_width))
        if n_cols == len(self._col_frames) and self._col_frames:
            # Same column count as last time — skip the rebuild so
            # we don't tear down widgets mid-keystroke.
            return

        # Tear down old columns
        for child in self.outer.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass
        self._col_frames = []

        # Build new columns
        for _ in range(n_cols):
            col = ctk.CTkFrame(self.outer, fg_color="transparent")
            col.pack(side="left", fill="both", expand=True, padx=2)
            self._col_frames.append(col)

        # Distribute rows in column-major order: the first n_cols
        # widgets go down the left column, the next n_cols down the
        # middle, etc. This matches the natural left-to-right
        # reading order of a wide layout.
        for i, spec in enumerate(self._rows):
            target = self._col_frames[i % n_cols]
            row = ctk.CTkFrame(target, fg_color="transparent")
            row.pack(fill="x", padx=2, pady=2)
            if spec.label_text:
                lbl = ctk.CTkLabel(
                    row, text=spec.label_text,
                    anchor="e", width=spec.label_width,
                )
                lbl.pack(side="left", padx=(4, 4), pady=3)
                if spec.tip:
                    ToolTip(lbl, spec.tip)
            widget = spec.factory(row)
            widget.pack(side="left", padx=4, pady=3, fill="x", expand=True)
            if spec.tip:
                ToolTip(widget, spec.tip)

        if self._reflow_cb is not None:
            try:
                self._reflow_cb()
            except Exception:
                pass


__all__ = ["ResponsiveGrid", "WidgetFactory"]
