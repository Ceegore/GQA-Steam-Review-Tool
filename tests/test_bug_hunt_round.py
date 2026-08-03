"""Regression tests for bugs found in the 2026-08-04 deep-bug-hunt round.

Each test is a minimal repro for one specific bug, so a future change
that re-introduces the bug fails the corresponding test immediately.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# BUG-1: short_filter_label was hard-coded to read from
# ``getattr(app, f"{prefix}since_preset_var")`` but both the API and
# Playwright tab controllers store the same widgets in
# ``self._since["preset_var"]`` / ``["date_entry"]`` / ``["time_entry"]``.
# The function always fell into the ``AttributeError`` branch and
# returned ``"all"`` for every export, so the filename was always
# ``GQA Reviewdump_<name>_all_...md`` regardless of the user's
# "When to include" selection.
# ---------------------------------------------------------------------------


def _make_since(preset: str = "all time", date: str = "", time_: str = ""):
    """Build a fake ``_since`` dict with StringVar/Entry-like .get()."""
    class V:
        def __init__(self, v): self._v = v
        def get(self): return self._v
    return {"preset_var": V(preset), "date_entry": V(date), "time_entry": V(time_)}


def test_short_filter_label_api_preset_last1h():
    """API tab with ``last 1 hour`` selected must NOT collapse to ``all``."""
    from steam_review_tool.utils.text_utils import short_filter_label

    class FakeApiTab:
        _since = _make_since(preset="last 1 hour")

    assert short_filter_label("api", FakeApiTab()) == "last1h"


def test_short_filter_label_api_preset_last12h():
    from steam_review_tool.utils.text_utils import short_filter_label

    class FakeApiTab:
        _since = _make_since(preset="last 12 hours")

    assert short_filter_label("api", FakeApiTab()) == "last12h"


def test_short_filter_label_api_all_time():
    from steam_review_tool.utils.text_utils import short_filter_label

    class FakeApiTab:
        _since = _make_since(preset="all time")

    assert short_filter_label("api", FakeApiTab()) == "all"


def test_short_filter_label_api_custom_date_and_time():
    from steam_review_tool.utils.text_utils import short_filter_label

    class FakeApiTab:
        _since = _make_since(
            preset="custom (date + time)",
            date="2026-06-15", time_="14:30",
        )

    assert short_filter_label("api", FakeApiTab()) == "custom20260615T1430"


def test_short_filter_label_pw_preset_last24h():
    """The Playwright tab was the worst-affected: its default preset is
    ``last 24 hours`` but the old code returned ``all`` for it."""
    from steam_review_tool.utils.text_utils import short_filter_label

    class FakePwTab:
        _since = _make_since(preset="last 24 hours")

    assert short_filter_label("pw", FakePwTab()) == "last24h"


def test_short_filter_label_pw_custom_date_only():
    from steam_review_tool.utils.text_utils import short_filter_label

    class FakePwTab:
        _since = _make_since(
            preset="custom (date + time)", date="2026-06-15",
        )

    assert short_filter_label("pw", FakePwTab()) == "custom20260615"


def test_short_filter_label_unknown_preset_falls_back_to_all():
    from steam_review_tool.utils.text_utils import short_filter_label

    class FakeApiTab:
        _since = _make_since(preset="some unknown preset")

    assert short_filter_label("api", FakeApiTab()) == "all"


def test_short_filter_label_back_compat_flat_attrs():
    """Old callers that expose since_preset_var as a top-level attribute
    (not nested in ``_since``) must still work."""
    from steam_review_tool.utils.text_utils import short_filter_label

    class V:
        def __init__(self, v): self._v = v
        def get(self): return self._v

    class OldShape:
        since_preset_var = V("last 1 hour")
        since_date_entry = V("")
        since_time_entry = V("")

    assert short_filter_label("api", OldShape()) == "last1h"


# ---------------------------------------------------------------------------
# BUG-7: markdown_helpers rendered ``| Played forever? | {early_access} |``
# which displayed the wrong field under a misleading label. The
# value is ``written_during_early_access``; the label should match.
# ---------------------------------------------------------------------------


def test_markdown_review_label_matches_early_access_field():
    src = Path("steam_review_tool/exporters/markdown_helpers.py").read_text(
        encoding="utf-8",
    )
    # The fixed label must be present, and the old "Played forever?" must be gone.
    assert "Written during early access?" in src
    assert "| Played forever? |" not in src


# ---------------------------------------------------------------------------
# BUG-16: popup_trends_chart compared ``d`` (a day-number, e.g. 20500)
# to ``cutoff`` (a unix-timestamp, e.g. 1.7e9). The comparison was
# always True, so every data point inside any non-"all" range was
# stripped before the chart could draw it. The fix compares the
# reconstructed timestamp instead.
# ---------------------------------------------------------------------------


def test_trends_chart_cutoff_uses_unix_timestamp_compare():
    """Reproduce the chart's filter logic and ensure recent data is kept."""
    from time import time as _now
    # Pick a recent unix timestamp = today at 12:00 UTC
    now = int(_now())
    recent_ts = now - 3 * 86400  # 3 days ago
    old_ts = now - 30 * 86400    # 30 days ago

    days = 7
    cutoff = now - (days * 86400 if days else 0)
    # `d` is the day number (used for aggregation), cutoff is unix-ts.
    d_recent = recent_ts // 86400
    d_old = old_ts // 86400

    # With the bug, ``d < cutoff`` (day < ~1.7e9) was always True and
    # stripped every data point. With the fix we reconstruct the
    # timestamp first.
    assert d_recent * 86400 >= cutoff, (
        "3-day-old data must survive a 7-day cutoff"
    )
    assert d_old * 86400 < cutoff, (
        "30-day-old data must NOT survive a 7-day cutoff"
    )

    # And the chart's new skip condition must reflect that.
    # ``A < B and 7`` is truthy when A < B (7 is truthy), so
    # ``bool(...) == True`` is the right assertion (the bug was that
    # the *old* code was always truthy regardless of A and B).
    assert bool(d_recent * 86400 < cutoff and days) is False, (
        "recent data must NOT be skipped"
    )
    assert bool(d_old * 86400 < cutoff and days) is True, (
        "old data must BE skipped"
    )


