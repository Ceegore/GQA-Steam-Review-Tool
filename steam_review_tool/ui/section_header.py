"""Small reusable helpers shared by every tab's build method."""
from __future__ import annotations

from typing import Optional

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


__all__ = ["make_section"]