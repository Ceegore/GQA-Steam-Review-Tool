"""Batch-dump dialog.

Lets the user queue multiple app IDs and fetch them in sequence. Mirrors
the original BatchDumpDialog.
"""
from __future__ import annotations

import threading
from typing import Callable, Optional

import customtkinter as ctk


class BatchDumpDialog:
    """Modal that lets the user queue multiple App IDs and bulk-export.

    The dialog needs two callbacks from the host:
      - ``on_run_item(app_id)``: invoked for each queued app.
      - ``get_current_app_id()``: returns the currently loaded App ID
        or ``None``. Used by the "Add current game" button.
    """

    def __init__(self, master) -> None:
        self.master = master
        self._top: Optional[ctk.CTkToplevel] = None
        self._queue_text: Optional[ctk.CTkTextbox] = None
        self._status_lbl: Optional[ctk.CTkLabel] = None
        self._start_btn: Optional[ctk.CTkButton] = None
        self._stop_flag = threading.Event()
        self._worker: Optional[threading.Thread] = None
        self._on_run_item: Optional[Callable[[int], None]] = None
        self._get_current_app_id: Callable[[], Optional[int]] = lambda: None

    def open(
        self,
        on_run_item: Callable[[int], None],
        get_current_app_id: Callable[[], Optional[int]] = lambda: None,
    ) -> None:
        if self._top is not None and self._top.winfo_exists():
            self._top.focus()
            return
        self._on_run_item = on_run_item
        self._get_current_app_id = get_current_app_id
        self._top = ctk.CTkToplevel(self.master)
        self._top.title("Batch dump")
        self._top.geometry("560x460")
        self._top.transient(self.master)
        self._build()

    def _build(self) -> None:
        top = self._top
        assert top is not None

        ctk.CTkLabel(
            top, text="Queue App IDs (one per line)",
            font=("", 12, "bold"),
        ).pack(anchor="w", padx=10, pady=(10, 2))

        row = ctk.CTkFrame(top, fg_color="transparent")
        row.pack(fill="x", padx=10, pady=2)
        self._queue_text = ctk.CTkTextbox(row, height=200)
        self._queue_text.pack(side="left", fill="both", expand=True)

        ctk.CTkButton(
            row, text="Add current game", command=self._on_add_to_queue,
            width=140,
        ).pack(side="top", padx=4, pady=2)
        ctk.CTkButton(
            row, text="Clear queue", command=self._on_clear_queue,
            width=140,
        ).pack(side="top", padx=4, pady=2)

        self._status_lbl = ctk.CTkLabel(top, text="Ready.", anchor="w")
        self._status_lbl.pack(fill="x", padx=10, pady=(8, 2))

        btns = ctk.CTkFrame(top, fg_color="transparent")
        btns.pack(fill="x", padx=10, pady=(4, 10))
        self._start_btn = ctk.CTkButton(
            btns, text="Start", fg_color="#1f6aa5", command=self._on_start,
        )
        self._start_btn.pack(side="left", padx=4)
        ctk.CTkButton(
            btns, text="Stop", command=self._on_stop,
        ).pack(side="left", padx=4)
        ctk.CTkButton(btns, text="Close", command=self._close).pack(
            side="right", padx=4,
        )

    # ---- handlers ----------------------------------------------------

    def _on_add_to_queue(self) -> None:
        # Resolve the currently-loaded app id via the host callback and
        # queue its integer form. Previously this appended the literal
        # string "current" which the start handler then silently
        # ignored — a no-op bug.
        app_id = self._get_current_app_id()
        if app_id is None:
            if self._status_lbl is not None:
                self._status_lbl.configure(text="No game currently loaded.")
            return
        existing = (self._queue_text.get("1.0", "end") or "").strip() if self._queue_text else ""
        new_line = str(app_id)
        combined = f"{existing}\n{new_line}" if existing else new_line
        if self._queue_text is not None:
            self._queue_text.delete("1.0", "end")
            self._queue_text.insert("1.0", combined)
        if self._status_lbl is not None:
            self._status_lbl.configure(text=f"Queued App {app_id}.")

    def _on_clear_queue(self) -> None:
        if self._queue_text is not None:
            self._queue_text.delete("1.0", "end")
        if self._status_lbl is not None:
            self._status_lbl.configure(text="Queue cleared.")

    def _on_start(self) -> None:
        raw = (self._queue_text.get("1.0", "end") or "").strip() if self._queue_text else ""
        ids: list[int] = []
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            # Accept raw integers OR full Steam URLs / steam:// links.
            if line.isdigit():
                ids.append(int(line))
            else:
                from ..utils.url_utils import resolve_app_id
                aid = resolve_app_id(line)
                if aid:
                    ids.append(aid)
        if not ids:
            if self._status_lbl is not None:
                self._status_lbl.configure(text="No valid App IDs in queue.")
            return
        # Dedupe while preserving order
        seen: set[int] = set()
        deduped: list[int] = []
        for a in ids:
            if a in seen:
                continue
            seen.add(a)
            deduped.append(a)
        self._stop_flag.clear()
        if self._start_btn is not None:
            self._start_btn.configure(state="disabled")
        self._worker = threading.Thread(
            target=self._batch_worker, args=(deduped,), daemon=True,
        )
        self._worker.start()

    def _on_stop(self) -> None:
        self._stop_flag.set()
        if self._status_lbl is not None:
            self._status_lbl.configure(text="Stopping…")

    def _close(self) -> None:
        self._on_stop()
        if self._top is not None:
            self._top.destroy()

    def _batch_worker(self, ids: list[int]) -> None:
        status_lbl = self._status_lbl
        start_btn = self._start_btn
        for i, app_id in enumerate(ids, 1):
            if self._stop_flag.is_set():
                break
            try:
                if self._top is not None and status_lbl is not None:
                    self._top.after(
                        0,
                        lambda i=i, a=app_id: status_lbl.configure(
                            text=f"({i}/{len(ids)}) Processing {a}…"
                        ),
                    )
                if self._on_run_item is not None:
                    self._on_run_item(app_id)
            except Exception as exc:
                if self._top is not None and status_lbl is not None:
                    self._top.after(
                        0,
                        lambda e=exc: status_lbl.configure(
                            text=f"Error: {e}"
                        ),
                    )
        if self._top is not None and start_btn is not None:
            self._top.after(
                0, lambda: start_btn.configure(state="normal"),
            )


__all__ = ["BatchDumpDialog"]