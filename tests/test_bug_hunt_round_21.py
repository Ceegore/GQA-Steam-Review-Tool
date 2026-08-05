"""Round-21 bug-hunt regression tests.

Real bugs found in a twenty-first systematic pass. Rounds
1-20 (9388ab1, 9ea69de, ed231bc, 80f9431, f913ae8,
e0514c0, 0e4f031, ba4255e, 49aa77a, 831219e, 04f47f6,
dfd6ff7, 6265d12, 561fc45, b795fbd, 95ea74e, 40d195a,
25c305a, 9e5b263, dc1d9d7) found 87 bugs across the
project. Round 21 found 8 more — this round has three
distinct audit targets:

1. **R20-3 false positive (R21-0)** — the R20
   bus-event audit incorrectly classified
   ``SCRAPE_STARTED`` and ``SCRAPE_FAILED`` as
   dead. They DO have a subscriber: the
   ``ActionStateMixin`` in ``ui/_action_state.py``
   subscribes INDIRECTLY via the
   ``install_action_state_bus(started_event=...,
   failed_event=...)`` kwargs, which
   ``tab_playwright.py`` wires up with the
   ``self.pw_wf.SCRAPE_STARTED`` /
   ``self.pw_wf.SCRAPE_FAILED`` constants. The R20
   audit walked direct ``bus.subscribe(event, ...)``
   calls and missed the 3-hop indirect chain
   (mixin kwargs → tab constants → workflow
   constants). R20-3's removal of those events
   broke the smoke test
   (``AttributeError: 'PlaywrightWorkflow' object
   has no attribute 'SCRAPE_STARTED'`` at
   ``tab_playwright`` construction time). R21-0
   restores both constants + both publishes;
   ``SCRAPE_PROGRESS`` stays removed (truly dead).
   The R20-3 test class is updated to assert the
   corrected contract: ``SCRAPE_PROGRESS`` is the
   ONLY dead PW event; ``SCRAPE_STARTED`` and
   ``SCRAPE_FAILED`` are live with the mixin as
   the (sole) subscriber.

2. **Logger-in-except traceback capture (R21-1 to
   R21-7)** — 7 ``_log.warning("...: %s", exc)``
   calls inside ``except ... as exc:`` blocks were
   silently dropping the traceback (the bare
   ``%s, exc`` formatting captures the exception
   message but NOT the frame / line number /
   call-chain the developer needs to debug).
   The R12-4 to R12-7 + R15-3 lesson was that
   ``_log.exception(...)`` (not ``_log.warning``)
   is the correct call inside an ``except`` block —
   ``_log.exception`` auto-captures the traceback
   via ``sys.exc_info()``. The R21 audit walked
   every ``except ... as exc:`` block in the
   codebase and converted 7 sites in 2 files
   (dump_folder_controller.py, storefront_parser.py)
   to ``_log.exception(...)``. The bare-exc
   pattern is the clearest bug; the multi-line
   "type+exc" pattern (5 sites in markdown_helpers,
   1 site in per_language_exporter, 1 site in
   steam_api_service) and the 4 remaining
   bare-exc sites (3 in steam_api_service, 1 in
   settings_store, 4 in playwright_subprocess)
   will be covered by R22 / R23.

The recurring lesson (compounding R12 + R15 +
R20): after consolidating helpers, audit the
SAME anti-pattern at boundaries the previous
rounds already audited. R12-4 found the first
``_log.warning(..., exc)`` losing the traceback.
R15-3 added more. R21 applies the same audit
to a fresh code region (the R16-3 +
R17-1 chokepoints + the storefront parser
network layer).

R21-1  controllers/dump_folder_controller.py:74:
       ``set_dump_root`` had
       ``except OSError as exc: _log.warning(
       "could not load settings for dump_root
       persist: %s", exc)`` — the traceback
       was silently dropped. A settings-load
       failure with only the bare exception
       message hides the file path /
       permissions error the developer needs
       to debug.

R21-2  controllers/dump_folder_controller.py:82:
       ``set_dump_root`` had the same
       anti-pattern in the save branch.

R21-3  controllers/dump_folder_controller.py:108:
       ``set_obsidian_vault`` had the same
       anti-pattern in the load branch.

R21-4  controllers/dump_folder_controller.py:117:
       ``set_obsidian_vault`` had the same
       anti-pattern in the save branch.

R21-5  services/storefront_parser.py:48:
       ``get_popularity_metrics`` had
       ``except requests.RequestException as exc:
       _log.warning(..., exc)`` — a network
       error with only the bare exception
       message hides the URL / params /
       response status the developer needs.

R21-6  services/storefront_parser.py:53:
       ``get_popularity_metrics`` had the same
       anti-pattern in the bad-response branch
       (``except (ValueError, UnicodeDecodeError)``).

R21-7  services/storefront_parser.py:120:
       ``get_storefront_stats_from_html`` had
       the same anti-pattern in the catch-all
       network branch.

Test discipline notes (compounding R12 + R15 +
R16 + R17 + R18 + R19 + R20 lessons):

- The R21 logger-in-except tests are
  static-check source-walkers that pin the
  ``_log.exception`` call inside every
  ``except ... as exc:`` block in the two
  fixed files. A regression that re-introduces
  the ``_log.warning("...: %s", exc)`` pattern
  (or removes the bare ``as exc:`` and switches
  to ``except SomeException:`` + manual
  ``sys.exc_info()``) would re-introduce the
  anti-pattern and the tests would fail.

- The R21-0 test (in
  ``test_bug_hunt_round_20.py``) is a
  static-check that pins the corrected R20-3
  contract: ``SCRAPE_PROGRESS`` is the ONLY
  dead PW event; ``SCRAPE_STARTED`` and
  ``SCRAPE_FAILED`` are live with the
  ``ActionStateMixin`` as the (sole)
  subscriber. The R20-3 false-positive lesson
  generalises: the bus-event audit must walk
  the indirect subscriber chain (mixin kwargs,
  callback closures, function parameters) —
  not just direct ``bus.subscribe(event, ...)``
  calls.

- The ``_strip_comments_and_docstrings`` helper
  is reused from R16 for the source-shape
  probes.

Stats: 8 bugs found, ~16 regression tests added.
"""
from __future__ import annotations

