"""Round-27 bug-hunt regression tests.

Real bugs found in a twenty-seventh systematic pass. Rounds
1-26 (9388ab1, 9ea69de, ed231bc, 80f9431, f913ae8,
e0514c0, 0e4f031, ba4255e, 49aa77a, 831219e, 04f47f6,
dfd6ff7, 6265d12, 561fc45, b795fbd, 95ea74e, 40d195a,
25c305a, 9e5b263, dc1d9d7, 22506de, 6891d1f, 448e2c3,
7773048, 16f1ad6, 26e8719) found 153 bugs across the
project. Round 27 found 3 more — this round targets
the same anti-pattern class as R17-2 / R20-2:
**dead public methods in the controllers/ layer**.

The recurring lesson (compounding R8 + R17-2 + R19-2 +
R20-1 + R20-2): "ANY public method that has zero
non-test callers is dead code". R8 audited bus
events (publish-without-subscriber), R17-2 audited
controller methods (defined-but-never-called),
R19-2 audited bus events again, R20-1 / R20-2 audited
controller methods + bus events.

R27 found 2 dead public methods on
:class:`DumpFolderController` + 1 dead import:

R27-1  controllers/dump_folder_controller.py:134-136
      :meth:`DumpFolderController.open_game_folder`
      was defined but never called from any UI /
      controller / test. The "open game folder"
      feature is documented in
      :mod:`ui.popup_help` ("Per-game folder:
      `<main>/<app_id>_<game_name>/`") but the
      wiring was never finished — no UI button
      ever calls this method. R27 removes it.

R27-2  controllers/dump_folder_controller.py:140-143
      :meth:`DumpFolderController.sync_to_obsidian`
      was defined but never called. The actual
      Obsidian sync happens via the export flow's
      ``run_export(..., obsidian_vault=...)``
      parameter (see
      :mod:`exporters.export_orchestrator`), which
      passes the vault through to
      :func:`exporters.obsidian_copier.copy_to_obsidian_vault`
      directly. The wrapper method on
      :class:`DumpFolderController` was a leftover
      from an earlier design where the controller
      was the single chokepoint. R27 removes it.

R27-3  controllers/dump_folder_controller.py:18
      The
      ``from ..exporters.obsidian_copier import copy_to_obsidian_vault``
      import became dead after R27-2 removed
      the only call site. R27 removes it (the
      function is still used by
      :mod:`exporters.export_orchestrator`).

The R27 round also introduces a project-wide
static-check guard
(``TestNoDeadPublicMethodInControllers``) that walks
every public method in ``controllers/*.py`` and
asserts that it has at least one non-test caller
OR is a known callback-like method (the audit
accepts callback wiring like
``self.on_X = self.method_name`` or
``callback=self.method_name`` as a valid form
of "caller").

The audit handles two false-positive patterns:

  1. **Callback-like methods** (``worker``,
     ``on_done``, ``progress_cb``, ``cursor_cb``,
     ``refresh_one``, ``remove_all``) — wired
     via kwargs (``on_done=self.on_done``) or
     passed as values (``self.worker``). These
     are excluded by name pattern (matching
     ``^on_|^(worker|on_done|progress_cb|_
     cursor_cb|refresh_one|remove_all)$``).
     This is the same exclusion R8 / R20-1 used
     for "indirect subscriber chain" detection.

  2. **Method references via attribute access**
     (``self.dump_ctrl.open_dump_folder``) —
     the audit matches the bare method name
     (e.g. ``open_dump_folder``) anywhere in the
     codebase, which catches both
     ``.open_dump_folder()`` calls and
     ``self.open_dump_folder = ...`` assignments.
"""
import ast
import re
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _strip_comments_and_docstrings(src: str) -> str:
    """Strip pure docstring + comment lines so a source-shape
    probe doesn't false-positive on explaining comments.
    """
    src = re.sub(r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'', "", src)
    out_lines: list[str] = []
    for line in src.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        out_lines.append(line)
    return "\n".join(out_lines)


