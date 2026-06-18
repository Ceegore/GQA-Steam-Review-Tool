"""Settings dialog.

Lets the user edit dump root, Obsidian vault, Apify token, keyword
list[Any], and the AI prompt template. Reads/writes via the
``settings_store`` service.
"""
from __future__ import annotations

import tkinter as tk
from typing import Callable, Optional, Any

import customtkinter as ctk

from ..services import settings_store


class SettingsDialog:
    """A modal for editing user preferences."""

    def __init__(self, master) -> None:
        self.master = master
        self._top: Optional[ctk.CTkToplevel] = None
        self._save_cb: Optional[Callable[[dict[str, Any]], None]] = None
        self._dump_root_var: Optional[tk.StringVar] = None
        self._obsidian_var: Optional[tk.StringVar] = None
        self._apify_var: Optional[tk.StringVar] = None

    def open(self, save_cb: Callable[[dict[str, Any]], None]) -> None:
        if self._top is not None and self._top.winfo_exists():
            self._top.focus()
            return
        self._save_cb = save_cb
        self._top = ctk.CTkToplevel(self.master)
        self._top.title("Settings")
        self._top.geometry("640x560")
        self._top.transient(self.master)
        self._build()

    def _build(self) -> None:
        top = self._top
        assert top is not None

        data = settings_store.load()

        body = ctk.CTkScrollableFrame(top)
        body.pack(fill="both", expand=True, padx=8, pady=8)

        # ---- Dump root -----------------------------------------------
        ctk.CTkLabel(body, text="Dump folder", font=("", 12, "bold")).pack(
            anchor="w", padx=4, pady=(6, 2),
        )
        self._dump_root_var = tk.StringVar(value=data.get("dump_root", ""))
        ctk.CTkEntry(body, textvariable=self._dump_root_var, width=500).pack(
            fill="x", padx=4, pady=2,
        )

        # ---- Obsidian vault ------------------------------------------
        ctk.CTkLabel(body, text="Obsidian vault (optional)", font=("", 12, "bold")).pack(
            anchor="w", padx=4, pady=(10, 2),
        )
        self._obsidian_var = tk.StringVar(value=data.get("obsidian_vault", ""))
        ctk.CTkEntry(body, textvariable=self._obsidian_var, width=500).pack(
            fill="x", padx=4, pady=2,
        )

        # ---- Apify token ---------------------------------------------
        ctk.CTkLabel(body, text="Apify token (optional)", font=("", 12, "bold")).pack(
            anchor="w", padx=4, pady=(10, 2),
        )
        self._apify_var = tk.StringVar(value=data.get("apify_token", ""))
        ctk.CTkEntry(body, textvariable=self._apify_var, width=500, show="•").pack(
            fill="x", padx=4, pady=2,
        )

        # ---- Keyword list[Any] (placeholder) ------------------------------
        ctk.CTkLabel(body, text="Keyword tags (comma-separated)", font=("", 12, "bold")).pack(
            anchor="w", padx=4, pady=(10, 2),
        )
        self._keywords_text = ctk.CTkTextbox(body, height=60)
        self._keywords_text.pack(fill="x", padx=4, pady=2)
        kw_str = ", ".join(data.get("keyword_list") or [])
        self._keywords_text.insert("1.0", kw_str)

        # ---- AI prompt template --------------------------------------
        ctk.CTkLabel(body, text="AI prompt template", font=("", 12, "bold")).pack(
            anchor="w", padx=4, pady=(10, 2),
        )
        self._ai_prompt_text = ctk.CTkTextbox(body, height=120)
        self._ai_prompt_text.pack(fill="x", padx=4, pady=2)
        self._ai_prompt_text.insert("1.0", data.get("ai_prompt_template", ""))

        # ---- Buttons -------------------------------------------------
        btns = ctk.CTkFrame(top, fg_color="transparent")
        btns.pack(fill="x", padx=8, pady=(0, 8))
        ctk.CTkButton(
            btns, text="Reset defaults", command=self._reset_defaults,
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            btns, text="Cancel", command=top.destroy,
        ).pack(side="right", padx=4)
        ctk.CTkButton(
            btns, text="Save", fg_color="#1f6aa5", command=self._save_and_close,
        ).pack(side="right", padx=4)

    def _reset_defaults(self) -> None:
        defaults = settings_store.reset_defaults()
        if self._dump_root_var is not None:
            self._dump_root_var.set(defaults["dump_root"])
        if self._obsidian_var is not None:
            self._obsidian_var.set(defaults["obsidian_vault"])
        if self._apify_var is not None:
            self._apify_var.set(defaults["apify_token"])
        if self._keywords_text is not None:
            self._keywords_text.delete("1.0", "end")
        if self._ai_prompt_text is not None:
            self._ai_prompt_text.delete("1.0", "end")

    def _save_and_close(self) -> None:
        kw_str = self._keywords_text.get("1.0", "end").strip() if self._keywords_text else ""
        kw_list = [k.strip() for k in kw_str.split(",") if k.strip()]
        data = {
            "dump_root": self._dump_root_var.get() if self._dump_root_var else "",
            "obsidian_vault": self._obsidian_var.get() if self._obsidian_var else "",
            "apify_token": self._apify_var.get() if self._apify_var else "",
            "keyword_list": kw_list,
            "ai_prompt_template": self._ai_prompt_text.get("1.0", "end").strip(),
        }
        try:
            settings_store.save(data)
        except OSError as exc:
            from tkinter import messagebox
            messagebox.showerror(
                "Save failed",
                f"Could not save settings:\n{exc}",
            )
            return
        if self._save_cb is not None:
            try:
                self._save_cb(data)
            except Exception:
                # Re-raise so the developer sees the bug; the user's
                # settings are already persisted on disk.
                import logging
                logging.getLogger(__name__).exception("settings save_cb failed")
        if self._top is not None:
            self._top.destroy()


__all__ = ["SettingsDialog"]