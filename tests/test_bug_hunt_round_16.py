"""Round-16 bug-hunt regression tests.

Real bugs found in a sixteenth systematic pass. Rounds 1-15
(9388ab1, 9ea69de, ed231bc, 80f9431, f913ae8, e0514c0,
0e4f031, ba4255e, 49aa77a, 831219e, 04f47f6, dfd6ff7,
6265d12, 561fc45, b795fbd) covered the int / str / or-default
residue, the chained-dict crash, the double-subscribe
pattern, the over-broad "find latest .md" walk, the missing
worker-shutdown wait, the broken batch-dump feature, the
missed R5 sites, the Tk widget-state + watch-thread-safety
issues, the destructive "Reset" button before commit, the
shared ``self._worker`` field, the backup-filename
collision, the sister-helper inconsistency, the
sync-on-main-thread network call, the
popup-window-destroy race, the consolidation of the
cross-platform "open path" ladder, the silent
export-failure hiding, the popup-search stale results, the
slow popup-open aggregation, the broad ``except Exception``
swallowing specific actionable errors, the file-content-hash
OOM, the non-deterministic safe-name walk, the markdown
table cell escaping, and the settings-persistence drift
bugs.

This round targets a new bug class: **duplicate code that
drifted — non-atomic public exporters + dump-root not
persisted**. Three real bugs found:

1. ``csv_exporter.reviews_to_csv`` used ``open(..., "w",
   ...)`` which is non-atomic — a crash mid-write would
   leave a half-written ``.csv`` file behind. The
   orchestrator worked around this with a private
   ``_write_csv_atomic`` duplicate. Fix: move the
   atomic pattern into the public function and have the
   orchestrator delegate to it.

2. ``json_exporter.reviews_to_json`` had the same
   non-atomic ``dest_path.write_text(...)`` problem, with
   a private ``_write_json_atomic`` workaround in the
   orchestrator. Same fix.

3. ``DumpFolderController.set_dump_root`` only updated
   the in-memory ``self.dump_root`` — the on-disk
   ``settings.json`` was NOT updated, so a user who
   picked a new dump folder via the "Set…" button
   (without opening the Settings dialog) would find
   their choice reverted on next app launch. Fix:
   persist the new dump_root to ``settings.json`` after
   updating the in-memory state.
"""
from __future__ import annotations

import inspect
import json
import re
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helper: strip pure comment / docstring lines from a source string before
# substring-regression checks. The R12 / R13 cross-project lesson was
# re-confirmed in R16: a docstring that DOCUMENTS the anti-pattern
# (``open(..., "w", ...)`` or ``dest_path.write_text(...)``) will be matched
# by a naive substring check. Strip them first.
# ---------------------------------------------------------------------------
def _strip_comments_and_docstrings(src: str) -> str:
    """Remove pure-comment lines AND all triple-quoted string regions
    (docstrings) from a source string.

    The R16 fix included docstrings that document the historical
    anti-pattern (e.g. ``implementation wrote via``\\ ``open(..., "w", ...)``
    in the csv_exporter docstring). A naive substring check would
    match the docstring's prose, not the actual code. Stripping all
    triple-quoted regions is the right move: any substring check
    that fires on a docstring explanation is by definition not
    checking the code.
    """
    # Drop all triple-quoted string regions (docstrings + multi-line
    # string literals). Use a non-greedy regex that handles both
    # ``"""`` and ``'''`` delimiters.
    src_no_docstrings = re.sub(
        r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'',
        "",
        src,
    )
    out_lines: list[str] = []
    for line in src_no_docstrings.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        out_lines.append(line)
    return "\n".join(out_lines)


