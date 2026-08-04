"""Search-window popup.

Searches a loaded ``.md`` export by full-text query + sentiment +
min-helpful filters. Mirrors the original SearchWindow.
"""
from __future__ import annotations

import re
import tkinter as tk
from pathlib import Path
from typing import Optional

import customtkinter as ctk

from ..utils.os_open import open_path_in_os


class SearchWindow:
    """A modal that lets the user grep through an exported ``.md``."""

    def __init__(
        self,
        master,
        title: str,
        text: str,
        file_path: str,
    ) -> None:
        self.master = master
        self.title = title
        self.text = text
        self.file_path = file_path
        self._top: Optional[ctk.CTkToplevel] = None
        self._query_var: Optional[tk.StringVar] = None
        self._sentiment_var: Optional[tk.StringVar] = None
        self._min_helpful_var: Optional[tk.StringVar] = None
        self._status_lbl: Optional[ctk.CTkLabel] = None
        self._results_box: Optional[ctk.CTkTextbox] = None
        self._after_id: Optional[str] = None

    # ---- public --------------------------------------------------------

    def open(self) -> None:
        if self._top is not None and self._top.winfo_exists():
            self._top.focus()
            return
        self._top = ctk.CTkToplevel(self.master)
        self._top.title(self.title)
        self._top.geometry("780x560")
        self._top.transient(self.master)
        self._build()

    # ---- internals -----------------------------------------------------

    def _build(self) -> None:
        top = self._top
        assert top is not None

        bar = ctk.CTkFrame(top, fg_color="transparent")
        bar.pack(fill="x", padx=8, pady=8)

        ctk.CTkLabel(bar, text="Query:", width=80, anchor="e").pack(
            side="left", padx=(0, 4),
        )
        self._query_var = tk.StringVar()
        self._query_var.trace_add("write", lambda *_: self._schedule_search())
        entry = ctk.CTkEntry(bar, textvariable=self._query_var, width=200)
        entry.pack(side="left", padx=4)
        entry.focus_set()

        ctk.CTkLabel(bar, text="Sentiment:", width=80, anchor="e").pack(
            side="left", padx=(8, 4),
        )
        self._sentiment_var = tk.StringVar(value="all")
        ctk.CTkOptionMenu(
            bar, values=["all", "positive", "negative"],
            variable=self._sentiment_var, width=100,
            command=lambda _v: self._schedule_search(),
        ).pack(side="left", padx=4)

        ctk.CTkLabel(bar, text="Min helpful:", width=80, anchor="e").pack(
            side="left", padx=(8, 4),
        )
        self._min_helpful_var = tk.StringVar(value="0")
        self._min_helpful_var.trace_add(
            "write", lambda *_: self._schedule_search(),
        )
        ctk.CTkEntry(
            bar, textvariable=self._min_helpful_var, width=60,
        ).pack(side="left", padx=4)

        ctk.CTkButton(
            bar, text="Open in editor", command=self._open_in_editor, width=120,
        ).pack(side="right", padx=4)

        self._status_lbl = ctk.CTkLabel(top, text="Type to search…", anchor="w")
        self._status_lbl.pack(fill="x", padx=12, pady=(0, 4))

        self._results_box = ctk.CTkTextbox(top)
        self._results_box.pack(fill="both", expand=True, padx=8, pady=8)
        self._set_results("(no query yet)")

    def _schedule_search(self) -> None:
        top = self._top
        if top is None:
            return
        if self._after_id is not None:
            try:
                top.after_cancel(self._after_id)
            except Exception:
                pass
        self._after_id = top.after(180, self._run_search)

    def _open_in_editor(self) -> None:
        # The cross-platform "open this path in the OS file manager"
        # helper now lives in ``utils.os_open``. The previous
        # 4-copy-paste of ``os.startfile / Popen / xdg-open`` was
        # a small drift hazard: a future fix to one site had to be
        # applied to all four.
        err = open_path_in_os(Path(self.file_path))
        if err is not None:
            tk.messagebox.showerror("Open failed", err)  # type: ignore[attr-defined]

    def _run_search(self) -> None:
        if self._top is None:
            return
        query_var = self._query_var
        sentiment_var = self._sentiment_var
        helpful_var = self._min_helpful_var
        if query_var is None or sentiment_var is None or helpful_var is None:
            return
        query = (query_var.get() or "").strip().lower()
        sentiment = sentiment_var.get()
        try:
            min_helpful = int(helpful_var.get() or 0)
        except ValueError:
            min_helpful = 0

        if not query and sentiment == "all" and min_helpful == 0:
            if self._status_lbl is not None:
                self._status_lbl.configure(text="Type to search…")
            self._set_results("(no query yet)")
            return

        blocks: list[tuple[str, str, str]] = []  # (rid, label, text)
        current_rid: Optional[str] = None
        current_label: Optional[str] = None
        current_lines: list[str] = []
        for line in self.text.splitlines():
            if line.startswith("### Review #"):
                if current_label is not None:
                    blocks.append((
                        current_rid or "?", current_label,
                        "\n".join(current_lines),
                    ))
                try:
                    # Strip the leading ``### Review #`` (the heading
                    # prefix) so we keep just the number, not
                    # ``# Review #1``. The previous ``line.split("#", 2)``
                    # dropped only the first two ``#``s and left a third
                    # in the suffix, producing labels like
                    # ``Review ## Review #1``.
                    num = line.split("### Review #", 1)[1].strip()
                except Exception:
                    num = "?"
                current_label = f"Review #{num}"
                current_rid = None
                current_lines = []
            elif line.strip() == "---" and current_label is not None:
                blocks.append((
                    current_rid or "?", current_label,
                    "\n".join(current_lines),
                ))
                current_label = None
                current_rid = None
                current_lines = []
            elif current_label is not None:
                m = re.search(r"^\| Author \| `(\d+)`", line)
                if m:
                    current_rid = m.group(1)
                current_lines.append(line)

        if current_label is not None:
            blocks.append((
                current_rid or "?", current_label,
                "\n".join(current_lines),
            ))

        # Filter blocks
        results: list[str] = []
        for rid, label, text in blocks:
            # Sentiment filter (heuristic by "Positive"/"Negative" cell)
            if sentiment != "all":
                # The previous version's nested-ternary on lines 175-178
                # had a precedence bug: when "Recommendation" was missing
                # the inline ``else True`` made EVERY block match,
                # ignoring the sentiment filter entirely.
                rec_idx = text.find("Recommendation")
                if rec_idx == -1:
                    continue  # malformed block — skip rather than match all
                rec_cell = text[rec_idx:rec_idx + 80]
                if sentiment == "positive" and "Positive" not in rec_cell:
                    continue
                if sentiment == "negative" and "Negative" not in rec_cell:
                    continue
            # Min-helpful filter
            if min_helpful > 0:
                m = re.search(r"\| Helpful count \| (\d+) \|", text)
                if not m or int(m.group(1)) < min_helpful:
                    continue
            # Text query
            if query and query not in text.lower():
                continue
            results.append(f"### {label}\n\n{text[:600]}\n")

        if not results:
            if self._status_lbl is not None:
                self._status_lbl.configure(text="0 matches")
            self._set_results("(no matches)")
            return
        if self._status_lbl is not None:
            self._status_lbl.configure(text=f"{len(results)} matches")
        self._set_results("\n---\n".join(results))

    def _set_results(self, text: str) -> None:
        if self._results_box is None:
            return
        # Toggle to ``normal`` for the insert, then back to
        # ``readonly`` so the user can select and copy the
        # matching review blocks (e.g. for a bug report) but
        # cannot accidentally edit them. The old
        # ``state="disabled"`` made the widget completely
        # non-interactive — the user couldn't even select a
        # snippet to copy.
        self._results_box.configure(state="normal")
        self._results_box.delete("1.0", "end")
        self._results_box.insert("1.0", text)
        self._results_box.configure(state="readonly")


__all__ = ["SearchWindow"]