import inspect
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
# Helper: find every ``except ... as <var>:`` block in a source string.
# Returns a list of (block_text, var_name) tuples. The block text is
# everything from the ``except`` line to the next top-level statement
# (heuristic: the next line at the SAME indent level as ``except``).
# ---------------------------------------------------------------------------
def _find_except_blocks(src: str) -> list[tuple[str, str | None]]:
    """Return ``[(block_text, var_name), ...]`` for every
    ``except ... as var:`` block in ``src``.

    A block is bounded by the ``except`` line + the
    indented body. We use a simple indent-level heuristic:
    the body ends at the first non-blank line whose
    indent is <= the ``except`` line's indent.
    """
    out: list[tuple[str, str | None]] = []
    lines = src.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r"^(\s*)except\b(.*?):\s*$", line)
        if not m:
            i += 1
            continue
        indent = m.group(1)
        rest = m.group(2)
        # ``as <var>`` may be present.
        var_match = re.search(r"\bas\s+(\w+)\b", rest)
        var_name = var_match.group(1) if var_match else None
        # Collect the body: lines that are MORE indented
        # than ``indent``, plus blank lines / comment
        # lines between them.
        body: list[str] = [line]
        j = i + 1
        while j < len(lines):
            nxt = lines[j]
            if not nxt.strip():
                body.append(nxt)
                j += 1
                continue
            stripped_indent = len(nxt) - len(nxt.lstrip())
            if stripped_indent > len(indent):
                body.append(nxt)
                j += 1
            else:
                break
        out.append(("\n".join(body), var_name))
        i = j
    return out


