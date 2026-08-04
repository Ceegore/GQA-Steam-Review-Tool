"""Pure analysis helpers for review collections.

Every function here is deterministic and has no UI/state dependencies,
so they can be unit-tested in isolation and reused by both tabs.
"""
from __future__ import annotations

import re
from typing import Optional, Any

from ..utils.coercion import safe_int, safe_str

# ---------------------------------------------------------------------------
# Heuristic phrase lists
# ---------------------------------------------------------------------------

DEFAULT_KEYWORD_TAGS: list[str] = [
    "crash", "freeze", "lag", "stutter", "stuck", "broken", "bug",
    "error", "glitch", "fps", "save", "lost", "missing", "refund",
    "performance", "uninstall", "not working", "doesn't work",
    "doesn't load", "won't launch", "wont launch", "black screen",
    "server", "online", "multiplayer", "controller", "sound", "audio",
    "music", "voice", "graphics", "ui", "menu", "tutorial", "laggy",
    "rubberbanding", "desync", "anticheat", "anti-cheat", "cheater",
    "hacker", "exploit", "pay to win", "p2w", "microtransaction",
]


def _safe_ts(r: dict[str, Any]) -> int:
    """Coerce a review's ``timestamp_created`` to ``int``, returning
    ``0`` for ``None`` or non-numeric values.

    The Steam API normally returns an int, but normalised review
    dicts (e.g. from the Apify client or a hand-rolled test) can
    carry ``None`` or a non-numeric string. Without this helper,
    every function that does ``int(r.get("timestamp_created", 0))``
    crashes the whole export on a single malformed row.
    """
    return safe_int(r, "timestamp_created", 0)

_BUG_PHRASES: list[str] = [
    "crash", "crashed", "freezes", "frozen", "stuck", "stuttering",
    "fps drop", "low fps", "black screen", "won't launch", "wont launch",
    "doesn't launch", "broken", "bug", "glitch", "error code", "ctd",
    "crash to desktop", "memory leak", "save file", "lost my save",
    "lost progress", "corrupt save", "not working", "doesn't work",
    "doesn't load", "stuck on", "softlock", "hard lock", "desync",
    "rubberbanding", "teleporting", "invisible enemy", "can't move",
    "no sound", "no audio", "sound cutting out", "controller not",
    "game-breaking", "game breaking", "unplayable", "uninstalling",
    "uninstalled", "wasted money", "garbage game", "refund request",
    "performance issue", "frame drops", "frozen screen",
]

_FEATURE_PHRASES: list[str] = [
    "would be nice", "would be great", "would love to see", "please add",
    "needs an option", "needs option", "should have", "should add",
    "missing feature", "needs a feature", "lacks", "needs better",
    "needs a way to", "wish there was", "wish there were", "i wish",
    "could use", "would be cool if", "suggestion", "feature request",
    "add a", "add an", "bring back", "should be", "needs the ability",
    "give us", "give players", "would prefer", "no way to",
    "needs to be", "needs more", "wants to",
]

_PRAISE_PHRASES: list[str] = [
    "love this game", "love it", "amazing game", "best game",
    "10/10", "masterpiece", "incredible", "fantastic", "excellent game",
    "perfect game", "great game", "awesome game", "fun game",
    "addictive", "highly recommend", "worth every penny", "worth it",
    "stunning", "beautiful game", "great soundtrack", "great music",
    "great story", "great graphics", "great gameplay", "brilliant",
    "wonderful", "gem", "phenomenal", "best in class",
]

