"""Collapsible group widget.

A clickable header that hides / shows a child container. Used for the
"Dump folder", "When to include", and "Dependencies" sections in the
tab layouts.
"""
from __future__ import annotations

from typing import Optional

import customtkinter as ctk


class CollapsibleGroup(ctk.CTkFrame):
    """A toggle-able container frame.

    Usage::

        g = CollapsibleGroup(parent, "Title", expanded=False)
        g.pack(fill="x", padx=4)         # the group itself is the outer frame
        g.add_child(ctk.CTkLabel(g.body, text="…"))
    """

    def __init__(
        self,
        master,
        title: str,
        expanded: bool = True,
        icon: str = "",
    ) -> None:
        super().__init__(master, fg_color="transparent")
        self._expanded = expanded

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=2, pady=(4, 2))
        self._title_lbl = ctk.CTkLabel(
            header,
            text=f"{icon}  {title}" if icon else title,
            font=("", 12, "bold"),
            cursor="hand2",
            anchor="w",
        )
        self._title_lbl.pack(side="left", padx=4)
        self._caret_lbl = ctk.CTkLabel(
            header, text="▾" if expanded else "▸",
            cursor="hand2", width=18,
        )
        self._caret_lbl.pack(side="right", padx=4)
        for w in (header, self._title_lbl, self._caret_lbl):
            w.bind("<Button-1>", lambda _e: self.toggle())

        self.body = ctk.CTkFrame(self, fg_color="transparent")
        if expanded:
            self.body.pack(fill="x", padx=4, pady=(0, 6))

    # ---- API -----------------------------------------------------------

    # ``outer`` is a back-compat alias for the group itself so the
    # legacy call pattern ``g.outer.pack(...)`` still works.
    @property
    def outer(self) -> "CollapsibleGroup":
        return self

    def add_child(self, widget: ctk.CTkBaseClass) -> None:
        widget.pack(in_=self.body, fill="x", padx=2, pady=2)

    def toggle(self) -> None:
        if self._expanded:
            self.body.pack_forget()
            self._caret_lbl.configure(text="▸")
            self._expanded = False
        else:
            self.body.pack(fill="x", padx=4, pady=(0, 6))
            self._caret_lbl.configure(text="▾")
            self._expanded = True

    def is_expanded(self) -> bool:
        return self._expanded


__all__ = ["CollapsibleGroup"]