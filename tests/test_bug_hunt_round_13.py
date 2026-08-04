"""Round-13 bug-hunt regression tests.

Real bugs found in a thirteenth systematic pass. Rounds 1-12
(9388ab1, 9ea69de, ed231bc, 80f9431, f913ae8, e0514c0,
0e4f031, ba4255e, 49aa77a, 831219e, 04f47f6, dfd6ff7)
covered the int / str / or-default residue, the chained-dict
crash, the double-subscribe pattern, the over-broad
"find latest .md" walk, the missing worker-shutdown wait, the
broken batch-dump feature, the missed R5 sites, the Tk
widget-state + watch-thread-safety issues, the destructive
"Reset" button before commit, the shared ``self._worker``
field, the backup-filename collision, the sister-helper
inconsistency, the sync-on-main-thread network call, the
popup-window-destroy race, the consolidation of the
cross-platform "open path" ladder, the silent export-failure
hiding, the popup-search stale results, and the slow
popup-open aggregation.

This round targets a new bug class: **broad ``except Exception``
swallowing specific actionable errors in non-UI code**. Where
R12 found 5 sites in ``markdown_helpers.py`` that hid export
failures behind ``except Exception: pass``, R13 found a
parallel pattern in the services / utils layer that hid
subprocess timeouts, network errors, resume-save failures,
and iteration-order non-determinism behind similar broad
excepts.

Six real bugs found:

1. ``install_playwright`` caught ``subprocess.TimeoutExpired``
   inside a broad ``except Exception`` and reported
   "Install failed to launch: Command '...' timed out after
   300 seconds" — the install DID launch, it just took too
   long, and the user lost the partial pip output that
   ``TimeoutExpired`` carries on its ``.stdout`` / ``.stderr``
   attributes.

2. ``install_chromium`` had the same bug as R13-1 (with a
   600 s timeout for the ~150 MB download).

3. ``storefront_parser.get_popularity_metrics`` caught every
   exception in a bare ``except Exception: return out`` and
   silently returned the empty metrics dict. The Trends tab
   stored ``None`` for all three metrics and the user had no
   way to tell whether Steam returned empty data or the
   request itself failed (timeout, connection refused, DNS
   error, etc.).

4. ``cursor_cb`` in ``steam_api_service.fetch_all_reviews``
   was wrapped in a bare ``except Exception: pass``. If
   ``resume_set`` (the default cursor callback) failed — disk
   full, file locked, perms denied — the fetch kept running,
   the user clicked Stop or the process died, and on next
   launch there was NO cursor to resume from. The user
   silently re-fetched every page from the start.

5. ``file_content_hash`` read the entire file into memory via
   ``f.read()``. The Obsidian-vault sync only ever uses
   this for ``.md`` files (a few MB at most), so the bug is
   latent — but the function is in ``utils.file_hash``,
   no docstring warning against binary blobs, and a user
   dragging a large video review (or pasting a binary by
   mistake) would OOM the process.

6. ``DumpRepository._guess_safe_name`` returned the FIRST
   match from ``os.scandir`` for the ``<app_id>_`` prefix.
   ``os.scandir`` order is OS-dependent and can vary
   between runs, so a user with two stale folders (e.g. a
   game that was renamed) could load the wrong
   ``seen_ids.json`` and silently re-dump every review.
"""
from __future__ import annotations

