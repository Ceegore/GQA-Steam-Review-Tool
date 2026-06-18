"""Central logger factory.

Wraps ``logging.getLogger`` so modules can do::

    from steam_review_tool.core.logger import get_logger
    log = get_logger(__name__)

without each module having to configure handlers/formatters. The
handlers are configured once at app startup (see ``main.py``).
"""
from __future__ import annotations

import logging
import sys
from typing import Optional

_CONFIGURED = False


def configure_logging(level: int = logging.INFO) -> None:
    """Attach a stderr handler the first time it's called (idempotent)."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(
        logging.Formatter("[%(asctime)s] %(levelname)s %(name)s: %(message)s",
                          datefmt="%H:%M:%S")
    )
    root = logging.getLogger("steam_review_tool")
    root.addHandler(handler)
    root.setLevel(level)
    _CONFIGURED = True


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Return a logger under the ``steam_review_tool`` namespace."""
    if name is None:
        return logging.getLogger("steam_review_tool")
    if not name.startswith("steam_review_tool"):
        name = f"steam_review_tool.{name}"
    return logging.getLogger(name)


__all__ = ["configure_logging", "get_logger"]