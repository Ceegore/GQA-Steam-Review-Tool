"""Headless smoke tests for the App + factory.

Each test launches the app in a SUBPROCESS so the Tcl interpreter
is fully isolated. This avoids "main thread is not in main loop"
errors that occur when multiple ``ctk.CTk()`` roots are created and
destroyed in the same pytest process.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


_HELPER = """
import sys
from steam_review_tool.factories.app_factory import build_app
try:
    app = build_app(**{k: v for k, v in __kwargs.items() if v is not None or k != "settings"})
    ok = (
        app.title() == "GQA Steam Review Tool"
        and len(app.tabview._tab_dict) == 3
    )
    if __kwargs.get("settings") is not None:
        ok = ok and app.settings["keyword_list"] == ["graphics", "crash"]
    if __kwargs.get("settings") is None:
        ok = ok and app.dump_repo.dump_root.exists()
    app.destroy()
    print("PASS" if ok else "FAIL")
except Exception as exc:
    print(f"FAIL:{type(exc).__name__}:{exc}")
"""


def _run_app_subprocess(extra_args: dict) -> tuple[int, str]:
    """Run the App-construction snippet in a fresh Python process."""
    args = " ".join(f"--{k.replace('_', '-')}={v!r}"
                   for k, v in extra_args.items())
    script = _HELPER.replace(
        "__kwargs", repr(extra_args).replace("'", '"'),
    )
    # Building the App spins up CustomTkinter (3 s) + 3 tabs (each
    # builds 4-8 widgets inside a CTkScrollableFrame, which in turn
    # triggers a reflow per resize). On a slow Windows VM the whole
    # stack takes ~50 s — the previous 30 s timeout was a false-fail
    # waiting to happen. 120 s is well clear of the worst observed
    # time and still short enough to surface a real hang.
    proc = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True, text=True, timeout=120,
        cwd=str(Path(__file__).resolve().parent.parent.parent),
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def test_factory_builds_app():
    rc, out = _run_app_subprocess({})
    assert "PASS" in out, f"App build failed: {out!r}"


def test_app_with_overrides():
    rc, out = _run_app_subprocess({
        "settings": {
            "dump_root": "",
            "obsidian_vault": "",
            "apify_token": "",
            "keyword_list": ["graphics", "crash"],
            "ai_prompt_template": "",
        },
    })
    assert "PASS" in out, f"App with overrides failed: {out!r}"


def test_app_resolve_dump_root_with_none_settings():
    """Regression: Path(None) crash when settings is None or empty."""
    # Pass nothing → settings=None in the factory.
    rc, out = _run_app_subprocess({})
    assert "PASS" in out, f"App with None settings failed: {out!r}"