"""Tests for ``services.review_analyzer`` (pure functions)."""
from steam_review_tool.services.review_analyzer import (
    classify_review_type,
    extract_tags,
    aggregate_top_themes,
    compute_deltas,
    split_first_24h,
    compute_playtime_histogram,
)


# ----- classify_review_type ----------------------------------------------


def test_classify_bug_phrase_wins_over_positive_vote():
    # "great" is positive, but "crashes" is a stronger bug signal.
    r = {"review": "great game but crashes constantly", "voted_up": True}
    assert classify_review_type(r) == "bug"


def test_classify_feature_request_phrase():
    r = {"review": "would be nice to have a dark mode option",
         "voted_up": True}
    assert classify_review_type(r) == "feature"


def test_classify_praise_with_positive_vote():
    r = {"review": "amazing game, masterpiece", "voted_up": True}
    assert classify_review_type(r) == "praise"


def test_classify_complaint_with_negative_vote():
    r = {"review": "boring, repetitive, waste of money", "voted_up": False}
    assert classify_review_type(r) == "complaint"


def test_classify_other_when_text_empty():
    assert classify_review_type({"review": "", "voted_up": True}) == "other"


# ----- extract_tags --------------------------------------------------------


def test_extract_tags_single_word_word_boundary():
    tags = extract_tags({"review": "I love the graphics and graphics design"})
    assert "graphics" in tags


def test_extract_tags_multi_word_substring():
    tags = extract_tags({"review": "this game suffers from black screen bug"})
    assert "black screen" in tags


def test_extract_tags_stem_forms():
    # crash → crashes / crashed / crashing all match
    tags = extract_tags({"review": "The game crashes, then crashed, then crashing"})
    assert "crash" in tags


def test_extract_tags_no_duplicates():
    tags = extract_tags({"review": "graphics graphics graphics"})
    assert tags.count("graphics") == 1


def test_extract_tags_empty_text():
    assert extract_tags({"review": ""}) == []


# ----- aggregate_top_themes -----------------------------------------------


def test_aggregate_top_themes_filters_by_sentiment():
    reviews = [
        {"review": "great graphics", "voted_up": True},
        {"review": "amazing gameplay", "voted_up": True},
        {"review": "stupid crashes", "voted_up": False},
    ]
    pos = aggregate_top_themes(reviews, top_n=5, mode="positive")
    neg = aggregate_top_themes(reviews, top_n=5, mode="negative")
    pos_themes = {t["theme"] for t in pos}
    neg_themes = {t["theme"] for t in neg}
    assert pos_themes.isdisjoint(neg_themes)


def test_aggregate_top_themes_returns_top_n():
    reviews = [
        {"review": f"phrase{i}", "voted_up": False}
        for i in range(10)
    ]
    out = aggregate_top_themes(reviews, top_n=3, mode="negative")
    assert len(out) <= 3


def test_aggregate_top_themes_provides_sample_quote():
    reviews = [
        {"review": "stupid crash after launch", "voted_up": False,
         "author": {"steamid": "12345"}, "recommendationid": "r1"},
    ]
    out = aggregate_top_themes(reviews, top_n=1, mode="negative")
    assert out and out[0]["sample_quote"]
    assert out[0]["sample_author"] == "12345"


# ----- compute_deltas ------------------------------------------------------


def test_compute_deltas_finds_new_only():
    old = [{"recommendationid": "a", "voted_up": True}]
    new = [
        {"recommendationid": "a", "voted_up": True},
        {"recommendationid": "b", "voted_up": False},
        {"recommendationid": "c", "voted_up": True},
    ]
    d = compute_deltas(old, new)
    assert d["count"] == 2
    assert d["positive"] == 1
    assert d["negative"] == 1
    rids = {r["recommendationid"] for r in d["reviews"]}
    assert rids == {"b", "c"}


def test_compute_deltas_empty_old_returns_all_new():
    d = compute_deltas(
        [],
        [{"recommendationid": "x", "voted_up": False}],
    )
    assert d["count"] == 1


# ----- split_first_24h -----------------------------------------------------


def test_split_first_24h_splits_around_earliest():
    base = 1_700_000_000
    reviews = [
        {"timestamp_created": base + 0},       # first
        {"timestamp_created": base + 3600},    # +1h, in first 24h
        {"timestamp_created": base + 25 * 3600},  # +25h, after
    ]
    out = split_first_24h(reviews)
    assert len(out["first_24h"]) == 2
    assert len(out["after"]) == 1


def test_split_first_24h_empty():
    assert split_first_24h([]) == {"first_24h": [], "after": []}


# ----- compute_playtime_histogram -----------------------------------------


def test_compute_playtime_histogram_empty():
    assert compute_playtime_histogram([]) == {}


def test_compute_playtime_histogram_buckets_split():
    reviews = [
        {"author": {"playtime_forever": 60}, "voted_up": True},
        {"author": {"playtime_forever": 60 * 10}, "voted_up": True},
        {"author": {"playtime_forever": 60 * 100}, "voted_up": False},
    ]
    hist = compute_playtime_histogram(reviews, buckets=3)
    assert hist
    total_pos = sum(b["pos"] for b in hist.values())
    total_neg = sum(b["neg"] for b in hist.values())
    assert total_pos == 2
    assert total_neg == 1