# ---------------------------------------------------------------------------
# BUG-R16-1: csv_exporter.reviews_to_csv is non-atomic
# ---------------------------------------------------------------------------
class TestCsvExporterAtomic:
    """``reviews_to_csv`` used ``open(..., "w", ...)`` which
    is non-atomic on a crash — a partial ``.csv`` would
    survive. The orchestrator worked around this with a
    private ``_write_csv_atomic`` duplicate. R16 fix: move
    the atomic pattern into the public function.

    The R16 fix also uses ``lineterminator="\\n"`` in the
    ``csv.writer`` so the on-disk line terminator is
    consistent across platforms (the default ``\\r\\n``
    was being translated to ``\\r\\r\\n`` on Windows by
    ``atomic_write_text``'s text-mode write, leaving a
    doubled line terminator that the default
    ``csv.reader`` interpreted as blank rows between data
    rows).
    """

    def test_reviews_to_csv_uses_atomic_write(self) -> None:
        """The public ``reviews_to_csv`` must route through
        ``atomic_write_text`` (not ``open(..., "w", ...)``)
        so a crash mid-write cannot leave a partial
        ``.csv`` file behind."""
        from pathlib import Path
        from steam_review_tool.exporters.csv_exporter import (
            reviews_to_csv,
        )
        import inspect
        src = inspect.getsource(reviews_to_csv)
        code = _strip_comments_and_docstrings(src)
        # Ban the unsafe open-with-write-mode call specifically
        # (we still want to allow read-mode opens if any are
        # added later). The pre-fix code did
        # ``open(dest_path, "w", encoding="utf-8")``.
        assert re.search(r"open\s*\(\s*[^)]*['\"][wa]['\"]", code) is None, (
            "reviews_to_csv must NOT use "
            "open(..., 'w', ...) — it's "
            "non-atomic. Use atomic_write_text instead."
        )
        assert "atomic_write_text" in code, (
            "reviews_to_csv must use atomic_write_text so a "
            "crash mid-write cannot leave a partial .csv "
            "file behind."
        )

    def test_csv_round_trip_via_csv_reader(self) -> None:
        """The exported CSV must be parseable by the
        default ``csv.reader`` with the expected row
        count (no doubled line terminators that would
        produce blank rows between data rows)."""
        from steam_review_tool.exporters.csv_exporter import (
            reviews_to_csv, COLUMNS,
        )
        import csv

        with tempfile.TemporaryDirectory() as td:
            dest = Path(td) / "reviews.csv"
            reviews = [
                {"recommendationid": "r1", "language": "english",
                 "voted_up": True, "author": {}},
                {"recommendationid": "r2", "language": "german",
                 "voted_up": False, "author": {}},
                {"recommendationid": "r3", "language": "french",
                 "voted_up": True, "author": {}},
            ]
            n = reviews_to_csv(reviews, dest)
            assert n == 3
            with open(dest, encoding="utf-8") as f:
                rows = list(csv.reader(f))
            # header + 3 data rows = 4 (no blank rows from
            # doubled line terminators).
            assert len(rows) == 4, (
                f"expected 4 rows (header + 3 data), got "
                f"{len(rows)}: {rows!r}"
            )
            assert rows[0] == COLUMNS
            assert rows[1][0] == "r1"
            assert rows[2][0] == "r2"
            assert rows[3][0] == "r3"

    def test_csv_atomic_write_does_not_leak_temp_files(self) -> None:
        """The atomic write pattern writes to a temp file
        then renames. If the rename fails, the temp file
        must be cleaned up. Pin the contract: the only
        file in the dir is the final ``reviews.csv`` (no
        ``.tmp`` leftovers)."""
        from steam_review_tool.exporters.csv_exporter import (
            reviews_to_csv,
        )
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td) / "reviews.csv"
            reviews_to_csv(
                [{"recommendationid": "r1", "language": "english",
                  "voted_up": True, "author": {}}],
                dest,
            )
            files = list(Path(td).iterdir())
            assert files == [dest], (
                f"expected only {dest} in {td}, got {files}"
            )


