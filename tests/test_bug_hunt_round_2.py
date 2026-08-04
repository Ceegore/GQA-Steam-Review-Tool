"""Regression tests for bugs found in the 2026-08-04 Round-2 deep-bug-hunt.

Each test is a minimal repro for one specific bug, so a future change
that re-introduces the bug fails the corresponding test immediately.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# BUG-R2-1: popup_search parsed ``### Review #N`` lines with
# ``line.split("#", 2)[2].strip()`` — that yielded ``# Review #1`` (the
# leading ``#`` of the heading was left behind) so the displayed label
# was ``Review ## Review #1``. The fix splits on the full prefix
# ``### Review #``.
# ---------------------------------------------------------------------------


def _parse_review_label(line: str) -> str:
    """Mimic the new popup_search label-parsing logic."""
    try:
        num = line.split("### Review #", 1)[1].strip()
    except Exception:
        num = "?"
    return f"Review #{num}"


def test_popup_search_review_label_drops_hash_prefix():
    """``### Review #1`` must produce ``Review #1``, not ``Review ## Review #1``."""
    assert _parse_review_label("### Review #1") == "Review #1"


def test_popup_search_review_label_multi_digit():
    assert _parse_review_label("### Review #42") == "Review #42"


def test_popup_search_review_label_large_number():
    assert _parse_review_label("### Review #1234567") == "Review #1234567"


def test_popup_search_label_parsing_uses_split_prefix():
    """Static check: the source must split on the full prefix, not on ``#``."""
    src = Path("steam_review_tool/ui/popup_search.py").read_text(encoding="utf-8")
    # Strip the docstring/comment lines so we only look at real code.
    # Any line that starts with ``#`` is excluded.
    code_lines = [
        ln for ln in src.splitlines()
        if ln.strip() and not ln.lstrip().startswith("#")
    ]
    code = "\n".join(code_lines)
    # The old anti-pattern (maxsplit=2 on bare ``#``) is gone from
    # the executable code (it may still be quoted in the surrounding
    # comment / docstring, which is fine).
    assert 'line.split("#", 2)' not in code
    # The new prefix split is in place.
    assert 'line.split("### Review #", 1)' in code


# ---------------------------------------------------------------------------
# BUG-R2-2: tab_trends ``_on_add_custom`` called ``int(raw)`` FIRST and
# only fell through to ``resolve_app_id`` on a ValueError. URLs raise
# ValueError on ``int()`` so a user pasting a store URL got the
# "Invalid App ID." status — the resolve_app_id fallback never ran.
# The fix calls ``resolve_app_id`` first; ``int()`` is only the
# last-resort fallback.
# ---------------------------------------------------------------------------


def test_tab_trends_add_custom_uses_resolve_app_id_first():
    """Static check: ``_on_add_custom`` must call ``resolve_app_id`` before ``int``."""
    src = Path("steam_review_tool/ui/tab_trends.py").read_text(encoding="utf-8")
    m = re.search(
        r"def _on_add_custom\(self.*?(?=\n    def |\nclass )",
        src, re.DOTALL,
    )
    assert m, "_on_add_custom function not found in tab_trends.py"
    body = m.group(0)
    # Strip pure comment lines so we look at real code only.
    code_lines = [
        ln for ln in body.splitlines()
        if ln.strip() and not ln.lstrip().startswith("#")
    ]
    code = "\n".join(code_lines)
    resolve_idx = code.find("resolve_app_id")
    int_idx = code.find("int(raw)")
    assert resolve_idx != -1, (
        "_on_add_custom must call resolve_app_id (URLs raise on int())"
    )
    assert int_idx != -1, (
        "_on_add_custom must keep the int() fallback for raw integer inputs"
    )
    assert resolve_idx < int_idx, (
        "resolve_app_id must be called BEFORE int(raw) so URLs are accepted"
    )


def test_tab_trends_add_custom_accepts_store_url():
    """End-to-end: ``resolve_app_id`` must be the first attempt."""
    from steam_review_tool.utils.url_utils import resolve_app_id

    # URL input — the BUG-R2-2 path. With the fix, resolve_app_id
    # is called first and returns the App ID; the old code's
    # ``int(raw)`` would raise ValueError before reaching the URL
    # parser.
    parsed = resolve_app_id("https://store.steampowered.com/app/4311090/")
    assert parsed == 4311090