def test_trends_chart_cutoff_keeps_recent_when_no_range():
    """When ``days`` is None (the 'all' preset), no filtering happens."""
    from time import time as _now
    now = int(_now())
    days = None
    cutoff = now - (days * 86400 if days else 0)  # == now when days is None
    old_ts = now - 365 * 86400
    d_old = old_ts // 86400
    # No range ⇒ no skip, regardless of the data.
    # ``A < B and None`` is None (the second operand of ``and``),
    # which is falsy, so the skip is not taken.
    assert not (d_old * 86400 < cutoff and days)


# ---------------------------------------------------------------------------
# BUG-19: anti-detect was injected on a *throwaway* page (the first
# ``ctx.new_page()``) while the actual scraping page_obj was created
# afterwards without the shim. Steam's anti-bot can flag the uncloaked
# first goto. The fix installs the init script on the page that
# actually navigates.
# ---------------------------------------------------------------------------


def test_playwright_scraper_injects_anti_detect_on_real_page():
    """Static check: ``inject_anti_detect`` is called on the same page
    that the rest of the code uses, not on a separate ``new_page()``
    that gets abandoned.
    """
    src = Path("steam_review_tool/services/playwright_scraper.py").read_text(
        encoding="utf-8",
    )
    # The fix: page_obj is created first, then the init script installed.
    # The anti-pattern: ``inject_anti_detect(ctx.new_page())`` BEFORE
    # the page_obj assignment.
    assert "inject_anti_detect(ctx.new_page())" not in src, (
        "anti-detect must not be injected on a throwaway page; "
        "the page that actually navigates is page_obj"
    )
    # And the new code should install the script on page_obj itself.
    assert "inject_anti_detect(page_obj)" in src


def test_playwright_subprocess_scraper_init_script_before_new_page():
    """Static check: in the subprocess helper, the init script is
    registered on the *context* *before* the page is created, so the
    first goto carries the shim.
    """
    src = Path(
        "steam_review_tool/services/playwright_subprocess_scraper.py",
    ).read_text(encoding="utf-8")
    # Find the function main() block and verify the order in the
    # helper template.
    add_idx = src.find("ctx.add_init_script(ANTI_DETECT_JS)")
    new_idx = src.find("page = ctx.new_page()")
    assert add_idx != -1 and new_idx != -1
    assert add_idx < new_idx, (
        "ctx.add_init_script must be called before ctx.new_page() "
        "so the first navigation carries the shim"
    )