# ---------------------------------------------------------------------------
# BUG-R16-2: json_exporter.reviews_to_json is non-atomic
# ---------------------------------------------------------------------------
class TestJsonExporterAtomic:
    """``reviews_to_json`` used ``dest_path.write_text(...)``
    which is non-atomic. Same fix as R16-1.
    """

    def test_reviews_to_json_uses_atomic_write(self) -> None:
        from steam_review_tool.exporters.json_exporter import (
            reviews_to_json,
        )
        import inspect
        src = inspect.getsource(reviews_to_json)
        code = _strip_comments_and_docstrings(src)
        # The unsafe patterns are the ``Path.write_text(...)``
        # call and a bare ``open(..., "w", ...)`` call. The
        # safe ``atomic_write_text`` is OK (and a substring
        # match) — we don't want to ban the safe helper.
        assert ".write_text(" not in code, (
            "reviews_to_json must NOT use "
            "dest_path.write_text(...) — it's "
            "non-atomic. Use atomic_write_text instead."
        )
        assert re.search(r"open\s*\(\s*['\"][wa]", code) is None, (
            "reviews_to_json must NOT use "
            "open(..., 'w', ...) — it's "
            "non-atomic. Use atomic_write_text instead."
        )
        assert "atomic_write_text" in code

    def test_json_round_trip(self) -> None:
        from steam_review_tool.exporters.json_exporter import (
            reviews_to_json,
        )
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td) / "reviews.json"
            reviews = [
                {"recommendationid": "r1", "language": "english",
                 "voted_up": True, "author": {"steamid": "123"}},
            ]
            n = reviews_to_json(reviews, dest)
            assert n == 1
            loaded = json.loads(dest.read_text(encoding="utf-8"))
            assert loaded == reviews

    def test_json_atomic_write_does_not_leak_temp_files(self) -> None:
        from steam_review_tool.exporters.json_exporter import (
            reviews_to_json,
        )
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td) / "reviews.json"
            reviews_to_json(
                [{"recommendationid": "r1"}], dest,
            )
            files = list(Path(td).iterdir())
            assert files == [dest]


