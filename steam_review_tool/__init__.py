"""Steam Review Analyzer — refactored into a 71-module package.

Subpackages
-----------
- ``core``      : Constants, timezones, paths, event bus, atomic write, logger
- ``interfaces``: Protocol contracts (ISteamApi, IExportTarget, …)
- ``models``    : Dataclasses (AppDetails, FilterConfig, ExportContext, …)
- ``utils``     : Pure helpers (no state)
- ``services``  : API/Storefront clients, stores, dependency installer
- ``exporters`` : Markdown / CSV / JSON / Obsidian sync
- ``ui``        : CustomTkinter widgets + dialogs + tab controllers
- ``controllers``: Workflow / state machines
- ``factories`` : App composition root

Public API entry points
-----------------------
- :func:`factories.app_factory.build_app` — construct the main App
- :func:`exporters.markdown_exporter.MarkdownExporter.render` — render docs
- :class:`services.steam_api_service.SteamAPI` — Steam Store client
"""
from __future__ import annotations

__version__ = "0.2.0"
__all__: list[str] = []