"""Tests for Markdown / CSV / JSON exporters."""
import csv
import json
from pathlib import Path

from steam_review_tool.models.export_context import ExportContext
from steam_review_tool.exporters.markdown_exporter import MarkdownExporter
from steam_review_tool.exporters.csv_exporter import reviews_to_csv, COLUMNS
from steam_review_tool.exporters.json_exporter import reviews_to_json
from steam_review_tool.exporters.per_language_exporter import (
    group_by_language, write_per_language, build_summary,
)
from steam_review_tool.exporters.obsidian_copier import copy_to_obsidian_vault
from steam_review_tool.exporters.export_orchestrator import run


def _sample_reviews():
    return [
        {"recommendationid": "r1", "language": "english", "voted_up": True,
         "review": "great graphics and no crash", "votes_up": 5,
         "author": {"steamid": "111", "playtime_forever": 600}},
        {"recommendationid": "r2", "language": "german", "voted_up": False,
         "review": "schrecklich, stürzt ab", "votes_up": 1,
         "author": {"steamid": "222", "playtime_forever": 30}},
        {"recommendationid": "r3", "language": "english", "voted_up": True,
         "review": "amazing game", "votes_up": 2,
         "author": {"steamid": "333", "playtime_forever": 1200}},
    ]


def _sample_app():
    return {
        "name": "Test Game",
        "type": "game",
        "developers": ["Dev One"],
        "publishers": ["Pub One"],
        "platforms": {"windows": True, "mac": False},
        "release_date": {"date": "2025-01-01", "coming_soon": False},
    }


# ---- MarkdownExporter -----------------------------------------------------


def test_markdown_contains_title_and_sections():
    ctx = ExportContext(
        app_id=42, app_details=_sample_app(), reviews=_sample_reviews(),
        language_param="all", review_filter="all", review_type="all",
        day_range=None, min_date_ts=None, keyword_list=["graphics"],
    )
    md = MarkdownExporter.render(ctx)
    assert "# Steam Reviews — Test Game" in md
    assert "## Game Information" in md
    assert "## Applied Filters" in md
    assert "## Summary" in md
    assert "## All Reviews" in md
    assert "### Review #1" in md
    assert "### Review #3" in md


def test_markdown_highlights_keywords():
    ctx = ExportContext(
        app_id=42, app_details=_sample_app(),
        reviews=[{"recommendationid": "r1", "language": "english",
                  "voted_up": True, "review": "great graphics",
                  "author": {"steamid": "1"}}],
        language_param="all", review_filter="all", review_type="all",
        day_range=None, min_date_ts=None, keyword_list=["graphics"],
    )
    md = MarkdownExporter.render(ctx)
    assert "**graphics**" in md


def test_markdown_continuation_omits_header():
    ctx = ExportContext(
        app_id=42, app_details=_sample_app(),
        reviews=_sample_reviews()[:1],
        language_param="all", review_filter="all", review_type="all",
        day_range=None, min_date_ts=None,
    )
    full = MarkdownExporter.render(ctx, include_header=True)
    cont = MarkdownExporter.render(ctx, include_header=False)
    assert "## Game Information" in full
    assert "## Game Information" not in cont
    # All Reviews section is always present
    assert "## All Reviews" in cont


def test_markdown_handles_missing_author():
    ctx = ExportContext(
        app_id=42, app_details=_sample_app(),
        reviews=[{"recommendationid": "r1", "language": "english",
                  "voted_up": True, "review": "x",
                  "author": {}}],
        language_param="all", review_filter="all", review_type="all",
        day_range=None, min_date_ts=None,
    )
    md = MarkdownExporter.render(ctx)
    assert "### Review #1" in md


# ---- CSV exporter ---------------------------------------------------------


def test_csv_writes_expected_columns(tmp_path):
    dest = tmp_path / "reviews.csv"
    n = reviews_to_csv(_sample_reviews(), dest)
    assert n == 3
    with open(dest, encoding="utf-8") as f:
        rows = list(csv.reader(f))
    assert rows[0] == COLUMNS
    assert len(rows) == 4  # header + 3 rows


