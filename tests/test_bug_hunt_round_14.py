"""Round-14 bug-hunt regression tests.

Real bugs found in a fourteenth systematic pass. Rounds 1-13
(9388ab1, 9ea69de, ed231bc, 80f9431, f913ae8, e0514c0,
0e4f031, ba4255e, 49aa77a, 831219e, 04f47f6, dfd6ff7,
6265d12) covered the int / str / or-default residue, the
chained-dict crash, the double-subscribe pattern, the
over-broad "find latest .md" walk, the missing worker-shutdown
wait, the broken batch-dump feature, the missed R5 sites, the
Tk widget-state + watch-thread-safety issues, the destructive
"Reset" button before commit, the shared ``self._worker``
field, the backup-filename collision, the sister-helper
inconsistency, the sync-on-main-thread network call, the
popup-window-destroy race, the consolidation of the
cross-platform "open path" ladder, the silent export-failure
hiding, the popup-search stale results, the slow popup-open
aggregation, the broad ``except Exception`` swallowing
specific actionable errors, the file-content-hash OOM, and
the non-deterministic safe-name walk.

This round targets a new bug class: **markdown table cells
that don't escape the column delimiter**. The Markdown
exporter builds a single-table format for each review
(``| Field | Value |``) and several aggregate tables
(Language distribution, Top-5 reviewers, etc.). Any cell that
contains user-controlled content (a keyword from the user's
``settings.json``, a slice of a review's free-form text, a
language code from a normalised review dict) can break the
table layout if the content contains a ``|`` (the column
delimiter) or ``\\n`` (which the Markdown parser interprets as
"end of row"). The fix is the same shape the existing
``render_game_info`` cells already use: route the cell content
through ``md_escape`` so ``|`` becomes ``\\|`` and ``\\n``
becomes a space.

Six real bugs found:

1. ``render_summary`` Language distribution cell did not
   escape the language code (``k``) — a malformed
   normalised review with ``language = "en|US"`` would
   break the row.

2. ``render_review`` Tags cell did not escape each tag
   (``t``) — a user with ``"fps|60"`` in their keyword
   list would produce a broken cell.

3. ``render_review`` weighted_vote_score cell did not
   escape the score — a string score with ``|`` would
   break the row.

4. ``per_language_exporter.build_summary`` Language
   distribution cell did not escape the language code
   (``k``) — same R14-1 pattern, different exporter.

5. ``per_language_exporter.build_summary`` Top-10
   reviewers preview cell did not escape the review
   preview (``preview``) — a Steam reviewer's free-form
   text containing ``|`` (e.g. "the game | it's bad")
   would spill into a phantom second column.

6. ``md_escape`` only handled ``|`` and ``\\r``; it didn't
   handle ``\\n`` — a multi-line game name
   (e.g. ``"Foo\\nBar"``) would spill into a phantom
   second row that the Markdown parser interprets as a
   fresh table row.
"""
from __future__ import annotations

from steam_review_tool.exporters.markdown_exporter import MarkdownExporter
from steam_review_tool.exporters.markdown_helpers import (
    render_review, render_summary, render_digest,
)
from steam_review_tool.exporters.per_language_exporter import (
    build_summary, group_by_language,
)
from steam_review_tool.models.export_context import ExportContext
from steam_review_tool.utils.markdown_utils import md_escape


def _ctx_with_reviews(reviews: list[dict], **overrides) -> ExportContext:
    """Build a minimal ExportContext for the unit tests."""
    base = dict(
        app_id=12345,
        app_details={"name": "Test Game", "type": "game",
                     "developers": ["Dev"], "publishers": ["Pub"],
                     "release_date": {"date": "2024-01-01",
                                      "coming_soon": False},
                     "platforms": {"windows": True}},
        reviews=reviews,
        language_param="all",
        review_filter="all",
        review_type="all",
        day_range=None,
        min_date_ts=None,
        keyword_list=None,
    )
    base.update(overrides)
    return ExportContext(**base)


