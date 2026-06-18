"""User-editable AI prompt template."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AIPromptTemplate:
    """A user-editable prompt template. ``{dump}`` is replaced at copy time."""
    template: str = ""

    def format(self, dump: str) -> str:
        return self.template.replace("{dump}", dump)


__all__ = ["AIPromptTemplate"]