def test_csv_quotes_review_text_with_newlines(tmp_path):
    reviews = [{"recommendationid": "r1", "language": "english",
                "voted_up": True, "review": "line1\nline2",
                "author": {}}]
    dest = tmp_path / "reviews.csv"
    reviews_to_csv(reviews, dest)
    text = dest.read_text(encoding="utf-8")
    assert "line1 line2" in text  # newline replaced with space


# ---- JSON exporter --------------------------------------------------------


def test_json_roundtrip(tmp_path):
    reviews = _sample_reviews()
    dest = tmp_path / "reviews.json"
    n = reviews_to_json(reviews, dest)
    assert n == 3
    loaded = json.loads(dest.read_text(encoding="utf-8"))
    assert loaded == reviews


# ---- Per-language exporter ------------------------------------------------


def test_group_by_language():
    groups = group_by_language(_sample_reviews())
    assert set(groups) == {"english", "german"}
    assert len(groups["english"]) == 2


def test_write_per_language_one_language_no_extra():
    ctx = ExportContext(
        app_id=42, app_details=_sample_app(),
        reviews=[_sample_reviews()[0]],
        language_param="english", review_filter="all", review_type="all",
        day_range=None, min_date_ts=None,
    )
    n = write_per_language(ctx.reviews, Path("/tmp/x"), ctx)
    assert n == 0


def test_write_per_language_multiple_languages(tmp_path):
    base = tmp_path / "export"
    ctx = ExportContext(
        app_id=42, app_details=_sample_app(), reviews=_sample_reviews(),
        language_param="all", review_filter="all", review_type="all",
        day_range=None, min_date_ts=None,
    )
    n = write_per_language(ctx.reviews, base, ctx)
    assert n == 2  # english + german
    assert (tmp_path / "export.english.md").exists()
    assert (tmp_path / "export.german.md").exists()


def test_build_summary_empty():
    md = build_summary([])
    assert "No reviews" in md


def test_build_summary_contains_sections():
    md = build_summary(_sample_reviews(), _sample_app())
    assert "Reviewer stats summary" in md
    assert "Totals" in md
    assert "Language distribution" in md
    assert "Purchase type" in md


# ---- Obsidian copier ------------------------------------------------------


def test_obsidian_copy_creates_file(tmp_path):
    src = tmp_path / "x.md"
    src.write_text("hello")
    vault = tmp_path / "vault"
    err = copy_to_obsidian_vault(src, vault)
    assert err is None
    assert (vault / "x.md").exists()


def test_obsidian_copy_skips_when_identical(tmp_path):
    src = tmp_path / "x.md"
    src.write_text("hello")
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "x.md").write_text("hello")
    # Should be a no-op (return None) because SHA-1 matches
    err = copy_to_obsidian_vault(src, vault)
    assert err is None
    # mtime should NOT have been updated (file unchanged)


def test_obsidian_copy_no_vault_is_noop(tmp_path):
    src = tmp_path / "x.md"
    src.write_text("hello")
    err = copy_to_obsidian_vault(src, None)
    assert err is None


# ---- Orchestrator ---------------------------------------------------------


def test_orchestrator_md_only(tmp_path):
    ctx = ExportContext(
        app_id=42, app_details=_sample_app(), reviews=_sample_reviews(),
        language_param="all", review_filter="all", review_type="all",
        day_range=None, min_date_ts=None,
    )
    out = tmp_path / "out.md"
    logs: list[str] = []
    result = run(ctx, out, log_cb=logs.append)
    assert result["md"].exists()
    assert result["csv"] is None
    assert result["json"] is None
    assert any("Exported 3 reviews" in m for m in logs)


def test_orchestrator_full_combo(tmp_path):
    ctx = ExportContext(
        app_id=42, app_details=_sample_app(), reviews=_sample_reviews(),
        language_param="all", review_filter="all", review_type="all",
        day_range=None, min_date_ts=None,
    )
    out = tmp_path / "out.md"
    result = run(
        ctx, out,
        also_csv=True, also_json=True, per_language=True,
    )
    assert result["md"].exists()
    assert result["csv"] and result["csv"].exists()
    assert result["json"] and result["json"].exists()
    assert result["per_lang"] == 2