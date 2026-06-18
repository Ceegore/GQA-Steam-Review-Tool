"""Orchestrate a full export: md + optional csv/json/per-lang + Obsidian copy.

Pulls together the small exporters behind a single ``run`` function so
callers don't need to remember which combo to invoke.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Callable, Optional, Any

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
    """
    log = log_cb or (lambda m: None)
    base = dest.with_suffix("")
    result: dict[str, Any] = {
        "md": None, "csv": None, "json": None,
        "per_lang": 0, "summary": None, "obsidian": None,
    }

    # Main .md
    md_text = MarkdownExporter.render(ctx, include_header=True)
    dest.write_text(md_text, encoding="utf-8")
    result["md"] = dest
    log(f"Exported {len(ctx.reviews)} reviews to {dest}")

    # Optional CSV
    if also_csv:
        csv_path = dest.with_suffix(".csv")
        try:
            reviews_to_csv(ctx.reviews, csv_path)
            result["csv"] = csv_path
            log(f"  + CSV: {csv_path}")
        except OSError as exc:
            log(f"  CSV write failed: {exc}")

    # Optional JSON
    if also_json:
        json_path = dest.with_suffix(".json")
        try:
            reviews_to_json(ctx.reviews, json_path)
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
            summary_path.write_text(summary_text, encoding="utf-8")
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


__all__ = ["run"]