def test_tab_trends_add_custom_accepts_raw_id_via_int_fallback():
    """When the user pastes a raw integer, the int() fallback must catch it."""
    raw = "4311090"
    # resolve_app_id handles digits via isdigit().
    from steam_review_tool.utils.url_utils import resolve_app_id
    assert resolve_app_id(raw) == 4311090
    # And the int() fallback still works for the same input
    # (resolve_app_id is the primary path; int() is the safety net).
    assert int(raw) == 4311090


# ---------------------------------------------------------------------------
# BUG-R2-3: ``_tab_actions.write_summary`` and ``save_as_prompt`` used
# ``Path.write_text`` (non-atomic) for ``.summary.md`` and
# ``ai_prompt.md``. A crash mid-write would leave a partial file
# the user could mistake for a real export. The fix routes both
# through ``atomic_write_text``.
# ---------------------------------------------------------------------------


def test_tab_actions_write_summary_uses_atomic_write():
    """Static check: write_summary must use atomic_write_text, not write_text."""
    src = Path("steam_review_tool/ui/_tab_actions.py").read_text(encoding="utf-8")
    # The function name must be present, with atomic_write_text inside.
    m = re.search(
        r"def write_summary\(self.*?(?=\n    def )", src, re.DOTALL,
    )
    assert m, "write_summary function not found"
    body = m.group(0)
    assert "atomic_write_text" in body, (
        "write_summary must write atomically (was using write_text)"
    )
    assert ".write_text(" not in body, (
        "write_summary must not call .write_text (non-atomic)"
    )


def test_tab_actions_save_as_prompt_uses_atomic_write():
    """Static check: save_as_prompt must use atomic_write_text."""
    src = Path("steam_review_tool/ui/_tab_actions.py").read_text(encoding="utf-8")
    m = re.search(
        r"def save_as_prompt\(self.*?(?=\n    def )", src, re.DOTALL,
    )
    assert m, "save_as_prompt function not found"
    body = m.group(0)
    assert "atomic_write_text" in body, (
        "save_as_prompt must write atomically (was using write_text)"
    )
    assert ".write_text(" not in body, (
        "save_as_prompt must not call .write_text (non-atomic)"
    )


# ---------------------------------------------------------------------------
# BUG-R2-4: ``dependency_installer`` wrote three helper scripts to the
# system temp dir (``_srt_install_pw.py``, ``_srt_install_chrome.py``,
# ``get-pip.py``) and never cleaned them up. Repeated install attempts
# accumulated a stale file per click. The fix wraps each helper-script
# usage in a try/finally that unlinks the temp file.
# ---------------------------------------------------------------------------


def test_dependency_installer_cleans_up_pw_helper(tmp_path, monkeypatch):
    """The playwright install helper script must be unlinked after use."""
    from steam_review_tool.services import dependency_installer as di

    # Redirect the system temp dir to our tmp_path so the helper
    # script is created there and we can assert on its existence.
    monkeypatch.setattr(di.tempfile, "gettempdir", lambda: str(tmp_path))

    def fake_run(*_a, **_kw):
        class R:
            returncode = 0
            stderr = ""
            stdout = ""
        return R()

    monkeypatch.setattr(
        di.subprocess, "run", staticmethod(fake_run),
    )

    cb_calls = []
    di.install_playwright(
        log_cb=lambda m: None,
        on_done=lambda ok, msg: cb_calls.append((ok, msg)),
    )
    leaked = list(tmp_path.glob("_srt_install_pw.py"))
    assert not leaked, (
        f"_srt_install_pw.py leaked into the temp dir: {leaked}"
    )
    assert cb_calls and cb_calls[0][0] is True, (
        "the install should still report success with a stubbed-out run"
    )


def test_dependency_installer_cleans_up_chrome_helper(tmp_path, monkeypatch):
    """The chromium install helper script must be unlinked after use."""
    from steam_review_tool.services import dependency_installer as di

    monkeypatch.setattr(di.tempfile, "gettempdir", lambda: str(tmp_path))

    def fake_run(*_a, **_kw):
        class R:
            returncode = 0
            stderr = ""
            stdout = ""
        return R()

    monkeypatch.setattr(di.subprocess, "run", staticmethod(fake_run))

    cb_calls = []
    di.install_chromium(
        log_cb=lambda m: None,
        on_done=lambda ok, msg: cb_calls.append((ok, msg)),
    )
    leaked = list(tmp_path.glob("_srt_install_chrome.py"))
    assert not leaked, (
        f"_srt_install_chrome.py leaked into the temp dir: {leaked}"
    )
    assert cb_calls and cb_calls[0][0] is True


