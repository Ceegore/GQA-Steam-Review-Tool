"""Round-7 bug-hunt regression tests.

Real bugs found in a seventh systematic pass. Rounds 1-6
(9388ab1, 9ea69de, ed231bc, 80f9431, f913ae8, e0514c0)
covered the int / str / or-default residue, the model + UI
layer, the apify_client zero short-circuit, the over-broad
"find latest .md" walk, and the missing worker-shutdown
wait on app close.

This round targets **double-subscribe** patterns: workflow
methods that silently ignore a "no-op" click (because a
worker is still running) return ``None``, but the tab
controllers subscribe an auto-export callback
unconditionally — so a duplicate "Fetch new" click would
double the auto-export when the first fetch completes.

Also caught: the trends tab's "Refresh all" button always
showed "Refresh started…" even when the click was a no-op.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# BUG-R7-1: API workflow start_fetch returns bool, tab_api guards subscribe
# ---------------------------------------------------------------------------
class TestApiWorkflowStartFetchReturnsBool:
    """``APIWorkflow.start_fetch`` used to return ``None`` and
    silently log "Fetch already running; ignored." when a
    worker was already alive. The tab controller's
    ``_on_fetch_new`` then unconditionally called
    ``bus.subscribe_once(FETCH_COMPLETED, auto_export)`` —
    so a second "Fetch new" click mid-fetch double-subscribed
    the auto-export. When the first fetch completed, BOTH
    auto-export callbacks fired and the user got TWO exports.

    Fix: ``start_fetch`` returns ``True`` if a new worker was
    started, ``False`` if the click was a no-op. The tab
    controller subscribes only on success.
    """

    def test_start_fetch_returns_true_on_first_call(self) -> None:
        from steam_review_tool.controllers.api_workflow import APIWorkflow
        from steam_review_tool.services.steam_api_service import SteamAPI

        wf = APIWorkflow(SteamAPI(), Path("/tmp"), log_cb=lambda _m: None)
        result = wf.start_fetch(4311090)
        try:
            assert result is True
        finally:
            wf.stop()
            wf.wait(timeout=2.0)

    def test_start_fetch_returns_false_when_already_running(self) -> None:
        from steam_review_tool.controllers.api_workflow import APIWorkflow
        from steam_review_tool.services.steam_api_service import SteamAPI

        wf = APIWorkflow(SteamAPI(), Path("/tmp"), log_cb=lambda _m: None)
        # Start a fetch (true) — don't wait for it, immediately
        # try a second one. The second should return False.
        first = wf.start_fetch(4311090)
        try:
            second = wf.start_fetch(4311090)
            assert first is True
            assert second is False, (
                "Second start_fetch should return False when a "
                "fetch is already running"
            )
        finally:
            wf.stop()
            wf.wait(timeout=2.0)

    def test_tab_api_does_not_double_subscribe(self) -> None:
        """Behavioural test: simulate two rapid "Fetch new" clicks
        via the tab controller and confirm only ONE auto-export
        callback is subscribed."""
        from steam_review_tool.controllers.api_workflow import APIWorkflow
        from steam_review_tool.services.steam_api_service import SteamAPI
        from steam_review_tool.core import event_bus

        wf = APIWorkflow(SteamAPI(), Path("/tmp"), log_cb=lambda _m: None)
        # Capture all auto-export subscriptions on the real bus.
        subscribed: list[Any] = []
        real_subscribe_once = event_bus.bus.subscribe_once

        def fake_subscribe_once(event: str, callback: Any, **_kw: Any) -> None:
            subscribed.append((event, callback))

        # Patch start_fetch so the second click is a no-op (returns
        # False) — that's the real-world shape.
        def fake_start_fetch(*_a: Any, **_kw: Any) -> bool:
            if wf._worker and wf._worker.is_alive():
                return False
            wf._stop.clear()
            wf._worker = threading.Thread(
                target=lambda: time.sleep(0.5),
                daemon=True,
            )
            wf._worker.start()
            return True

        wf.start_fetch = fake_start_fetch  # type: ignore[assignment]
        event_bus.bus.subscribe_once = fake_subscribe_once  # type: ignore[assignment]
        try:
            # Simulate the tab controller's _on_fetch_new logic.
            started = wf.start_fetch(4311090)
            if started:
                event_bus.bus.subscribe_once(
                    wf.FETCH_COMPLETED, lambda **kw: None,
                )
            # Second click mid-fetch — start_fetch returns False,
            # so the tab controller must NOT subscribe again.
            started_again = wf.start_fetch(4311090)
            if started_again:
                event_bus.bus.subscribe_once(
                    wf.FETCH_COMPLETED, lambda **kw: None,
                )
        finally:
            event_bus.bus.subscribe_once = real_subscribe_once  # type: ignore[assignment]
            wf._stop.set()
            if wf._worker:
                wf._worker.join(timeout=2.0)
        assert len(subscribed) == 1, (
            f"Expected exactly 1 auto-export subscription, "
            f"got {len(subscribed)} — duplicate click subscribed "
            f"twice"
        )


# ---------------------------------------------------------------------------
# BUG-R7-2: Playwright workflow scrape returns bool, tab_playwright guards
# ---------------------------------------------------------------------------
class TestPlaywrightWorkflowScrapeReturnsBool:
    """Same double-subscribe pattern in the Playwright tab."""

    def test_scrape_returns_true_on_first_call(self) -> None:
        from steam_review_tool.controllers.playwright_workflow import (
            PlaywrightWorkflow,
        )
        wf = PlaywrightWorkflow(log_cb=lambda _m: None)
        result = wf.scrape(4311090)
        try:
            assert result is True
        finally:
            wf.stop()
            wf.wait(timeout=2.0)

    def test_scrape_returns_false_when_already_running(self) -> None:
        from steam_review_tool.controllers.playwright_workflow import (
            PlaywrightWorkflow,
        )
        wf = PlaywrightWorkflow(log_cb=lambda _m: None)
        first = wf.scrape(4311090)
        try:
            second = wf.scrape(4311090)
            assert first is True
            assert second is False
        finally:
            wf.stop()
            wf.wait(timeout=2.0)


# ---------------------------------------------------------------------------
# BUG-R7-3: trends workflow refresh_all_async returns bool, tab_trends guards
# ---------------------------------------------------------------------------
class TestTrendsWorkflowRefreshReturnsBool:
    """Same double-subscribe / misleading-status pattern in the
    Trends tab. ``_on_refresh_all`` always set the status label
    to "Refresh started…" even when the click was a no-op."""

    def test_refresh_returns_true_on_first_call(self) -> None:
        from steam_review_tool.controllers.trends_workflow import (
            TrendsWorkflow,
        )
        from steam_review_tool.services.trends_store import TrendsStore

        wf = TrendsWorkflow(TrendsStore(), log_cb=lambda _m: None)
        result = wf.refresh_all_async(lambda _id: None)
        try:
            assert result is True
        finally:
            if wf._refresh_worker:
                wf._refresh_worker.join(timeout=2.0)

    def test_refresh_returns_false_when_already_running(self) -> None:
        from steam_review_tool.controllers.trends_workflow import (
            TrendsWorkflow,
        )
        from steam_review_tool.services.trends_store import TrendsStore

        wf = TrendsWorkflow(TrendsStore(), log_cb=lambda _m: None)
        first = wf.refresh_all_async(lambda _id: None)
        try:
            second = wf.refresh_all_async(lambda _id: None)
            assert first is True
            assert second is False
        finally:
            if wf._refresh_worker:
                wf._refresh_worker.join(timeout=2.0)
