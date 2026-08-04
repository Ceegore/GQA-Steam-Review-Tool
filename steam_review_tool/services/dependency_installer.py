"""Install Playwright + Chromium into the external Python interpreter.

Runs the heavy lifting in a worker thread so the GUI stays responsive,
and reports progress via a callback so the caller can update a log
text widget without coupling.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import Callable, Optional

from ..utils.os_open import open_path_in_os
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
    # Each helper script we write into the system temp dir gets an
    # explicit try/finally cleanup. Without it, every install attempt
    # left a stale ``_srt_install_pw.py`` / ``_srt_install_chrome.py`` /
    # ``get-pip.py`` behind in ``%TEMP%`` — accumulating one file per
    # user click and (on Windows) eventually tripping AV heuristics.
    try:
        try:
            result = subprocess.run(
                [python_exe, str(helper)],
                capture_output=True, text=True, timeout=300,
            )
        except subprocess.TimeoutExpired as exc:
            # ``TimeoutExpired`` carries the partial stdout / stderr
            # of the still-running subprocess — the user wants to
            # know WHAT pip printed before it hung (e.g. "downloading
            # 47 / 152 MB"). The old broad ``except Exception``
            # caught the timeout and reported a misleading
            # "Install failed to launch: Command timed out after
            # 300 seconds" — the install DID launch, it just took
            # too long.
            partial = (exc.stdout or "") + (exc.stderr or "")
            tail = partial[-800:] if partial else "(no output captured)"
            on_done(
                False,
                f"Install timed out after 300s.\nLast output:\n{tail}",
            )
            return
        except (FileNotFoundError, OSError) as exc:
            on_done(
                False,
                f"Install failed to launch: {exc}",
            )
            return
        except Exception as exc:
            # Defensive catch-all for unexpected subprocess errors
            # (e.g. ``KeyboardInterrupt`` propagated through the
            # worker, or a future Python version adding a new
            # exception subclass).
            on_done(False, f"Install failed: {type(exc).__name__}: {exc}")
            return
        if result.returncode == 0:
            on_done(True, "Playwright installed.")
            return

        stderr = (result.stderr or "") + (result.stdout or "")
        # Match the specific "pip is missing" signals (CPython prints
        # one of these variants) — NOT a bare ``"pip"`` substring,
        # which also matches legitimate install errors like
        # "Could not install requirement pip-23.0.1" and would
        # trigger a needless get-pip.py download.
        pip_missing_signals = (
            "No module named pip",
            "No module named 'pip'",
            "No module named \"pip\"",
        )
        if any(s in stderr for s in pip_missing_signals):
            log_cb("pip missing in target Python, bootstrapping from get-pip.py…")
            try:
                tmp = Path(tempfile.gettempdir()) / "get-pip.py"
                urllib.request.urlretrieve(
                    "https://bootstrap.pypa.io/get-pip.py", str(tmp),
                )
                try:
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
                finally:
                    try:
                        tmp.unlink()
                    except OSError:
                        pass
            except Exception as exc:
                on_done(False, f"Bootstrap failed: {exc}")
                return

        on_done(False, f"Install failed (exit {result.returncode}): {stderr[-800:]}")
    finally:
        try:
            helper.unlink()
        except OSError:
            pass


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
    try:
        try:
            result = subprocess.run(
                [python_exe, str(helper)],
                capture_output=True, text=True, timeout=600,
            )
        except subprocess.TimeoutExpired as exc:
            # Same pattern as ``install_playwright`` — surface the
            # partial output instead of a misleading "Install failed
            # to launch" message.
            partial = (exc.stdout or "") + (exc.stderr or "")
            tail = partial[-1000:] if partial else "(no output captured)"
            on_done(
                False,
                f"Chromium download timed out after 600s.\n"
                f"Last output:\n{tail}",
            )
            return
        except (FileNotFoundError, OSError) as exc:
            on_done(
                False,
                f"Install failed to launch: {exc}",
            )
            return
        except Exception as exc:
            on_done(False, f"Install failed: {type(exc).__name__}: {exc}")
            return
        if result.returncode != 0:
            on_done(False, (
                result.stderr or result.stdout or "Unknown error"
            )[-1000:])
            return
        on_done(True, "Chromium downloaded.")
    finally:
        try:
            helper.unlink()
        except OSError:
            pass


def open_pw_cache() -> Optional[str]:
    """Open the Playwright browser cache folder. Returns an error message
    if it doesn't exist yet, otherwise ``None``.

    The cache path differs by platform:
      * Windows: ``%LOCALAPPDATA%\\ms-playwright`` (preferred) or
        ``%USERPROFILE%\\AppData\\Local\\ms-playwright`` (fallback).
      * macOS:   ``~/Library/Caches/ms-playwright``.
      * Linux:   ``$XDG_CACHE_HOME/ms-playwright`` (defaults to
        ``~/.cache/ms-playwright``).

    The previous hard-coded Windows path silently returned
    "does not exist yet" on macOS/Linux because the user has no
    ``~/AppData/Local`` directory.
    """
    if sys.platform == "win32":
        local_app = os.environ.get("LOCALAPPDATA")
        if local_app:
            cache = Path(local_app) / "ms-playwright"
        else:
            cache = Path.home() / "AppData" / "Local" / "ms-playwright"
    elif sys.platform == "darwin":
        cache = Path.home() / "Library" / "Caches" / "ms-playwright"
    else:
        # Linux / other Unix: honour $XDG_CACHE_HOME, fall back to
        # ``~/.cache`` per the freedesktop spec.
        xdg = os.environ.get("XDG_CACHE_HOME")
        cache = (
            Path(xdg) / "ms-playwright" if xdg
            else Path.home() / ".cache" / "ms-playwright"
        )
    if not cache.exists():
        return (
            f"Playwright cache folder does not exist yet:\n{cache}\n\n"
            "It will be created when you install Chromium."
        )
    # The cross-platform "open this path in the OS file manager"
    # helper lives in ``utils.os_open``. The previous
    # ``shutil.which("xdg-open") or "xdg-open"`` was a no-op
    # fallback: if xdg-open wasn't on PATH, we still ended up
    # calling ``subprocess.Popen(["xdg-open", ...])`` which
    # raised ``FileNotFoundError`` (now routed through the
    # helper and returned as a normal error string).
    return open_path_in_os(cache)


__all__ = ["install_playwright", "install_chromium", "open_pw_cache"]