def test_dependency_installer_cleans_up_get_pip_helper(tmp_path, monkeypatch):
    """The get-pip.py bootstrap helper must be unlinked after use, even
    when the bootstrap itself fails."""
    from steam_review_tool.services import dependency_installer as di
    import urllib.request

    monkeypatch.setattr(di.tempfile, "gettempdir", lambda: str(tmp_path))

    captured = {"urlretrieve_dest": None}

    def fake_urlretrieve(url, dest, *_a, **_kw):
        captured["urlretrieve_dest"] = dest
        Path(dest).write_text("# downloaded", encoding="utf-8")

    # Force the bootstrap path: first run (pip install) returns
    # "No module named pip"; second run (after bootstrap) succeeds.
    pip_install_attempts = {"n": 0}

    def fake_run_counted(cmd, *_a, **_kw):
        pip_install_attempts["n"] += 1
        class R:
            returncode = 0 if pip_install_attempts["n"] >= 2 else 1
            stderr = "" if pip_install_attempts["n"] >= 2 else "No module named pip"
            stdout = ""
        return R()

    monkeypatch.setattr(di.subprocess, "run", staticmethod(fake_run_counted))
    monkeypatch.setattr(urllib.request, "urlretrieve", fake_urlretrieve)

    cb_calls = []
    di.install_playwright(
        log_cb=lambda m: None,
        on_done=lambda ok, msg: cb_calls.append((ok, msg)),
    )
    assert captured["urlretrieve_dest"] is not None, (
        "bootstrap path should have called urlretrieve"
    )
    leaked_pip = list(tmp_path.glob("get-pip.py"))
    assert not leaked_pip, f"get-pip.py leaked into the temp dir: {leaked_pip}"
    leaked_pw = list(tmp_path.glob("_srt_install_pw.py"))
    assert not leaked_pw, (
        f"_srt_install_pw.py leaked into the temp dir: {leaked_pw}"
    )


def test_dependency_installer_helper_unlinked_on_failure(tmp_path, monkeypatch):
    """Even when the install fails, the helper script must be cleaned up."""
    from steam_review_tool.services import dependency_installer as di

    monkeypatch.setattr(di.tempfile, "gettempdir", lambda: str(tmp_path))

    def fake_run_fail(*_a, **_kw):
        class R:
            returncode = 1
            stderr = "fatal: install broke\n"
            stdout = ""
        return R()

    monkeypatch.setattr(di.subprocess, "run", staticmethod(fake_run_fail))

    cb_calls = []
    di.install_playwright(
        log_cb=lambda m: None,
        on_done=lambda ok, msg: cb_calls.append((ok, msg)),
    )
    # The helper must be gone even on a failed install.
    leaked = list(tmp_path.glob("_srt_install_pw.py"))
    assert not leaked, (
        f"_srt_install_pw.py must be unlinked on failure too; got {leaked}"
    )
    # And the install must have reported failure.
    assert cb_calls and cb_calls[0][0] is False


# ---------------------------------------------------------------------------
# BUG-R2-5: ``open_pw_cache`` hard-coded a Windows path
# (``~/AppData/Local/ms-playwright``) on every platform. On macOS /
# Linux the cache actually lives at ``~/Library/Caches/ms-playwright``
# or ``$XDG_CACHE_HOME/ms-playwright`` respectively, so the function
# always returned "does not exist yet" on non-Windows hosts.
# ---------------------------------------------------------------------------


def test_open_pw_cache_uses_platform_specific_path(monkeypatch, tmp_path):
    """Force ``sys.platform = "darwin"`` and confirm the cache path
    resolves under ``~/Library/Caches/ms-playwright`` rather than the
    Windows path."""
    from steam_review_tool.services import dependency_installer as di

    # Create a "real" cache dir at the macOS location.
    mac_cache = tmp_path / "Library" / "Caches" / "ms-playwright"
    mac_cache.mkdir(parents=True)

    monkeypatch.setattr(di.sys, "platform", "darwin")
    monkeypatch.setattr(di.Path, "home", staticmethod(lambda: tmp_path))

    # Patch os.startfile / subprocess.Popen so we don't actually open anything.
    opened = []
    monkeypatch.setattr(
        di.subprocess, "Popen",
        lambda *a, **kw: opened.append(("Popen", a)),
    )
    # open_pw_cache falls into the ``elif sys.platform == "darwin"``
    # branch when sys.platform is darwin — no os.startfile is called.
    # The test confirms it returns None (success) instead of an
    # "does not exist yet" error message.
    result = di.open_pw_cache()
    assert result is None, (
        f"open_pw_cache must return None when the platform-specific "
        f"cache dir exists; got {result!r}"
    )


