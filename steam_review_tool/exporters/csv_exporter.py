"""CSV exporter."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

COLUMNS: list[str] = [
    "recommendationid", "language", "voted_up", "votes_up",
    "votes_funny", "comment_count", "author_steamid",
    "author_playtime_min", "author_last_played",
    "timestamp_created", "timestamp_updated", "weighted_vote_score",
    "steam_purchase", "received_for_free", "written_during_early_access",
    "review_text",
]


def reviews_to_csv(reviews: list[dict[str, Any]], dest_path: Path) -> int:
    """Write ``reviews`` to a CSV file. Returns row count."""
    with open(dest_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        for r in reviews:
            author = r.get("author", {}) or {}
            w.writerow([
                str(r.get("recommendationid", "")),
                str(r.get("language") or ""),
                int(bool(r.get("voted_up"))),
                int(r.get("votes_up", 0) or 0),
                int(r.get("votes_funny", 0) or 0),
                int(r.get("comment_count", 0) or 0),
                str(author.get("steamid", "")),
                int(author.get("playtime_forever", 0) or 0),
                int(author.get("last_played", 0) or 0),
                int(r.get("timestamp_created", 0) or 0),
                int(r.get("timestamp_updated", 0) or 0),
                str(r.get("weighted_vote_score", "")),
                int(bool(r.get("steam_purchase"))),
                int(bool(r.get("received_for_free"))),
                int(bool(r.get("written_during_early_access"))),
                (r.get("review") or "").replace("\n", " ").replace("\r", " "),
            ])
    return len(reviews)


__all__ = ["reviews_to_csv", "COLUMNS"]