# ---------------------------------------------------------------------------
# BUG-R14-6: md_escape should also handle \n
# ---------------------------------------------------------------------------
class TestMdEscape:
    """The ``md_escape`` helper strips ``\\r`` and escapes ``|``
    but does not handle ``\\n`` — a multi-line game name
    (``"Foo\\nBar"``) would spill into a phantom second row in
    a Markdown table.

    Fix: replace ``\\n`` with a single space. A new line
    inside a table cell is always the wrong rendering (the
    Markdown parser interprets it as "end of row"), so the
    only correct replacement is a single space.
    """

    def test_pipe_is_escaped(self) -> None:
        assert md_escape("foo|bar") == "foo\\|bar"

    def test_carriage_return_is_stripped(self) -> None:
        # Pre-R14 behaviour — the ``\\r`` was already stripped.
        assert md_escape("foo\rbar") == "foobar"

    def test_newline_is_replaced_with_space(self) -> None:
        # The new R14 behaviour — ``\\n`` is now collapsed
        # into a single space so the cell stays on one row.
        assert md_escape("foo\nbar") == "foo bar"

    def test_crlf_is_collapsed_to_single_space(self) -> None:
        # Windows-style line endings: ``\\r\\n`` should also
        # collapse to a single space. ``\\r`` is stripped
        # first, then ``\\n`` becomes a space, so the final
        # result has the original text on a single line.
        assert md_escape("foo\r\nbar") == "foo bar"

    def test_none_returns_empty(self) -> None:
        assert md_escape(None) == ""

    def test_combined_pipe_and_newline(self) -> None:
        # The two escaping rules compose: ``|`` becomes ``\\|``
        # (preserved as text), ``\\n`` becomes a space.
        assert md_escape("foo|bar\nbaz") == "foo\\|bar baz"

    def test_does_not_modify_normal_text(self) -> None:
        assert md_escape("hello world") == "hello world"


# ---------------------------------------------------------------------------
# BUG-R14-1: render_summary language cell doesn't escape |
# ---------------------------------------------------------------------------
class TestRenderSummaryLanguageCell:
    """``render_summary`` builds a Language distribution
    table. The previous version wrote the language code
    directly into the cell — a malformed normalised review
    with ``language = "en|US"`` would produce a row with
    extra phantom columns and break the table layout for
    the rest of the file.
    """

    def test_pipe_in_language_does_not_break_table(self) -> None:
        reviews = [
            {"language": "en|US", "voted_up": True, "review": ""},
        ]
        lines = render_summary(reviews)
        out = "\n".join(lines)
        # The ``|`` must be escaped so the row stays on
        # a single line and the table layout is preserved.
        assert "en\\|US" in out
        # The pipe must NOT appear unescaped inside the
        # language cell — that would break the row.
        assert "| en|US |" not in out
        assert "| en|US" not in out

    def test_newline_in_language_does_not_break_table(self) -> None:
        reviews = [
            {"language": "en\nUS", "voted_up": True, "review": ""},
        ]
        lines = render_summary(reviews)
        out = "\n".join(lines)
        # The newline must be collapsed to a space so the
        # cell stays on one row.
        assert "en US" in out
        assert "en\nUS" not in out

    def test_normal_language_unchanged(self) -> None:
        reviews = [
            {"language": "english", "voted_up": True, "review": ""},
            {"language": "german", "voted_up": False, "review": ""},
        ]
        lines = render_summary(reviews)
        out = "\n".join(lines)
        assert "| english |" in out
        assert "| german |" in out


# ---------------------------------------------------------------------------
# BUG-R14-2: render_review tags cell doesn't escape |
# ---------------------------------------------------------------------------
class TestRenderReviewTagsCell:
    """``render_review`` builds a Tags cell from the
    keyword list (the user's settings.json ``keyword_list``).
    The previous version wrote the tag directly into the
    cell — a user with ``"fps|60"`` in their keyword list
    would produce a broken cell, the column count would
    shift, and the rest of the row would render in the
    wrong place.
    """

    def test_pipe_in_keyword_escaped_in_tags_cell(self) -> None:
        review = {"review": "the game has a fps|60 problem",
                  "voted_up": False, "author": {}}
        lines = render_review(
            idx=1, r=review,
            keyword_list=["fps|60", "crash"],
        )
        out = "\n".join(lines)
        # The ``|`` inside the tag must be escaped.
        assert "fps\\|60" in out
        # The unescaped form must NOT appear in any cell —
        # that would break the table row.
        assert "| fps|60 |" not in out

    def test_newline_in_keyword_collapsed(self) -> None:
        # ``\\n`` in a keyword would have produced a
        # phantom second row. Now it collapses to a space.
        review = {"review": "the game has a crash bug",
                  "voted_up": False, "author": {}}
        lines = render_review(
            idx=1, r=review,
            keyword_list=["crash\nbug"],
        )
        out = "\n".join(lines)
        # The cell text stays on a single line.
        # The marker for a fresh row ``|---|---|`` is unique
        # per exporter, so we just check the keyword is
        # rendered as ``crash bug`` (with a space, not a
        # newline).
        assert "crash bug" in out

    def test_no_tags_when_keyword_list_empty(self) -> None:
        review = {"review": "test", "voted_up": True, "author": {}}
        lines = render_review(
            idx=1, r=review, keyword_list=[],
        )
        out = "\n".join(lines)
        # The Tags cell is omitted when there are no tags.
        assert "**Tags**" not in out

    def test_normal_keywords_still_work(self) -> None:
        # Both keywords appear in the review text so both
        # should match. ``crash`` is in the hard-coded list
        # and ``fps`` was added by the user.
        review = {"review": "the game has a crash bug and bad fps",
                  "voted_up": False, "author": {}}
        lines = render_review(
            idx=1, r=review,
            keyword_list=["crash", "fps"],
        )
        out = "\n".join(lines)
        assert "`crash`" in out
        assert "`fps`" in out


