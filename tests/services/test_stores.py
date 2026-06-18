"""Tests for settings, resume, dump, and trends stores."""
import json
from pathlib import Path

import pytest

from steam_review_tool.services import resume_store, settings_store
from steam_review_tool.services.dump_repository import DumpRepository
from steam_review_tool.services.trends_store import TrendsStore


# ---- resume_store ---------------------------------------------------------


def test_resume_set_then_get(tmp_path, monkeypatch):
    # Redirect CONFIG_FILE to a tmp file
    cfg = tmp_path / "resume.json"
    monkeypatch.setattr(resume_store, "CONFIG_FILE", cfg)
    resume_store.set_("api", 42, cursor="abc", fetched=100)
    data = resume_store.get("api", 42)
    assert data == {"cursor": "abc", "fetched": 100}


def test_resume_clear(tmp_path, monkeypatch):
    cfg = tmp_path / "resume.json"
    monkeypatch.setattr(resume_store, "CONFIG_FILE", cfg)
    resume_store.set_("api", 42, cursor="abc")
    resume_store.clear("api", 42)
    assert resume_store.get("api", 42) is None


def test_resume_missing_returns_none(tmp_path, monkeypatch):
    cfg = tmp_path / "resume.json"
    monkeypatch.setattr(resume_store, "CONFIG_FILE", cfg)
    assert resume_store.get("api", 999) is None


# ---- settings_store -------------------------------------------------------


def test_settings_load_returns_defaults_when_missing(tmp_path, monkeypatch):
    f = tmp_path / "settings.json"
    monkeypatch.setattr(settings_store, "SETTINGS_FILE", f)
    data = settings_store.load()
    assert data["open_after_export"] is True
    assert data["also_csv"] is False


def test_settings_save_and_load_roundtrip(tmp_path, monkeypatch):
    f = tmp_path / "settings.json"
    monkeypatch.setattr(settings_store, "SETTINGS_FILE", f)
    payload = {"dump_root": "X:/foo", "apify_token": "secret"}
    settings_store.save(payload)
    loaded = settings_store.load()
    assert loaded["dump_root"] == "X:/foo"
    assert loaded["apify_token"] == "secret"
    # Defaults still present
    assert "open_after_export" in loaded


# ---- dump_repository ------------------------------------------------------


def test_dump_repository_load_seen_returns_empty_when_missing(tmp_path):
    repo = DumpRepository(tmp_path)
    assert repo.load_seen(42, "test") == set()


def test_dump_repository_save_then_load(tmp_path):
    repo = DumpRepository(tmp_path)
    repo.save_seen(42, "test", {"a", "b", "c"}, name="Test Game")
    assert repo.load_seen(42, "test") == {"a", "b", "c"}


def test_dump_repository_folder_creates_subdir(tmp_path):
    repo = DumpRepository(tmp_path)
    folder = repo.folder_for(42, "Test Game")
    assert folder.exists()
    # Spaces are sanitised to underscores by DumpRepository's defence
    # chain (sanitize_for_filename first, then the safe-name regex).
    assert folder.name == "42_Test_Game"


# ---- trends_store ---------------------------------------------------------


def test_trends_store_add_and_list(tmp_path):
    store = TrendsStore.__new__(TrendsStore)
    store.path = tmp_path / "trends.json"
    store.add(42, "Game X")
    assert store.is_tracked(42)
    assert any(a["name"] == "Game X" for a in store.tracked_apps())


def test_trends_store_record_and_series(tmp_path):
    store = TrendsStore.__new__(TrendsStore)
    store.path = tmp_path / "trends.json"
    from steam_review_tool.models.trends_snapshot import TrendsSnapshot
    store.record(TrendsSnapshot(app_id=42, ts=1700000000, wishlist=100))
    store.record(TrendsSnapshot(app_id=42, ts=1700001000, wishlist=120))
    series = store.series(42, "wishlist")
    assert len(series) == 2
    assert series[0].wishlist == 100
    assert series[1].wishlist == 120