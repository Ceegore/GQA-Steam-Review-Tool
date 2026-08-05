"""Internal helpers for the Markdown exporter.

Split out so the main ``markdown_exporter.py`` stays small. Functions
here are *not* part of the public API — the only entry point is
``MarkdownExporter.render``.
"""
from __future__ import annotations

import re
from typing import Optional, Any

from ..core.logger import get_logger
from ..services.pre_ai_digest import (
    build_pre_ai_digest, quick_stats_footer,
)
from ..services.review_analyzer import classify_review_type, extract_tags
from ..utils.coercion import safe_int, safe_str
from ..utils.markdown_utils import md_escape, ts_to_iso, yesno

_log = get_logger(__name__)


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
    """Render the pre-AI digest block.

    Returns ``[]`` on failure AND logs a ``warning`` — the old
    bare ``except Exception: pass`` silently dropped the entire
    digest for the export without telling the user, so a
    malformed review row (non-string ``review`` field, non-string
    keyword list entry) would remove the most useful top-of-file
    summary without any visible signal.
    """
    try:
        digest = build_pre_ai_digest(reviews, app_details=app, keyword_list=kw, top_n=5)
        return digest.splitlines() + [""]
    except Exception as exc:
        _log.exception(
            "pre-AI digest skipped (reviews=%d): %s",
            len(reviews), exc,
        )
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
    # ``r.get("language", "—")`` only fires when the *key* is
    # missing. The Steam API and the Apify normaliser can both
    # return a present key with value ``None`` for malformed
    # review rows; treat those the same as "missing" so the
    # language table is consistent and ``None`` never becomes a
    # ``dict`` key (which is invalid in JSON / Markdown tables).
    # The same review-set can also carry a NON-string
    # ``language`` (int / list / dict) — a hand-rolled test or
    # a buggy normaliser. The previous ``r.get("language") or
    # "—"`` short-circuited the int to itself (since non-zero
    # int is truthy) and then crashed ``md_escape(k)`` with
    # ``AttributeError: 'int' object has no attribute
    # 'replace'`` for the table cell. The R18-4 fix coerces
    # the language value to a str (falling back to ``"—"`` on
    # any non-string type) before storing in the dict. Same
    # R12-1 to R12-3 defensive-coercion pattern.
    langs: dict[str, int] = {}
    for r in reviews:
        raw_lang = r.get("language")
        if raw_lang is None or not isinstance(raw_lang, str):
            lang = "—"
        else:
            lang = raw_lang or "—"
        langs[lang] = langs.get(lang, 0) + 1

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
            # Escape ``k`` so a malformed language code (e.g.
            # ``"en|US"``) doesn't break the table. The Steam
            # API normally returns 2-5 letter codes but a
            # hand-rolled / Apify-normalised review can carry
            # an arbitrary string here.
            lines.append(f"| {md_escape(k)} | {langs[k]} |")
        lines.append("")
    return lines


def highlight_keywords(text: str, keyword_list: Optional[list[Any]]) -> str:
    if not keyword_list or not text:
        return text
    # Defensive: a non-string keyword entry used to crash
    # ``k.strip()`` with ``AttributeError`` and the bare
    # ``except Exception: pass`` then returned the unhighlighted
    # text without telling the user — the export looked correct
    # but the highlight pass was silently skipped. Same for any
    # later regex failure. Log + fall through to the safe
    # "return text unchanged" path.
    cleaned_kw = [k for k in keyword_list if isinstance(k, str) and k.strip()]
    if not cleaned_kw:
        return text
    try:
        sorted_kw = sorted(cleaned_kw, key=lambda k: -len(k))
        parts = []
        for k in sorted_kw:
            if " " in k:
                parts.append(re.escape(k))
            else:
                parts.append(re.escape(k) + r"(?:e?s|e?d|ing)?")
        pat = "|".join(parts)
        return re.sub(rf"(?i)\b({pat})\b", r"**\1**", text)
    except Exception as exc:
        _log.exception(
            "keyword highlight skipped (text len=%d, kws=%d): %s",
            len(text), len(cleaned_kw), exc,
        )
        return text