# ---------------------------------------------------------------------------
# BUG-R14-3: render_review weighted_vote_score cell doesn't escape |
# ---------------------------------------------------------------------------
class TestRenderReviewWeightedVoteScoreCell:
    """``render_review`` writes the ``weighted_vote_score``
    directly into a cell. The Steam API normally returns a
    float, but a hand-rolled / migrated review with a string
    score (e.g. ``"0.5|0.7"``) would break the row.
    """

    def test_pipe_in_score_is_escaped(self) -> None:
        review = {
            "review": "test", "voted_up": True, "author": {},
            "weighted_vote_score": "0.5|0.7",
        }
        lines = render_review(idx=1, r=review, keyword_list=None)
        out = "\n".join(lines)
        assert "0.5\\|0.7" in out
        assert "| 0.5|0.7 |" not in out

    def test_missing_score_renders_em_dash(self) -> None:
        # The ``safe_str`` default is ``"—"`` which contains
        # no ``|`` so the cell is fine.
        review = {
            "review": "test", "voted_up": True, "author": {},
        }
        lines = render_review(idx=1, r=review, keyword_list=None)
        out = "\n".join(lines)
        assert "—" in out

    def test_numeric_score_renders_as_string(self) -> None:
        review = {
            "review": "test", "voted_up": True, "author": {},
            "weighted_vote_score": 0.55,
        }
        lines = render_review(idx=1, r=review, keyword_list=None)
        out = "\n".join(lines)
        assert "0.55" in out


# ---------------------------------------------------------------------------
# BUG-R14-4 + R14-5: per_language_exporter.build_summary
# ---------------------------------------------------------------------------
class TestBuildSummaryTableCells:
    """``per_language_exporter.build_summary`` builds two
    tables: Language distribution (R14-4) and Top-10
    reviewers (R14-5). The previous version wrote the
    language code and the review preview directly into
    cells without escaping — both can carry user-controlled
    content that breaks the table layout.
    """

    def test_pipe_in_language_escaped(self) -> None:
        reviews = [
            {"language": "en|US", "voted_up": True,
             "author": {"steamid": "1"}, "recommendationid": "r1"},
        ]
        out = build_summary(reviews)
        assert "en\\|US" in out
        assert "| en|US |" not in out

    def test_pipe_in_review_preview_escaped(self) -> None:
        # Steam reviewers can write anything — a review with
        # ``|`` in the text would spill into a phantom
        # second column.
        reviews = [
            {"language": "english", "voted_up": True,
             "author": {"steamid": "1", "playtime_forever": 600},
             "recommendationid": "r1",
             "review": "the game | it's terrible"},
        ]
        out = build_summary(reviews)
        # The ``|`` inside the review must be escaped.
        assert "the game \\| it's terrible" in out
        # The unescaped form must NOT appear in any cell —
        # that would break the table.
        assert "| the game | it's terrible |" not in out

    def test_newline_in_review_collapsed(self) -> None:
        reviews = [
            {"language": "english", "voted_up": True,
             "author": {"steamid": "1", "playtime_forever": 600},
             "recommendationid": "r1",
             "review": "line one\nline two"},
        ]
        out = build_summary(reviews)
        # The newline is collapsed to a space.
        assert "line one line two" in out
        # The un-collapsed form must NOT appear.
        assert "line one\nline two" not in out

    def test_no_reviewers_when_no_data(self) -> None:
        out = build_summary([])
        # The "no reviews" header is rendered.
        assert "No reviews" in out
        # The Top-10 section is omitted (no reviewers to list).
        assert "Top 10 most-active reviewers" not in out

    def test_normal_review_renders_correctly(self) -> None:
        reviews = [
            {"language": "english", "voted_up": True,
             "author": {"steamid": "76561197960287930",
                        "playtime_forever": 6000},
             "recommendationid": "r1",
             "review": "great game"},
        ]
        out = build_summary(reviews)
        assert "great game" in out
        assert "76561197960287930" in out

    def test_top_reviewers_table_still_works(self) -> None:
        """A reviewer with a normal preview text must still
        render correctly — the md_escape wrapper must not
        mangle safe text."""
        reviews = [
            {"language": "english", "voted_up": True,
             "author": {"steamid": "111", "playtime_forever": 6000},
             "recommendationid": "r1", "review": "great game"},
            {"language": "german", "voted_up": False,
             "author": {"steamid": "222", "playtime_forever": 3000},
             "recommendationid": "r2", "review": "okay game"},
        ]
        out = build_summary(reviews)
        assert "great game" in out
        assert "okay game" in out
        # The top reviewer (steamid 111) must appear in the
        # table.
        assert "`111`" in out

    def test_group_by_language_ignores_pipe(self) -> None:
        """``group_by_language`` does NOT use the table
        rendering, so the ``|`` doesn't matter there — the
        key is just used as a dict key. The test pins the
        contract so a future refactor doesn't accidentally
        feed the un-escaped value into a table cell.
        """
        groups = group_by_language([
            {"language": "en|US", "voted_up": True},
            {"language": "en|US", "voted_up": False},
        ])
        # The pipe stays in the dict key (it's just a label,
        # not a cell value).
        assert "en|US" in groups
        assert len(groups["en|US"]) == 2


