"""HTML scraping helpers for the Steam storefront.

These parse wishlist/follower/review counts out of the public Steam
store pages. They're a cheap alternative to Playwright; the trade-off
is that some counts may be missing if Steam changes the DOM.
"""
from __future__ import annotations

import re
from typing import Optional, Any

import requests

from ..core.logger import get_logger


_log = get_logger(__name__)


class StorefrontParser:
    """HTML-only metrics scraper (no browser automation required)."""

    def __init__(self, session: Optional[requests.Session] = None) -> None:
        from ..core.constants import DEFAULT_USER_AGENT
        self.session = session or requests.Session()
        self.session.headers.setdefault(
            "User-Agent", DEFAULT_USER_AGENT,
        )

    def get_popularity_metrics(
        self, app_id: int, language: str = "english"
    ) -> dict[str, Any]:
        """Scrape wishlist / follower / review counts from the storefront HTML."""
        url = f"https://store.steampowered.com/app/{app_id}/"
        out: dict[str, Any] = {"wishlist": None, "followers": None, "reviews": None}
        try:
            r = self.session.get(url, params={"l": language}, timeout=30)
            r.raise_for_status()
            html = r.text
        except requests.RequestException as exc:
            # The previous bare ``except Exception: return out``
            # silently dropped network errors — the trends tab
            # stored ``None`` for all three metrics and the user
            # had no way to tell whether Steam returned empty data
            # or the request itself failed. Use ``_log.exception``
            # (not ``_log.warning``) so the traceback is captured
            # — a network error with only the bare exception
            # message hides the URL / params / response status
            # the developer needs to debug. The ``exc`` arg is
            # still included in the log line (per the R13 fix
            # contract) so the underlying cause ("DNS lookup
            # failed", "503 Service Unavailable", ...) is
            # visible in the user's stderr log without having
            # to scroll through the traceback. Same R12-4 to
            # R12-7 + R15-3 lesson.
            _log.exception(
                "get_popularity_metrics(%d, %s) failed: %s",
                app_id, language, exc,
            )
            return out
        except (ValueError, UnicodeDecodeError) as exc:
            # Same R12-4 + R15-3 traceback-capture lesson:
            # ``_log.exception`` captures the traceback for
            # a bad-response failure (HTML gibberish, encoding
            # issues, etc.). The ``exc`` arg keeps the R13
            # contract: the underlying cause is visible in
            # the log line.
            _log.exception(
                "get_popularity_metrics(%d, %s): bad response: %s",
                app_id, language, exc,
            )
            return out

        for pat in (
            r'"wishlist_count"\s*:\s*(\d+)',
            r'(\d[\d,]+)\s*people\s*have\s*this\s*in\s*their\s*wishlist',
            r'"inWishlist"\s*:\s*(\d+)',
            r'wishlist_count["\s:]+(\d+)',
        ):
            m = re.search(pat, html, re.IGNORECASE)
            if m:
                try:
                    out["wishlist"] = int(m.group(1).replace(",", ""))
                    break
                except Exception:
                    pass

        for pat in (
            r'"followed_by_count"\s*:\s*(\d+)',
            r'(\d[\d,]+)\s*followers',
            r'"numFollowers"\s*:\s*(\d+)',
        ):
            m = re.search(pat, html, re.IGNORECASE)
            if m:
                try:
                    out["followers"] = int(m.group(1).replace(",", ""))
                    break
                except Exception:
                    pass

        for pat in (
            r'"review_summary_num"\s*:\s*(\d+)',
            r'"total_reviews"\s*:\s*(\d+)',
            r'>([\d,]+)<[^>]*reviews?[^\d<]',
        ):
            m = re.search(pat, html, re.IGNORECASE)
            if m:
                try:
                    out["reviews"] = int(m.group(1).replace(",", ""))
                    break
                except Exception:
                    pass
        return out

    def get_storefront_stats_from_html(self, app_id: int) -> dict[str, Any]:
        """Extract user-visible review summary from storefront HTML.

        Works even when the JSON review API returns 0 reviews (the case
        for newly-published apps whose review cache is not yet populated).
        """
        url = f"https://store.steampowered.com/app/{app_id}/"
        out = {
            "total_reviews": 0,
            "score_label": "Unknown",
            "score": 0,
            "positive_pct": 0.0,
            "html_ok": False,
        }
        try:
            r = self.session.get(url, params={"l": "english"}, timeout=30)
            r.raise_for_status()
            html = r.text
        except (requests.RequestException, ValueError) as exc:
            # Same R12-4 + R15-3 traceback-capture lesson:
            # ``_log.exception`` captures the traceback so
            # a developer can see WHICH URL / response failed
            # (Steam's anti-bot heuristics regularly produce
            # surprising HTML, so the traceback matters).
            # The ``exc`` arg keeps the log line useful
            # (the underlying HTTP error is visible
            # without scrolling through the traceback).
            _log.exception("stats fetch failed: %s", exc)
            return out

        m = re.search(
            r'"review_summary"\s*:\s*\{[^{}]*?'
            r'"review_score"\s*:\s*(\d+)[^{}]*?'
            r'"review_score_desc"\s*:\s*"([^"]+)"[^{}]*?'
            r'"total_positive"\s*:\s*(\d+)[^{}]*?'
            r'"total_negative"\s*:\s*(\d+)[^{}]*?'
            r'"total_reviews"\s*:\s*(\d+)',
            html,
        )
        if m:
            score, label, pos, neg, total = m.groups()
            out["score"] = int(score)
            out["score_label"] = label
            out["total_reviews"] = int(total)
            pos_i, total_i = int(pos), int(total)
            out["positive_pct"] = (
                round(100 * pos_i / total_i, 1) if total_i else 0.0
            )
            out["html_ok"] = True
            return out

        m = re.search(
            r'(Overwhelmingly Positive|Very Positive|Positive|Mostly Positive|'
            r'Mixed|Mostly Negative|Negative|Very Negative|Overwhelmingly Negative)'
            r'\s*\((\d+)\s*reviews?\)',
            html,
        )
        if m:
            out["score_label"] = m.group(1)
            out["total_reviews"] = int(m.group(2))
            out["html_ok"] = True
        return out


__all__ = ["StorefrontParser"]