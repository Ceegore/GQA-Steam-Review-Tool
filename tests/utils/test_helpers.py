"""Tests for utility helpers."""
from datetime import datetime, timezone

from steam_review_tool.utils.text_utils import (
    sanitize_for_filename, make_export_basename, short_filter_label,
)
from steam_review_tool.utils.datetime_utils import (
    parse_since_preset, compute_since_timestamp,
)
from steam_review_tool.utils.url_utils import resolve_app_id
from steam_review_tool.utils.file_hash import file_content_hash
from steam_review_tool.utils.markdown_utils import (
    md_escape, ts_to_iso, yesno,
)


# ---- text_utils -----------------------------------------------------------


def test_sanitize_strips_invalid_chars():
    assert sanitize_for_filename('a/b\\c|d') == 'a_b_c_d'


def test_sanitize_collapses_whitespace():
    assert sanitize_for_filename("a   b\tc") == "a_b_c"


def test_sanitize_falls_back_to_app():
    assert sanitize_for_filename("") == "app"
    assert sanitize_for_filename("///") == "app"


def test_sanitize_truncates():
    s = "x" * 100
    out = sanitize_for_filename(s, max_len=20)
    assert len(out) <= 20


def test_make_export_basename_uses_expected_format():
    out = make_export_basename("My Game", "all", datetime(2026, 6, 18, 14, 30))
    assert out.startswith("GQA Reviewdump_")
    assert out.endswith(".md")
    assert "20260618-1430" in out


# ---- datetime_utils -------------------------------------------------------


def test_parse_since_preset_known_label():
    assert parse_since_preset("last 3 hours") == 3
    assert parse_since_preset("all time") == 0
    assert parse_since_preset("custom (date + time)") == -1


def test_parse_since_preset_unknown_returns_zero():
    assert parse_since_preset("nonsense") == 0


def test_compute_since_timestamp_all_time_returns_none():
    assert compute_since_timestamp("all time") is None


def test_compute_since_timestamp_relative_hours():
    now = datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)
    # Convert: now is naive Berlin time → the helper creates a Berlin now.
    # We pass `now=` so it works regardless of timezone.
    from steam_review_tool.core.timezone import BERLIN
    now_b = now.astimezone(BERLIN)
    ts = compute_since_timestamp("last 1 hour", now=now_b)
    assert ts is not None
    # The cutoff is 1h before now
    expected = int((now_b.timestamp()) - 3600)
    assert ts == expected


def test_compute_since_timestamp_custom_invalid_returns_none():
    assert compute_since_timestamp(
        "custom (date + time)", custom_date_str="not-a-date",
    ) is None


def test_compute_since_timestamp_custom_valid():
    ts = compute_since_timestamp(
        "custom (date + time)",
        custom_date_str="2026-06-18", custom_time_str="12:00",
    )
    assert ts is not None
    assert ts > 0


# ---- url_utils ------------------------------------------------------------


def test_resolve_app_id_bare_int():
    assert resolve_app_id("12345") == 12345


def test_resolve_app_id_store_url():
    assert resolve_app_id("https://store.steampowered.com/app/4311090/x") == 4311090


def test_resolve_app_id_steam_run_url():
    assert resolve_app_id("steam://run/999") == 999


def test_resolve_app_id_garbage():
    assert resolve_app_id("not a url at all") is None
    assert resolve_app_id("") is None


# ---- file_hash ------------------------------------------------------------


def test_file_content_hash_changes_with_content(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("hello")
    h1 = file_content_hash(p)
    p.write_text("hello world")
    h2 = file_content_hash(p)
    assert h1 != h2
    assert len(h1) == 40  # SHA-1 hex


def test_file_content_hash_missing_returns_empty(tmp_path):
    assert file_content_hash(tmp_path / "no-such.txt") == ""


# ---- markdown_utils -------------------------------------------------------


def test_md_escape_pipe():
    assert md_escape("a|b") == "a\\|b"


def test_md_escape_carriage_return():
    assert md_escape("a\rb") == "ab"


def test_md_escape_none():
    assert md_escape(None) == ""


def test_ts_to_iso_none():
    assert ts_to_iso(None) == "—"


def test_ts_to_iso_zero():
    assert ts_to_iso(0) == "—"


def test_ts_to_iso_valid():
    out = ts_to_iso(1700000000)
    assert "2023-" in out
    assert "UTC" in out


def test_yesno():
    assert yesno(True) == "✓"
    assert yesno(False) == "✗"
    assert yesno(None) == "—"