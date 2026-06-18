"""Cross-cutting action handlers — copy-to-clipboard, search, open-store, etc.

These don't fit any single tab; they live in their own controller so
the tabs can stay focused on building widgets.
"""
from __future__ import annotations

import os
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import Optional

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
    try:
        if sys.platform == "win32":
            os.startfile(str(path))  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
        return None
    except Exception as exc:
        return str(exc)


def copy_to_clipboard(root, text: str) -> None:
    """Copy ``text`` to the system clipboard via Tk.

    Must be called on the Tk main thread; calling it from a worker
    thread can deadlock the GUI.
    """
    if not isinstance(text, str):
        raise TypeError(f"text must be str, got {type(text).__name__}")
    try:
        root.clipboard_clear()
        root.clipboard_append(text)
    except Exception:
        # Clipboard operations can fail in headless test environments;
        # the user-visible action ("copy") just no-ops in that case.
        pass


def find_latest_dump_md(dump_root: Path) -> Optional[Path]:
    """Return the most recently modified ``.md`` file under ``dump_root``.

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
                        elif entry.name.endswith(".md"):
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


__all__ = [
    "open_store_page",
    "open_in_editor",
    "copy_to_clipboard",
    "find_latest_dump_md",
]