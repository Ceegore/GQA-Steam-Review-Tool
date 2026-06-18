"""Abstract review source — Steam API or Playwright, used interchangeably."""
from __future__ import annotations

from typing import Iterator, Protocol

from ..models.filter_config import FilterConfig
from ..models.review import Review


class IReviewSource(Protocol):
    """Anything that can stream reviews for an app.

    Implementations: ``SteamApiSource`` (cached) and
    ``PlaywrightSource`` (real-time, browser-based). The UI treats them
    interchangeably behind a factory.
    """

    def stream(self, app_id: int, config: FilterConfig) -> Iterator[Review]: ...

    def cancel(self) -> None: ...


__all__ = ["IReviewSource"]