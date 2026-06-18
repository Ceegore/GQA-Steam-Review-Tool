"""Review-related models and enums."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Any


@dataclass
class Review:
    """Lightweight wrapper around a Steam review dict.

    The original code passes raw dicts everywhere. We keep the dict[str, Any]
    shape internally for compatibility, but this dataclass is the
    *public* type used by interfaces.
    """
    data: dict[str, Any]

    @property
    def recommendation(self) -> Optional[bool]:
        v = self.data.get("voted_up")
        return bool(v) if v is not None else None

    @property
    def language(self) -> str:
        return self.data.get("language", "")

    @property
    def timestamp_created(self) -> int:
        return int(self.data.get("timestamp_created", 0))

    @property
    def review_id(self) -> str:
        return self.data.get("recommendationid", "")

    @property
    def author_steamid(self) -> str:
        return str(self.data.get("author", {}).get("steamid", ""))


class ReviewSort:
    """Sort order accepted by Steam's reviews API."""

    ALL = "all"
    RECENT = "recent"
    UPDATED = "updated"


class ReviewType:
    """Reviewer sentiment filter — kept as a namespace of constants."""

    ALL = "all"
    POSITIVE = "positive"
    NEGATIVE = "negative"


__all__ = ["Review", "ReviewSort", "ReviewType"]