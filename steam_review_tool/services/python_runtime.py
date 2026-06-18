"""Locate a usable Python interpreter for pip / Playwright.

When the app is frozen into a .exe we no longer have ``sys.executable``
as our running interpreter. This helper searches PATH and common
Windows install locations for one we can shell out to.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional


def find_external_python() -> Optional[str]:
    """Return a path to a Python interpreter usable from a frozen .exe.

    Strategy:
      1. If we are NOT in a frozen binary, ``sys.executable`` is correct.
      2. Otherwise, search PATH for python/python3/py.
      3. Otherwise, probe common Windows install locations.
    """
    if not getattr(sys, "frozen", False):
        return sys.executable

    for name in ("python", "python3", "py"):
        path = shutil.which(name)
        if path:
            return path

    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Python" / "Python312" / "python.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Python" / "Python311" / "python.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Python" / "Python310" / "python.exe",
        Path("C:/Python312/python.exe"),
        Path("C:/Python311/python.exe"),
        Path("C:/Python310/python.exe"),
        Path(os.environ.get("PROGRAMFILES", "")) / "Python312" / "python.exe",
        Path(os.environ.get("PROGRAMFILES", "")) / "Python311" / "python.exe",
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return None


def probe_external_python(snippet: str, timeout: int = 30) -> tuple[bool, str]:
    """Run ``snippet`` in an external Python and return (ok, output).

    Used to verify that ``import playwright`` / ``playwright install``
    actually works against the discovered interpreter.
    """
    py = find_external_python()
    if not py:
        return False, "No Python interpreter found"
    try:
        proc = subprocess.run(
            [py, "-c", snippet],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        return proc.returncode == 0, out
    except Exception as exc:
        return False, str(exc)


__all__ = ["find_external_python", "probe_external_python"]