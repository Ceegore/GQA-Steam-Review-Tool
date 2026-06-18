"""Shared secondary actions used by both the API and Playwright tabs.

The tab controllers (`tab_api`, `tab_playwright`) compose one instance
of ``TabActions`` to delegate cross-cutting handlers (summary, search,
batch, AI prompt, open-store, open-latest-md) without re-implementing
them in two places.
"""
from __future__ import annotations

from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Any, Callable, Optional

from ..controllers.action_handler import (
    copy_to_clipboard, find_latest_dump_md, open_in_editor, open_store_page,
)
from ..controllers.dump_folder_controller import DumpFolderController
from ..core.event_bus import bus
from ..exporters.per_language_exporter import build_summary
from ..services import settings_store
from .popup_batch_dump import BatchDumpDialog
from .popup_search import SearchWindow
from .popup_top_complaints import TopComplaintsDialog


class TabActions:
    """Mixin-style secondary actions shared by both data-source tabs."""

    def __init__(
        self,
        *,
        master: Any,
        dump_ctrl: DumpFolderController,
        log_fn: Callable[[str], None],
        open_settings_fn: Optional[Callable[[], None]] = None,
    ) -> None:
        self.master = master
        self.dump_ctrl = dump_ctrl
        self._log = log_fn
        self._open_settings = open_settings_fn or (lambda: None)

    # ---- store page --------------------------------------------------

    def open_store(self) -> None:
        if getattr(self.master, "app_id", None) is None:
            self._log("Load a game first.")
            return
        open_store_page(self.master.app_id)

    # ---- summary -----------------------------------------------------

    def write_summary(self) -> None:
        latest = find_latest_dump_md(self.dump_ctrl.dump_root)
        if not latest:
            self._log("No .md dumps found.")
            return
        text = build_summary(
            getattr(self.master, "reviews", []) or [],
            getattr(self.master, "app_details", None),
        )
        out = latest.with_name(latest.stem + ".summary.md")
        try:
            out.write_text(text, encoding="utf-8")
            self._log(f"Summary → {out}")
        except OSError as exc:
            self._log(f"Summary write failed: {exc}")

    # ---- search ------------------------------------------------------

    def search_dump(self) -> None:
        latest = find_latest_dump_md(self.dump_ctrl.dump_root)
        if not latest:
            self._log("No .md dumps found.")
            messagebox.showinfo("Search", "No .md dumps in dump folder yet.")
            return
        try:
            text = latest.read_text(encoding="utf-8")
        except OSError as exc:
            self._log(f"Could not read dump: {exc}")
            return
        SearchWindow(
            self.master,
            title=f"Search — {latest.name}",
            text=text,
            file_path=str(latest),
        ).open()

    # ---- batch -------------------------------------------------------

    def batch_dump(self) -> None:
        dialog = BatchDumpDialog(self.master)
        dialog.open(
            on_run_item=lambda app_id: bus.publish(
                "batch.run_item", app_id=app_id,
            ),
            get_current_app_id=lambda: self.master.app_id,
        )

    # ---- AI prompt ---------------------------------------------------

    def copy_with_ai_prompt(self) -> None:
        latest = find_latest_dump_md(self.dump_ctrl.dump_root)
        if not latest:
            self._log("No .md to copy.")
            return
        settings = settings_store.load()
        prompt = settings.get("ai_prompt_template", "") or ""
        body = f"# Prompt\n{prompt}\n\n# Latest dump\n"
        try:
            body += latest.read_text(encoding="utf-8")
        except OSError as exc:
            self._log(f"Could not read dump: {exc}")
            return
        copy_to_clipboard(self.master, body)
        self._log("Copied latest dump + AI prompt to clipboard.")

    def save_as_prompt(self) -> None:
        latest = find_latest_dump_md(self.dump_ctrl.dump_root)
        if not latest:
            self._log("No .md to bundle.")
            return
        settings = settings_store.load()
        prompt = settings.get("ai_prompt_template", "") or ""
        try:
            dump = latest.read_text(encoding="utf-8")
        except OSError as exc:
            self._log(f"Could not read dump: {exc}")
            return
        out = latest.with_name("ai_prompt.md")
        try:
            out.write_text(
                f"# AI prompt\n{prompt}\n\n# Dump\n{dump}",
                encoding="utf-8",
            )
            self._log(f"Saved prompt bundle → {out}")
        except OSError as exc:
            self._log(f"Save failed: {exc}")

    def quick_view_negatives(self) -> None:
        reviews = getattr(self.master, "reviews", []) or []
        negs = [r for r in reviews if r.get("voted_up") is False]
        if not negs:
            self._log("No negative reviews to view.")
            return
        TopComplaintsDialog(
            self.master, negs, settings_store.load().get("keyword_list"),
        ).open()

    def top_complaints(self) -> None:
        reviews = getattr(self.master, "reviews", []) or []
        if not reviews:
            self._log("No reviews loaded.")
            return
        TopComplaintsDialog(
            self.master, reviews,
            settings_store.load().get("keyword_list"),
        ).open()

    def open_latest_md(self) -> None:
        latest = find_latest_dump_md(self.dump_ctrl.dump_root)
        if not latest:
            self._log("No .md dumps found.")
            return
        err = open_in_editor(latest)
        if err:
            self._log(f"Open failed: {err}")

    def open_dump_folder(self) -> None:
        err = self.dump_ctrl.open_dump_folder()
        if err:
            self._log(err)

    def pick_dump_root(self) -> Optional[Path]:
        path = filedialog.askdirectory(
            title="Pick dump folder",
            initialdir=str(self.dump_ctrl.dump_root),
        )
        if not path:
            return None
        p = Path(path)
        self.dump_ctrl.set_dump_root(p)
        self._log(f"Dump folder → {p}")
        return p

    def pick_obsidian_vault(self) -> None:
        path = filedialog.askdirectory(title="Pick Obsidian vault")
        if not path:
            return
        self.dump_ctrl.obsidian_vault = Path(path)
        self._log(f"Obsidian vault → {path}")

    def clear_obsidian_vault(self) -> None:
        self.dump_ctrl.obsidian_vault = None
        self._log("Obsidian vault cleared.")

    def open_settings(self) -> None:
        self._open_settings()


__all__ = ["TabActions"]