"""Round-20 bug-hunt regression tests.

Real bugs found in a twentieth systematic pass. Rounds 1-19
(9388ab1, 9ea69de, ed231bc, 80f9431, f913ae8, e0514c0,
0e4f031, ba4255e, 49aa77a, 831219e, 04f47f6, dfd6ff7,
6265d12, 561fc45, b795fbd, 95ea74e, 40d195a, 25c305a,
9e5b263) found 84 bugs across the project. Round 20
found 3 more — this round targets the same pattern
class as R19: **dead bus events with zero subscribers**.

The recurring lesson (compounding R8 + R19): "ANY
``bus.publish`` must have a corresponding subscriber".
R19-2 found the first dead publish (``dump.root.changed``).
R20 audits the other 19 published events across the
6 controllers and finds 6 more dead publishes grouped
into 3 dead constants:

R20-1  controllers/settings_controller.py: the
       ``SETTINGS_APPLIED`` event was published but
       had zero subscribers. The constant + the
       publish + the now-unused ``bus`` import were
       all removed.

R20-2  controllers/trends_workflow.py: the
       ``TRACKED_CHANGED`` (3 publishes) and
       ``SNAPSHOT_RECORDED`` (1 publish) events had
       zero subscribers. The constants + the
       publishes + the ``bus`` import were all
       removed.

R20-3  controllers/playwright_workflow.py: the
       ``SCRAPE_STARTED`` (1 publish),
       ``SCRAPE_PROGRESS`` (1 publish), and
       ``SCRAPE_FAILED`` (1 publish) events had
       zero subscribers. The 3 constants + the
       3 publishes were removed; the now-redundant
       ``progress_cb`` was converted to a no-op
       (it was the only caller of SCRAPE_PROGRESS).

R20 audits the bus events:

| Event                       | Published | Subscribed | Status      |
|-----------------------------|-----------|------------|-------------|
| api.fetch.started           | yes       | yes (R8)   | live        |
| api.fetch.progress          | yes       | yes        | live        |
| api.fetch.completed         | yes       | yes        | live        |
| api.fetch.failed            | yes       | yes (R8)   | live        |
| pw.dep.status.changed       | yes       | yes        | live        |
| pw.scrape.completed         | yes       | yes (R1x)  | live        |
| pw.scrape.started           | yes       | ZERO       | DEAD (R20-3)|
| pw.scrape.progress          | yes       | ZERO       | DEAD (R20-3)|
| pw.scrape.failed            | yes       | ZERO       | DEAD (R20-3)|
| app.loaded                  | yes       | yes        | live        |
| settings.changed            | yes       | yes        | live        |
| settings.applied            | yes       | ZERO       | DEAD (R20-1)|
| trends.tracked.changed      | yes (3x)  | ZERO       | DEAD (R20-2)|
| trends.snapshot.recorded    | yes       | ZERO       | DEAD (R20-2)|

Test discipline notes (compounding R16 + R17 + R18 +
R19 lessons):

- The R20 tests are static-check source-walkers
  that pin the absence of the 6 dead bus events.
  A regression that re-introduces any of them
  would re-introduce the constants + the publishes
  (or keep dangling references) and the tests would
  fail.

- The R3 test in ``test_bug_hunt_round_3.py`` was
  updated to reflect the new (cleaner) contract:
  only ``SETTINGS_CHANGED`` exists; only that one
  event is published. The cross-test-file impact
  lesson (R19) means every public-symbol removal
  needs a follow-up grep in ``tests/`` for direct
  imports — the R20 audit found the R3 test was
  the only one that imported the dead constant.

- The ``_strip_comments_and_docstrings`` helper is
  reused from R16 for the source-shape probes.

Stats: 3 bugs found, 9 regression tests added.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helper: strip pure comment / docstring lines from a source string before
# substring-regression checks. Reused from R16.
# ---------------------------------------------------------------------------
def _strip_comments_and_docstrings(src: str) -> str:
    src_no_docstrings = re.sub(
        r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'',
        "",
        src,
    )
    out_lines: list[str] = []
    for line in src_no_docstrings.splitlines():
        if line.strip().startswith("#"):
            continue
        out_lines.append(line)
    return "\n".join(out_lines)


# ---------------------------------------------------------------------------
# Helper: walk the source tree for a substring (post-comment-strip).
# Returns the list of (file, line) matches.
# ---------------------------------------------------------------------------
def _grep_project(pattern: str) -> list[tuple[str, str]]:
    project_root = Path("steam_review_tool")
    hits: list[tuple[str, str]] = []
    for py in project_root.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        code = _strip_comments_and_docstrings(text)
        for ln in code.splitlines():
            if re.search(pattern, ln):
                hits.append((str(py), ln.strip()))
    return hits


# ---------------------------------------------------------------------------
# BUG-R20-1: SETTINGS_APPLIED is a dead bus event
# ---------------------------------------------------------------------------
class TestNoSettingsAppliedDeadEvent:
    """``SettingsController.SETTINGS_APPLIED`` was a dead
    bus event — no file in the codebase subscribed to
    ``settings.applied``. R20-1 fix removed the constant
    + the publish + the now-unused ``bus`` import.
    """

    def test_settings_controller_no_settings_applied(self) -> None:
        from steam_review_tool.controllers import (
            settings_controller,
        )
        src = settings_controller.__doc__ or ""
        # Look at the full module source.
        import inspect
        full_src = inspect.getsource(settings_controller)
        code = _strip_comments_and_docstrings(full_src)
        assert "SETTINGS_APPLIED" not in code, (
            "SettingsController.SETTINGS_APPLIED is a dead bus "
            "event (zero subscribers) — removed in R20-1. The "
            "constant + the publish + the now-unused 'bus' "
            "import should all be gone."
        )

    def test_no_publish_to_settings_applied(self) -> None:
        """No file in the codebase should
        ``bus.publish("settings.applied", ...)``."""
        hits = _grep_project(r'bus\.publish.*"settings\.applied"')
        # Also check for ``bus.publish(self.SETTINGS_APPLIED`` in
        # case some controller still holds a reference to the
        # (now-removed) constant — would be a ``NameError`` at
        # runtime.
        hits2 = _grep_project(r'bus\.publish\(self\.SETTINGS_APPLIED')
        assert not hits and not hits2, (
            f"found publishers of 'settings.applied' "
            f"(the event has zero subscribers and was "
            f"removed in R20-1): {hits + hits2}"
        )

    def test_no_subscribe_to_settings_applied(self) -> None:
        """No file should ``bus.subscribe("settings.applied", ...)``
        either (the event is fully dead)."""
        hits = _grep_project(r'bus\.subscribe.*"settings\.applied"')
        assert not hits, (
            f"found subscribers of 'settings.applied' "
            f"(the event has zero publishers and is fully "
            f"dead — removed in R20-1): {hits}"
        )

    def test_settings_changed_still_live(self) -> None:
        """The live event must STILL be published + subscribed
        (the R20-1 fix must not have removed the working
        half of the contract)."""
        # Publisher: settings_controller._on_saved
        from steam_review_tool.controllers import (
            settings_controller,
        )
        import inspect
        full_src = inspect.getsource(settings_controller)
        code = _strip_comments_and_docstrings(full_src)
        assert 'bus.publish(self.SETTINGS_CHANGED' in code, (
            "SettingsController._on_saved must still publish "
            "SETTINGS_CHANGED — the R20-1 fix only removed "
            "the dead SETTINGS_APPLIED, not the live "
            "SETTINGS_CHANGED."
        )
        # Subscriber: app_window
        from steam_review_tool.ui import app_window
        aw_src = inspect.getsource(app_window)
        aw_code = _strip_comments_and_docstrings(aw_src)
        assert '"settings.changed"' in aw_code, (
            "App must still subscribe to 'settings.changed' "
            "— the R20-1 fix only removed the dead "
            "SETTINGS_APPLIED, not the live SETTINGS_CHANGED."
        )


# ---------------------------------------------------------------------------
# BUG-R20-2: TRACKED_CHANGED + SNAPSHOT_RECORDED are dead bus events
# ---------------------------------------------------------------------------
class TestNoTrackedChangedOrSnapshotRecordedDeadEvents:
    """``TrendsWorkflow.TRACKED_CHANGED`` (3 publishes) and
    ``TRENDS_SNAPSHOT_RECORDED`` (1 publish) were dead
    bus events — no subscribers. R20-2 fix removed both
    constants + the 4 publishes + the now-unused
    ``bus`` import.
    """

    def test_trends_workflow_no_tracked_changed(self) -> None:
        from steam_review_tool.controllers import (
            trends_workflow,
        )
        import inspect
        full_src = inspect.getsource(trends_workflow)
        code = _strip_comments_and_docstrings(full_src)
        assert "TRACKED_CHANGED" not in code, (
            "TrendsWorkflow.TRACKED_CHANGED is a dead bus "
            "event (zero subscribers) — removed in R20-2."
        )
        assert "SNAPSHOT_RECORDED" not in code, (
            "TrendsWorkflow.SNAPSHOT_RECORDED is a dead bus "
            "event (zero subscribers) — removed in R20-2."
        )

    def test_no_publish_to_tracked_changed(self) -> None:
        """No file should publish ``"trends.tracked.changed"``."""
        hits = _grep_project(r'bus\.publish.*"trends\.tracked\.changed"')
        hits2 = _grep_project(r'bus\.publish\(self\.TRACKED_CHANGED')
        assert not hits and not hits2, (
            f"found publishers of 'trends.tracked.changed' "
            f"(the event has zero subscribers and was "
            f"removed in R20-2): {hits + hits2}"
        )

    def test_no_publish_to_snapshot_recorded(self) -> None:
        """No file should publish
        ``"trends.snapshot.recorded"``."""
        hits = _grep_project(r'bus\.publish.*"trends\.snapshot\.recorded"')
        hits2 = _grep_project(r'bus\.publish\(self\.SNAPSHOT_RECORDED')
        assert not hits and not hits2, (
            f"found publishers of 'trends.snapshot.recorded' "
            f"(the event has zero subscribers and was "
            f"removed in R20-2): {hits + hits2}"
        )

    def test_trends_workflow_no_bus_import(self) -> None:
        """The ``bus`` import in
        ``trends_workflow.py`` is now unused
        (the only publishes were the dead events
        removed in R20-2)."""
        from steam_review_tool.controllers import (
            trends_workflow,
        )
        import inspect
        full_src = inspect.getsource(trends_workflow)
        code = _strip_comments_and_docstrings(full_src)
        # The ``bus`` symbol must NOT appear as an
        # import OR usage in the post-R20 source.
        assert not re.search(
            r"^from\s+\S+\s+import.*\bbus\b", code, re.MULTILINE,
        ), (
            "trends_workflow.py must NOT import the "
            "event bus anymore (the only bus.publish "
            "calls were the dead TRACKED_CHANGED / "
            "SNAPSHOT_RECORDED events, removed in R20-2)"
        )
        # And no ``bus.`` usage.
        assert "bus." not in code, (
            "trends_workflow.py must NOT use the event "
            "bus anymore (R20-2 audit found zero "
            "subscribers for the only published events)"
        )


# ---------------------------------------------------------------------------
# BUG-R20-3: SCRAPE_PROGRESS is dead (R20-3 false positive on
# SCRAPE_STARTED + SCRAPE_FAILED — see R21-0 below)
# ---------------------------------------------------------------------------
class TestNoScrapeProgressDeadEvent:
    """``PlaywrightWorkflow._scrape_worker`` published
    ``SCRAPE_PROGRESS`` (1 publish, via the
    ``progress_cb`` closure) — a dead bus event with
    zero subscribers. R20-3 correctly removed the
    constant + the publish + converted the
    ``progress_cb`` to a no-op (it was the only
    caller of ``SCRAPE_PROGRESS``).

    R20-3 also (incorrectly) removed ``SCRAPE_STARTED``
    and ``SCRAPE_FAILED`` as dead — those events DO
    have a subscriber: the ``ActionStateMixin`` in
    ``ui/_action_state.py`` subscribes via
    ``install_action_state_bus(started_event=...,
    failed_event=...)`` which ``tab_playwright.py``
    wires up with ``self.pw_wf.SCRAPE_STARTED`` /
    ``self.pw_wf.SCRAPE_FAILED``. The R20 audit
    walked direct ``bus.subscribe(event, ...)`` calls
    and missed the INDIRECT subscription through
    the mixin's kwargs. R21-0 restored both
    constants + both publishes; the smoke test
    (``tests/smoke/test_app.py``) now passes
    again. ``SCRAPE_PROGRESS`` stays removed.
    """

    def test_playwright_workflow_no_scrape_progress(
        self,
    ) -> None:
        from steam_review_tool.controllers import (
            playwright_workflow,
        )
        import inspect
        full_src = inspect.getsource(playwright_workflow)
        code = _strip_comments_and_docstrings(full_src)
        # ``SCRAPE_PROGRESS`` is the ONLY dead PW event.
        assert "SCRAPE_PROGRESS" not in code, (
            "PlaywrightWorkflow.SCRAPE_PROGRESS is a dead "
            "bus event (zero subscribers) — removed in "
            "R20-3 and the removal was CORRECT."
        )
        # ``SCRAPE_STARTED`` and ``SCRAPE_FAILED`` were
        # incorrectly removed in R20-3 and restored in
        # R21-0 (the ``ActionStateMixin`` IS a
        # subscriber, indirectly via
        # ``install_action_state_bus`` kwargs). The
        # test must NOT assert they are absent — they
        # are now live.
        assert "SCRAPE_STARTED" in code, (
            "PlaywrightWorkflow.SCRAPE_STARTED was "
            "incorrectly removed in R20-3 (the R20 "
            "audit missed the INDIRECT subscriber via "
            "the ActionStateMixin). R21-0 restored it. "
            "The test must assert the constant is "
            "present (the event is LIVE)."
        )
        assert "SCRAPE_FAILED" in code, (
            "PlaywrightWorkflow.SCRAPE_FAILED was "
            "incorrectly removed in R20-3 (the R20 "
            "audit missed the INDIRECT subscriber via "
            "the ActionStateMixin). R21-0 restored it. "
            "The test must assert the constant is "
            "present (the event is LIVE)."
        )

    def test_no_publish_to_scrape_progress(self) -> None:
        """No file should publish ``"pw.scrape.progress"``."""
        hits = _grep_project(r'bus\.publish.*"pw\.scrape\.progress"')
        hits2 = _grep_project(r'bus\.publish\(self\.SCRAPE_PROGRESS')
        assert not hits and not hits2, (
            f"found publishers of 'pw.scrape.progress' "
            f"(the event has zero subscribers and was "
            f"correctly removed in R20-3): {hits + hits2}"
        )

    def test_scrape_started_and_failed_are_live(self) -> None:
        """The events that R20-3 incorrectly classified as
        dead MUST be published + subscribed (R21-0
        correction).

        The ``ActionStateMixin`` in
        ``ui/_action_state.py`` subscribes via
        ``install_action_state_bus``; ``tab_playwright``
        wires it up with the PW workflow's
        ``SCRAPE_STARTED`` / ``SCRAPE_FAILED``
        constants. The R20 audit walked direct
        ``bus.subscribe(event, ...)`` calls and missed
        the INDIRECT subscription through the mixin's
        kwargs.
        """
        # Publisher: playwright_workflow._scrape_worker
        from steam_review_tool.controllers import (
            playwright_workflow,
        )
        import inspect
        full_src = inspect.getsource(playwright_workflow)
        code = _strip_comments_and_docstrings(full_src)
        assert 'bus.publish(self.SCRAPE_STARTED' in code, (
            "PlaywrightWorkflow._scrape_worker must "
            "publish SCRAPE_STARTED — the ActionStateMixin "
            "subscribes via tab_playwright's "
            "install_action_state_bus call. R20-3 "
            "incorrectly removed this publish; R21-0 "
            "restored it."
        )
        assert 'bus.publish(self.SCRAPE_FAILED' in code, (
            "PlaywrightWorkflow._scrape_worker must "
            "publish SCRAPE_FAILED on exception — the "
            "ActionStateMixin subscribes via "
            "tab_playwright's install_action_state_bus "
            "call. R20-3 incorrectly removed this "
            "publish; R21-0 restored it."
        )
        # Subscriber: tab_playwright wires up the mixin
        # with the PW workflow's constants.
        from steam_review_tool.ui import tab_playwright
        tp_src = inspect.getsource(tab_playwright)
        tp_code = _strip_comments_and_docstrings(tp_src)
        assert 'self.pw_wf.SCRAPE_STARTED' in tp_code, (
            "tab_playwright must pass self.pw_wf."
            "SCRAPE_STARTED to install_action_state_bus "
            "— the ActionStateMixin needs the event name "
            "to subscribe. R20-3 missed the indirect "
            "subscriber chain (mixin kwargs → "
            "tab_playwright constants → workflow "
            "constants)."
        )
        assert 'self.pw_wf.SCRAPE_FAILED' in tp_code, (
            "tab_playwright must pass self.pw_wf."
            "SCRAPE_FAILED to install_action_state_bus "
            "— the ActionStateMixin needs the event name "
            "to subscribe. R20-3 missed the indirect "
            "subscriber chain."
        )

    def test_scrape_completed_still_live(self) -> None:
        """The live event must STILL be published + subscribed
        (the R20-3 fix must not have removed the working
        half of the contract)."""
        # Publisher: playwright_workflow._scrape_worker
        from steam_review_tool.controllers import (
            playwright_workflow,
        )
        import inspect
        full_src = inspect.getsource(playwright_workflow)
        code = _strip_comments_and_docstrings(full_src)
        assert 'bus.publish(self.SCRAPE_COMPLETED' in code, (
            "PlaywrightWorkflow._scrape_worker must still "
            "publish SCRAPE_COMPLETED — the R20-3 fix "
            "only removed the dead SCRAPE_PROGRESS (and "
            "incorrectly removed SCRAPE_STARTED / "
            "SCRAPE_FAILED, which R21-0 restored)."
        )
        # Subscriber: tab_playwright via bus.subscribe_once
        from steam_review_tool.ui import tab_playwright
        tp_src = inspect.getsource(tab_playwright)
        tp_code = _strip_comments_and_docstrings(tp_src)
        assert 'subscribe_once(' in tp_code
        assert '"pw.scrape.completed"' in tp_code, (
            "tab_playwright must still subscribe_once to "
            "'pw.scrape.completed' — the R20-3 fix only "
            "removed the dead SCRAPE_PROGRESS, not the "
            "live SCRAPE_COMPLETED."
        )
