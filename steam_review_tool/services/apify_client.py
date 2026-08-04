"""Apify "Steam Reviews Scraper" actor wrapper.

Apify scrapes the storefront via a real headless browser, which
**bypasses** Steam's JSON review cache and returns truly current data.
The actor costs ~$1 per 1,000 reviews (free tier ~$5/month credit).
"""
from __future__ import annotations

from typing import Optional, Any

import requests

from ..core.constants import DEFAULT_USER_AGENT
from ..utils.coercion import safe_coerce_int


def _first_present(*values: Any) -> Any:
    """Return the first ``value`` that is not None, else the last value.

    Distinct from ``a or b or c``: that pattern treats ``0`` and
    ``""`` as "absent" (Python's falsy semantics), which silently
    loses real 0-valued numeric fields. This helper keeps
    ``0`` and ``""`` as valid values and only treats ``None`` as
    "absent" — the right semantics for normalising a partial
    dict (e.g. an Apify response that may or may not include
    each field).
    """
    for v in values:
        if v is not None:
            return v
    return values[-1] if values else None


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
        """Translate Apify's dict[str, Any] into the Steam-API shape.

        All numeric fields are coerced through :func:`safe_coerce_int`
        and use :func:`_first_present` for field-priority lookups
        (Apify's snake_case + camelCase variants) so a present
        ``0`` value is preserved. The old ``a or b or c`` pattern
        treated ``0`` as "absent" and silently overwrote real
        zero counts with the fallback.
        """
        return {
            "recommendationid": _first_present(
                item.get("recommendationid"),
                item.get("reviewId"),
                item.get("id"),
            ),
            "language": _first_present(item.get("language"), "english"),
            "review": _first_present(
                item.get("reviewText"),
                item.get("review"),
                item.get("text", ""),
            ),
            "timestamp_created": safe_coerce_int(
                _first_present(
                    item.get("createdAt"),
                    item.get("timestamp_created"),
                ),
                default=0,
            ),
            "timestamp_updated": safe_coerce_int(
                _first_present(
                    item.get("updatedAt"),
                    item.get("timestamp_updated"),
                ),
                default=0,
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
            "votes_up": safe_coerce_int(
                _first_present(
                    item.get("helpfulCount"),
                    item.get("votes_up"),
                ),
                default=0,
            ),
            "votes_funny": safe_coerce_int(
                _first_present(
                    item.get("funnyCount"),
                    item.get("votes_funny"),
                ),
                default=0,
            ),
            "comment_count": safe_coerce_int(
                _first_present(
                    item.get("commentCount"),
                    item.get("comment_count"),
                ),
                default=0,
            ),
            "steam_purchase": item.get("steamPurchase"),
            "received_for_free": item.get("receivedForFree"),
            "written_during_early_access": item.get("earlyAccessReview"),
            "weighted_vote_score": item.get("weightedVoteScore"),
            "author": {
                "steamid": _first_present(
                    item.get("userId"),
                    item.get("steamid"),
                    "",
                ),
                "playtime_forever": safe_coerce_int(
                    _first_present(
                        item.get("playtimeForever"),
                        item.get("playtime_forever"),
                    ),
                    default=0,
                ),
                "last_played": safe_coerce_int(
                    _first_present(
                        item.get("lastPlayed"),
                        item.get("last_played"),
                    ),
                    default=0,
                ),
            },
        }


__all__ = ["ApifyClient"]