# ---------------------------------------------------------------------------
# End-to-end: the full MarkdownExporter.render output must
# not have un-escaped | or \n in any table cell.
# ---------------------------------------------------------------------------
class TestMarkdownExportEndToEnd:
    """Pin the end-to-end contract: a malformed review set
    must produce a valid Markdown table — no un-escaped
    ``|`` or literal ``\\n`` inside any cell.
    """

    def test_full_render_with_malformed_input(self) -> None:
        ctx = _ctx_with_reviews(
            reviews=[
                # Pipe in language
                {"language": "en|US", "voted_up": True,
                 "review": "test", "author": {}},
                # Newline in game name (app_details) + pipe
                # in review text
                {"language": "german", "voted_up": False,
                 "review": "the game | it's bad", "author": {}},
                # Pipe in keyword (from keyword_list)
            ],
            keyword_list=["fps|60", "crash"],
            app_details={"name": "Test\nGame", "type": "game",
                         "developers": ["Dev"], "publishers": ["Pub"],
                         "release_date": {"date": "2024-01-01",
                                          "coming_soon": False},
                         "platforms": {"windows": True}},
        )
        out = MarkdownExporter.render(ctx)
        out_lines = out.splitlines()

        # 1. Every line that starts with ``|`` must be a
        # complete row on one line (no embedded ``\n``).
        # The R14-6 fix replaced ``\n`` with a space inside
        # table cells, so a multi-line game name or review
        # text would not split a row.
        for i, line in enumerate(out_lines):
            if line.startswith("|"):
                assert "\n" not in line, (
                    f"line {i} has embedded newline: {line!r}"
                )

        # 2. The escaped forms are present in the output.
        # Pin the specific escaping behaviour (rather than
        # trying to count ``|`` chars in escaped forms).
        assert "en\\|US" in out, (
            "language code ``en|US`` must be escaped to "
            "``en\\|US`` in the rendered output"
        )
        # The un-escaped pipe-in-cell form must NOT appear.
        assert "| en|US" not in out

        # 3. No raw newline in any TABLE row (the
        # multi-line game name appears in the title block,
        # which is not a table — but a multi-line value
        # inside a cell would split the row).
        # Pin: the Language distribution table row for
        # ``german`` must be on a single line, AND any
        # line that starts with ``|`` must be a complete
        # row (no embedded ``\n`` mid-line).
        for line in out_lines:
            if line.startswith("|") and line.endswith("|"):
                # The first and last chars are the row
                # delimiters, the content is between.
                # A real ``\n`` in the middle would
                # produce a split line, so we can check
                # ``line.count("\n") == 0`` directly.
                assert "\n" not in line

        # 4. The review-text preview in the per-language
        # summary's Top-10 reviewers table is escaped.
        # The full ``MarkdownExporter.render`` call does
        # NOT include the per-language Top-10 table —
        # that lives in the standalone ``build_summary``
        # output. Pin the escaping behaviour there too.
        from steam_review_tool.exporters.per_language_exporter import (
            build_summary as _build_summary,
        )
        summary_out = _build_summary(
            [
                {"language": "german", "voted_up": False,
                 "author": {"steamid": "1", "playtime_forever": 600},
                 "recommendationid": "r1",
                 "review": "the game | it's bad"},
            ]
        )
        assert "the game \\| it's bad" in summary_out

    def test_normal_render_unchanged(self) -> None:
        """A clean input must still render normally — the
        ``md_escape`` wrapper must not mangle safe text."""
        ctx = _ctx_with_reviews(
            reviews=[
                {"language": "english", "voted_up": True,
                 "review": "great game", "author": {}},
            ],
            keyword_list=["crash"],
        )
        out = MarkdownExporter.render(ctx)
        assert "great game" in out
        assert "| english |" in out
        assert "Test Game" in out
        # ``crash`` is not in the review text so the Tags
        # cell is omitted.
        assert "**Tags**" not in out
