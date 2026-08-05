"""Welcome dialog — shown on first launch.

Greets the user, lists the headline features, and offers a
"Don't show again" checkbox that is persisted in ``settings.json``
under the ``greeting_shown`` key. The dialog is **modal** (the
rest of the app blocks until the user clicks Close / unchecks the
checkbox + Close) — that matches every other pop-up in the app
(Help, Settings, Search) and avoids the case where a new user
misses the greeting behind the main window.

The GQA logo (``assets/gqa_logo.png``) is rendered at the top of
the popup via :class:`CTkImage` so it scales cleanly with the
system theme (light/dark) and HiDPI scaling.
"""
from __future__ import annotations

import os
import tkinter as tk
from pathlib import Path
from typing import Callable, Optional

import customtkinter as ctk

from ..services.settings_store import save as save_settings


# Resolved relative to this module so PyInstaller's bundling finds
# the logo at runtime (``sys._MEIPASS`` is handled by ``__file__``).
_LOGO_PATH = Path(__file__).resolve().parent / "assets" / "gqa_logo.png"


WELCOME_TITLE = "Welcome to the GQA Steam Review Tool"

WELCOME_BODY = """\
Welcome — and thanks for trying the GQA Steam Review Tool (https://gqa.gmbh/)!

This is a small, focused desktop tool for QA / product folks who
need to dump every Steam review of a game (in every language
Steam ships) and hand the result to an LLM for structured
analysis. The output is one self-contained .md file per game.

WHAT IT DOES
───────────
• Fetches ALL Steam reviews via the public JSON API, paginated,
  in any language. Exports to Markdown (+ optional CSV / JSON /
  per-language split).

• When the JSON API is empty or lagging (new games, last 24-72 h),
  the Playwright tab launches a real headless Chromium and hits
  Steam's un-cached AJAX endpoint. So you can review a freshly
  released title the same day it launches.

• Auto-dedup via the seen-IDs file: subsequent "Fetch new" runs
  only pull reviews you haven't dumped before.

• "Top complaints" / "Quick: negatives" / "Copy + AI prompt" —
  one click from raw reviews to AI-ready context.

• Trends tab tracks wishlist / follower / review counts over
  time and renders a chart.

STATUS
──────
Work in progress. The main fetch + export path is solid;
Chromium-based scraping, the Trends time-series, and the various
AI integrations are still being polished. Things break —
especially around Steam's cache + Playwright's anti-bot
heuristics. Please file issues with your App ID and a sample
review URL.

CREDITS
───────
GQA — Game Quality Assurance (https://gqa.gmbh/). The "GQA" in the
tool's title stands for this purpose.

Author: Christoph Möbius (https://gqa.gmbh/) — feedback and bug
reports welcome.
"""


