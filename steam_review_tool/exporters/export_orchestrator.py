"""Orchestrate a full export: md + optional csv/json/per-lang + Obsidian copy.

Pulls together the small exporters behind a single ``run`` function so
callers don't need to remember which combo to invoke.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional, Any

from ..core.atomic_write import atomic_write_text
from ..models.export_context import ExportContext
from .csv_exporter import reviews_to_csv
from .json_exporter import reviews_to_json
from .markdown_exporter import MarkdownExporter
from .obsidian_copier import copy_to_obsidian_vault
from .per_language_exporter import build_summary, write_per_language


def run(
    ctx: ExportContext,
    dest: Path,
    *,
    also_csv: bool = False,
    also_json: bool = False,
    per_language: bool = False,
    write_summary: bool = False,
    obsidian_vault: Optional[Path] = None,
    log_cb: Optional[Callable[[str], None]] = None,
) -> dict[str, Any]:
    """Run the export and return a small result dict.

    Returns ``{md, csv, json, per_lang, summary, obsidian}`` each
    containing a Path (or None) so the caller can show toasts.

    Every write path goes through :func:`atomic_write_text` so a
    crash mid-export cannot leave a half-written ``.md`` /
    ``.csv`` / ``.json`` / ``.summary.md`` behind. ``MarkdownExporter.write``
    already used atomic writes; the orchestrator previously did not,
    which was an inconsistency that bit a real user.
    """
    log = log_cb or (lambda m: None)
    base = dest.with_suffix("")
    result: dict[str, Any] = {
        "md": None, "csv": None, "json": None,
        "per_lang": 0, "summary": None, "obsidian": None,
    }

    # Main .md
    md_text = MarkdownExporter.render(ctx, include_header=True)
    atomic_write_text(dest, md_text)
    result["md"] = dest
    log(f"Exported {len(ctx.reviews)} reviews to {dest}")

    # Optional CSV
    if also_csv:
        csv_path = dest.with_suffix(".csv")
        try:
            _write_csv_atomic(ctx.reviews, csv_path)
            result["csv"] = csv_path
            log(f"  + CSV: {csv_path}")
        except OSError as exc:
            log(f"  CSV write failed: {exc}")

    # Optional JSON
    if also_json:
        json_path = dest.with_suffix(".json")
        try:
            _write_json_atomic(ctx.reviews, json_path)
            result["json"] = json_path
            log(f"  + JSON: {json_path}")
        except OSError as exc:
            log(f"  JSON write failed: {exc}")

    # Per-language splits
    if per_language:
        try:
            n = write_per_language(ctx.reviews, base, ctx)
            result["per_lang"] = n
            if n:
                log(f"  + {n} per-language files")
        except Exception as exc:
            log(f"  Per-language export failed: {exc}")

    # Standalone summary
    if write_summary:
        try:
            summary_text = build_summary(ctx.reviews, ctx.app_details)
            summary_path = Path(f"{base}.summary.md")
            atomic_write_text(summary_path, summary_text)
            result["summary"] = summary_path
            log(f"  + Summary: {summary_path}")
        except OSError as exc:
            log(f"  Summary write failed: {exc}")

    # Obsidian vault copy
    if obsidian_vault:
        err = copy_to_obsidian_vault(dest, obsidian_vault)
        if err is None:
            result["obsidian"] = obsidian_vault / dest.name
            log(f"  ✓ Copied to Obsidian vault: {obsidian_vault}")
        else:
            log(f"  Obsidian copy failed: {err}")

    return result


def _write_csv_atomic(
    reviews: list[dict[str, Any]], dest: Path,
) -> None:
    """Render the CSV and write atomically.

    Delegates to the public :func:`reviews_to_csv` (now
    itself atomic in the R16 fix) so the row-building logic
    lives in exactly one place — the previous private
    duplicate of the 30-row CSV writer used here was a
    drift hazard: a future change to the safe-``str`` /
    safe-int / newline-replacement logic would have to be
    applied to both sites.
    """
    from .csv_exporter import reviews_to_csv
    reviews_to_csv(reviews, dest)


def _write_json_atomic(
    reviews: list[dict[str, Any]], dest: Path,
) -> None:
    """Render JSON and write atomically.

    Delegates to the public :func:`reviews_to_json` (now
    itself atomic in the R16 fix) for the same
    de-duplication reason as :func:`_write_csv_atomic`.
    """
    from .json_exporter import reviews_to_json
    reviews_to_json(reviews, dest)


__all__ = ["run"]