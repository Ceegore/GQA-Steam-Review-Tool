"""Tests for ``services.pre_ai_digest``."""
from steam_review_tool.services.pre_ai_digest import (
    build_pre_ai_digest, quick_stats_footer,
)


def test_digest_empty_returns_marker():
    md = build_pre_ai_digest([])
    assert "No reviews yet" in md


def test_digest_includes_pos_neg_split():
    reviews = [
        {"review": "great game", "voted_up": True,
         "author": {"steamid": "1"}},
        {"review": "boring", "voted_up": False,
         "author": {"steamid": "2"}},
    ]
    md = build_pre_ai_digest(reviews)
    assert "**2** reviews" in md
    assert "1 positive" in md
    assert "1 negative" in md
    assert "50.0% positive" in md


def test_digest_includes_app_name():
    md = build_pre_ai_digest(
        [{"review": "great", "voted_up": True, "author": {}}],
        app_details={"name": "My Game"},
    )
    assert "My Game" in md


def test_quick_stats_footer_zero():
    assert quick_stats_footer([]) == "No reviews."


def test_quick_stats_footer_counts():
    reviews = [
        {"voted_up": True},
        {"voted_up": False},
        {"voted_up": True},
    ]
    s = quick_stats_footer(reviews)
    assert "3 reviews" in s
    assert "2 positive" in s
    assert "1 negative" in s