# ---------------------------------------------------------------------------
# BUG-R16-3: dump_folder_controller.set_dump_root doesn't persist
# ---------------------------------------------------------------------------
class TestSetDumpRootPersists:
    """``DumpFolderController.set_dump_root`` previously
    only updated the in-memory ``self.dump_root`` and
    published a bus event. The on-disk ``settings.json``
    was NOT updated, so a user who picked a new dump
    folder via the "Set…" button (without opening the
    Settings dialog) would find their choice reverted
    on next app launch.

    Fix: load the current settings, write the new
    ``dump_root`` to the in-memory copy, then save back
    to ``settings.json``.
    """

    def test_set_dump_root_persists_to_settings(self) -> None:
        """The on-disk ``settings.json`` must reflect the
        new ``dump_root`` after ``set_dump_root`` is
        called — the user's choice must survive an app
        restart."""
        from steam_review_tool.services import settings_store
        from steam_review_tool.controllers.dump_folder_controller import (
            DumpFolderController,
        )

        with tempfile.TemporaryDirectory() as td:
            fake_file = Path(td) / "settings.json"
            with patch.object(
                settings_store, "SETTINGS_FILE", fake_file,
            ):
                # Use Windows-friendly absolute paths in
                # the test (on Windows, ``Path("/orig/dump")``
                # is normalised to ``"\\orig\\dump"``).
                orig_dir = Path(td) / "orig"
                new_dir = Path(td) / "new"
                orig_dir.mkdir()
                new_dir.mkdir()
                # Initial state: user has a default
                # dump_root.
                settings_store.save({
                    "dump_root": str(orig_dir),
                    "obsidian_vault": "",
                    "apify_token": "",
                    "keyword_list": [],
                    "ai_prompt_template": "",
                })
                # User picks a new dump folder via the
                # "Set…" button.
                ctrl = DumpFolderController(
                    dump_root=orig_dir,
                )
                ctrl.set_dump_root(new_dir)
                # The on-disk settings must now reflect
                # the new dump_root.
                loaded = settings_store.load()
                assert loaded["dump_root"] == str(new_dir), (
                    f"on-disk settings must reflect the new "
                    f"dump_root, got {loaded['dump_root']!r}"
                )

    def test_set_dump_root_preserves_other_settings(self) -> None:
        """Persisting the new dump_root must not erase the
        other settings (same R15-1 contract — the save
        function overwrites the entire file)."""
        from steam_review_tool.services import settings_store
        from steam_review_tool.controllers.dump_folder_controller import (
            DumpFolderController,
        )

        with tempfile.TemporaryDirectory() as td:
            fake_file = Path(td) / "settings.json"
            with patch.object(
                settings_store, "SETTINGS_FILE", fake_file,
            ):
                # Use Windows-friendly absolute paths in
                # the test.
                orig_dir = Path(td) / "orig"
                new_dir = Path(td) / "new"
                orig_dir.mkdir()
                new_dir.mkdir()
                vault_dir = Path(td) / "vault"
                vault_dir.mkdir()
                settings_store.save({
                    "dump_root": str(orig_dir),
                    "obsidian_vault": str(vault_dir),
                    "apify_token": "orig_token",
                    "keyword_list": ["a", "b"],
                    "ai_prompt_template": "orig prompt",
                    "also_csv": True,
                })
                ctrl = DumpFolderController(
                    dump_root=orig_dir,
                )
                ctrl.set_dump_root(new_dir)
                loaded = settings_store.load()
                # New dump_root was persisted.
                assert loaded["dump_root"] == str(new_dir)
                # Other settings were preserved.
                assert loaded["obsidian_vault"] == str(vault_dir)
                assert loaded["apify_token"] == "orig_token"
                assert loaded["keyword_list"] == ["a", "b"]
                assert loaded["ai_prompt_template"] == "orig prompt"
                assert loaded["also_csv"] is True

    def test_set_dump_root_no_op_when_no_settings_file(self) -> None:
        """On a first launch (no settings file), the
        ``set_dump_root`` call must not raise. The
        ``_load_settings`` call inside the R16-3 fix
        falls back to ``{}`` on ``OSError``."""
        from steam_review_tool.services import settings_store
        from steam_review_tool.controllers.dump_folder_controller import (
            DumpFolderController,
        )

        with tempfile.TemporaryDirectory() as td:
            fake_file = Path(td) / "no_such_file.json"
            with patch.object(
                settings_store, "SETTINGS_FILE", fake_file,
            ):
                # Use Windows-friendly absolute paths.
                orig_dir = Path(td) / "orig"
                new_dir = Path(td) / "new"
                orig_dir.mkdir()
                new_dir.mkdir()
                ctrl = DumpFolderController(
                    dump_root=orig_dir,
                )
                # Must not raise on a missing settings
                # file.
                ctrl.set_dump_root(new_dir)
                # The in-memory state is updated regardless.
                assert ctrl.dump_root == new_dir
                # The on-disk state is created with the
                # new dump_root and the other fields
                # default to DEFAULTS (via the
                # ``settings_store.load()`` merge).
                loaded = settings_store.load()
                assert loaded["dump_root"] == str(new_dir)


