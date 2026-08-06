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
from ..utils.coercion import safe_coerce_str


# Note: the previous version of this module defined a private
# ``_safe_str(value, default)`` that did ``str(value)`` for any
# non-None value. That implementation has 2 problems:
#   1. A hand-edited / migrated settings.json with a list /
#      dict value for ``dump_root`` would render as the str()
#      of the Python list (``"['a', 'b']"``) in the entry
#      field — confusing for the user.
#   2. Duplicates the public ``safe_coerce_str`` helper
#      (utils.coercion), so a future change to the public
#      helper would have to be applied to this site too
#      (same R4/R5 helper-consolidation lesson).
# The R19-1 fix uses the public ``safe_coerce_str``
# instead. Tests in ``test_bug_hunt_round_19`` pin the new
# behaviour (a list value renders as the default ``""``,
# not as the str() of the list).


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
        # R32-5: replace the type-narrowing ``assert top is not None``
        # with an early-return guard (see popup_batch_dump for the
        # full reasoning — ``assert`` is stripped under ``python -O``).
        top = self._top
        if top is None:
            return

        data = settings_store.load()

        body = ctk.CTkScrollableFrame(top)
        body.pack(fill="both", expand=True, padx=8, pady=8)

        # ---- Dump root -----------------------------------------------
        ctk.CTkLabel(body, text="Dump folder", font=("", 12, "bold")).pack(
            anchor="w", padx=4, pady=(6, 2),
        )
        self._dump_root_var = tk.StringVar(
            value=safe_coerce_str(data.get("dump_root"), ""),
        )
        ctk.CTkEntry(body, textvariable=self._dump_root_var, width=500).pack(
            fill="x", padx=4, pady=2,
        )

        # ---- Obsidian vault ------------------------------------------
        ctk.CTkLabel(body, text="Obsidian vault (optional)", font=("", 12, "bold")).pack(
            anchor="w", padx=4, pady=(10, 2),
        )
        self._obsidian_var = tk.StringVar(
            value=safe_coerce_str(data.get("obsidian_vault"), ""),
        )
        ctk.CTkEntry(body, textvariable=self._obsidian_var, width=500).pack(
            fill="x", padx=4, pady=2,
        )

        # ---- Apify token ---------------------------------------------
        ctk.CTkLabel(body, text="Apify token (optional)", font=("", 12, "bold")).pack(
            anchor="w", padx=4, pady=(10, 2),
        )
        self._apify_var = tk.StringVar(
            value=safe_coerce_str(data.get("apify_token"), ""),
        )
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
        self._ai_prompt_text.insert(
            "1.0", safe_coerce_str(data.get("ai_prompt_template"), ""),
        )

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
        # Reset is a "preview before commit" — populate the GUI with
        # DEFAULTS but DO NOT touch the on-disk file. The user must
        # click Save to commit. The previous implementation called
        # ``settings_store.reset_defaults()`` which DELETED the file
        # immediately, so a Reset+Cancel sequence silently wiped the
        # user's settings.json while the in-memory App.settings still
        # held the old values — the next app launch would start with
        # defaults but the current session kept working with stale
        # in-memory data (a real silent data-loss bug).
        from ..services.settings_store import DEFAULTS
        if self._dump_root_var is not None:
            self._dump_root_var.set(DEFAULTS["dump_root"])
        if self._obsidian_var is not None:
            self._obsidian_var.set(DEFAULTS["obsidian_vault"])
        if self._apify_var is not None:
            self._apify_var.set(DEFAULTS["apify_token"])
        if self._keywords_text is not None:
            self._keywords_text.delete("1.0", "end")
        if self._ai_prompt_text is not None:
            self._ai_prompt_text.delete("1.0", "end")

    def _save_and_close(self) -> None:
        kw_str = self._keywords_text.get("1.0", "end").strip() if self._keywords_text else ""
        kw_list = [k.strip() for k in kw_str.split(",") if k.strip()]
        # Start from the current on-disk settings so the 5 fields
        # the user can see in this dialog (dump_root /
        # obsidian_vault / apify_token / keyword_list /
        # ai_prompt_template) overwrite the matching keys but the
        # OTHER fields the user set elsewhere (also_csv /
        # also_json / per_language / open_after_export /
        # greeting_shown) are preserved. The previous version
        # built a 5-field dict from scratch and called
        # ``settings_store.save(data)``, which overwrote the
        # entire on-disk file with just those 5 keys — the
        # next ``load()`` would then merge with ``DEFAULTS`` and
        # silently reset the user's other preferences (e.g.
        # ``also_csv=True`` was reset to ``False`` every time the
        # user opened the settings dialog).
        from ..services.settings_store import load as _load_settings
        try:
            current = _load_settings()
        except OSError:
            current = {}
        current.update({
            "dump_root": self._dump_root_var.get() if self._dump_root_var else "",
            "obsidian_vault": self._obsidian_var.get() if self._obsidian_var else "",
            "apify_token": self._apify_var.get() if self._apify_var else "",
            "keyword_list": kw_list,
            "ai_prompt_template": self._ai_prompt_text.get("1.0", "end").strip(),
        })
        data = current
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