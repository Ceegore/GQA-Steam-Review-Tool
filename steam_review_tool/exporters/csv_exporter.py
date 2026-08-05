"""CSV exporter."""
from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any

from ..core.atomic_write import atomic_write_text
from ..utils.coercion import safe_int, safe_str


COLUMNS: list[str] = [
    "recommendationid", "language", "voted_up", "votes_up",
    "votes_funny", "comment_count", "author_steamid",
    "author_playtime_min", "author_last_played",
    "timestamp_created", "timestamp_updated", "weighted_vote_score",
    "steam_purchase", "received_for_free", "written_during_early_access",
    "review_text",
]


def _render_csv(reviews: list[dict[str, Any]]) -> str:
    """Render the CSV body in memory.

    Pulled out of :func:`reviews_to_csv` so the atomic-write
    path can call it without duplicating the row-building
    logic.

    ``lineterminator="\n"`` is critical: the default
    ``csv.writer`` uses ``"\r\n"`` (the CSV spec's
    official line terminator), but ``atomic_write_text``
    writes through ``os.fdopen(..., "w", encoding="utf-8")``
    which, on Windows, translates any ``"\n"`` in the
    payload to ``"\r\n"``. The combination — ``"\r\n"`` in
    the StringIO becoming ``"\r" + "\r\n"`` in the file —
    left a doubled line terminator on disk. Reading the
    file back with the default ``csv.reader`` then
    produced blank rows between data rows (the test
    ``test_csv_writes_expected_columns`` went from
    ``len(rows) == 4`` to ``len(rows) == 8``). Using
    ``lineterminator="\n"`` keeps the on-disk line
    terminator consistent across platforms.
    """
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
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
    return buf.getvalue()


def reviews_to_csv(reviews: list[dict[str, Any]], dest_path: Path) -> int:
    """Write ``reviews`` to a CSV file. Returns row count.

    All numeric columns are coerced through :func:`safe_int` so a
    single review with a ``None`` / non-numeric ``votes_up`` /
    ``timestamp_created`` cannot crash the whole export.

    The write is **atomic** — a crash mid-write cannot leave a
    half-written ``.csv`` file behind. The previous
    implementation wrote via ``open(..., "w", ...)`` which
    was non-atomic; a partial ``.csv`` would survive an
    unexpected exit, leaving the user with a silently-
    truncated export. The export orchestrator had already
    worked around this by rendering to a ``StringIO`` and
    calling ``atomic_write_text`` (private
    ``_write_csv_atomic``); this R16 fix moves the atomic
    pattern into the public function so any caller
    (including tests) gets the safe behaviour.
    """
    atomic_write_text(dest_path, _render_csv(reviews))
    return len(reviews)


__all__ = ["reviews_to_csv", "COLUMNS", "_render_csv"]
