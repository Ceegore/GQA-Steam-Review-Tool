"""Entry point for the refactored Steam Review Analyzer.

Run with::

    python main.py

The old monolithic ``steam_review_tool.py`` still ships as a
back-compat shim; new work should import from ``steam_review_tool.*``.
"""
from __future__ import annotations

from steam_review_tool.core.logger import configure_logging
from steam_review_tool.factories.app_factory import build_app


def main() -> None:
    configure_logging()
    app = build_app()
    app.mainloop()


if __name__ == "__main__":
    main()