import hashlib
import logging
import subprocess
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# BUG-R13-1 + R13-2: dependency_installer catches TimeoutExpired as Exception
# ---------------------------------------------------------------------------
class TestDependencyInstallerTimeoutSurfaced:
    """``install_playwright`` and ``install_chromium`` used a
    broad ``except Exception`` that caught the
    ``subprocess.TimeoutExpired`` raised when the pip / playwright
    subprocess overran the 300 s / 600 s timeout. The user saw
    "Install failed to launch: Command '...' timed out after
    300 seconds" — the install DID launch, it just took too
    long, and the user lost the partial stdout / stderr that
    ``TimeoutExpired`` carries on its ``.stdout`` / ``.stderr``
    attributes.

    Fix: catch ``TimeoutExpired`` specifically, surface the
    partial output (truncated to 800 / 1000 chars), and use a
    different "Install timed out" message. Catch
    ``(FileNotFoundError, OSError)`` separately for the
    "failed to launch" case. Leave the broad ``except Exception``
    as a last-ditch safety net for unexpected subclass exceptions.
    """

    def _make_on_done(self) -> tuple[list, callable]:
        calls: list[tuple[bool, str]] = []
        def on_done(ok: bool, msg: str) -> None:
            calls.append((ok, msg))
        return calls, on_done

    def test_install_playwright_timeout_carries_partial_output(
        self,
    ) -> None:
        """When the pip subprocess times out, the on_done message
        must include the partial output that was captured before
        the timeout — the user wants to know "downloading 47 / 152
        MB" not just "timed out"."""
        from steam_review_tool.services import dependency_installer

        calls, on_done = self._make_on_done()

        # A fake TimeoutExpired that carries partial output
        # (the way the real ``subprocess.TimeoutExpired`` does
        # in Python 3.12+). The real call uses ``text=True`` so
        # ``.stdout`` / ``.stderr`` are ``str``, not ``bytes``.
        fake_exc = subprocess.TimeoutExpired(
            cmd=["python", "helper.py"], timeout=300,
        )
        fake_exc.stdout = "Downloading playwright-1.40.0 (47/152 MB)\n"
        fake_exc.stderr = ""

        with patch.object(dependency_installer, "_find_python",
                          return_value="/usr/bin/python"), \
             patch("steam_review_tool.services.dependency_installer"
                   ".subprocess.run",
                   side_effect=fake_exc):
            dependency_installer.install_playwright(
                log_cb=lambda _msg: None,
                on_done=on_done,
            )
        assert len(calls) == 1
        ok, msg = calls[0]
        assert ok is False
        assert "timed out" in msg.lower(), (
            f"expected 'timed out' in error message, got: {msg!r}"
        )
        assert "Downloading playwright" in msg, (
            f"expected partial output in error message, got: {msg!r}"
        )
        # The "Install failed to launch" message is reserved for
        # actual launch failures (FileNotFoundError, etc.) — the
        # timeout case must NOT use that misleading label.
        assert "failed to launch" not in msg.lower(), (
            f"timeout should not use 'Install failed to launch' "
            f"wording, got: {msg!r}"
        )

    def test_install_playwright_filenotfound_is_launch_failure(
        self,
    ) -> None:
        """When the python interpreter doesn't exist (FileNotFoundError),
        the message must say "Install failed to launch" — this IS a
        launch failure, not a timeout."""
        from steam_review_tool.services import dependency_installer

        calls, on_done = self._make_on_done()

        with patch.object(dependency_installer, "_find_python",
                          return_value="/missing/python"), \
             patch("steam_review_tool.services.dependency_installer"
                   ".subprocess.run",
                   side_effect=FileNotFoundError("python not found")):
            dependency_installer.install_playwright(
                log_cb=lambda _msg: None,
                on_done=on_done,
            )
        assert len(calls) == 1
        ok, msg = calls[0]
        assert ok is False
        assert "failed to launch" in msg.lower()
        assert "python not found" in msg

    def test_install_playwright_timeout_no_partial_output(
        self,
    ) -> None:
        """When the subprocess times out with NO captured output
        (the common case for a hung network connection), the
        message must still say 'timed out' and include a
        '(no output captured)' placeholder so the user knows
        the subprocess produced nothing before hanging."""
        from steam_review_tool.services import dependency_installer

        calls, on_done = self._make_on_done()

        fake_exc = subprocess.TimeoutExpired(
            cmd=["python", "helper.py"], timeout=300,
        )
        fake_exc.stdout = None
        fake_exc.stderr = None

        with patch.object(dependency_installer, "_find_python",
                          return_value="/usr/bin/python"), \
             patch("steam_review_tool.services.dependency_installer"
                   ".subprocess.run",
                   side_effect=fake_exc):
            dependency_installer.install_playwright(
                log_cb=lambda _msg: None,
                on_done=on_done,
            )
        assert len(calls) == 1
        ok, msg = calls[0]
        assert ok is False
        assert "timed out" in msg.lower()
        assert "no output" in msg.lower()

    def test_install_chromium_timeout_carries_partial_output(
        self,
    ) -> None:
        from steam_review_tool.services import dependency_installer

        calls, on_done = self._make_on_done()

        fake_exc = subprocess.TimeoutExpired(
            cmd=["python", "chrome.py"], timeout=600,
        )
        fake_exc.stdout = "Downloading Chromium r1234 (47%)\n"
        fake_exc.stderr = ""

        with patch.object(dependency_installer, "_find_python",
                          return_value="/usr/bin/python"), \
             patch("steam_review_tool.services.dependency_installer"
                   ".subprocess.run",
                   side_effect=fake_exc):
            dependency_installer.install_chromium(
                log_cb=lambda _msg: None,
                on_done=on_done,
            )
        assert len(calls) == 1
        ok, msg = calls[0]
        assert ok is False
        assert "timed out" in msg.lower()
        assert "Chromium r1234" in msg


