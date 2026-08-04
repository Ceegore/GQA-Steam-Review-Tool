"""Pre-AI digest generator.

Produces a compact Markdown block designed to be the FIRST thing an
AI sees when handed a ``.md`` export. Stats, top complaints / praise,
auto-classified types, and the top-3 reviewers by playtime.
"""
from __future__ import annotations

from typing import Optional, Any

from ..utils.coercion import safe_int, safe_str
from .review_analyzer import aggregate_top_themes, classify_review_type


def build_pre_ai_digest(
    reviews: list[dict[str, Any]],
    app_details: Optional[dict[str, Any]] = None,
    keyword_list: Optional[list[str]] = None,
    top_n: int = 5,
) -> str:
    """Return a short Markdown digest."""
    total = len(reviews)
    if total == 0:
        return "## Pre-AI Digest\n\n_No reviews yet._\n"
    pos = sum(1 for r in reviews if r.get("voted_up"))
    neg = total - pos
    pct = round(100 * pos / total, 1) if total else 0.0
    name = (app_details or {}).get("name") if app_details else None

    lines: list[str] = []
    lines.append("## Pre-AI Digest")
    if name:
        lines.append(f"**{name}**")
    lines.append("")
    lines.append(
        f"- Total: **{total}** reviews "
        f"({pos} positive / {neg} negative, {pct}% positive)"
    )

    top_neg = aggregate_top_themes(reviews, top_n=top_n, mode="negative",
                                    keyword_list=keyword_list)
    if top_neg:
        lines.append("- **Top complaints** (with example quotes):")
        for t in top_neg:
            lines.append(f"  - `{t['theme']}` ({t['count']}×) — "
                         f"\"{t['sample_quote'][:90]}\"")

    top_pos = aggregate_top_themes(reviews, top_n=top_n, mode="positive",
                                    keyword_list=keyword_list)
    if top_pos:
        lines.append("- **Top praise** (with example quotes):")
        for t in top_pos:
            lines.append(f"  - `{t['theme']}` ({t['count']}×) — "
                         f"\"{t['sample_quote'][:90]}\"")

    type_counts: dict[str, int] = {}
    for r in reviews:
        rt = classify_review_type(r)
        type_counts[rt] = type_counts.get(rt, 0) + 1
    if type_counts:
        bits = ", ".join(f"{k}: {v}" for k, v in
                         sorted(type_counts.items(), key=lambda kv: -kv[1]))
        lines.append(f"- **Auto-classified types**: {bits}")

    reviewers = []
    for r in reviews:
        author = r.get("author", {}) or {}
        pt = safe_int(author, "playtime_forever", 0) / 60.0
        steamid = safe_str(author, "steamid", "")
        if steamid:
            reviewers.append((
                pt, steamid, safe_str(r, "recommendationid", ""),
                (r.get("review") or "")[:60],
            ))
    reviewers.sort(key=lambda x: -x[0])
    if reviewers:
        lines.append("- **Top 3 reviewers by playtime**:")
        for pt, steamid, rid, text in reviewers[:3]:
            url = f"https://steamcommunity.com/profiles/{steamid}"
            lines.append(f"  - [{pt:.1f}h]({url}) — \"{text}\"")
    lines.append("")
    return "\n".join(lines)


def quick_stats_footer(reviews: list[dict[str, Any]]) -> str:
    """A one-line plain-text summary used by the TopComplaintsDialog."""
    total = len(reviews)
    if total == 0:
        return "No reviews."
    pos = sum(1 for r in reviews if r.get("voted_up"))
    pct = round(100 * pos / total, 1)
    return f"{total} reviews ({pos} positive / {total - pos} negative — {pct}% positive)"


__all__ = ["build_pre_ai_digest", "quick_stats_footer"]