# ---------------------------------------------------------------------------
# BUG-R21-1 to R21-4: dump_folder_controller.py logger-in-except sites
# ---------------------------------------------------------------------------
class TestDumpFolderControllerUsesLogException:
    """``DumpFolderController.set_dump_root`` and
    ``set_obsidian_vault`` had 4 ``_log.warning(
    "...: %s", exc)`` calls inside ``except OSError
    as exc:`` blocks — silently dropping the
    traceback. R21-1 to R21-4 fixes convert all 4
    to ``_log.exception(...)`` (which auto-captures
    the traceback via ``sys.exc_info()``).

    The R16-3 (``set_dump_root``) and R17-1
    (``set_obsidian_vault``) chokepoints
    introduced these sites. R21 audits them with
    the same R12-4 to R12-7 lesson applied to the
    fresh code region.
    """

    def _src(self) -> str:
        from steam_review_tool.controllers import (
            dump_folder_controller,
        )
        full_src = inspect.getsource(dump_folder_controller)
        return _strip_comments_and_docstrings(full_src)

    def test_set_dump_root_load_uses_log_exception(self) -> None:
        """R21-1: ``set_dump_root`` load branch
        (``except OSError:``) must use
        ``_log.exception`` so the traceback is
        captured."""
        src = self._src()
        # The R21-1 fix replaced
        # ``_log.warning("could not load settings
        # for dump_root persist: %s", exc)`` with
        # ``_log.exception("could not load
        # settings for dump_root persist")`` —
        # the ``%s, exc`` is GONE, the message
        # text is preserved (minus the ``: %s``
        # tail that ``_log.exception`` makes
        # redundant).
        assert (
            '_log.exception("could not load settings '
            'for dump_root persist")'
        ) in src, (
            "set_dump_root's load branch must use "
            "_log.exception (R21-1 fix) — the previous "
            "_log.warning('...: %s', exc) silently "
            "dropped the traceback."
        )
        # Anti-pattern: the old ``%s, exc`` form is
        # gone from the file (R21-1 fix).
        assert (
            'could not load settings for dump_root '
            'persist: %s'
        ) not in src, (
            "set_dump_root's load branch still has "
            "the R21-1 anti-pattern '_log.warning(..., "
            "'...: %s', exc)' — the traceback is "
            "silently dropped."
        )

    def test_set_dump_root_save_uses_log_exception(self) -> None:
        """R21-2: ``set_dump_root`` save branch
        (``except OSError:``) must use
        ``_log.exception``."""
        src = self._src()
        assert (
            '_log.exception("could not persist '
            'dump_root to settings")'
        ) in src, (
            "set_dump_root's save branch must use "
            "_log.exception (R21-2 fix)."
        )
        assert (
            'could not persist dump_root to settings: %s'
        ) not in src, (
            "set_dump_root's save branch still has "
            "the R21-2 anti-pattern '_log.warning(..., "
            "'...: %s', exc)'."
        )

    def test_set_obsidian_vault_load_uses_log_exception(self) -> None:
        """R21-3: ``set_obsidian_vault`` load branch
        (``except OSError:``) must use
        ``_log.exception``."""
        src = self._src()
        assert (
            '_log.exception("could not load settings '
            'for obsidian_vault persist")'
        ) in src, (
            "set_obsidian_vault's load branch must use "
            "_log.exception (R21-3 fix)."
        )
        assert (
            'could not load settings for obsidian_vault '
            'persist: %s'
        ) not in src, (
            "set_obsidian_vault's load branch still has "
            "the R21-3 anti-pattern '_log.warning(..., "
            "'...: %s', exc)'."
        )

    def test_set_obsidian_vault_save_uses_log_exception(self) -> None:
        """R21-4: ``set_obsidian_vault`` save branch
        (``except OSError:``) must use
        ``_log.exception``."""
        src = self._src()
        assert (
            '_log.exception("could not persist '
            'obsidian_vault to settings")'
        ) in src, (
            "set_obsidian_vault's save branch must use "
            "_log.exception (R21-4 fix)."
        )
        assert (
            'could not persist obsidian_vault to '
            'settings: %s'
        ) not in src, (
            "set_obsidian_vault's save branch still has "
            "the R21-4 anti-pattern '_log.warning(..., "
            "'...: %s', exc)'."
        )

    def test_no_except_block_uses_log_warning_with_exc(self) -> None:
        """The static-check guard for the 4 R21
        fixes: walk every ``except ... as exc:``
        block in ``dump_folder_controller.py`` and
        assert that none of them use the
        ``_log.warning("...: %s", exc)`` anti-pattern
        (the traceback-dropping form)."""
        src = self._src()
        for block_text, var_name in _find_except_blocks(src):
            if var_name is None:
                # No ``as exc`` binding — the
                # ``_log.warning("...: %s", exc)``
                # pattern can't apply (no ``exc``
                # in scope). Skip.
                continue
            # The anti-pattern: ``_log.warning(...)``
            # inside the block, where the LAST
            # formatting arg is the bound variable.
            # We use a regex to be precise about
            # the form.
            warn_call = re.search(
                rf'_log\.warning\([^)]*%s[^)]*,\s*{var_name}\s*\)',
                block_text,
            )
            assert not warn_call, (
                f"dump_folder_controller.py has an "
                f"except-block using '_log.warning(...)' "
                f"with the bound variable {var_name!r} as "
                f"the last arg — the traceback is "
                f"silently dropped. Use '_log.exception(...)' "
                f"instead (R12-4 to R12-7 + R15-3 lesson). "
                f"Block:\n{block_text}"
            )


