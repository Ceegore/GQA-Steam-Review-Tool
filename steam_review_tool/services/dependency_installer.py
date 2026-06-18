"""Install Playwright + Chromium into the external Python interpreter.

Runs the heavy lifting in a worker thread so the GUI stays responsive,
and reports progress via a callback so the caller can update a log
text widget without coupling.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import Callable, Optional

from .python_runtime import find_external_python


def _find_python() -> Optional[str]:
    return find_external_python()


def install_playwright(
    log_cb: Callable[[str], None],
    on_done: Callable[[bool, str], None],
) -> None:
    """Install the ``playwright`` package via pip into an external Python.

    Falls back to bootstrapping pip from ``get-pip.py`` if pip is
    missing in the target interpreter.
    """
    python_exe = _find_python()
    if not python_exe:
        on_done(False, (
            "Could not find a working Python interpreter on the system.\n"
            "Please install Python 3.10+ from https://www.python.org/downloads/\n"
            "(make sure to tick 'Add Python to PATH' during install)."
        ))
        return

    log_cb(f"Using Python: {python_exe}")
    helper = Path(tempfile.gettempdir()) / "_srt_install_pw.py"
    helper.write_text(
        "import subprocess, sys\n"
        "rc = subprocess.call([sys.executable, '-m', 'pip', 'install', 'playwright'])\n"
        "sys.exit(rc)\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [python_exe, str(helper)],
        capture_output=True, text=True, timeout=300,
    )
    if result.returncode == 0:
        on_done(True, "Playwright installed.")
        return

    stderr = (result.stderr or "") + (result.stdout or "")
    if "No module named pip" in stderr or "pip" in stderr.lower():
        log_cb("pip missing in target Python, bootstrapping from get-pip.py…")
        try:
            tmp = Path(tempfile.gettempdir()) / "get-pip.py"
            urllib.request.urlretrieve(
                "https://bootstrap.pypa.io/get-pip.py", str(tmp),
            )
            boot = subprocess.run(
                [python_exe, str(tmp)],
                capture_output=True, text=True, timeout=120,
            )
            if boot.returncode != 0:
                raise RuntimeError(boot.stderr or boot.stdout)
            log_cb("pip bootstrapped. Retrying playwright install…")
            result = subprocess.run(
                [python_exe, str(helper)],
                capture_output=True, text=True, timeout=300,
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr or result.stdout)
            on_done(True, "Playwright installed after pip bootstrap.")
            return
        except Exception as exc:
            on_done(False, f"Bootstrap failed: {exc}")
            return

    on_done(False, f"Install failed (exit {result.returncode}): {stderr[-800:]}")


def install_chromium(
    log_cb: Callable[[str], None],
    on_done: Callable[[bool, str], None],
) -> None:
    """Download the Playwright Chromium binary (~150 MB)."""
    python_exe = _find_python()
    if not python_exe:
        on_done(False, "Could not find Python to run 'playwright install'.")
        return

    helper = Path(tempfile.gettempdir()) / "_srt_install_chrome.py"
    helper.write_text(
        "import subprocess, sys\n"
        "rc = subprocess.call([sys.executable, '-m', 'playwright', 'install', 'chromium'])\n"
        "sys.exit(rc)\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [python_exe, str(helper)],
        capture_output=True, text=True, timeout=600,
    )
    if result.returncode != 0:
        on_done(False, (
            result.stderr or result.stdout or "Unknown error"
        )[-1000:])
        return
    on_done(True, "Chromium downloaded.")


def open_pw_cache() -> Optional[str]:
    """Open the Playwright browser cache folder. Returns an error message
    if it doesn't exist yet, otherwise ``None``.
    """
    cache = Path.home() / "AppData" / "Local" / "ms-playwright"
    if not cache.exists():
        return (
            f"Playwright cache folder does not exist yet:\n{cache}\n\n"
            "It will be created when you install Chromium."
        )
    try:
        if sys.platform == "win32":
            # Use os.startfile so Explorer opens the actual folder.
            # (Passing `"explore"` to ``Path.open`` was dead code —
            # Path.open takes a file mode, not an Explorer verb.)
            os.startfile(str(cache))  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(cache)])
        else:
            opener = shutil.which("xdg-open") or "xdg-open"
            subprocess.Popen([opener, str(cache)])
    except Exception as exc:
        return str(exc)
    return None


__all__ = ["install_playwright", "install_chromium", "open_pw_cache"]