# ---------------------------------------------------------------------------
# BUG-R13-3: storefront_parser.get_popularity_metrics swallows network errors
# ---------------------------------------------------------------------------
class TestStorefrontParserLogsNetworkErrors:
    """``get_popularity_metrics`` caught every exception (network,
    decode, anything) in a bare ``except Exception: return out``
    and silently returned the empty metrics dict. The Trends tab
    stored ``None`` for all three metrics and the user had no
    way to tell whether Steam returned empty data or the request
    itself failed (timeout, connection refused, DNS error, etc.).

    Fix: split the catch into ``requests.RequestException`` (the
    network-class exception) and ``(ValueError, UnicodeDecodeError)``
    (the decode-class), and log both with the app_id + language
    so the user can spot a missing metrics line in the stderr log.
    """

    def test_network_error_logs_warning(self) -> None:
        import requests
        from steam_review_tool.services.storefront_parser import (
            StorefrontParser,
        )

        records: list[logging.LogRecord] = []
        handler = _ListHandler(records)
        logger = logging.getLogger(
            "steam_review_tool.services.storefront_parser",
        )
        logger.addHandler(handler)
        old_level = logger.level
        logger.setLevel(logging.DEBUG)
        try:
            parser = StorefrontParser()
            with patch.object(
                parser.session, "get",
                side_effect=requests.ConnectionError(
                    "DNS lookup failed",
                ),
            ):
                out = parser.get_popularity_metrics(
                    12345, language="english",
                )
            # The function still returns the empty dict so the
            # caller doesn't crash — but the user-visible stderr
            # log now shows the actual cause.
            assert out == {
                "wishlist": None, "followers": None, "reviews": None,
            }
            assert any(
                "DNS lookup failed" in r.getMessage()
                and "12345" in r.getMessage()
                for r in records
            ), (
                f"expected a warning with app_id 12345 and the "
                f"underlying 'DNS lookup failed' message, got: "
                f"{[r.getMessage() for r in records]}"
            )
        finally:
            logger.removeHandler(handler)
            logger.setLevel(old_level)

    def test_http_error_logs_warning(self) -> None:
        import requests
        from steam_review_tool.services.storefront_parser import (
            StorefrontParser,
        )

        records: list[logging.LogRecord] = []
        handler = _ListHandler(records)
        logger = logging.getLogger(
            "steam_review_tool.services.storefront_parser",
        )
        logger.addHandler(handler)
        old_level = logger.level
        logger.setLevel(logging.DEBUG)
        try:
            parser = StorefrontParser()
            with patch.object(
                parser.session, "get",
                side_effect=requests.HTTPError("503 Service Unavailable"),
            ):
                out = parser.get_popularity_metrics(
                    99999, language="german",
                )
            assert out == {
                "wishlist": None, "followers": None, "reviews": None,
            }
            assert any(
                "503" in r.getMessage()
                and "99999" in r.getMessage()
                and "german" in r.getMessage()
                for r in records
            )
        finally:
            logger.removeHandler(handler)
            logger.setLevel(old_level)

    def test_success_does_not_log_warning(self) -> None:
        from steam_review_tool.services.storefront_parser import (
            StorefrontParser,
        )

        records: list[logging.LogRecord] = []
        handler = _ListHandler(records)
        logger = logging.getLogger(
            "steam_review_tool.services.storefront_parser",
        )
        logger.addHandler(handler)
        try:
            parser = StorefrontParser()
            with patch.object(
                parser.session, "get",
                return_value=_FakeResponse(
                    200,
                    '{"review_summary":{}}',
                ),
            ):
                out = parser.get_popularity_metrics(12345)
            # No warnings on a successful fetch (the JSON may
            # not contain the fields we look for, but the
            # network call itself succeeded).
            warnings = [
                r for r in records
                if "get_popularity_metrics" in r.getMessage()
            ]
            assert not warnings, (
                f"successful fetch should not log a warning, got: "
                f"{[r.getMessage() for r in warnings]}"
            )
            # And the function returns the empty dict (no
            # wishlist / followers / reviews found in the JSON).
            assert out == {
                "wishlist": None, "followers": None, "reviews": None,
            }
        finally:
            logger.removeHandler(handler)