# ---------------------------------------------------------------------------
# BUG-R21-5 to R21-7: storefront_parser.py logger-in-except sites
# ---------------------------------------------------------------------------
class TestStorefrontParserUsesLogException:
    """``StorefrontParser.get_popularity_metrics`` and
    ``get_storefront_stats_from_html`` had 3
    ``_log.warning("...: %s", exc)`` calls inside
    ``except ... as exc:`` blocks — silently dropping
    the traceback. R21-5 to R21-7 fixes convert all 3
    to ``_log.exception(...)``."""

    def _src(self) -> str:
        from steam_review_tool.services import (
            storefront_parser,
        )
        full_src = inspect.getsource(storefront_parser)
        return _strip_comments_and_docstrings(full_src)

    def test_get_popularity_metrics_network_error_uses_log_exception(
        self,
    ) -> None:
        """R21-5: ``get_popularity_metrics`` network
        branch (``except requests.RequestException as exc:``)
        must use ``_log.exception`` (not
        ``_log.warning``) so the traceback is captured.

        The R21-5 fix preserves the R13 fix contract:
        the log line still includes the ``exc`` arg
        so the underlying cause ("DNS lookup failed",
        "503 Service Unavailable", ...) is visible
        in the user's stderr log. ``_log.exception``
        additionally captures the traceback (R12-4 to
        R12-7 + R15-3 lesson)."""
        src = self._src()
        assert (
            '_log.exception(\n                "get_popularity_metrics'
            '(%d, %s) failed: %s"'
        ) in src, (
            "get_popularity_metrics's network branch "
            "must use _log.exception with the exc arg "
            "preserved (R21-5 fix — captures traceback "
            "AND keeps the R13 cause-in-log contract)."
        )
        # Anti-pattern: the previous ``_log.warning``
        # with the same args is gone.
        assert (
            '_log.warning(\n                "get_popularity_metrics'
            '(%d, %s) failed: %s"'
        ) not in src, (
            "get_popularity_metrics's network branch "
            "still has the R21-5 anti-pattern "
            "'_log.warning(..., exc)' — the traceback "
            "is silently dropped."
        )

    def test_get_popularity_metrics_bad_response_uses_log_exception(
        self,
    ) -> None:
        """R21-6: ``get_popularity_metrics`` bad-response
        branch (``except (ValueError, UnicodeDecodeError) as exc:``)
        must use ``_log.exception``."""
        src = self._src()
        assert (
            '_log.exception(\n                "get_popularity_metrics'
            '(%d, %s): bad response: %s"'
        ) in src, (
            "get_popularity_metrics's bad-response "
            "branch must use _log.exception with the "
            "exc arg preserved (R21-6 fix)."
        )
        assert (
            '_log.warning(\n                "get_popularity_metrics'
            '(%d, %s): bad response: %s"'
        ) not in src, (
            "get_popularity_metrics's bad-response "
            "branch still has the R21-6 anti-pattern."
        )

    def test_get_storefront_stats_from_html_uses_log_exception(self) -> None:
        """R21-7: ``get_storefront_stats_from_html``
        network branch (``except (requests.RequestException,
        ValueError) as exc:``) must use ``_log.exception``."""
        src = self._src()
        assert (
            '_log.exception("stats fetch failed: %s", exc)'
        ) in src, (
            "get_storefront_stats_from_html's network "
            "branch must use _log.exception with the "
            "exc arg preserved (R21-7 fix)."
        )
        assert (
            '_log.warning("stats fetch failed: %s", exc)'
        ) not in src, (
            "get_storefront_stats_from_html's network "
            "branch still has the R21-7 anti-pattern "
            "'_log.warning(..., '...: %s', exc)'."
        )

    def test_no_except_block_uses_log_warning_with_exc(self) -> None:
        """The static-check guard for the 3 R21
        fixes: walk every ``except ... as exc:``
        block in ``storefront_parser.py`` and assert
        that none of them use the
        ``_log.warning("...: %s", exc)`` anti-pattern."""
        src = self._src()
        for block_text, var_name in _find_except_blocks(src):
            if var_name is None:
                continue
            warn_call = re.search(
                rf'_log\.warning\([^)]*%s[^)]*,\s*{var_name}\s*\)',
                block_text,
            )
            assert not warn_call, (
                f"storefront_parser.py has an except-block "
                f"using '_log.warning(...)' with the bound "
                f"variable {var_name!r} as the last arg — "
                f"the traceback is silently dropped. Use "
                f"'_log.exception(...)' instead. Block:\n"
                f"{block_text}"
            )


