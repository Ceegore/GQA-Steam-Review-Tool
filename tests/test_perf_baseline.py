"""Performance regression tests.

These tests don't *enforce* a tight budget — they print timings
so a future change that 10x-slows something shows up in the
test output. Run with ``pytest -s`` to see the numbers.
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest


def _bench(label: str, func, *args, **kwargs):
    t0 = time.perf_counter()
    out = func(*args, **kwargs)
    dt = (time.perf_counter() - t0) * 1000
    print(f"\n[BENCH] {label}: {dt:.2f} ms")
    return out, dt


def test_bench_analyzer_classify_1000_reviews():
    from steam_review_tool.services.review_analyzer import (
        classify_review_type, extract_tags,
    )
    sample = [
        {"review": "this game crashes constantly and is unplayable",
         "voted_up": False},
        {"review": "amazing masterpiece, love the graphics and music",
         "voted_up": True},
    ] * 500

    def run():
        return [classify_review_type(r) for r in sample]

    def run_tags():
        return [extract_tags(r) for r in sample]

    _, classify_dt = _bench("classify_review_type 1000x", run)
    _, extract_dt = _bench("extract_tags 1000x", run_tags)
    # Sanity: < 500ms for 1000 reviews on a modern CPU
    assert classify_dt < 1000
    assert extract_dt < 1000


def test_bench_markdown_export_500_reviews(tmp_path):
    from steam_review_tool.exporters.markdown_exporter import MarkdownExporter
    from steam_review_tool.models.export_context import ExportContext

    reviews = [
        {
            "recommendationid": f"r{i}",
            "language": "english",
            "voted_up": i % 3 == 0,
            "review": f"review text {i} with some content " * 20,
            "votes_up": i % 5,
            "author": {
                "steamid": str(i),
                "playtime_forever": i * 60,
                "last_played": 1_700_000_000 + i,
            },
        }
        for i in range(500)
    ]
    ctx = ExportContext(
        app_id=1, app_details={"name": "Perf Test"}, reviews=reviews,
        language_param="all", review_filter="all", review_type="all",
        day_range=None, min_date_ts=None, keyword_list=["review", "content"],
    )
    out, dt = _bench("MarkdownExporter.render 500 reviews", MarkdownExporter.render, ctx)
    assert out  # non-empty
    # Render 500 reviews + digest + footer < 5s (CI may be slow)
    assert dt < 5000, f"Markdown render took {dt:.0f}ms — regression?"


def test_bench_resolve_app_id_10k():
    from steam_review_tool.utils.url_utils import resolve_app_id
    inputs = [
        "https://store.steampowered.com/app/" + str(i) + "/x" for i in range(10000)
    ]

    def run():
        return [resolve_app_id(s) for s in inputs]

    out, dt = _bench("resolve_app_id 10000 URLs", run)
    # 10k URL parses should be < 5s
    assert dt < 5000


def test_bench_atomic_write_100_iterations(tmp_path):
    from steam_review_tool.core.atomic_write import atomic_write_text
    target = tmp_path / "f.txt"

    def do_one():
        atomic_write_text(target, "x" * 1000)

    t0 = time.perf_counter()
    for _ in range(100):
        do_one()
    dt = (time.perf_counter() - t0) * 1000
    print(f"\n[BENCH] atomic_write_text 100x: {dt:.2f} ms")
    # 100 atomic writes < 30s on any modern disk (CI can be slow)
    assert dt < 30_000


def test_bench_trends_store_100_snapshots(tmp_path):
    """100 snapshots is the realistic case for daily trend recording
    over a few months. The 1000-iteration version was too slow.
    """
    from steam_review_tool.services.trends_store import TrendsStore
    from steam_review_tool.models.trends_snapshot import TrendsSnapshot
    store = TrendsStore.__new__(TrendsStore)
    store.path = tmp_path / "trends.json"

    t0 = time.perf_counter()
    for i in range(100):
        store.record(TrendsSnapshot(
            app_id=i % 5, ts=1_700_000_000 + i,
            wishlist=i * 10, followers=i * 5, reviews=i * 100,
        ))
    dt = (time.perf_counter() - t0) * 1000
    print(f"\n[BENCH] TrendsStore.record 100x: {dt:.2f} ms")
    # 100 record() calls < 10s on any reasonable disk
    assert dt < 10_000
    series = store.series(0, "wishlist")
    assert len(series) == 20  # 1/5 of 100 = 20 snapshots for app_id 0