class _FakeResponse:
    """Minimal stand-in for ``requests.Response`` so we can
    drive the storefront parser through its real code path
    without going over the network."""

    def __init__(self, status_code: int, text: str = "") -> None:
        self.status_code = status_code
        self.text = text

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(
                f"{self.status_code} error",
                response=self,
            )


class _ListHandler(logging.Handler):
    def __init__(self, records: list[logging.LogRecord]) -> None:
        super().__init__(level=logging.DEBUG)
        self._records = records

    def emit(self, record: logging.LogRecord) -> None:
        self._records.append(record)


# ---------------------------------------------------------------------------
# BUG-R13-4: cursor_cb silently swallows resume_set failures
# ---------------------------------------------------------------------------
class TestCursorCallbackLogsFailures:
    """``fetch_all_reviews`` wraps the ``cursor_cb(cursor)`` call
    in a bare ``except Exception: pass``. If ``resume_set`` (the
    default cursor callback from ``api_workflow``) raises — disk
    full, file locked, perms denied — the fetch keeps running,
    the user clicks Stop or the process dies, and on next launch
    there is NO cursor to resume from. The user silently
    re-fetches every page from the start.

    Fix: catch ``OSError`` (the disk-class exception) and log a
    warning so the user can spot a missing resume state.
    """

    def test_cursor_cb_failure_logs_warning(self) -> None:
        from steam_review_tool.services.steam_api_service import SteamAPI

        records: list[logging.LogRecord] = []
        handler = _ListHandler(records)
        logger = logging.getLogger(
            "steam_review_tool.services.steam_api_service",
        )
        logger.addHandler(handler)
        old_level = logger.level
        logger.setLevel(logging.DEBUG)
        try:
            api = SteamAPI()
            # Two pages. After page 2, the new_cursor matches
            # the previous cursor, so the loop terminates.
            page1 = _make_page(
                reviews=[{"recommendationid": "r1",
                          "author": {"steamid": "1"},
                          "voted_up": True}],
                cursor="c2",
            )
            page2 = _make_page(
                reviews=[{"recommendationid": "r2",
                          "author": {"steamid": "2"},
                          "voted_up": True}],
                cursor="c2",  # same as previous → loop exits
            )
            # The cursor_cb raises OSError on every call (simulating
            # a disk-full situation).
            failing_cb = MagicMock(
                side_effect=OSError("No space left on device"),
            )

            with patch.object(
                api.session, "get",
                side_effect=[page1, page2],
            ):
                reviews = api.fetch_all_reviews(
                    app_id=12345,
                    cursor_cb=failing_cb,
                )
            # The fetch itself still completed — we just couldn't
            # save the resume cursors.
            assert len(reviews) == 2
            assert failing_cb.call_count == 1  # called once
            # The user-visible warning was logged.
            assert any(
                "resume-cursor save failed" in r.getMessage()
                and "No space left" in r.getMessage()
                for r in records
            ), (
                f"expected a warning about the resume-cursor save "
                f"failure, got: "
                f"{[r.getMessage() for r in records]}"
            )
        finally:
            logger.removeHandler(handler)
            logger.setLevel(old_level)

    def test_cursor_cb_success_does_not_log_warning(self) -> None:
        from steam_review_tool.services.steam_api_service import SteamAPI

        records: list[logging.LogRecord] = []
        handler = _ListHandler(records)
        logger = logging.getLogger(
            "steam_review_tool.services.steam_api_service",
        )
        logger.addHandler(handler)
        try:
            api = SteamAPI()
            # Two pages: page 1 advances the cursor, page 2 has
            # the same cursor as page 1 (loop exits) — the
            # cursor_cb fires once on the page-1 → page-2
            # transition.
            page1 = _make_page(
                reviews=[{"recommendationid": "r1",
                          "author": {"steamid": "1"},
                          "voted_up": True}],
                cursor="c2",
            )
            page2 = _make_page(
                reviews=[{"recommendationid": "r2",
                          "author": {"steamid": "2"},
                          "voted_up": True}],
                cursor="c2",  # same as page 1 → loop exits
            )
            ok_cb = MagicMock()  # no exception

            with patch.object(api.session, "get",
                              side_effect=[page1, page2]):
                api.fetch_all_reviews(
                    app_id=12345, cursor_cb=ok_cb,
                )
            assert ok_cb.call_count == 1
            warnings = [
                r for r in records
                if "resume-cursor" in r.getMessage()
            ]
            assert not warnings, (
                f"successful cursor save should not log a warning, "
                f"got: {[r.getMessage() for r in warnings]}"
            )
        finally:
            logger.removeHandler(handler)