# ---------------------------------------------------------------------------
# BUG-R16-4: orchestrator's private _write_csv/json_atomic are duplicates
# ---------------------------------------------------------------------------
class TestOrchestratorDelegatesToPublicExporters:
    """The export orchestrator had private
    ``_write_csv_atomic`` and ``_write_json_atomic``
    functions that duplicated the public
    ``reviews_to_csv`` and ``reviews_to_json`` row-
    building logic. The R16-4 fix removes the duplication
    by having the orchestrator delegate to the public
    functions (which are themselves atomic in the R16-1
    + R16-2 fixes).
    """

    def test_orchestrator_delegates_to_reviews_to_csv(self) -> None:
        """The orchestrator's ``_write_csv_atomic`` must
        delegate to the public ``reviews_to_csv``
        instead of duplicating the row-building logic."""
        from steam_review_tool.exporters.export_orchestrator import (
            _write_csv_atomic, _write_json_atomic,
        )
        # The orchestrator's private function must
        # delegate to the public one (not duplicate it).
        body_csv = inspect.getsource(_write_csv_atomic)
        body_json = inspect.getsource(_write_json_atomic)
        body_csv_code = _strip_comments_and_docstrings(body_csv)
        assert "reviews_to_csv" in body_csv_code, (
            "_write_csv_atomic must delegate to "
            "reviews_to_csv instead of duplicating "
            "the row-building logic"
        )
        body_json_code = _strip_comments_and_docstrings(body_json)
        assert "reviews_to_json" in body_json_code, (
            "_write_json_atomic must delegate to "
            "reviews_to_json instead of duplicating "
            "the json.dumps"
        )
        # The private functions must not have a local
        # csv.writer or io.StringIO (which would mean
        # they're duplicating the rendering logic).
        assert "csv.writer" not in body_csv_code, (
            "_write_csv_atomic must NOT use csv.writer "
            "locally — it should delegate to reviews_to_csv"
        )
        assert "io.StringIO" not in body_csv_code, (
            "_write_csv_atomic must NOT use io.StringIO "
            "locally — it should delegate to reviews_to_csv"
        )
        # And no local json.dumps (same delegation
        # contract).
        assert "json.dumps" not in body_json_code, (
            "_write_json_atomic must NOT use json.dumps "
            "locally — it should delegate to reviews_to_json"
        )

    def test_orchestrator_delegates_to_reviews_to_json(self) -> None:
        """The orchestrator's ``_write_json_atomic`` must
        delegate to the public ``reviews_to_json``."""
        from steam_review_tool.exporters.export_orchestrator import (
            _write_json_atomic,
        )
        body = inspect.getsource(_write_json_atomic)
        body_code = _strip_comments_and_docstrings(body)
        assert "reviews_to_json" in body_code
        assert "json.dumps" not in body_code, (
            "_write_json_atomic must delegate to "
            "reviews_to_json instead of duplicating "
            "json.dumps"
        )

    def test_end_to_end_orchestrator_export_is_atomic(self) -> None:
        """The full ``run_export`` flow must produce a
        CSV / JSON file via the atomic path. Pin the
        end-to-end contract: the file is created
        atomically (no leftover temp files), and the
        content is parseable by the standard
        ``csv.reader`` / ``json.loads``."""
        from steam_review_tool.exporters.export_orchestrator import (
            run as run_export,
        )
        from steam_review_tool.models.export_context import (
            ExportContext,
        )
        import csv

        with tempfile.TemporaryDirectory() as td:
            dest = Path(td) / "reviews.md"
            csv_path = Path(td) / "reviews.csv"
            json_path = Path(td) / "reviews.json"
            ctx = ExportContext(
                app_id=12345,
                app_details={"name": "Test", "type": "game",
                             "developers": [], "publishers": [],
                             "release_date": {"date": "2024-01-01",
                                              "coming_soon": False},
                             "platforms": {}},
                reviews=[
                    {"recommendationid": "r1", "language": "english",
                     "voted_up": True, "author": {}},
                    {"recommendationid": "r2", "language": "german",
                     "voted_up": False, "author": {}},
                ],
                language_param="all",
                review_filter="all",
                review_type="all",
                day_range=None, min_date_ts=None,
            )
            result = run_export(
                ctx, dest, also_csv=True, also_json=True,
            )
            # CSV was created.
            assert result["csv"] == csv_path
            with open(csv_path, encoding="utf-8") as f:
                rows = list(csv.reader(f))
            # Header + 2 data rows = 3 (no blank rows from
            # doubled line terminators).
            assert len(rows) == 3, (
                f"expected 3 rows (header + 2 data), got "
                f"{len(rows)}: {rows!r}"
            )
            # JSON was created.
            assert result["json"] == json_path
            loaded = json.loads(json_path.read_text(encoding="utf-8"))
            assert len(loaded) == 2
            # No leftover temp files in the dir.
            assert sorted(p.name for p in Path(td).iterdir()) == [
                "reviews.csv", "reviews.json", "reviews.md",
            ]