class WelcomeDialog:
    """One-shot welcome popup. Modal; persisted via settings."""

    def __init__(
        self,
        master: ctk.CTkBaseClass,
        *,
        settings: dict,
        on_save_settings: Callable[[dict], None],
    ) -> None:
        self.master = master
        self._settings = settings
        self._on_save_settings = on_save_settings
        self._top: Optional[ctk.CTkToplevel] = None
        self._dont_show_var = ctk.BooleanVar(value=False)
        self._logo_image: Optional[ctk.CTkImage] = None

    def open(self) -> None:
        if self._top is not None and self._top.winfo_exists():
            self._top.focus_force()
            return
        top = ctk.CTkToplevel(self.master)
        top.title(WELCOME_TITLE)
        top.geometry("680x620")
        top.transient(self.master)
        try:
            top.grab_set()
        except tk.TclError:
            pass
        self._top = top
        self._build(top)
        top.update_idletasks()
        try:
            mx = self.master.winfo_rootx()
            my = self.master.winfo_rooty()
            mw = self.master.winfo_width()
            mh = self.master.winfo_height()
            tw = top.winfo_width()
            th = top.winfo_height()
            top.geometry(
                f"+{mx + (mw - tw) // 2}+{my + (mh - th) // 2}"
            )
        except tk.TclError:
            pass
        top.focus_force()

    def _build(self, top: ctk.CTkToplevel) -> None:
        outer = ctk.CTkFrame(top)
        outer.pack(fill="both", expand=True, padx=10, pady=10)

        # ---- Logo + heading (side-by-side) ------------------------
        header = ctk.CTkFrame(outer, fg_color="transparent")
        header.pack(fill="x", padx=4, pady=(4, 6))
        self._load_logo(header)
        heading = ctk.CTkLabel(
            header,
            text=WELCOME_TITLE,
            font=("", 17, "bold"),
            anchor="w",
            justify="left",
        )
        heading.pack(side="left", padx=(10, 0), pady=4)

        # ---- Scrollable body ---------------------------------------
        body_frame = ctk.CTkFrame(outer)
        body_frame.pack(fill="both", expand=True, padx=2, pady=2)
        text = tk.Text(
            body_frame, wrap="word",
            bg="#1a1a1a", fg="#e0e0e0",
            insertbackground="#e0e0e0",
            font=("Segoe UI", 10),
            padx=8, pady=8, borderwidth=0, highlightthickness=0,
        )
        scroll = ctk.CTkScrollbar(body_frame, command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        text.insert("1.0", WELCOME_BODY)
        # ``state="readonly"`` lets the user select and copy the
        # welcome text (e.g. the URL for filing a bug report) but
        # prevents accidental edits. The old ``state="disabled"``
        # made the widget completely non-interactive.
        text.configure(state="readonly")
        text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        # ---- Footer: don't-show-again + close -------------------
        footer = ctk.CTkFrame(top, fg_color="transparent")
        footer.pack(fill="x", padx=10, pady=(0, 10))
        ctk.CTkCheckBox(
            footer, text="Don't show this again",
            variable=self._dont_show_var,
        ).pack(side="left")
        ctk.CTkButton(
            footer, text="Close", width=120, command=self._on_close,
        ).pack(side="right")

    def _load_logo(self, parent: ctk.CTkFrame) -> None:
        """Render the GQA logo to the left of the heading. Silently
        skip if the asset isn't shipped (e.g. source-only checkout
        without the bundled asset)."""
        try:
            from PIL import Image  # Pillow ships with customtkinter
        except ImportError:
            Image = None
        if Image is None or not _LOGO_PATH.exists():
            return
        try:
            # Load with Pillow, then hand to CTkImage so it
            # auto-scales on HiDPI displays and adapts to the
            # current theme.
            img = Image.open(_LOGO_PATH)
            # Cap the rendered height to 56 px so it doesn't dwarf
            # the heading on big monitors. Width follows.
            target_h = 56
            ratio = target_h / img.height
            target_w = int(img.width * ratio)
            self._logo_image = ctk.CTkImage(
                light_image=img, dark_image=img,
                size=(target_w, target_h),
            )
            ctk.CTkLabel(parent, image=self._logo_image, text="").pack(
                side="left", padx=(2, 0), pady=2,
            )
        except tk.TclError:
            # Image-load / CTkImage failures are non-fatal — the
            # popup still works without the logo.
            self._logo_image = None

    def _on_close(self) -> None:
        if self._dont_show_var.get():
            self._settings["greeting_shown"] = True
            try:
                self._on_save_settings(self._settings)
            except Exception as exc:
                # R24: the previous ``except Exception: pass`` silently
                # dropped any failure from the persistence callback.
                # ``_persist_settings`` (R23-1) already logs internally,
                # but a callback from another caller, or an exception
                # raised BEFORE the persistence call ran, would never
                # be visible — the greeting would silently fail to
                # be remembered and reappear on next launch. Always
                # log so the developer can spot the failure in stderr.
                import logging
                logging.getLogger(__name__).exception(
                    "welcome-dialog on_save_settings callback failed: %s",
                    exc,
                )
        try:
            if self._top is not None and self._top.winfo_exists():
                self._top.grab_release()
                self._top.destroy()
        except tk.TclError:
            pass
        self._top = None


__all__ = ["WelcomeDialog", "WELCOME_TITLE", "WELCOME_BODY"]