def _make_page(
    *, reviews: list[dict], cursor: str,
) -> "requests.Response":
    """Build a minimal ``requests.Response``-like object that
    the ``fetch_all_reviews`` inner code can consume."""
    class _R:
        status_code = 200
        text = ""
        def raise_for_status(self) -> None:
            pass
        def json(self) -> dict:
            return {
                "success": 1,
                "reviews": reviews,
                "cursor": cursor,
                "query_summary": {"total_reviews": len(reviews)},
            }
    return _R()


# ---------------------------------------------------------------------------
# BUG-R13-5: file_content_hash reads entire file into memory
# ---------------------------------------------------------------------------
class TestFileContentHashBlockStreamed:
    """``file_content_hash`` used ``f.read()`` which loaded the
    entire file into memory. For a 10 MB ``.md`` export this is
    fine, but the function is in ``utils.file_hash`` and a user
    dragging a large binary blob to their Obsidian vault would
    OOM the process.

    Fix: block-stream the file with a 1 MiB read chunk.
    """

    def test_small_file_hash_matches_naive(self) -> None:
        """The block-streamed hash must produce the same SHA-1 as
        the naive ``f.read()`` for small files."""
        from steam_review_tool.utils.file_hash import file_content_hash

        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"hello world\n" * 100)
            path = Path(f.name)
        try:
            out = file_content_hash(path)
            expected = hashlib.sha1(
                b"hello world\n" * 100,
            ).hexdigest()
            assert out == expected
        finally:
            path.unlink()

    def test_empty_file(self) -> None:
        from steam_review_tool.utils.file_hash import file_content_hash

        with tempfile.NamedTemporaryFile(delete=False) as f:
            path = Path(f.name)
        try:
            assert file_content_hash(path) == (
                hashlib.sha1(b"").hexdigest()
            )
        finally:
            path.unlink()

    def test_large_file_hash_matches_naive(self) -> None:
        """For a file larger than the 1 MiB chunk, the
        block-streamed hash must still match the naive hash."""
        from steam_review_tool.utils.file_hash import file_content_hash

        # 3 MiB of random-ish bytes (deterministic so the test
        # is reproducible) — bigger than the 1 MiB chunk.
        data = bytes((i * 7919) & 0xFF for i in range(3 * 1024 * 1024))
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(data)
            path = Path(f.name)
        try:
            out = file_content_hash(path)
            expected = hashlib.sha1(data).hexdigest()
            assert out == expected
        finally:
            path.unlink()

    def test_missing_file_returns_empty(self) -> None:
        from steam_review_tool.utils.file_hash import file_content_hash

        # The previous OSError-swallow contract is preserved —
        # a missing file returns ``""`` so the caller can skip
        # the copy without raising.
        assert file_content_hash(
            Path("/nonexistent/does-not-exist.md"),
        ) == ""


