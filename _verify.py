"""Permanent verification script. Run with::

    python _verify.py

Exits 0 if the package is in a healthy state, 1 otherwise. Kept in
the repo as a pre-commit-style sanity gate.
"""
from __future__ import annotations

import os
import sys
import traceback


def line_count(path: str) -> int:
    with open(path, encoding="utf-8") as f:
        return sum(1 for _ in f)


def main() -> int:
    # 1. All modules import cleanly
    modules: list[str] = []
    for root, _, files in os.walk("steam_review_tool"):
        for f in files:
            if f.endswith(".py") and not f.startswith("__"):
                rel = os.path.join(root, f)
                modules.append(rel[:-3].replace(os.sep, "."))

    failed: list[tuple[str, str]] = []
    for m in modules:
        try:
            __import__(m)
        except Exception as exc:
            failed.append((m, f"{type(exc).__name__}: {exc}"))

    print(f"Modules:       {len(modules)} ({len(failed)} failures)")
    for m, e in failed:
        print(f"  FAIL: {m}: {e}")

    # 2. No file over 500 lines
    sizes: list[tuple[int, str]] = []
    for root, _, files in os.walk("steam_review_tool"):
        for f in files:
            if f.endswith(".py") and not f.startswith("__"):
                p = os.path.join(root, f)
                sizes.append((line_count(p), p))
    over = [(n, p) for n, p in sizes if n > 500]
    print(f"Files > 500:   {len(over)}")
    for n, p in over:
        print(f"  LARGE: {n} lines: {p}")

    # 3. App build (headless)
    print("App build:     ", end="")
    try:
        from steam_review_tool.factories.app_factory import build_app
        app = build_app()
        app.update_idletasks()
        app.destroy()
        print("OK")
    except Exception:
        traceback.print_exc()
        print("FAIL")
        return 1

    # 4. Old monolith still ships as a back-compat shim
    if os.path.exists("steam_review_tool.py"):
        orig = line_count("steam_review_tool.py")
        print(f"Old monolith:  {orig} lines (preserved)")
    else:
        print("Old monolith:  MISSING (was deleted)")

    # Final verdict
    if failed or over:
        print()
        print("STATUS: FAIL")
        return 1
    print()
    print("STATUS: PASS")
    print(f"  {len(modules)} modules, "
          f"avg {sum(n for n, _ in sizes) // len(sizes)} lines/file, "
          f"max {max(n for n, _ in sizes)} lines.")
    return 0


if __name__ == "__main__":
    sys.exit(main())