def render_review(idx: int, r: dict[str, Any], keyword_list: Optional[list[Any]]) -> list[str]:
    """Render one review block (table + body + footer separator)."""
    # ``r.get("author", {})`` only returns ``{}`` for a MISSING key.
    # A present-but-None ``author`` (e.g. from a hand-rolled review
    # dict) would fall through to ``None.get("steamid")`` and crash.
    # The trailing ``or {}`` collapses that case into the empty dict
    # so the subsequent ``.get`` is safe. Same pattern below for
    # ``last_played``.
    author = (r.get("author") or {}).get("steamid") or "—"
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
        f"| Language | `{r.get('language') or '—'}` |",
        f"| Posted | {ts_to_iso(r.get('timestamp_created'))} |",
        f"| Updated | {ts_to_iso(r.get('timestamp_updated'))} |",
        f"| Written during early access? | {yesno(r.get('written_during_early_access'))} |",
        f"| Purchase type | {purchase_badge} |",
        f"| Received for free | {yesno(r.get('received_for_free'))} |",
    ]
    playtime = safe_int(r.get("author", {}) or {}, "playtime_forever", 0)
    lines.append(f"| Playtime (minutes) | {playtime} (~{playtime/60:.1f} h) |")
    # ``or {}`` collapses a present-but-None ``author`` into a
    # empty dict (see the matching fix on line 136).
    lines.append(f"| Last played | {ts_to_iso((r.get('author') or {}).get('last_played'))} |")
    lines.append(f"| Helpful count | {safe_int(r, 'votes_up', 0)} |")
    lines.append(f"| Funny count | {safe_int(r, 'votes_funny', 0)} |")
    lines.append(f"| Comment count | {safe_int(r, 'comment_count', 0)} |")
    lines.append(
        f"| Review score (dev weight) | "
        # ``md_escape`` so a hypothetical ``"0.5|0.7"`` score
        # doesn't break the table — the safe_str default
        # (``"—"``) doesn't contain ``|`` but a real float
        # could in theory be a string with a ``|`` (e.g. a
        # hand-rolled / migrated review with a non-standard
        # score encoding).
        f"{md_escape(safe_str(r, 'weighted_vote_score', '—'))} |"
    )

    try:
        rtype = classify_review_type(r)
        if rtype != "other":
            lines.append(f"| **Auto-type** | **{rtype}** |")
    except Exception as exc:
        # These two helpers were hardened in R12-1 / R12-2 to
        # no longer crash on non-string review / keyword
        # fields, but a future regression (or a totally
        # unexpected input) could still surface here. Log a
        # warning so the user can spot a partial export; the
        # rest of the review row is still produced below.
        _log.exception(
            "classify_review_type failed for review #%d: %s",
            idx, exc,
        )

    try:
        tags = extract_tags(r, keyword_list)
        if tags:
            # ``md_escape`` each tag so a keyword containing a
            # ``|`` (the table-cell delimiter) doesn't break the
            # row. The previous ``f"`{t}`"`` was safe for the
            # common case (a normal keyword like "crash" or
            # "fps") but a user who enters ``"fps|60"`` in
            # their keyword list would produce a broken cell.
            tag_line = " ".join(f"`{md_escape(t)}`" for t in tags)
            lines.append(f"| **Tags** | {tag_line} |")
    except Exception as exc:
        _log.exception(
            "extract_tags failed for review #%d: %s",
            idx, exc,
        )
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
            pt = safe_int(a, "playtime_forever", 0) / 60.0
            steamid = safe_str(a, "steamid", "")
            if steamid:
                reviewers.append((
                    pt, steamid,
                    safe_str(r, "recommendationid", ""),
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
    except Exception as exc:
        # The previous bare ``except Exception: pass`` silently
        # dropped the Top-5-reviewers table for the whole
        # export on the first malformed review row. Log a
        # warning so a partial export is at least visible.
        _log.exception(
            "Top-5-reviewers footer skipped (reviews=%d): %s",
            len(reviews), exc,
        )
    try:
        stats = quick_stats_footer(reviews)
        if stats:
            lines += ["---", "", stats, ""]
    except Exception as exc:
        _log.exception(
            "quick_stats_footer skipped (reviews=%d): %s",
            len(reviews), exc,
        )
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