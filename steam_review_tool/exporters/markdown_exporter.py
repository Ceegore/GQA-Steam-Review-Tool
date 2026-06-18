"""Public Markdown exporter — renders an ``ExportContext`` to .md text.

Implements the ``IExportTarget`` protocol (via duck-typing: has
``name`` + ``write(ctx, dest) -> int``).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..models.export_context import ExportContext
from . import markdown_helpers as H


class MarkdownExporter:
    """Renders a clean, self-contained .md file with game info + all reviews."""

    name = "markdown"

    @classmethod
    def render(
        cls, ctx: ExportContext, include_header: bool = True,
    ) -> str:
        """Render the review collection as a Markdown document.

        ``include_header=False`` skips the title, game-info table,
        filters table, and language distribution — used for split-export
        continuation files (part 2, 3, …).
        """
        lines: list[str] = []
        app = ctx.app_details or {}
        keyword_list = ctx.keyword_list

        if include_header:
            lines += H.render_title_block(
                ctx.app_id, app, ctx.fetched_at.isoformat(),
            )
            lines += H.render_digest(ctx.reviews, app, keyword_list)
            lines += H.render_game_info(ctx.app_id, app)
            lines += H.render_filters(ctx)
            lines += H.render_summary(ctx.reviews)

        lines.append("## All Reviews")
        lines.append("")

        for i, r in enumerate(ctx.reviews, 1):
            lines += H.render_review(i, r, keyword_list)

        if include_header:
            lines += H.render_footer(ctx.reviews)

        return "\n".join(lines)

    @classmethod
    def write(cls, ctx: ExportContext, dest: Path) -> int:
        """Write the rendered document to ``dest``. Returns review count.

        Creates any missing parent directories. Uses an atomic write
        so a crash mid-write doesn't leave a half-written .md file.
        """
        from ..core.atomic_write import atomic_write_text
        text = cls.render(ctx, include_header=True)
        atomic_write_text(dest, text)
        return len(ctx.reviews)

    @staticmethod
    def render_continuation(ctx: ExportContext) -> str:
        """Render a continuation file (no header / footer)."""
        return MarkdownExporter.render(ctx, include_header=False)


__all__ = ["MarkdownExporter"]