# ---------------------------------------------------------------------------
# BUG-R21-0: R20-3 false positive — the bus-event audit must walk the
# indirect subscriber chain (mixin kwargs → tab constants → workflow
# constants), not just direct ``bus.subscribe(event, ...)`` calls.
# ---------------------------------------------------------------------------
class TestR20IndirectSubscriberChain:
    """The R20 bus-event audit walked direct
    ``bus.subscribe(event, ...)`` calls and
    concluded that ``SCRAPE_STARTED`` and
    ``SCRAPE_FAILED`` had zero subscribers. They
    DO have a subscriber: the ``ActionStateMixin``
    in ``ui/_action_state.py`` subscribes via
    ``install_action_state_bus(started_event=...,
    failed_event=...)``, which ``tab_playwright.py``
    wires up with ``self.pw_wf.SCRAPE_STARTED`` /
    ``self.pw_wf.SCRAPE_FAILED``. The R20 audit
    missed the 3-hop indirect chain:

      1. ``ui/_action_state.py:install_action_state_bus``
         does ``bus.subscribe(started_event, ...)``
         — the event name is a FUNCTION PARAMETER.
      2. ``ui/tab_playwright.py`` calls
         ``self.install_action_state_bus(
         started_event=self.pw_wf.SCRAPE_STARTED, ...)``
         — passes the workflow's constant as the
         kwarg value.
      3. ``controllers/playwright_workflow.py``
         defines ``SCRAPE_STARTED = "pw.scrape.started"``
         — the constant resolves to the event name.

    A direct-subscriber audit (grep for
    ``bus.subscribe("pw.scrape.started", ...)``)
    finds NOTHING because the subscribe is to a
    function parameter. R20-3's removal of the
    constants + publishes broke the smoke test
    (AttributeError at tab_playwright construction).
    R21-0 restored both events as LIVE with the
    ``ActionStateMixin`` as the (sole) subscriber.

    This test pins the R21-0 lesson: the bus-event
    audit must follow the indirect subscriber chain.
    """

    def test_action_state_mixin_subscribe_uses_kwargs(self) -> None:
        """``ActionStateMixin.install_action_state_bus``
        subscribes via the ``started_event`` /
        ``failed_event`` kwargs — the event names are
        function parameters (resolved at call time from
        the worker's constants), not string literals.
        A direct-subscriber audit (grep for
        ``bus.subscribe("pw.scrape.started", ...)``)
        will miss this (R20-3 false positive)."""
        from steam_review_tool.ui import _action_state
        src = inspect.getsource(_action_state)
        code = _strip_comments_and_docstrings(src)
        # The mixin builds a list of (event, callback)
        # pairs from the kwargs, then iterates and
        # subscribes. The subscribe line is
        # ``bus.subscribe(event, cb)`` (the loop
        # variable) — the actual event names come from
        # the list entries.
        assert "bus.subscribe(event, cb)" in code, (
            "ActionStateMixin.install_action_state_bus "
            "must iterate over a list of (event, cb) "
            "pairs and call bus.subscribe(event, cb) "
            "for each. The R20-3 false positive was "
            "based on a grep for "
            "bus.subscribe('pw.scrape.started', ...) "
            "which finds nothing because the event "
            "name is a kwarg resolved at call time."
        )
        # The list must include entries for all 3
        # events (started / completed / failed).
        assert "(started_event," in code, (
            "ActionStateMixin must include a "
            "(started_event, callback) entry in the "
            "subs list — the started event is one of "
            "the 3 events the mixin wires up."
        )
        assert "(failed_event," in code, (
            "ActionStateMixin must include a "
            "(failed_event, callback) entry in the "
            "subs list."
        )
        assert "(completed_event," in code, (
            "ActionStateMixin must include a "
            "(completed_event, callback) entry in the "
            "subs list."
        )

    def test_pw_tab_wires_mixin_with_pw_workflow_constants(self) -> None:
        """``tab_playwright.py`` must pass the PW
        workflow's ``SCRAPE_STARTED`` /
        ``SCRAPE_FAILED`` constants to the mixin —
        the constants exist (R21-0 restoration) so
        the call resolves without AttributeError."""
        from steam_review_tool.ui import tab_playwright
        from steam_review_tool.controllers import (
            playwright_workflow,
        )
        # The constants must exist on the PW
        # workflow class (R21-0 restored them).
        assert hasattr(playwright_workflow.PlaywrightWorkflow,
                       "SCRAPE_STARTED"), (
            "PlaywrightWorkflow.SCRAPE_STARTED was "
            "incorrectly removed in R20-3; R21-0 "
            "restored it. The tab_playwright caller "
            "in install_action_state_bus needs the "
            "constant to resolve (without it, the "
            "smoke test fails with AttributeError)."
        )
        assert hasattr(playwright_workflow.PlaywrightWorkflow,
                       "SCRAPE_FAILED"), (
            "PlaywrightWorkflow.SCRAPE_FAILED was "
            "incorrectly removed in R20-3; R21-0 "
            "restored it."
        )
        # The tab must actually pass the constants
        # to the mixin.
        src = inspect.getsource(tab_playwright)
        code = _strip_comments_and_docstrings(src)
        assert (
            'started_event=self.pw_wf.SCRAPE_STARTED'
        ) in code, (
            "tab_playwright must pass self.pw_wf."
            "SCRAPE_STARTED to "
            "install_action_state_bus — the "
            "ActionStateMixin needs the event name "
            "to subscribe (R21-0 lesson: indirect "
            "subscriber chain)."
        )
        assert (
            'failed_event=self.pw_wf.SCRAPE_FAILED'
        ) in code, (
            "tab_playwright must pass self.pw_wf."
            "SCRAPE_FAILED to "
            "install_action_state_bus."
        )
