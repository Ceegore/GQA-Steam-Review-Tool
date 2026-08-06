"""Help dialog: a scrollable Markdown walk-through of the main workflows."""
from __future__ import annotations

import tkinter as tk
from typing import Optional, Any

import customtkinter as ctk


HELP_TEXT = """\
# GQA Steam Review Tool — How to use

A small, focused PM/QA tool for early-game review analysis. The
output is designed to be fed to an AI (ChatGPT, Claude, etc.)
for fast, structured analysis.

## Recommended workflow (5 min per game)

1. **Load the game** (Steam API tab): paste the App ID, hit Enter.
2. **Fetch new reviews** (green button in the action bar): pulls only
   reviews you haven't dumped before.
3. **Open Top complaints**: see the most-common complaint / praise
   themes with example quotes.
4. **Copy + AI prompt**: copies the latest .md + your custom prompt
   template to the clipboard.
5. **Refresh trends**: scrapes current wishlist / follower / review
   counts and records a new data point.

## Tips

- **Use the Steam API tab** for established games (cache miss delay ~0h).
- **Use the Playwright tab** for new releases (last 24-72h,
  bypasses cache). Playwright launches a real headless Chromium
  and hits Steam's un-cached AJAX endpoint, so you can review a
  freshly released title the same day it launches.
- **Settings → AI prompt template**: edit the template used for
  Copy + AI prompt. Placeholders: `{name}`, `{app_id}`, `{n}`.
- **Settings → Keyword tags**: comma-separated list of words/phrases
  to highlight in the .md export.
- **Search the latest dump** with the 🔍 Search button.

## Keyboard shortcuts

- `Ctrl+F` — Start a Steam API fetch
- `Ctrl+Shift+F` — "Fetch new" (dedup + auto-export)
- `Ctrl+S` — Stop the current fetch
- `Ctrl+E` — Export to .md
- `Ctrl+W` — Toggle watch mode
- `Ctrl+P` — Start a Playwright scrape
- `Ctrl+Shift+P` — Playwright "Fetch new"
- `Ctrl+R` — Resume a stopped fetch

## Where are my files?

- Main dump folder: shown in the **status bar** at the bottom of the
  window and in each tab's Game section.
- Per-game folder: `<main>/<app_id>_<game_name>/`.

---

GQA — Game Quality Assurance (https://gqa.gmbh/). A purpose-built
tool for early-game review analysis, built to save a QA analyst
an afternoon of copy-paste.

Author: **Christoph Möbius** (https://gqa.gmbh/) — feedback and bug
reports welcome.
"""


class HelpDialog:
    """Scrollable Markdown guide."""

    def __init__(self, master) -> None:
        self.master = master
        self._top: Optional[ctk.CTkToplevel] = None

    def open(self) -> None:
        if self._top is not None and self._top.winfo_exists():
            self._top.focus()
            return
        self._top = ctk.CTkToplevel(self.master)
        self._top.title("How to use the GQA Steam Review Tool")
        self._top.geometry("720x680")
        self._top.transient(self.master)
        self._build()

    def _build(self) -> None:
        # R32-3: replace the type-narrowing ``assert top is not None``
        # with an early-return guard (see popup_batch_dump for the
        # full reasoning — ``assert`` is stripped under ``python -O``).
        top = self._top
        if top is None:
            return

        frame = ctk.CTkFrame(top)
        frame.pack(fill="both", expand=True, padx=8, pady=8)

        text = tk.Text(
            frame, wrap="word", bg="#1a1a1a", fg="#e0e0e0",
            insertbackground="#e0e0e0", font=("Segoe UI", 10),
        )
        scroll = ctk.CTkScrollbar(frame, command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        text.insert("1.0", HELP_TEXT)
        # ``state="readonly"`` lets the user select and copy the
        # help text (right-click → Copy, or Ctrl+C) but prevents
        # accidental edits. The old ``state="disabled"`` made
        # the widget completely non-interactive, so the user
        # couldn't even select a snippet to copy into a search.
        text.configure(state="readonly")
        text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        ctk.CTkButton(top, text="Close", command=top.destroy).pack(
            pady=(0, 8),
        )


__all__ = ["HelpDialog", "HELP_TEXT"]