# ---------------------------------------------------------------------------
# BUG-R27-1: open_game_folder dead method removed
# ---------------------------------------------------------------------------
class TestOpenGameFolderRemoved:
    """R27-1: ``DumpFolderController.open_game_folder``
    was defined but never called. R27 removes it.
    """

    def _src(self) -> str:
        from steam_review_tool.controllers import (
            dump_folder_controller,
        )
        return _strip_comments_and_docstrings(
            ast.unparse(ast.parse(_read(
                Path(dump_folder_controller.__file__),
            ))),
        )

    def test_open_game_folder_method_gone(self) -> None:
        """R27-1: the ``open_game_folder`` method
        must NOT be defined on
        :class:`DumpFolderController`."""
        from steam_review_tool.controllers.dump_folder_controller import (
            DumpFolderController,
        )
        assert not hasattr(DumpFolderController, "open_game_folder"), (
            "DumpFolderController.open_game_folder is "
            "still defined (R27-1 anti-pattern: dead "
            "public method). The method has zero "
            "non-test callers in the codebase."
        )

    def test_open_game_folder_source_gone(self) -> None:
        """R27-1 source-shape: ``def open_game_folder``
        must not appear in the source."""
        from steam_review_tool.controllers import (
            dump_folder_controller,
        )
        src = _strip_comments_and_docstrings(
            ast.unparse(ast.parse(_read(
                Path(dump_folder_controller.__file__),
            ))),
        )
        assert "def open_game_folder" not in src, (
            "dump_folder_controller.py still has "
            "`def open_game_folder` (R27-1 anti-pattern). "
            "The method has zero non-test callers."
        )


# ---------------------------------------------------------------------------
# BUG-R27-2: sync_to_obsidian dead method removed
# ---------------------------------------------------------------------------
class TestSyncToObsidianRemoved:
    """R27-2: ``DumpFolderController.sync_to_obsidian``
    was defined but never called. The actual
    Obsidian sync happens via
    :func:`exporters.export_orchestrator.run_export`
    ``obsidian_vault=...`` parameter. R27 removes
    the dead wrapper.
    """

    def test_sync_to_obsidian_method_gone(self) -> None:
        """R27-2: the ``sync_to_obsidian`` method
        must NOT be defined on
        :class:`DumpFolderController`."""
        from steam_review_tool.controllers.dump_folder_controller import (
            DumpFolderController,
        )
        assert not hasattr(
            DumpFolderController, "sync_to_obsidian",
        ), (
            "DumpFolderController.sync_to_obsidian is "
            "still defined (R27-2 anti-pattern: dead "
            "public method). The wrapper has zero "
            "non-test callers; the actual sync happens "
            "via run_export(..., obsidian_vault=...)."
        )

    def test_sync_to_obsidian_source_gone(self) -> None:
        """R27-2 source-shape: ``def sync_to_obsidian``
        must not appear in the source."""
        from steam_review_tool.controllers import (
            dump_folder_controller,
        )
        src = _strip_comments_and_docstrings(
            ast.unparse(ast.parse(_read(
                Path(dump_folder_controller.__file__),
            ))),
        )
        assert "def sync_to_obsidian" not in src, (
            "dump_folder_controller.py still has "
            "`def sync_to_obsidian` (R27-2 anti-pattern). "
            "The method has zero non-test callers."
        )


# ---------------------------------------------------------------------------
# BUG-R27-3: copy_to_obsidian_vault import removed
# ---------------------------------------------------------------------------
class TestCopyToObsidianVaultImportRemoved:
    """R27-3: the
    ``from ..exporters.obsidian_copier import copy_to_obsidian_vault``
    import became dead after R27-2 removed the only
    call site. R27 removes the import. The function
    is still used by
    :mod:`exporters.export_orchestrator`.
    """

    def test_obsidian_copier_import_gone(self) -> None:
        """R27-3: the import must be gone from
        ``dump_folder_controller.py`` (it's still
        imported by ``export_orchestrator.py``)."""
        from steam_review_tool.controllers import (
            dump_folder_controller,
        )
        # Strip docstrings + comments so the
        # import mention in the module docstring
        # doesn't false-positive.
        src = _strip_comments_and_docstrings(
            _read(Path(dump_folder_controller.__file__)),
        )
        assert (
            "from ..exporters.obsidian_copier import"
        ) not in src, (
            "dump_folder_controller.py still imports "
            "from `exporters.obsidian_copier` (R27-3). "
            "The import became dead after R27-2 removed "
            "the only call site."
        )
        # Verify the function is still imported
        # elsewhere (in export_orchestrator).
        from steam_review_tool.exporters import (
            export_orchestrator,
        )
        orch_src = _strip_comments_and_docstrings(
            _read(Path(export_orchestrator.__file__)),
        )
        assert "copy_to_obsidian_vault" in orch_src, (
            "export_orchestrator must still import + use "
            "copy_to_obsidian_vault (the R27-3 removal "
            "must not break the actual sync feature)."
        )