# ---------------------------------------------------------------------------
# BUG-R13-6: _guess_safe_name non-deterministic iteration order
# ---------------------------------------------------------------------------
class TestGuessSafeNameDeterministic:
    """``DumpRepository._guess_safe_name`` returned the FIRST
    match from ``os.scandir`` for the ``<app_id>_`` prefix.
    ``os.scandir`` order is OS-dependent and can vary between
    runs, so a user with two stale folders (e.g. a game that
    was renamed and the old folder was never cleaned up) could
    load the wrong ``seen_ids.json`` and silently re-dump every
    review.

    Fix: walk the matching folders, keep the one with the
    highest mtime, return its safe_name. The most recently
    modified folder is almost always the one the user is
    currently working with.
    """

    def test_returns_only_matching_folder(self) -> None:
        from steam_review_tool.services.dump_repository import (
            DumpRepository,
        )

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "12345_Foo").mkdir()
            (root / "99999_Other").mkdir()
            repo = DumpRepository(root)
            assert repo._guess_safe_name(12345) == "Foo"
            assert repo._guess_safe_name(99999) == "Other"
            # No folder for this app_id — falls back to str(app_id).
            assert repo._guess_safe_name(42424) == "42424"

    def test_picks_most_recently_modified_when_multiple_match(
        self,
    ) -> None:
        from steam_review_tool.services.dump_repository import (
            DumpRepository,
        )

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            older = root / "12345_Original_Name"
            older.mkdir()
            (older / "seen_ids.json").write_text(
                '{"seen_ids": ["a"]}', encoding="utf-8",
            )
            # Make the "older" folder 1 hour older so the
            # mtime comparison is unambiguous.
            older_time = time.time() - 3600
            import os
            os.utime(older, (older_time, older_time))

            newer = root / "12345_Renamed_Game"
            newer.mkdir()
            (newer / "seen_ids.json").write_text(
                '{"seen_ids": ["b"]}', encoding="utf-8",
            )
            # Newer folder gets the current time.
            now = time.time()
            os.utime(newer, (now, now))

            repo = DumpRepository(root)
            # The most recently modified folder must win —
            # in this case ``Renamed_Game``.
            assert repo._guess_safe_name(12345) == "Renamed_Game"

    def test_unreadable_folder_is_skipped(self) -> None:
        """A folder that raises OSError on ``stat`` must NOT
        poison the "best" comparison with a default mtime of
        0 (which would always win against real folders)."""
        from steam_review_tool.services.dump_repository import (
            DumpRepository,
        )

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            # Create one real folder, then patch ``os.scandir``
            # to also return a fake unreadable entry alongside
            # the real one — the function must skip the fake
            # one and pick the real one.
            good = root / "12345_Good"
            good.mkdir()
            now = time.time()
            import os
            os.utime(good, (now, now))

            good_entry = MagicMock()
            good_entry.name = "12345_Good"
            good_entry.is_dir.return_value = True
            good_entry.stat.return_value = MagicMock(
                st_mtime=now,
            )

            fake_entry = MagicMock()
            fake_entry.name = "12345_BadEntry"
            fake_entry.is_dir.return_value = True
            fake_entry.stat.side_effect = OSError("permission denied")

            class _FakeScandir:
                def __init__(self, _path) -> None:
                    pass
                def __enter__(self):
                    return iter([fake_entry, good_entry])
                def __exit__(self, *a) -> None:
                    pass

            repo = DumpRepository(root)
            with patch("os.scandir", _FakeScandir):
                # The fake entry raises on stat; the real entry
                # is found and returned. Without the OSError
                # skip, the fake entry would still register
                # ``best_mtime = 0`` (the default), which would
                # NOT win against the real entry — but the
                # *intent* of the test is that the function
                # tolerates the OSError and doesn't crash.
                assert (
                    repo._guess_safe_name(12345) == "Good"
                )

    def test_falls_back_when_no_match(self) -> None:
        from steam_review_tool.services.dump_repository import (
            DumpRepository,
        )

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "12345_Foo").mkdir()
            (root / "99999_Other").mkdir()
            repo = DumpRepository(root)
            assert repo._guess_safe_name(42424) == "42424"

    def test_nonexistent_root_returns_str_id(self) -> None:
        from steam_review_tool.services.dump_repository import (
            DumpRepository,
        )

        repo = DumpRepository(Path("/nonexistent/root/12345"))
        assert repo._guess_safe_name(12345) == "12345"
