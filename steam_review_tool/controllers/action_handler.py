"""Cross-cutting action handlers — copy-to-clipboard, search, open-store, etc.

These don't fit any single tab; they live in their own controller so
the tabs can stay focused on building widgets.
"""
from __future__ import annotations

import os
import tkinter as tk
import webbrowser
from pathlib import Path
from typing import Optional

from ..utils.os_open import open_path_in_os
from ..utils.url_utils import MAX_STEAM_APP_ID, resolve_app_id


def open_store_page(app_id: int) -> None:
    """Open the Steam store page for ``app_id`` in the user's browser.

    Validates that ``app_id`` is a plausible Steam App ID before
    constructing the URL — otherwise the URL would contain arbitrary
    text the user pasted.
    """
    if not isinstance(app_id, int) or app_id <= 0 or app_id > MAX_STEAM_APP_ID:
        raise ValueError(
            f"invalid app_id for open_store_page: {app_id!r}"
        )
    webbrowser.open_new_tab(f"https://store.steampowered.com/app/{app_id}/")


def open_in_editor(path: Path) -> Optional[str]:
    """Open ``path`` in the OS default application for its type.

    Returns ``None`` on success, an error string on failure, or a
    string error if the path doesn't exist.
    """
    if not path.exists():
        return f"Path does not exist: {path}"
    return open_path_in_os(path)


def copy_to_clipboard(root: tk.Misc, text: str) -> None:
    """Copy ``text`` to the system clipboard via Tk.

    Must be called on the Tk main thread; calling it from a worker
    thread can deadlock the GUI.
    """
    if not isinstance(text, str):
        raise TypeError(f"text must be str, got {type(text).__name__}")
    try:
        root.clipboard_clear()
        root.clipboard_append(text)
    # R32-13: narrow the broad ``except Exception`` to the
    # specific Tk error class. ``root.clipboard_clear()`` and
    # ``root.clipboard_append()`` only raise ``tk.TclError`` (e.g.
    # in headless test environments without a display, or when
    # the clipboard is owned by another process on X11). Catching
    # the bare ``Exception`` would also swallow programming bugs
    # like ``AttributeError`` if ``root`` were ``None``, hiding
    # them as silent no-ops. The R25 lesson (31 UI widget-op
    # narrowings) applies here too — "too-broad except" is the
    # same anti-pattern regardless of whether the body is
    # widget-op or clipboard-op.
    except tk.TclError:
        # Clipboard operations can fail in headless test
        # environments; the user-visible action ("copy") just
        # no-ops in that case.
        pass


def find_latest_dump_md(dump_root: Path) -> Optional[Path]:
    """Return the most recently modified ``GQA Reviewdump_*.md`` file
    under ``dump_root``.

    Filters to the canonical export-name pattern
    (``GQA Reviewdump_*.md``) so the "latest" file is always a real
    export, not a per-language split (``.english.md``), the
    standalone summary (``.summary.md``), the AI-prompt bundle
    (``ai_prompt.md``), or a user-created readme. The old code
    returned ANY ``.md`` file, which made the "Open latest .md"
    and "Search" actions randomly open the AI-prompt bundle
    after a "Save as prompt" run — confusing for the user.

    Uses ``os.scandir`` for speed (avoids the O(n) stat-everything
    walk that ``Path.rglob`` performs), and short-circuits as soon
    as a candidate newer than the running best is found.
    """
    if not dump_root.exists() or not dump_root.is_dir():
        return None

    best: Optional[Path] = None
    best_mtime: float = -1.0

    # Walk the tree iteratively so we can stop early on a hit.
    stack = [dump_root]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                for entry in it:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(Path(entry.path))
                        elif _is_dump_export_md(entry.name):
                            try:
                                mt = entry.stat(follow_symlinks=False).st_mtime
                            except OSError:
                                continue
                            if mt > best_mtime:
                                best_mtime = mt
                                best = Path(entry.path)
                    except OSError:
                        continue
        except OSError:
            continue
    return best


def _is_dump_export_md(name: str) -> bool:
    """``True`` if ``name`` is a canonical export dump file.

    The exporter names every main dump ``GQA Reviewdump_<game>_
    <filter>_<YYYYMMDD-HHMM>.md``. Per-language splits add a
    second dot (``.english.md``), the standalone summary adds
    ``.summary.md``, and the AI-prompt bundle is ``ai_prompt.md``
    — all of which should NOT be returned as "the latest dump".
    """
    if not name.startswith("GQA Reviewdump_") or not name.endswith(".md"):
        return False
    # The part before ``.md`` must be the timestamp stem — no
    # extra dots (which would mean per-language / summary).
    stem = name[:-3]  # strip ".md"
    return "." not in stem


__all__ = [
    "open_store_page",
    "open_in_editor",
    "copy_to_clipboard",
    "find_latest_dump_md",
]