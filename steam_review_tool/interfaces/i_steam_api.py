"""Steam API access interface."""
from __future__ import annotations

from typing import Iterator, Optional, Protocol, Any


class ISteamApi(Protocol):
    """Thin wrapper around the public Steam Store API."""

    def resolve_app_id(self, query: str) -> Optional[int]: ...

    def get_app_details(
        self, app_id: int, language: str = "english"
    ) -> Optional[dict[str, Any]]: ...

    def get_popularity_metrics(
        self, app_id: int, language: str = "english"
    ) -> dict[str, Any]: ...

    def get_storefront_stats_from_html(self, app_id: int) -> dict[str, Any]: ...

    def fetch_all_reviews(
        self,
        app_id: int,
        *,
        language: str = "all",
        review_filter: str = "all",
        review_type: str = "all",
        day_range: Optional[int] = None,
        min_date_ts: Optional[int] = None,
        min_helpful: int = 0,
        num_per_page: int = 100,
        on_progress=None,
        cancel_flag=None,
    ) -> list[dict[str, Any]]: ...

    def poll_recent_reviews(
        self,
        app_id: int,
        language: str,
        cursor: str,
        seen_ids: set[str],
    ) -> tuple[list[dict[str, Any]], str]: ...


__all__ = ["ISteamApi"]