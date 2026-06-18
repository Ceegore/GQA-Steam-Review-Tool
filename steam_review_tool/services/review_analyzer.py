"""Pure analysis helpers for review collections.

Every function here is deterministic and has no UI/state dependencies,
so they can be unit-tested in isolation and reused by both tabs.
"""
from __future__ import annotations

import re
from typing import Optional, Any

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
    text = (review.get("review") or "").lower()
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
    text = (review.get("review") or "").lower()
    if not text:
        return []
    hits: list[str] = []
    for kw in keyword_list:
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
    counts: dict[str, dict[str, Any]] = {}
    for r in reviews:
        if mode == "negative" and r.get("voted_up"):
            continue
        if mode == "positive" and not r.get("voted_up"):
            continue
        text = (r.get("review") or "").lower()
        if not text:
            continue
        for phrase in keyword_list:
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
                    counts[phrase]["sample_author"] = author.get("steamid", "")
                    counts[phrase]["sample_rid"] = str(
                        r.get("recommendationid", "")
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
        pt = int(author.get("playtime_forever", 0) or 0) / 60.0
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
    timestamps = [int(r.get("timestamp_created", 0) or 0) for r in reviews]
    if not timestamps:
        return {"first_24h": [], "after": []}
    earliest = (
        min(t for t in timestamps if t > 0)
        if any(t > 0 for t in timestamps) else 0
    )
    if earliest == 0:
        return {"first_24h": [], "after": list(reviews)}
    cutoff = earliest + 24 * 3600
    first_24h = [
        r for r in reviews
        if earliest <= int(r.get("timestamp_created", 0) or 0) <= cutoff
    ]
    after = [
        r for r in reviews
        if int(r.get("timestamp_created", 0) or 0) > cutoff
    ]
    return {"first_24h": first_24h, "after": after, "earliest_ts": earliest}


def compute_deltas(
    old_reviews: list[dict[str, Any]], new_reviews: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compare two review sets by ``recommendationid``."""
    old_ids = {
        str(r.get("recommendationid", ""))
        for r in old_reviews if r.get("recommendationid")
    }
    new_only = [
        r for r in new_reviews
        if str(r.get("recommendationid", "")) not in old_ids
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