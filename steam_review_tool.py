"""
Steam Review Analyzer — legacy entry-point shim.

The original 9,360-line monolith has been refactored into a 71-module
package under ``steam_review_tool/``. This file is kept as a
back-compat shim so old invocations like::

    python steam_review_tool.py

keep working. It does **not** contain any business logic — it just
forwards into the new package and prints a one-time deprecation
notice the first time it's invoked.

New code should target ``main.py`` directly. The full source of the
monolith is preserved as ``steam_review_tool.legacy.py.bak`` for
historical reference; it is no longer on the import path.
"""
from __future__ import annotations

import os
import sys
import warnings


_DEPR_MSG = (
    "`steam_review_tool.py` is a legacy back-compat shim. "
    "The actual source lives in the `steam_review_tool/` package "
    "(71 modules, max 500 lines each). "
    "Use `python main.py` for new invocations, or import from "
    "`steam_review_tool.services.*`, `steam_review_tool.exporters.*`, "
    "etc. The full original monolith is preserved as "
    "`steam_review_tool.legacy.py.bak`."
)

# Show the deprecation notice once per process. The shim still works;
# we just tell people that ``main.py`` is the new entry point.
if not os.environ.get("SRT_SHIM_QUIET"):
    warnings.warn(_DEPR_MSG, DeprecationWarning, stacklevel=2)
    os.environ["SRT_SHIM_QUIET"] = "1"

# Make the package's public API importable as ``steam_review_tool.X``
# (the old names). This is what every legacy caller relied on.
from steam_review_tool.factories.app_factory import build_app  # noqa: E402
from steam_review_tool.services.steam_api_service import SteamAPI  # noqa: E402
from steam_review_tool.exporters.markdown_exporter import (  # noqa: E402
    MarkdownExporter,
)
from steam_review_tool.exporters.csv_exporter import (  # noqa: E402
    reviews_to_csv,
)
from steam_review_tool.exporters.json_exporter import (  # noqa: E402
    reviews_to_json,
)
from steam_review_tool.exporters.per_language_exporter import (  # noqa: E402
    build_summary,
    group_by_language,
    write_per_language,
)
from steam_review_tool.exporters.export_orchestrator import (  # noqa: E402
    run as export_run,
)
from steam_review_tool.exporters.obsidian_copier import (  # noqa: E402
    copy_to_obsidian_vault,
)


def main() -> None:
    """Legacy entry point: build the App and start the Tk mainloop."""
    app = build_app()
    app.mainloop()


if __name__ == "__main__":
    main()


__all__ = [
    "SteamAPI",
    "MarkdownExporter",
    "reviews_to_csv",
    "reviews_to_json",
    "build_summary",
    "group_by_language",
    "write_per_language",
    "export_run",
    "copy_to_obsidian_vault",
    "build_app",
    "main",
]