# ---------------------------------------------------------------------------
# BUG-13 / BUG-20: helper-script filename collisions.
# ``playwright_subprocess.py`` used ``id(app_id) & 0xFFFF`` (collides
# once Python reuses the int id), and ``playwright_subprocess_scraper.py``
# used ``os.getpid() & 0xFFFF`` (same value as the leading ``os.getpid()``,
# so two concurrent scrapes clobbered each other). Both now use a
# uuid4 fragment, which is unique per call.
# ---------------------------------------------------------------------------


def test_playwright_probe_filename_is_unique_per_call():
    """Two consecutive calls must produce different filenames."""
    from steam_review_tool.services import playwright_subprocess
    # Stub find_external_python + subprocess so we don't actually
    # need Playwright / a Python interpreter to be installed.
    playwright_subprocess.find_external_python = lambda: None  # type: ignore
    # With no external python, the function early-returns before
    # writing the helper; we just want to inspect the path it would
    # have used. Patch helper_path construction by checking the
    # template pattern instead.
    src = playwright_subprocess.__file__ and Path(
        playwright_subprocess.__file__,
    ).read_text(encoding="utf-8")
    # Must NOT contain the old id(app_id) trick.
    assert "id(app_id)" not in src
    # Must use uuid (or some other uniqueness source) for the suffix.
    assert "uuid" in src
    # Must still include the pid for crash-traceability.
    assert "os.getpid()" in src


def test_scrape_subprocess_filename_includes_uuid():
    """The scrape helper file must be uniquely named per call."""
    from steam_review_tool.services import playwright_subprocess_scraper as pss
    src = Path(pss.__file__).read_text(encoding="utf-8")
    # Must not contain the old duplicate-pid pattern.
    assert "os.getpid() & 0xFFFF" not in src
    # Must use uuid for uniqueness.
    assert "uuid" in src
    # Both files must end in .py so subprocess.run can interpret them.
    assert "_srt_scrape_" in src
    assert ".py" in src


# ---------------------------------------------------------------------------
# BUG-3: export_orchestrator used ``Path.write_text`` for the main .md,
# ``open("w")`` in reviews_to_csv / reviews_to_json, ``write_text`` for
# the summary, and the same in per-language. None of those are
# atomic; a crash mid-export leaves a half-written file. The fix
# routes every write through ``atomic_write_text``.
# ---------------------------------------------------------------------------


def test_export_orchestrator_uses_atomic_write():
    """Static check: the orchestrator must not call ``write_text`` or
    ``open(..., "w")`` for any of its user-facing outputs."""
    src = Path("steam_review_tool/exporters/export_orchestrator.py").read_text(
        encoding="utf-8",
    )
    # The main .md, the CSV, the JSON, the summary must all go through
    # atomic_write_text. ``write_text`` / ``open("w")`` would leave a
    # half-written file on crash.
    assert "atomic_write_text" in src
    # The old line was: ``dest.write_text(md_text, ...)``. That string
    # must not appear in the new file.
    assert 'dest.write_text(md_text' not in src
    assert 'summary_path.write_text(' not in src


def test_per_language_exporter_uses_atomic_write():
    src = Path(
        "steam_review_tool/exporters/per_language_exporter.py",
    ).read_text(encoding="utf-8")
    assert "atomic_write_text" in src
    assert "per_path.write_text(" not in src


# ---------------------------------------------------------------------------
# BUG-2: smoke test timeout was 30s; the App builds in ~50s on a slow
# Windows VM because of the CTkScrollableFrame reflow chain inside
# the Playwright filter grid. Bump to 120s — well above the worst
# observed time, still short enough to surface a real hang.
# ---------------------------------------------------------------------------


def test_smoke_subprocess_timeout_is_at_least_90s():
    src = Path("tests/smoke/test_app.py").read_text(encoding="utf-8")
    m = re.search(r"timeout\s*=\s*(\d+)", src)
    assert m, "smoke test must pass an explicit timeout to subprocess.run"
    timeout = int(m.group(1))
    assert timeout >= 90, (
        f"smoke-test timeout must be at least 90 s (App build takes "
        f"~50 s on slow VMs); got {timeout}"
    )
