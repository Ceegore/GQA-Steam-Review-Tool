# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for Steam Review Analyzer.

Build with:
    pyinstaller build.spec

The refactored code lives in the ``steam_review_tool/`` package; the
``steam_review_tool.py`` shim is a thin entry-point that calls
``steam_review_tool.factories.app_factory.build_app().mainloop()``.

This spec therefore:
  - Bundles the entire ``steam_review_tool`` package via
    ``collect_submodules``.
  - Still points Analysis at ``steam_review_tool.py`` because the .exe
    expects a single entry-point file. That shim does the import + DI
    wiring, then enters the CTk mainloop.
  - Drops CustomTkinter assets + tkinter assets + requests submodules.
"""

from PyInstaller.utils.hooks import collect_all, collect_submodules

# ---------------------------------------------------------------------------
# Collect CustomTkinter assets (themes, fonts, JSON descriptors).
# Without this the UI throws "no default theme" errors at startup.
# ---------------------------------------------------------------------------
ctk_datas, ctk_binaries, ctk_hiddenimports = collect_all("customtkinter")

# Some Python distributions split tkinter into a separate package; collect
# defensively so PyInstaller doesn't miss tcl/tk assets.
try:
    tk_datas, tk_binaries, tk_hiddenimports = collect_all("tkinter")
except Exception:
    tk_datas, tk_binaries, tk_hiddenimports = [], [], []

# requests has no data files, but pull submodules just in case.
requests_hiddenimports = collect_submodules("requests")

# The refactored package — collect every sub-module + submodule so
# nothing is missing from the .exe.
package_hiddenimports = collect_submodules("steam_review_tool")

# Static JS snippets are read by PlaywrightSubprocess at runtime; we
# don't embed them, the worker writes them to %TEMP% each run.

block_cipher = None

a = Analysis(
    ["steam_review_tool.py"],
    pathex=[],
    binaries=ctk_binaries + tk_binaries,
    datas=ctk_datas + tk_datas,
    hiddenimports=(
        ctk_hiddenimports
        + tk_hiddenimports
        + requests_hiddenimports
        + package_hiddenimports
    ),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Trim size: drop modules that are not used at all.
        "matplotlib", "numpy", "scipy", "pandas", "PyQt5", "PyQt6",
        "PySide2", "PySide6", "wx", "IPython", "notebook", "pytest",
        "pytest_asyncio", "sphinx", "setuptools", "pkg_resources",
        "test", "unittest", "lib2to3", "tkinter.test",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="SteamReviewAnalyzer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,            # Compress with UPX if available on PATH
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,        # windowed app: no console window pops up
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon="icon.ico",   # drop a .ico here if you have one
)