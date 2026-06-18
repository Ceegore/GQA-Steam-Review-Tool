"""Apify "Steam Reviews Scraper" actor wrapper.

Apify scrapes the storefront via a real headless browser, which
**bypasses** Steam's JSON review cache and returns truly current data.
The actor costs ~$1 per 1,000 reviews (free tier ~$5/month credit).
"""
from __future__ import annotations

from typing import Optional, Any

import requests

from ..core.constants import DEFAULT_USER_AGENT


class ApifyClient:
    """Thin wrapper around Apify's Steam Reviews Scraper."""

    APIFY_STEAM_REVIEWS_ACTOR = "bebity~steam-reviews-scraper"

    def __init__(
        self,
        token: str = "",
        session: Optional[requests.Session] = None,
    ) -> None:
        self.token = token
        self.session = session or requests.Session()
        self.session.headers.setdefault("User-Agent", DEFAULT_USER_AGENT)

    def set_token(self, token: str) -> None:
        self.token = token

    def fetch(
        self,
        app_id: int,
        max_items: int = 100,
        sort: str = "recent",
        language: str = "all",
    ) -> list[dict[str, Any]]:
        """Run the actor synchronously and return normalized reviews."""
        if not self.token:
            raise ValueError("Apify token is required")
        url = (
            f"https://api.apify.com/v2/acts/{self.APIFY_STEAM_REVIEWS_ACTOR}"
            "/run-sync-get-dataset-items"
        )
        params = {"token": self.token, "timeout": 120}
        payload = {
            "appIds": [str(app_id)],
            "maxItems": max_items,
            "sort": sort,
            "language": language,
        }
        r = self.session.post(
            url, params=params, json=payload,  # type: ignore[arg-type]
            timeout=180,
        )
        r.raise_for_status()
        items = r.json()
        if not isinstance(items, list):
            raise ValueError(f"Unexpected Apify response: {items!r}")

        out: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            out.append(self._normalize(item))
        return out

    @staticmethod
    def _normalize(item: dict[str, Any]) -> dict[str, Any]:
        """Translate Apify's dict[str, Any] into the Steam-API shape."""
        return {
            "recommendationid": (
                item.get("recommendationid")
                or item.get("reviewId")
                or item.get("id")
            ),
            "language": item.get("language", "english"),
            "review": (
                item.get("reviewText")
                or item.get("review")
                or item.get("text", "")
            ),
            "timestamp_created": (
                item.get("createdAt")
                or item.get("timestamp_created")
                or 0
            ),
            "timestamp_updated": (
                item.get("updatedAt")
                or item.get("timestamp_updated")
                or 0
            ),
            "voted_up": (
                item.get("votedUp")
                if item.get("votedUp") is not None
                else (
                    item.get("voted_up")
                    if item.get("voted_up") is not None
                    else item.get("positive", False)
                )
            ),
            "votes_up": item.get("helpfulCount") or item.get("votes_up", 0),
            "votes_funny": item.get("funnyCount") or item.get("votes_funny", 0),
            "comment_count": (
                item.get("commentCount") or item.get("comment_count", 0)
            ),
            "steam_purchase": item.get("steamPurchase"),
            "received_for_free": item.get("receivedForFree"),
            "written_during_early_access": item.get("earlyAccessReview"),
            "weighted_vote_score": item.get("weightedVoteScore"),
            "author": {
                "steamid": (
                    item.get("userId") or item.get("steamid") or ""
                ),
                "playtime_forever": (
                    item.get("playtimeForever")
                    or item.get("playtime_forever", 0)
                ),
                "last_played": (
                    item.get("lastPlayed") or item.get("last_played", 0)
                ),
            },
        }


__all__ = ["ApifyClient"]