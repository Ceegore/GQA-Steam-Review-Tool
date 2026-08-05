"""Small reusable helpers shared by every tab's build method."""
from __future__ import annotations

from typing import Callable, Optional

import customtkinter as ctk


def make_section(
    parent: ctk.CTkBaseClass,
    title: str,
    right_widget: Optional[ctk.CTkBaseClass] = None,
) -> ctk.CTkFrame:
    """Create a titled section frame with an optional right-side widget.

    Returns the body frame so the caller can pack controls into it.
    """
    sec = ctk.CTkFrame(parent)
    sec.pack(fill="x", padx=6, pady=(8, 4))
    ctk.CTkLabel(sec, text=title, font=("", 13, "bold")).pack(
        side="left", padx=(8, 4), pady=4,
    )
    if right_widget is not None:
        right_widget.pack(side="right", padx=8, pady=4)
    body = ctk.CTkFrame(sec, fg_color="transparent")
    body.pack(fill="x", padx=4, pady=(2, 6))
    return body


def labelled_entry(
    parent: ctk.CTkBaseClass,
    label_text: str,
    placeholder: str = "",
    width: int = 200,
    on_submit: Optional[Callable[[], None]] = None,
) -> tuple[ctk.CTkFrame, ctk.CTkEntry]:
    """Create a labelled single-line entry.

    Returns ``(row_frame, entry)`` — the row frame contains
    the label + entry packed side-by-side, the entry is
    returned separately so the caller can wire up
    ``on_change`` traces without re-querying Tk.
    """
    row = ctk.CTkFrame(parent, fg_color="transparent")
    row.pack(fill="x", padx=4, pady=2)
    ctk.CTkLabel(row, text=label_text, width=140, anchor="w").pack(
        side="left", padx=(4, 6),
    )
    entry = ctk.CTkEntry(row, placeholder_text=placeholder, width=width)
    entry.pack(side="left", padx=4, fill="x", expand=True)
    if on_submit is not None:
        entry.bind("<Return>", lambda _e: on_submit())
    return row, entry


__all__ = ["make_section", "labelled_entry"]