"""CSV exporter."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from ..utils.coercion import safe_int, safe_str

COLUMNS: list[str] = [
    "recommendationid", "language", "voted_up", "votes_up",
    "votes_funny", "comment_count", "author_steamid",
    "author_playtime_min", "author_last_played",
    "timestamp_created", "timestamp_updated", "weighted_vote_score",
    "steam_purchase", "received_for_free", "written_during_early_access",
    "review_text",
]


def reviews_to_csv(reviews: list[dict[str, Any]], dest_path: Path) -> int:
    """Write ``reviews`` to a CSV file. Returns row count.

    All numeric columns are coerced through :func:`safe_int` so a
    single review with a ``None`` / non-numeric ``votes_up`` /
    ``timestamp_created`` cannot crash the whole export.
    """
    with open(dest_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        for r in reviews:
            author = r.get("author", {}) or {}
            w.writerow([
                safe_str(r, "recommendationid", ""),
                str(r.get("language") or ""),
                int(bool(r.get("voted_up"))),
                safe_int(r, "votes_up", 0),
                safe_int(r, "votes_funny", 0),
                safe_int(r, "comment_count", 0),
                safe_str(author, "steamid", ""),
                safe_int(author, "playtime_forever", 0),
                safe_int(author, "last_played", 0),
                safe_int(r, "timestamp_created", 0),
                safe_int(r, "timestamp_updated", 0),
                # ``safe_str`` preserves a real ``0`` / ``0.0`` (a
                # perfectly valid weighted_vote_score). The old
                # ``str(r.get(..., "") or "")`` pattern used ``or``
                # which treats 0 as falsy and silently rendered an
                # empty cell for a real 0 — same R5 residue that
                # ``markdown_helpers.render_review`` already fixed
                # (line 179) by switching to ``safe_str``.
                safe_str(r, "weighted_vote_score", ""),
                int(bool(r.get("steam_purchase"))),
                int(bool(r.get("received_for_free"))),
                int(bool(r.get("written_during_early_access"))),
                (r.get("review") or "").replace("\n", " ").replace("\r", " "),
            ])
    return len(reviews)


__all__ = ["reviews_to_csv", "COLUMNS"]