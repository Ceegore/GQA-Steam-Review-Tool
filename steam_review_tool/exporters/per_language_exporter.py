"""Per-language split export + standalone Markdown summary."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional, Any

from ..core.logger import get_logger
from ..models.export_context import ExportContext
from ..utils.coercion import safe_int, safe_str
from ..utils.markdown_utils import md_escape
from .markdown_exporter import MarkdownExporter


_log = get_logger(__name__)


def _coerce_lang_key(lang: Any) -> str:
    """Defensive coercion for the ``language`` field.

    A hand-rolled / Apify-normalised review can carry a
    non-string ``language`` value (int, list, None). The previous
    ``(r.get("language") or "unknown").strip() or "unknown"``
    crashed with ``AttributeError`` for any non-string
    (e.g. an int) and the bare ``except OSError`` below
    didn't even catch the AttributeError — it would
    propagate up to the orchestrator and silently skip
    the whole per-language export. The fix (R18-4) is
    the same R12-1 to R12-3 pattern: ``isinstance`` check
    first, then ``str`` coercion, then ``.strip()``.
    """
    if not isinstance(lang, str):
        return "unknown"
    s = lang.strip()
    return s or "unknown"


def group_by_language(reviews: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Return ``{lang_code: [review, ...]}``."""
    out: dict[str, list[dict[str, Any]]] = {}
    for r in reviews:
        lang = _coerce_lang_key(r.get("language"))
        out.setdefault(lang, []).append(r)
    return out


def write_per_language(
    reviews: list[dict[str, Any]], base_path_no_ext: Path, export_ctx: ExportContext,
) -> int:
    """Write one extra ``.md`` per language (if reviews span >1 langs).

    Returns the number of extra files written. Each file is written
    atomically so a crash mid-write cannot leave a half-written
    per-language ``.md`` behind.
    """
    from ..core.atomic_write import atomic_write_text
    groups = group_by_language(reviews)
    if len(groups) <= 1:
        return 0
    n = 0
    base = str(base_path_no_ext)
    for lang, lang_reviews in groups.items():
        # ``group_by_language`` already coerces non-string
        # language values to ``"unknown"`` (R18-4 fix) so
        # ``lang`` is guaranteed to be a str here. The
        # safe-char replacement below stays as defence
        # against the legit string case.
        safe_lang = "".join(
            c if c.isalnum() or c in "-_." else "_" for c in lang
        ) or "unknown"
        per_path = Path(f"{base}.{safe_lang}.md")
        ctx = ExportContext(**{**export_ctx.__dict__, "reviews": lang_reviews})
        try:
            md = MarkdownExporter.render(ctx, include_header=True)
            atomic_write_text(per_path, md)
            n += 1
        except OSError as exc:
            # The previous version had a bare
            # ``except OSError: pass`` here which silently
            # dropped the per-language file write failure.
            # A user with a full disk / read-only vault would
            # see the main ``.md`` export succeed but every
            # per-language file would silently fail — the
            # orchestrator's returned count would be lower
            # than expected with no visible signal. Log a
            # warning (R12-4 to R12-7 + R17-3 lesson) so the
            # dev can spot the partial export in stderr.
            # Continue with the remaining languages so a
            # single bad file doesn't drop the whole
            # per-language batch.
            _log.warning(
                "per-language file write failed for %s: %s: %s",
                per_path, type(exc).__name__, exc,
            )
    return n


# ---- Standalone summary ----------------------------------------------------

_STOP_WORDS = set(
    "the and a an is of to in for on with this that it as at by be or are "
    "was not have from but".split()
)


