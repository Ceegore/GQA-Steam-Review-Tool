"""Steam Store / Reviews API client.

A thin ``requests.Session`` wrapper around the public Steam endpoints.
The original monolith's ``SteamAPI`` class had ~1,090 lines; this file
hosts the *core* HTTP methods (resolve_app_id, get_app_details,
fetch_all_reviews, poll_recent_reviews). HTML scraping lives in
``storefront_parser`` and Apify scraping lives in ``apify_client``.
"""
from __future__ import annotations

import time
from typing import Callable, Optional, Any

import requests

from ..core.constants import (
    DEFAULT_USER_AGENT,
    STEAM_API_BASE,
    STEAM_API_PAGE_DELAY_SEC,
    STEAM_POLL_DELAY_SEC,
    STEAM_REVIEWS_BASE,
)
from ..core.logger import get_logger
from ..utils.coercion import safe_int
from ..utils.url_utils import resolve_app_id as _resolve_app_id


_log = get_logger(__name__)


class SteamAPI:
    """Thin wrapper around the public Steam Store API."""

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "DNT": "1",
            "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "Referer": "https://store.steampowered.com/",
            "X-Requested-With": "XMLHttpRequest",
        })
        # In-memory set of review IDs we have already processed in watch mode.
        self._seen_review_ids: set[str] = set()

    # ---- seen-IDs (watch mode) -----------------------------------------

    def reset_seen_reviews(self) -> None:
        self._seen_review_ids.clear()

    def export_seen_review_ids(self) -> list[str]:
        return list(self._seen_review_ids)

    def import_seen_review_ids(self, ids: list[str]) -> None:
        self._seen_review_ids = set(ids)

    # ---- ID / URL parsing ----------------------------------------------

    @staticmethod
    def resolve_app_id(query: str) -> Optional[int]:
        return _resolve_app_id(query)

    # ---- App metadata --------------------------------------------------

    def get_app_details(
        self, app_id: int, language: str = "english"
    ) -> Optional[dict[str, Any]]:
        """Fetch full app metadata (name, dev, publisher, descriptions, ...)."""
        url = f"{STEAM_API_BASE}/appdetails"
        try:
            r = self.session.get(
                url,
                params={"appids": str(app_id), "l": language},
                timeout=30,
            )
            r.raise_for_status()
            data = r.json()
        except (requests.RequestException, ValueError) as exc:
            _log.warning("get_app_details failed: %s", exc)
            return None

        node = data.get(str(app_id))
        if not node or not node.get("success"):
            return None
        return node.get("data")

    # ---- Reviews pagination -------------------------------------------

    def fetch_all_reviews(
        self,
        app_id: int,
        language: str = "all",
        review_filter: str = "all",
        review_type: str = "all",
        day_range: Optional[int] = None,
        min_date_ts: Optional[int] = None,
        num_per_page: int = 100,
        progress_cb: Optional[Callable[[int, int, int], None]] = None,
        log_cb: Optional[Callable[[str], None]] = None,
        stop_flag: Optional[Callable[[], bool]] = None,
        start_cursor: str = "*",
        cursor_cb: Optional[Callable[[str], None]] = None,
        purchase_type: str = "all",
        playtime_filter_min: Optional[int] = None,
        playtime_filter_max: Optional[int] = None,
        filter_offtopic_activity: bool = True,
    ) -> list[dict[str, Any]]:
        """Iterate the full reviews feed via cursor pagination.

        Stops when Steam returns an empty/unchanged cursor or
        ``stop_flag()`` returns True. ``progress_cb(page, kept, total)``
        is called per page. ``min_date_ts`` is applied CLIENT-SIDE
        because the Steam API has no native "since timestamp" param.
        """
        all_reviews: list[dict[str, Any]] = []
        cursor = start_cursor or "*"
        page = 0
        total_reported = 0

        while True:
            if stop_flag and stop_flag():
                if log_cb:
                    log_cb("Fetch cancelled by user.")
                break

            params = {
                "json": 1,
                "language": language,
                "filter": review_filter,
                "review_type": review_type,
                "num_per_page": num_per_page,
                "cursor": cursor,
                "purchase_type": purchase_type,
                "filter_offtopic_activity": (
                    "true" if filter_offtopic_activity else "false"
                ),
            }
            if day_range is not None:
                params["day_range"] = day_range
            if playtime_filter_min is not None:
                params["playtime_filter_min"] = playtime_filter_min
            if playtime_filter_max is not None:
                params["playtime_filter_max"] = playtime_filter_max

            try:
                r = self.session.get(
                    f"{STEAM_REVIEWS_BASE}/{app_id}",
                    params=params,  # type: ignore[arg-type]
                    timeout=60,
                )
                r.raise_for_status()
                data = r.json()
            except (requests.RequestException, ValueError) as exc:
                if log_cb:
                    log_cb(f"Network error on page {page}: {exc}")
                break

            if not data.get("success"):
                if log_cb:
                    log_cb("Steam returned success=0; aborting.")
                break

            page_reviews = data.get("reviews", []) or []
            # ``or {}`` collapses a present-but-None ``query_summary``
            # (e.g. from a hand-rolled test response) into an empty
            # dict so ``.get("total_reviews", ...)`` doesn't crash.
            total_reported = (
                (data.get("query_summary") or {}).get(
                    "total_reviews", total_reported,
                )
            )

            if min_date_ts is not None:
                # ``safe_int`` keeps a None or non-numeric
                # ``timestamp_created`` from crashing the whole
                # export — it was the same pattern R3-2 fixed in
                # ``filter_controller`` (where the bare ``int()``
                # raised on None / non-numeric strings).
                page_reviews = [
                    rv for rv in page_reviews
                    if safe_int(rv, "timestamp_created", 0) >= min_date_ts
                ]

            all_reviews.extend(page_reviews)
            page += 1

            if progress_cb:
                progress_cb(page, len(all_reviews), total_reported)
            if log_cb:
                log_cb(
                    f"Page {page}: +{len(page_reviews)} reviews "
                    f"(total kept: {len(all_reviews)}, server total: {total_reported})"
                )

            new_cursor = data.get("cursor", "")
            if not new_cursor or new_cursor == cursor:
                break
            cursor = new_cursor
            if cursor_cb is not None:
                # The previous bare ``except Exception: pass``
                # silently dropped resume-cursor save failures
                # (disk full, file locked, perms denied). The
                # fetch kept running, the user clicked Stop or the
                # process died, and on next launch there was NO
                # cursor to resume from — silently re-fetching
                # every page from the start. Surface the error so
                # the user can spot a missing resume state.
                try:
                    cursor_cb(cursor)
                except OSError as exc:
                    _log.warning(
                        "resume-cursor save failed: %s: %s",
                        type(exc).__name__, exc,
                    )
            time.sleep(STEAM_API_PAGE_DELAY_SEC)

        return all_reviews

    def poll_recent_reviews(
        self,
        app_id: int,
        max_pages: int = 1,
        page_size: int = 100,
        language: str = "all",
    ) -> list[dict[str, Any]]:
        """Fetch the most recent reviews using ``filter='recent'``.

        Returns only reviews whose ``recommendationid`` we have not seen
        before in this session (watch-mode diff). The internal set of
        seen IDs is updated in place.

        Still uses Steam's JSON review cache (24-72h lag for new apps).
        For truly real-time data use the Playwright source instead.
        """
        new_reviews: list[dict[str, Any]] = []
        cursor = "*"
        for _ in range(max_pages):
            params = {
                "json": 1,
                "language": language,
                "filter": "recent",
                "num_per_page": page_size,
                "cursor": cursor,
            }
            try:
                r = self.session.get(
                    f"{STEAM_REVIEWS_BASE}/{app_id}",
                    params=params,  # type: ignore[arg-type]
                    timeout=60,
                )
                r.raise_for_status()
                data = r.json()
            except (requests.RequestException, ValueError) as exc:
                _log.warning("poll_recent_reviews error: %s", exc)
                break

            if not data.get("success"):
                break

            for rv in data.get("reviews", []) or []:
                rid = rv.get("recommendationid")
                if rid and rid not in self._seen_review_ids:
                    self._seen_review_ids.add(rid)
                    new_reviews.append(rv)

            new_cursor = data.get("cursor", "")
            if not new_cursor or new_cursor == cursor:
                break
            cursor = new_cursor
            time.sleep(STEAM_POLL_DELAY_SEC)
        return new_reviews


__all__ = ["SteamAPI"]