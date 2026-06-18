"""User-configurable keyword list[Any] used to tag reviews."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class KeywordList:
    """Plain list[Any] of case-insensitive substrings used for tag extraction."""
    items: list[str] = field(default_factory=list[Any])

    def contains(self, text: str) -> list[str]:
        if not text:
            return []
        lower = text.lower()
        return [k for k in self.items if k.lower() in lower]


__all__ = ["KeywordList"]