def build_summary(
    reviews: list[dict[str, Any]], app_details: Optional[dict[str, Any]] = None,
) -> str:
    """Markdown summary: totals, langs, purchase types, top-10 reviewers,
    top-20 words. Independent of the main ``.md`` exporter.
    """
    total = len(reviews)
    if total == 0:
        return "# Reviewer stats summary\n\n_No reviews._\n"

    pos = sum(1 for r in reviews if r.get("voted_up"))
    neg = total - pos
    pct = round(100 * pos / total, 1)

    # ``r.get("language", "—")`` only fires when the key is missing.
    # The Steam API and the Apify normaliser can both return a present
    # key with value ``None`` for malformed review rows; treat those
    # the same as "missing" so the language table is consistent
    # (and ``None`` never becomes a dict key).
    langs: dict[str, int] = {}
    for r in reviews:
        lang = r.get("language") or "—"
        langs[lang] = langs.get(lang, 0) + 1

    purchases = {"steam": 0, "non_steam": 0, "unknown": 0}
    for r in reviews:
        if r.get("steam_purchase") is True:
            purchases["steam"] += 1
        elif r.get("steam_purchase") is False:
            purchases["non_steam"] += 1
        else:
            purchases["unknown"] += 1

    reviewers: list[tuple[str, int, str, str]] = []
    for r in reviews:
        author = r.get("author", {}) or {}
        # ``safe_str`` collapses a present-but-None value into
        # the missing-key default. The old ``str(... .get(...,
        # "—"))`` pattern rendered the literal ``"None"`` for
        # present-but-None fields — same R5-1 bug that the
        # main export pipeline caught. The downstream URL
        # ``f"…/profiles/{steamid}/review/{rid}"`` then
        # contained the literal ``None`` substring.
        rid = safe_str(r, "recommendationid", "—")
        steamid = safe_str(author, "steamid", "—")
        pt = safe_int(author, "playtime_forever", 0)
        text = (r.get("review") or "").strip().replace("\n", " ")
        reviewers.append((steamid, pt, rid, text))
    reviewers.sort(key=lambda x: x[1], reverse=True)
    top10 = reviewers[:10]

    words: dict[str, int] = {}
    for r in reviews:
        text = (r.get("review") or "").lower()
        for w in re.findall(r"[a-zäöüß]{3,}", text):
            if w in _STOP_WORDS:
                continue
            words[w] = words.get(w, 0) + 1
    top_words = sorted(words.items(), key=lambda kv: kv[1], reverse=True)[:20]

    name = (app_details or {}).get("name") if app_details else None
    lines = ["# Reviewer stats summary"]
    if name:
        lines.append(f"\n**{name}**")
    lines.append("")
    lines.append("## Totals")
    lines.append("")
    lines.append(f"- **Total reviews**: {total}")
    lines.append(f"- **Positive**: {pos} ({pct}%)")
    lines.append(f"- **Negative**: {neg} ({round(100 - pct, 1)}%)")
    lines.append("")
    lines.append("## Language distribution")
    lines.append("")
    lines.append("| Language | Reviews |")
    lines.append("|---|---|")
    for k in sorted(langs, key=lambda _k: langs[_k], reverse=True):
        # ``md_escape`` so a malformed language code containing
        # ``|`` (the table-cell delimiter) doesn't break the
        # row. Same R14 fix as the main ``render_summary``.
        lines.append(f"| {md_escape(k)} | {langs[k]} |")
    lines.append("")
    lines.append("## Purchase type")
    lines.append("")
    lines.append("| Type | Reviews |")
    lines.append("|---|---|")
    for k, v in purchases.items():
        lines.append(f"| {k} | {v} |")
    lines.append("")
    lines.append("## Top 10 most-active reviewers (by playtime)")
    lines.append("")
    lines.append("| SteamID | Hours | Recommendation | Preview |")
    lines.append("|---|---|---|---|")
    for steamid, pt, rid, text in top10:
        preview = text[:80] + ("…" if len(text) > 80 else "")
        # ``md_escape`` the preview so a review text containing
        # ``|`` (the table-cell delimiter) doesn't break the
        # row. The review is the user's free-form text and a
        # Steam reviewer can write literally anything — a
        # ``"the game | it's bad"`` sentence would otherwise
        # spill into a phantom second column.
        lines.append(
            f"| `{steamid}` | {pt/60:.1f} | "
            f"[link](https://steamcommunity.com/profiles/{steamid}/review/{rid}) "
            f"| {md_escape(preview)} |"
        )
    lines.append("")
    if top_words:
        lines.append("## Top 20 words in review text")
        lines.append("")
        lines.append("| Word | Count |")
        lines.append("|---|---|")
        for w, c in top_words:
            lines.append(f"| {w} | {c} |")
        lines.append("")
    return "\n".join(lines)


__all__ = ["group_by_language", "write_per_language", "build_summary"]