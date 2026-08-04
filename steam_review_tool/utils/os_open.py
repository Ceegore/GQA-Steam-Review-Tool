"""Cross-platform helper for "open this path in the OS file manager".

The platform-specific incantations lived in 4 different places
(``controllers/action_handler.open_in_editor``,
``controllers/dump_folder_controller._default_open``,
``services/dependency_installer.open_pw_cache``,
``ui/popup_search._open_in_editor``) and they were all
copy-pastes of the same 8-line ``if sys.platform == …`` ladder.
Each copy was a small drift hazard: a future fix to one site
(e.g. validating that the path exists first) had to be applied
to all four by hand.

The single source-of-truth lives here. Every caller either
imports ``open_path_in_os`` directly or wraps it in a thin
"return error string on failure" adapter.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional


def open_path_in_os(path: Path) -> Optional[str]:
    """Open ``path`` in the OS file manager / default application.

    Returns ``None`` on success and a human-readable error string
    on failure (so the caller can show it in the GUI log). The
    error string is intentionally the raw exception text — the
    Tk dialog that wraps this will display it verbatim.

    The ``subprocess.Popen`` calls on macOS and Linux are
    fire-and-forget; if the user's ``open`` / ``xdg-open`` command
    is missing or fails, the function returns the resulting
    ``FileNotFoundError`` / ``OSError`` as an error string. We
    intentionally do not ``wait()`` the subprocess — opening a
    folder in Explorer / Finder / Nautilus returns control to
    the user immediately, and waiting would block the caller.
    """
    try:
        if sys.platform == "win32":
            # ``os.startfile`` is the canonical way to ask
            # Explorer / the Windows shell to open the file or
            # folder. Raises ``FileNotFoundError`` for missing
            # paths.
            os.startfile(str(path))  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            # Linux / other Unix. ``xdg-open`` is the freedesktop
            # standard. If it isn't installed, the ``Popen`` call
            # raises ``FileNotFoundError`` which we surface as
            # the error string.
            subprocess.Popen(["xdg-open", str(path)])
        return None
    except Exception as exc:
        return str(exc)


__all__ = ["open_path_in_os"]
