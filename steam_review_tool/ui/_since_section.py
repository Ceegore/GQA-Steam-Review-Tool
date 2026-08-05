"""Shared "When to include (German time)" section builder.

Used by both the API and the Playwright tab. Keeps the per-tab file
size under the 500-LOC hard limit and ensures the two tabs have
identical "since" semantics.
"""
from __future__ import annotations

import logging
import tkinter as tk
from typing import Callable, Optional, Any

import customtkinter as ctk

from ..core.constants import SINCE_PRESETS, SINCE_PRESET_LABELS
from ..core.timezone import current_berlin_str
from ..ui.tooltip import ToolTip
from ..utils.datetime_utils import parse_since_preset


def build_since_section(
    parent: ctk.CTkBaseClass,
    *,
    prefix: str = "",
    on_change: Optional[Callable[[], None]] = None,
    log_fn: Optional[Callable[[str], None]] = None,
) -> dict[str, Any]:
    """Build the "When to include (German time)" section.

    Returns a dict[str, Any] of widget refs so the caller can read/write values:

        refs = build_since_section(parent, prefix="api_")
        preset_value = refs["preset_var"].get()
    """
    sec = ctk.CTkFrame(parent)
    sec.pack(fill="x", padx=8, pady=(4, 4))

    # Header row with live clock on the right
    hdr = ctk.CTkFrame(sec, fg_color="transparent")
    hdr.pack(fill="x", padx=8, pady=(6, 2))
    ctk.CTkLabel(
        hdr, text="When to include (German time)", font=("", 13, "bold"),
    ).pack(side="left", padx=4)
    clock_lbl = ctk.CTkLabel(hdr, text="", text_color="gray")
    clock_lbl.pack(side="right", padx=8)

    # Row 1: preset + live "since" label
    r1 = ctk.CTkFrame(sec, fg_color="transparent")
    r1.pack(fill="x", padx=8, pady=(2, 2))
    ctk.CTkLabel(r1, text="Since preset:", width=120, anchor="e").pack(
        side="left", padx=(4, 6),
    )
    preset_var = ctk.StringVar(value="all time")
    preset_menu = ctk.CTkOptionMenu(
        r1, values=SINCE_PRESET_LABELS, variable=preset_var, width=200,
    )
    preset_menu.pack(side="left", padx=4)
    ToolTip(preset_menu, "How far back to include reviews.")

    since_label = ctk.CTkLabel(r1, text="(all time)", text_color="gray")
    since_label.pack(side="left", padx=8)

    # Row 2: custom date + time
    r2 = ctk.CTkFrame(sec, fg_color="transparent")
    r2.pack(fill="x", padx=8, pady=(2, 6))
    ctk.CTkLabel(r2, text="Custom date:", width=120, anchor="e").pack(
        side="left", padx=(4, 6),
    )
    date_entry = ctk.CTkEntry(r2, width=140, placeholder_text="YYYY-MM-DD")
    date_entry.pack(side="left", padx=4)
    ToolTip(date_entry, "Only include reviews from this date onwards.")

    ctk.CTkLabel(r2, text="Time:", width=60, anchor="e").pack(
        side="left", padx=(20, 4),
    )
    time_entry = ctk.CTkEntry(r2, width=100, placeholder_text="HH:MM")
    time_entry.pack(side="left", padx=4)
    ToolTip(time_entry, "Berlin-time lower bound (24h clock).")

    # Initial label state
    def _refresh_label() -> None:
        try:
            hours = parse_since_preset(preset_var.get())
            if hours == 0:
                since_label.configure(text="(all time)")
            elif hours > 0:
                since_label.configure(text=f"({hours} h back)")
            else:
                d = date_entry.get().strip()
                t = time_entry.get().strip()
                since_label.configure(
                    text=(f"({d} {t}".rstrip() + ")") if d or t else "(custom)",
                )
            clock_lbl.configure(text=f"🕒 Now: {current_berlin_str()} (Berlin)")
        except tk.TclError:
            # R29: the since section's widget teardown
            # race. ``preset_var`` / ``date_entry`` /
            # ``time_entry`` / ``since_label`` /
            # ``clock_lbl`` are all Tk variables /
            # widgets. If the parent is destroyed
            # before the trace fires (e.g. the user
            # closes the tab mid-``_on_preset_change``),
            # the ``.get()`` / ``.configure()`` calls
            # raise ``tk.TclError``. The previous
            # version had NO try/except — the
            # exception propagated out of
            # ``_refresh_label`` and crashed the
            # preset change. R29 wraps the widget
            # ops in ``try: ... except tk.TclError:
            # pass`` so only the actually-expected
            # teardown race is silently dropped;
            # programming bugs (TypeError if
            # ``current_berlin_str()`` returns
            # something weird) still propagate.
            pass

    _refresh_label()

    def _on_preset_change(_value: object) -> None:
        _refresh_label()
        if on_change is not None:
            try:
                on_change()
            except Exception as exc:
                # The previous version only forwarded the
                # failure to ``log_fn`` (which is optional and
                # typically None in this app). When the user
                # didn't supply a log_fn, the exception was
                # silently swallowed — the preset change
                # "looked" applied but the dependent state
                # (e.g. dump-folder label refresh) silently
                # broke. Always log via the standard logger
                # so the developer can spot the failure in
                # stderr even when no log_fn is wired.
                logging.getLogger(__name__).exception(
                    "since-section on_change callback failed: %s",
                    exc,
                )
                if log_fn is not None:
                    log_fn(f"since-section callback failed: {exc}")

    def _on_entry_change(_event: object = None) -> None:
        _refresh_label()

    preset_var.trace_add("write", lambda *_: _on_preset_change(None))
    date_entry.bind("<KeyRelease>", lambda _e: _on_entry_change())
    time_entry.bind("<KeyRelease>", lambda _e: _on_entry_change())

    return {
        "frame": sec,
        "preset_var": preset_var,
        "date_entry": date_entry,
        "time_entry": time_entry,
        "since_label": since_label,
        "clock_label": clock_lbl,
        "refresh": _refresh_label,
    }


__all__ = ["build_since_section"]