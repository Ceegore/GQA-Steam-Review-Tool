"""Responsive widgets: filter grid + action bar wrapping.

Two widgets live here:

* :class:`ResponsiveGrid` — ``(label, widget)`` filter rows flow
  into N columns based on container width. Re-flows on
  ``<Configure>``, debounced and gated by a recursion guard so a
  drag of the window edge triggers exactly one reflow (not dozens).

* :class:`WrapFrame` — horizontal layout that wraps children to a
  new row when the current row is full. Uses ``place()`` to avoid
  CustomTkinter's broken pack-reparent behaviour.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

import customtkinter as ctk
import tkinter as tk

from .tooltip import ToolTip


WidgetFactory = Callable[[ctk.CTkFrame], ctk.CTkBaseClass]


# ---------------------------------------------------------------------------
# Responsive filter grid
# ---------------------------------------------------------------------------

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

    The grid re-flows on ``<Configure>``, but only after a 50 px width
    change AND with a 200 ms debounce. Without the debounce, dragging
    the window edge fires dozens of ``<Configure>`` events per second
    and each reflow destroys + recreates every widget — visible as a
    multi-second UI freeze on slower machines.
    """

    _SLACK_PX = 50
    _DEBOUNCE_MS = 200

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
        self._after_id: Optional[str] = None
        self._last_w: int = -1
        self._reflowing: bool = False
        self.outer.bind("<Configure>", self._on_configure)

    def add_row(
        self,
        label_text: str,
        factory: WidgetFactory,
        *,
        tip: str = "",
        label_width: Optional[int] = None,
    ) -> None:
        self._rows.append(_RowSpec(
            label_text=label_text,
            factory=factory,
            label_width=label_width if label_width is not None else self.label_width,
            tip=tip,
        ))

    def on_reflow(self, cb: Callable[[], None]) -> None:
        self._reflow_cb = cb

    def build(self) -> None:
        try:
            self.outer.update_idletasks()
        except tk.TclError:
            pass
        self._relayout()

    def _on_configure(self, event) -> None:
        new_w = event.width
        if abs(new_w - self._last_w) < self._SLACK_PX:
            return
        self._last_w = new_w
        if self._after_id is not None:
            try:
                self.outer.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None
        self._after_id = self.outer.after(self._DEBOUNCE_MS, self._do_reflow)

    def _do_reflow(self) -> None:
        self._after_id = None
        self._relayout()

    def _relayout(self) -> None:
        if self._reflowing:
            return
        self._reflowing = True
        try:
            try:
                width = self.outer.winfo_width()
            except tk.TclError:
                return
            if width < 50 or not self._rows:
                return
            n_cols = max(1, min(len(self._rows), width // self.min_col_width))
            if n_cols == len(self._col_frames) and self._col_frames:
                return

            for child in self.outer.winfo_children():
                try:
                    child.destroy()
                except tk.TclError:
                    pass
            self._col_frames = []

            for _ in range(n_cols):
                col = ctk.CTkFrame(self.outer, fg_color="transparent")
                col.pack(side="left", fill="both", expand=True, padx=2)
                self._col_frames.append(col)

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
                except Exception as exc:
                    # R24: the previous ``except Exception: pass``
                    # silently dropped any failure from the
                    # caller-supplied reflow callback. The callback
                    # is typically a tab controller's
                    # ``_refresh_button_states`` or label-update
                    # hook — bugs in those handlers would be
                    # invisible. Always log so the failure is at
                    # least visible in stderr (mirrors the R23
                    # fix-shape in ``_since_section._on_preset_change``).
                    import logging
                    logging.getLogger(__name__).exception(
                        "ResponsiveGrid on_reflow callback failed: %s",
                        exc,
                    )
        finally:
            self._reflowing = False


# ---------------------------------------------------------------------------
# WrapFrame — horizontal layout that wraps to a new row on overflow.
# ---------------------------------------------------------------------------


class WrapFrame(ctk.CTkFrame):
    """A horizontal frame whose children wrap to a new row when full.

    Children are added with :meth:`add(widget)`. They are laid out
    left-to-right in the current row; when the next child's requested
    width would push the row past the frame's width, a new row is
    started. ``side="right"`` items go on the right of the last row
    (they don't wrap).

    Implementation: widgets stay parented to the WrapFrame and are
    positioned with ``place()`` — Tk's pack-into-new-parent does not
    reparent reliably under CustomTkinter, and place() avoids the
    whole class of issues.

    The frame re-flows on ``<Configure>``, debounced 150 ms, so a
    window resize only triggers one rebuild per settle.
    """

    _DEBOUNCE_MS = 150
    _SLACK_PX = 30

    def __init__(
        self,
        master: ctk.CTkBaseClass,
        *,
        padx: int = 4,
        pady: int = 4,
        row_gap: int = 2,
    ) -> None:
        super().__init__(master, fg_color="transparent")
        self._padx = padx
        self._pady = pady
        self._row_gap = row_gap
        self._items: list[tuple[ctk.CTkBaseClass, str]] = []
        self._after_id: Optional[str] = None
        self._last_w: int = -1
        self._reflowing: bool = False
        self.bind("<Configure>", self._on_configure)

    def add(
        self,
        widget: ctk.CTkBaseClass,
        *,
        side: str = "left",
    ) -> None:
        if side not in ("left", "right"):
            raise ValueError(f"side must be 'left' or 'right', got {side!r}")
        self._items.append((widget, side))
        self._relayout()

    def _on_configure(self, event) -> None:
        if abs(event.width - self._last_w) < self._SLACK_PX:
            return
        self._last_w = event.width
        if self._after_id is not None:
            try:
                self.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None
        self._after_id = self.after(self._DEBOUNCE_MS, self._relayout)

    def _relayout(self) -> None:
        if self._reflowing:
            return
        self._reflowing = True
        try:
            self._after_id = None
            try:
                width = self.winfo_width()
            except tk.TclError:
                return
            if width < 50 or not self._items:
                return

            for w, _ in self._items:
                try:
                    w.place_forget()
                except tk.TclError:
                    pass

            lefts = [w for w, s in self._items if s == "left"]
            rights = [w for w, s in self._items if s == "right"]

            reqs: dict = {}
            for ww, _ in self._items:
                try:
                    reqs[ww] = self._req_size(ww)
                except Exception as exc:  # pragma: no cover - defensive
                    reqs[ww] = (100, 30)

            # Lay out left items row-by-row.
            rows: list[list[ctk.CTkBaseClass]] = []
            cur_row: list[ctk.CTkBaseClass] = []
            cur_w = 0
            for w in lefts:
                ww, hh = reqs[w]
                if cur_w + ww > width and cur_row:
                    rows.append(cur_row)
                    cur_row = []
                    cur_w = 0
                cur_row.append(w)
                cur_w += ww
            if cur_row:
                rows.append(cur_row)

            # Place left-side widgets.
            y = 0
            row_heights: list[int] = []
            for row in rows:
                rh = max(reqs[w][1] for w in row)
                row_heights.append(rh)
                x = 0
                for w in row:
                    ww, hh = reqs[w]
                    self._place(w, x, y + (rh - hh) // 2 if rh > hh else y)
                    x += ww
                y += rh + self._row_gap

            # Right-pinned widgets sit on the right of the last row.
            if rights:
                last_row_h = max(row_heights) if row_heights else 0
                right_row_h = max(reqs[w][1] for w in rights)
                row_h = max(last_row_h, right_row_h)
                last_y = sum(row_heights) + self._row_gap * max(0, len(row_heights) - 1)
                # Pack right items right-to-left.
                x = width
                for w in rights:
                    ww, hh = reqs[w]
                    x -= ww
                    self._place(
                        w, x,
                        last_y + (row_h - hh) // 2 if row_h > hh else last_y,
                    )
                y = last_y + row_h + self._row_gap

            # Reserve vertical room so the parent doesn't clip us.
            try:
                self.configure(height=y if y > 0 else 1)
            except tk.TclError:
                pass
        finally:
            self._reflowing = False

    def _place(
        self, widget: ctk.CTkBaseClass, x: int, y: int,
    ) -> None:
        try:
            widget.place(in_=self, x=x, y=y)
        except tk.TclError:
            pass

    def _req_size(self, widget: ctk.CTkBaseClass) -> tuple[int, int]:
        try:
            widget.update_idletasks()
            w = max(0, int(widget.winfo_reqwidth())) + 2 * self._padx
            h = max(0, int(widget.winfo_reqheight())) + 2 * self._pady
            return (w, h)
        except tk.TclError:
            return (100, 30)


__all__ = ["ResponsiveGrid", "WidgetFactory", "WrapFrame"]
