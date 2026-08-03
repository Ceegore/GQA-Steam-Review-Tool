"""Internal helpers for the Markdown exporter.

Split out so the main ``markdown_exporter.py`` stays small. Functions
here are *not* part of the public API — the only entry point is
``MarkdownExporter.render``.
"""
from __future__ import annotations

import re
from typing import Optional, Any

from ..services.pre_ai_digest import (
    build_pre_ai_digest, quick_stats_footer,
)
from ..services.review_analyzer import classify_review_type, extract_tags
from ..utils.markdown_utils import md_escape, ts_to_iso, yesno


def render_title_block(app_id: int, app: dict[str, Any], fetched_at_iso: str) -> list[str]:
    """Render the document title and timestamp block."""
    name = app.get("name") or f"App {app_id}"
    return [
        f"# Steam Reviews — {name}",
        "",
        f"*Export generated {fetched_at_iso}*",
        "",
    ]


def render_digest(reviews: list[dict[str, Any]], app: dict[str, Any], kw: Optional[list[Any]]) -> list[str]:
    """Render the pre-AI digest block. Returns ``[]`` on any error."""
    try:
        digest = build_pre_ai_digest(reviews, app_details=app, keyword_list=kw, top_n=5)
        return digest.splitlines() + [""]
    except Exception:
        return []


def render_game_info(app_id: int, app: dict[str, Any]) -> list[str]:
    """Render the "Game Information" Markdown table."""
    name = app.get("name") or f"App {app_id}"
    rel = app.get("release_date", {}) or {}
    platforms = app.get("platforms", {}) or {}
    plat_str = ", ".join(k for k, v in platforms.items() if v) or "—"
    return [
        "## Game Information",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| App ID | `{app_id}` |",
        f"| Name | {md_escape(name)} |",
        f"| Type | {md_escape(app.get('type', '—'))} |",
        f"| Developer | {md_escape(', '.join(app.get('developers', []) or ['—']))} |",
        f"| Publisher | {md_escape(', '.join(app.get('publishers', []) or ['—']))} |",
        f"| Release | {md_escape(rel.get('date', '—'))} "
        f"({'coming soon' if rel.get('coming_soon') else 'released'}) |",
        f"| Platforms | {md_escape(plat_str)} |",
        f"| Store page | https://store.steampowered.com/app/{app_id}/ |",
        "",
    ]


def render_filters(ctx) -> list[str]:
    return [
        "## Applied Filters",
        "",
        "| Parameter | Value |",
        "|---|---|",
        f"| language | `{ctx.language_param}` |",
        f"| filter (sort) | `{ctx.review_filter}` |",
        f"| review_type | `{ctx.review_type}` |",
        f"| day_range | {ctx.day_range if ctx.day_range is not None else 'all time'} |",
        f"| min_date | {ts_to_iso(ctx.min_date_ts) if ctx.min_date_ts else '—'} |",
        "",
    ]


def render_summary(reviews: list[dict[str, Any]]) -> list[str]:
    total = len(reviews)
    pos = sum(1 for r in reviews if r.get("voted_up"))
    neg = total - pos
    pct = round(100 * pos / total, 1) if total else 0.0
    langs: dict[str, int] = {}
    for r in reviews:
        langs[r.get("language", "—")] = langs.get(r.get("language", "—"), 0) + 1

    lines = [
        "## Summary",
        "",
        f"- Total reviews (after filters): **{total}**",
        f"- Positive: **{pos}** ({pct}%)",
        f"- Negative: **{neg}** ({round(100 - pct, 1)}%)",
        "",
    ]
    if langs:
        lines += ["**Language distribution:**", ""]
        lines += ["| Language | Reviews |", "|---|---|"]
        for k in sorted(langs, key=lambda _k: langs[_k], reverse=True):
            lines.append(f"| {k} | {langs[k]} |")
        lines.append("")
    return lines


def highlight_keywords(text: str, keyword_list: Optional[list[Any]]) -> str:
    if not keyword_list or not text:
        return text
    try:
        sorted_kw = sorted(
            (k for k in keyword_list if k.strip()),
            key=lambda k: -len(k),
        )
        if not sorted_kw:
            return text
        parts = []
        for k in sorted_kw:
            if " " in k:
                parts.append(re.escape(k))
            else:
                parts.append(re.escape(k) + r"(?:e?s|e?d|ing)?")
        pat = "|".join(parts)
        return re.sub(rf"(?i)\b({pat})\b", r"**\1**", text)
    except Exception:
        return text