_COMPLAINT_PHRASES: list[str] = [
    "not worth", "not worth it", "waste of money", "waste of time",
    "disappointing", "disappointed", "boring", "repetitive",
    "too short", "too long", "overpriced", "too expensive", "rip off",
    "money grab", "cash grab", "lazy", "uninspired", "repetitive",
    "lack of content", "no content", "no endgame", "no replay value",
    "unbalanced", "poor design", "bad design", "terrible design",
    "unfair", "predatory", "anti-consumer", "scam", "greedy",
    "shouldn't have", "should not have", "forced", "unfun",
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def classify_review_type(review: dict[str, Any]) -> str:
    """Classify a single review as 'bug'/'feature'/'praise'/'complaint'/'other'.

    Priority order: bug > feature > complaint > praise > other.
    """
    # The review field is normally a string, but normalised
    # review dicts (Apify client, hand-rolled tests) can carry
    # ``None`` or a non-string (int, list, dict). Calling
    # ``.lower()`` on those used to raise ``AttributeError`` and
    # the ``except Exception: pass`` blocks in
    # ``markdown_helpers.render_review`` / ``render_digest``
    # would silently drop the auto-type and pre-AI digest for
    # the entire export. Coerce to ``""`` so a malformed row
    # falls into the "other" bucket instead of breaking the
    # whole export.
    raw = review.get("review")
    if not isinstance(raw, str):
        text = ""
    else:
        text = raw.lower()
    if not text:
        return "other"
    if any(p in text for p in _BUG_PHRASES):
        return "bug"
    if any(p in text for p in _FEATURE_PHRASES):
        return "feature"
    if review.get("voted_up"):
        if any(p in text for p in _PRAISE_PHRASES):
            return "praise"
    else:
        if any(p in text for p in _COMPLAINT_PHRASES):
            return "complaint"
    if review.get("voted_up"):
        return "praise"
    return "complaint"


def extract_tags(
    review: dict[str, Any], keyword_list: Optional[list[str]] = None
) -> list[str]:
    """Return the list[Any] of keyword tags that appear in ``review``."""
    if keyword_list is None:
        keyword_list = DEFAULT_KEYWORD_TAGS
    # Same defensive coercion as ``classify_review_type`` — the
    # review field can be ``None`` or a non-string (int / list /
    # dict) in normalised review dicts; the previous
    # ``(review.get("review") or "").lower()`` crashed with
    # ``AttributeError`` for those cases and the
    # ``except Exception: pass`` in
    # ``markdown_helpers.render_review`` would silently drop
    # the entire Tags row.
    raw = review.get("review")
    if not isinstance(raw, str):
        text = ""
    else:
        text = raw.lower()
    if not text:
        return []
    hits: list[str] = []
    for kw in keyword_list:
        # The keyword list is normally a list of strings, but
        # hand-rolled / migrated settings.json can carry ints
        # or other non-strings. ``kw.lower()`` on a non-string
        # used to crash with ``AttributeError``; skip those
        # entries so one bad keyword doesn't drop the whole
        # Tags row.
        if not isinstance(kw, str):
            continue
        kw_l = kw.lower().strip()
        if not kw_l:
            continue
        if " " in kw_l:
            if kw_l in text:
                hits.append(kw_l)
        else:
            base = re.escape(kw_l)
            pat = rf"\b({base}(?:e?s|e?d|ing)?)\b"
            if re.search(pat, text):
                hits.append(kw_l)
    seen = set()
    out = []
    for h in hits:
        if h not in seen:
            seen.add(h)
            out.append(h)
    return out


def aggregate_top_themes(
    reviews: list[dict[str, Any]],
    top_n: int = 5,
    mode: str = "negative",
    keyword_list: Optional[list[str]] = None,
) -> list[dict[str, Any]]:
    """Return the top N themes for the chosen sentiment."""
    if keyword_list is None:
        keyword_list = _BUG_PHRASES if mode == "negative" else _PRAISE_PHRASES
    # Same defensive coercion as ``extract_tags`` and
    # ``classify_review_type`` — a non-string keyword entry
    # (int / dict / list) in the keyword list used to raise
    # ``TypeError: 'in <string>' requires string as left
    # operand`` and the ``except Exception: pass`` block in
    # ``markdown_helpers.render_digest`` would silently drop
    # the entire Pre-AI Digest block from the export.
    cleaned_keywords: list[str] = [
        k for k in keyword_list if isinstance(k, str) and k
    ]
    counts: dict[str, dict[str, Any]] = {}
    for r in reviews:
        if mode == "negative" and r.get("voted_up"):
            continue
        if mode == "positive" and not r.get("voted_up"):
            continue
        # Defensive coercion for the review field — see the
        # matching fix in ``classify_review_type``.
        raw_review = r.get("review")
        if not isinstance(raw_review, str):
            continue
        text = raw_review.lower()
        if not text:
            continue
        for phrase in cleaned_keywords:
            if phrase in text:
                if phrase not in counts:
                    counts[phrase] = {
                        "theme": phrase,
                        "count": 0,
                        "sample_quote": "",
                        "sample_author": "",
                        "sample_rid": "",
                    }
                counts[phrase]["count"] += 1
                if not counts[phrase]["sample_quote"]:
                    author = r.get("author", {}) or {}
                    raw = (r.get("review") or "").strip().replace("\n", " ")
                    idx = raw.lower().find(phrase)
                    if idx >= 0:
                        start = max(0, idx - 40)
                        end = min(len(raw), idx + 80)
                        snippet = raw[start:end]
                        if start > 0:
                            snippet = "…" + snippet
                        if end < len(raw):
                            snippet = snippet + "…"
                    else:
                        snippet = raw[:120] + ("…" if len(raw) > 120 else "")
                    counts[phrase]["sample_quote"] = snippet
                    counts[phrase]["sample_author"] = safe_str(
                        author, "steamid", "",
                    )
                    counts[phrase]["sample_rid"] = safe_str(
                        r, "recommendationid", "",
                    )
    out = sorted(counts.values(), key=lambda x: x["count"], reverse=True)
    return out[:top_n]


def compute_playtime_histogram(
    reviews: list[dict[str, Any]], buckets: int = 5,
) -> dict[str, Any]:
    """Return ``{bucket_label: {pos, neg}}`` for review playtime."""
    pos_hours = []
    neg_hours = []
    for r in reviews:
        author = r.get("author", {}) or {}
        pt = safe_int(author, "playtime_forever", 0) / 60.0
        if r.get("voted_up"):
            pos_hours.append(pt)
        else:
            neg_hours.append(pt)
    if not pos_hours and not neg_hours:
        return {}
    all_pts = pos_hours + neg_hours
    max_pt = max(all_pts) if all_pts else 1
    max_pt = max(max_pt, 1.0)
    edges = [max_pt * i / buckets for i in range(buckets + 1)]
    out: dict[str, Any] = {}
    for i in range(buckets):
        label = f"{edges[i]:.1f}–{edges[i+1]:.1f}h"
        out[label] = {
            "pos": sum(1 for p in pos_hours if edges[i] <= p < edges[i+1]
                       or (i == buckets - 1 and p == edges[i+1])),
            "neg": sum(1 for p in neg_hours if edges[i] <= p < edges[i+1]
                       or (i == buckets - 1 and p == edges[i+1])),
        }
    return out


def split_first_24h(reviews: list[dict[str, Any]]) -> dict[str, Any]:
    """Split reviews into 'first 24h' (after the earliest post) and 'after'."""
    if not reviews:
        return {"first_24h": [], "after": []}
    # A list comprehension over a non-empty iterable always produces a
    # non-empty list, so the previous ``if not timestamps:`` branch
    # was dead code. Skip the unnecessary rebuild and just coerce
    # each entry, tolerating ``None`` / non-numeric values.
    timestamps: list[int] = []
    for r in reviews:
        raw = r.get("timestamp_created")
        if raw is None:
            timestamps.append(0)
            continue
        try:
            timestamps.append(int(raw))
        except (TypeError, ValueError):
            timestamps.append(0)
    earliest = (
        min(t for t in timestamps if t > 0)
        if any(t > 0 for t in timestamps) else 0
    )
    if earliest == 0:
        return {"first_24h": [], "after": list(reviews)}
    cutoff = earliest + 24 * 3600
    first_24h = [
        r for r in reviews
        if earliest <= _safe_ts(r) <= cutoff
    ]
    after = [
        r for r in reviews
        if _safe_ts(r) > cutoff
    ]
    return {"first_24h": first_24h, "after": after, "earliest_ts": earliest}


def compute_deltas(
    old_reviews: list[dict[str, Any]], new_reviews: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compare two review sets by ``recommendationid``."""
    old_ids = {
        safe_str(r, "recommendationid", "")
        for r in old_reviews if r.get("recommendationid")
    }
    new_only = [
        r for r in new_reviews
        if safe_str(r, "recommendationid", "") not in old_ids
    ]
    pos = sum(1 for r in new_only if r.get("voted_up"))
    return {
        "count": len(new_only),
        "positive": pos,
        "negative": len(new_only) - pos,
        "reviews": new_only,
    }


__all__ = [
    "DEFAULT_KEYWORD_TAGS",
    "classify_review_type",
    "extract_tags",
    "aggregate_top_themes",
    "compute_playtime_histogram",
    "split_first_24h",
    "compute_deltas",
]