# ---------------------------------------------------------------------------
# R27 project-wide dead-method audit
# ---------------------------------------------------------------------------
class TestNoDeadPublicMethodInControllers:
    """R27 global sweep: walk every public method
    in ``controllers/*.py`` and assert that it
    has at least one non-test caller (a method
    reference or a call site in production
    code) OR is a known callback-like method
    (wired via ``self.on_X = self.method`` or
    ``callback=self.method``).

    The audit handles two false-positive patterns
    (see R27 module docstring):
      1. Callback-like methods — excluded by name
         pattern (``^on_|^(worker|on_done|_
         progress_cb|cursor_cb|refresh_one|_
         remove_all)$``).
      2. Method references via attribute access —
         the bare method name is searched
         anywhere in the codebase.
    """

    # Callback-like method names that are wired
    # via kwargs, not by direct call. These are
    # excluded from the dead-method check.
    _CALLBACK_NAMES = {
        "worker", "on_done", "progress_cb",
        "cursor_cb", "refresh_one", "remove_all",
        # Also exclude methods starting with "on_"
        # (handled by the prefix check below).
    }

    def _is_callback_name(self, name: str) -> bool:
        """Return True if the method name is a
        callback that wouldn't be called by name."""
        if name in self._CALLBACK_NAMES:
            return True
        if name.startswith("on_"):
            return True
        return False

    def _get_public_methods(
        self, root: Path,
    ) -> list[tuple[str, str | None, str]]:
        """Return list of ``(file, class, method)``
        for every public method in
        ``controllers/*.py``."""
        out: list[tuple[str, str | None, str]] = []
        for path in sorted(
            (root / "steam_review_tool" / "controllers").glob("*.py"),
        ):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    cls_name = node.name
                    for item in node.body:
                        if (
                            isinstance(item, ast.FunctionDef)
                            and not item.name.startswith("_")
                            and not self._is_callback_name(item.name)
                        ):
                            out.append(
                                (path.name, cls_name, item.name),
                            )
                elif (
                    isinstance(node, ast.FunctionDef)
                    and not node.name.startswith("_")
                    and not self._is_callback_name(node.name)
                ):
                    out.append((path.name, None, node.name))
        return out

    def test_no_dead_public_method_in_controllers(self) -> None:
        """Project-wide anti-pattern guard.

        Walks every public method in
        ``controllers/*.py`` and asserts each has
        at least one non-test caller. A "caller"
        is a reference to the method name in any
        ``steam_review_tool/`` source file OTHER
        THAN the file where the method is defined
        (tests are excluded from the production
        caller set — a test calling a dead method
        doesn't count as a real consumer).
        """
        from steam_review_tool import __file__ as pkg_init
        repo = Path(pkg_init).parent.parent
        methods = self._get_public_methods(repo)
        # Build a map of (file, method_name) -> source
        method_sources: dict[tuple[str, str], str] = {}
        for f, cls, m in methods:
            path = repo / "steam_review_tool" / "controllers" / f
            method_sources[(f, m)] = path.read_text(encoding="utf-8")
        # Walk all production source files (controllers + ui + services
        # + exporters + utils + core) and look for references.
        production_sources: dict[Path, str] = {}
        for sub in (
            "controllers", "ui", "services", "exporters",
            "utils", "core", "interfaces",
        ):
            d = repo / "steam_review_tool" / sub
            if not d.is_dir():
                continue
            for p in d.rglob("*.py"):
                if "__pycache__" in p.parts:
                    continue
                production_sources[p] = p.read_text(encoding="utf-8")
        # For each method, look for the method name in production
        # sources OUTSIDE the method's own file.
        offenders: list[str] = []
        for f, cls, m in methods:
            self_path = repo / "steam_review_tool" / "controllers" / f
            self_src = method_sources[(f, m)]
            found_caller = False
            for p, src in production_sources.items():
                if p == self_path:
                    continue
                # Match the method name as a call or reference.
                # Use word boundaries to avoid matching substrings.
                if re.search(rf"\b{re.escape(m)}\b", src):
                    found_caller = True
                    break
            if not found_caller:
                offenders.append(
                    f"{f}:{cls or '<module>'}.{m} — "
                    f"public method with no non-test caller "
                    f"anywhere in steam_review_tool/. "
                    f"Dead code; remove it."
                )
        assert not offenders, (
            "R27 anti-pattern: public method on a "
            "controller class with no non-test caller. "
            "The method is dead code and should be removed. "
            "Offenders:\n\n" + "\n\n".join(offenders)
        )
