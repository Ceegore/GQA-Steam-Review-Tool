"""Composition root: wire up all services + the App window.

This is the ONLY place that knows which concrete classes to instantiate
and how they connect. Everything else depends on interfaces, so swapping
``SteamAPI`` for a stub in tests is trivial.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Any

from ..core.paths import default_dump_root
from ..core.timezone import current_berlin_str
from ..services.dump_repository import DumpRepository
from ..services.settings_store import load as load_settings
from ..services.steam_api_service import SteamAPI
from ..services.trends_store import TrendsStore
from ..ui.app_window import App


def build_app(
    *,
    dump_root: Optional[Path] = None,
    settings: Optional[dict[str, Any]] = None,
    steam_api: Optional[SteamAPI] = None,
) -> App:
    """Construct the main App, with all collaborators injected."""
    settings = settings if settings is not None else load_settings()
    root = Path(settings.get("dump_root") or dump_root or default_dump_root())
    return App(
        steam_api=steam_api or SteamAPI(),
        dump_repository=DumpRepository(root),
        trends_store=TrendsStore(),
        settings=settings,
    )


__all__ = ["build_app"]