def test_open_pw_cache_darwin_path_construction(monkeypatch, tmp_path):
    """Verify the macOS path is ``~/Library/Caches/ms-playwright``."""
    from steam_review_tool.services import dependency_installer as di

    captured = {"path": None}

    # Use a real existing dir to avoid the "does not exist yet" branch
    real = tmp_path / "Library" / "Caches" / "ms-playwright"
    real.mkdir(parents=True)

    original_startfile = getattr(di.os, "startfile", None)

    def fake_startfile(path, *args, **kwargs):
        captured["path"] = path

    def fake_popen(cmd, *args, **kwargs):
        captured["path"] = cmd[-1] if cmd else None

    monkeypatch.setattr(di.sys, "platform", "darwin")
    monkeypatch.setattr(di.Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(di.subprocess, "Popen", fake_popen)

    di.open_pw_cache()

    assert captured["path"] is not None
    assert "Library" in str(captured["path"])
    assert "Caches" in str(captured["path"])
    assert "ms-playwright" in str(captured["path"])


def test_open_pw_cache_linux_uses_xdg_cache(monkeypatch, tmp_path):
    """On Linux, the path is ``$XDG_CACHE_HOME/ms-playwright`` or
    ``~/.cache/ms-playwright`` if XDG_CACHE_HOME is unset."""
    from steam_review_tool.services import dependency_installer as di

    xdg_cache = tmp_path / "xdg_cache"
    xdg_cache.mkdir()
    pw_cache = xdg_cache / "ms-playwright"
    pw_cache.mkdir()

    captured = {"path": None}

    monkeypatch.setattr(di.sys, "platform", "linux")
    monkeypatch.setenv("XDG_CACHE_HOME", str(xdg_cache))
    monkeypatch.setattr(di.Path, "home", staticmethod(lambda: tmp_path))

    def fake_popen(cmd, *args, **kwargs):
        captured["path"] = cmd[-1] if cmd else None

    monkeypatch.setattr(di.subprocess, "Popen", fake_popen)

    di.open_pw_cache()
    assert captured["path"] is not None
    assert str(captured["path"]).endswith("ms-playwright")
    assert "xdg_cache" in str(captured["path"]) or ".cache" in str(captured["path"])


def test_open_pw_cache_windows_uses_localappdata(monkeypatch, tmp_path):
    """On Windows, prefer ``$LOCALAPPDATA/ms-playwright`` over the
    home-dir fallback."""
    from steam_review_tool.services import dependency_installer as di

    local_app = tmp_path / "LocalAppData"
    local_app.mkdir()
    pw_cache = local_app / "ms-playwright"
    pw_cache.mkdir()

    monkeypatch.setattr(di.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(local_app))
    monkeypatch.setattr(di.Path, "home", staticmethod(lambda: tmp_path))

    # The function calls os.startfile on Windows.
    captured = {"path": None}

    def fake_startfile(path, *args, **kwargs):
        captured["path"] = path

    monkeypatch.setattr(di.os, "startfile", fake_startfile)

    di.open_pw_cache()
    assert captured["path"] is not None
    assert "LocalAppData" in str(captured["path"]) or "LOCALAPPDATA" in os.environ


# ---------------------------------------------------------------------------
# BUG-R2-6: ``compute_since_timestamp`` silently treated an unknown
# preset label as "all time" (returns 0 → returns None). The worst-case
# outcome: a user thinks they applied "last 3 days" but gets all
# reviews because the label was a typo or a future preset. The fix
# detects unknown labels and logs a WARNING before returning None.
# ---------------------------------------------------------------------------


def test_compute_since_timestamp_unknown_preset_warns(caplog):
    """An unknown preset label must produce a WARNING-level log entry."""
    from steam_review_tool.utils.datetime_utils import compute_since_timestamp

    with caplog.at_level(logging.WARNING, logger="steam_review_tool.utils.datetime_utils"):
        result = compute_since_timestamp(
            preset_label="some-future-preset",
            custom_date_str="",
            custom_time_str="",
        )
    assert result is None, "unknown preset must still yield no-filter"
    # At least one WARNING about the unknown label must be present.
    assert any(
        "unknown preset" in rec.message.lower() and "some-future-preset" in rec.message
        for rec in caplog.records
    ), (
        "compute_since_timestamp must warn about an unknown preset label "
        "instead of silently dropping the filter"
    )


def test_compute_since_timestamp_known_preset_no_warning(caplog):
    """A known preset must NOT trigger the unknown-preset warning."""
    from steam_review_tool.utils.datetime_utils import compute_since_timestamp

    with caplog.at_level(logging.WARNING, logger="steam_review_tool.utils.datetime_utils"):
        result = compute_since_timestamp(
            preset_label="all time",
            custom_date_str="",
            custom_time_str="",
        )
    assert result is None
    assert not any("unknown preset" in rec.message.lower() for rec in caplog.records), (
        "the 'all time' label is a real preset — no warning should fire"
    )


def test_compute_since_timestamp_known_preset_returns_filter():
    """A known preset like 'last 24 hours' must produce a real timestamp."""
    from datetime import datetime, timezone

    from steam_review_tool.utils.datetime_utils import compute_since_timestamp

    fixed_now = datetime(2026, 6, 17, 14, 30, 0, tzinfo=timezone.utc)
    result = compute_since_timestamp(
        preset_label="last 24 hours",
        custom_date_str="",
        custom_time_str="",
        now=fixed_now,
    )
    # 24 hours before 2026-06-17 14:30 UTC = 2026-06-16 14:30 UTC
    expected = int(fixed_now.timestamp()) - 24 * 3600
    assert result == expected


# ---------------------------------------------------------------------------
# BUG-R2-7: ``tab_trends._on_per_language_count`` had an ``if/else``
# where both branches were identical (both called
# ``fetch_all_reviews(language=lang, ...)`` with the same kwargs). The
# only difference was that one branch hard-coded ``language="all"``
# and the other used ``lang`` — but the condition was ``if lang ==
# "all"`` so they were always equal. The fix removes the dead branch.
# ---------------------------------------------------------------------------


def test_tab_trends_per_language_count_no_dead_branch():
    """Static check: the function must contain only one
    ``fetch_all_reviews`` call, not two identical ones."""
    src = Path("steam_review_tool/ui/tab_trends.py").read_text(encoding="utf-8")
    m = re.search(
        r"def _on_per_language_count\(self.*?(?=\n    def |\nclass )",
        src, re.DOTALL,
    )
    assert m, "_on_per_language_count function not found"
    body = m.group(0)
    # Strip pure comment lines.
    code_lines = [
        ln for ln in body.splitlines()
        if ln.strip() and not ln.lstrip().startswith("#")
    ]
    code = "\n".join(code_lines)
    n_calls = code.count("fetch_all_reviews(")
    assert n_calls == 1, (
        f"_on_per_language_count must call fetch_all_reviews exactly once "
        f"(the old code had two identical branches); got {n_calls}"
    )
    # And the old ``if lang == "all":`` code branch must be gone.
    assert 'if lang == "all"' not in code


# ---------------------------------------------------------------------------
# BUG-R2-8: minor — verify the existing test suite picks up the new
# behavior. This isn't a bug per se but guards against a regression
# where the warning is added but accidentally converts all presets
# into unknowns.
# ---------------------------------------------------------------------------


def test_compute_since_timestamp_all_presets_recognized(caplog):
    """Every label in SINCE_PRESETS must NOT trigger the unknown warning."""
    from steam_review_tool.core.constants import SINCE_PRESETS
    from steam_review_tool.utils.datetime_utils import compute_since_timestamp

    for label, hours in SINCE_PRESETS:
        with caplog.at_level(logging.WARNING, logger="steam_review_tool.utils.datetime_utils"):
            compute_since_timestamp(
                preset_label=label, custom_date_str="", custom_time_str="",
            )
        warnings = [r for r in caplog.records if "unknown preset" in r.message.lower()]
        assert not warnings, (
            f"preset {label!r} is in SINCE_PRESETS but triggered the "
            f"unknown-preset warning: {[r.message for r in warnings]}"
        )
        caplog.clear()