def render_review(idx: int, r: dict[str, Any], keyword_list: Optional[list[Any]]) -> list[str]:
    """Render one review block (table + body + footer separator)."""
    author = r.get("author", {}).get("steamid") or "—"
    profile = (
        f"https://steamcommunity.com/profiles/{author}"
        if author != "—" else "—"
    )
    review_id = r.get("recommendationid") or "—"
    review_url = (
        f"https://steamcommunity.com/profiles/{author}/review/{review_id}"
        if author != "—" and review_id != "—" else "—"
    )

    if r.get("steam_purchase"):
        purchase_badge = "✅ verified"
    elif r.get("received_for_free"):
        purchase_badge = "🎁 free"
    elif r.get("steam_purchase") is False:
        purchase_badge = "🔑 key"
    else:
        purchase_badge = "—"

    lines = [
        f"### Review #{idx}",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Recommendation | {'👍 Positive' if r.get('voted_up') else '👎 Negative'} |",
        f"| Author | `{author}` ([profile]({profile})) |",
        f"| Review URL | [link]({review_url}) |",
        f"| Language | `{r.get('language', '—')}` |",
        f"| Posted | {ts_to_iso(r.get('timestamp_created'))} |",
        f"| Updated | {ts_to_iso(r.get('timestamp_updated'))} |",
        f"| Written during early access? | {yesno(r.get('written_during_early_access'))} |",
        f"| Purchase type | {purchase_badge} |",
        f"| Received for free | {yesno(r.get('received_for_free'))} |",
    ]
    playtime = r.get("author", {}).get("playtime_forever", 0) or 0
    lines.append(f"| Playtime (minutes) | {playtime} (~{playtime/60:.1f} h) |")
    lines.append(f"| Last played | {ts_to_iso(r.get('author', {}).get('last_played'))} |")
    lines.append(f"| Helpful count | {r.get('votes_up', 0)} |")
    lines.append(f"| Funny count | {r.get('votes_funny', 0)} |")
    lines.append(f"| Comment count | {r.get('comment_count', 0)} |")
    lines.append(f"| Review score (dev weight) | {r.get('weighted_vote_score', '—')} |")

    try:
        rtype = classify_review_type(r)
        if rtype != "other":
            lines.append(f"| **Auto-type** | **{rtype}** |")
    except Exception:
        pass

    try:
        tags = extract_tags(r, keyword_list)
        if tags:
            tag_line = " ".join(f"`{t}`" for t in tags)
            lines.append(f"| **Tags** | {tag_line} |")
    except Exception:
        pass
    lines.append("")

    review_text = (r.get("review") or "").strip()
    if review_text:
        lines.append("**Review text:**")
        lines.append("")
        highlighted = highlight_keywords(review_text, keyword_list)
        lines.append("> " + highlighted.replace("\n", "\n> "))
    else:
        lines.append("*(no review text)*")
    lines.append("")
    lines.append("---")
    lines.append("")
    return lines


def render_footer(reviews: list[dict[str, Any]]) -> list[str]:
    """Render the closing "Notes" + "Top reviewers" + one-line summary."""
    lines = [
        "",
        "## Notes",
        "",
        "- Reviews are fetched from the public Steam Store API "
        "(`/appreviews/<id>?json=1`) using cursor-based pagination.",
        "- The `language=all` parameter asks Steam to return reviews in "
        "all languages, but Steam may still respect your Steam-account "
        "language preferences.",
        "- `min_date` is applied client-side (Steam API has no native "
        "`since` parameter).",
        "- Some reviews are deleted/withdrawn by users after fetching.",
        "",
    ]
    try:
        reviewers = []
        for r in reviews:
            a = r.get("author", {}) or {}
            pt = int(a.get("playtime_forever", 0) or 0) / 60.0
            steamid = str(a.get("steamid", ""))
            if steamid:
                reviewers.append((
                    pt, steamid,
                    str(r.get("recommendationid", "")),
                    a.get("playtime_at_review", 0),
                ))
        reviewers.sort(key=lambda x: -x[0])
        if reviewers:
            lines += [
                "## Top 5 reviewers by playtime (for follow-up)",
                "",
                "| Hours | SteamID | Recommendation | Profile |",
                "|---|---|---|---|",
            ]
            for pt, steamid, rid, _ in reviewers[:5]:
                url = f"https://steamcommunity.com/profiles/{steamid}"
                rev = f"https://steamcommunity.com/profiles/{steamid}/review/{rid}"
                lines.append(
                    f"| {pt:.1f} | `{steamid}` | [link]({rev}) | [open]({url}) |"
                )
            lines.append("")
    except Exception:
        pass
    try:
        stats = quick_stats_footer(reviews)
        if stats:
            lines += ["---", "", stats, ""]
    except Exception:
        pass
    return lines


__all__ = [
    "render_title_block",
    "render_digest",
    "render_game_info",
    "render_filters",
    "render_summary",
    "render_review",
    "render_footer",
    "highlight_keywords",
]