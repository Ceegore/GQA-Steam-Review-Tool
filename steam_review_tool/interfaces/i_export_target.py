"""Export target interface — one impl per output format."""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

from ..models.export_context import ExportContext


class IExportTarget(Protocol):
    """Anything that can serialize an ExportContext to a destination."""

    name: str

    def write(self, ctx: ExportContext, dest: Path) -> int:
        """Return the number of items written."""
        ...


__all__ = ["IExportTarget"]