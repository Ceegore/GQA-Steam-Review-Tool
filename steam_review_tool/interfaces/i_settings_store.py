"""Settings persistence interface."""
from __future__ import annotations

from typing import Any, Protocol


class ISettingsStore(Protocol):
    """Read/write the user-preferences JSON file."""

    def load(self) -> dict[str, Any]: ...

    def save(self, data: dict[str, Any]) -> None: ...

    def apply(self, data: dict[str, Any]) -> None: ...


__all__ = ["ISettingsStore"]