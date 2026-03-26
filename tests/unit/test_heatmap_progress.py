"""Tests for heatmap and progress workspace region display modes (v0.44.0)."""

import textwrap
from pathlib import Path

import pytest

from dazzle.core.ir.workspaces import DisplayMode, WorkspaceRegion
from dazzle.core.lexer import Lexer, TokenType
from dazzle.core.parser import parse_dsl


class TestDisplayModeEnum:
    """DisplayMode enum includes HEATMAP and PROGRESS."""

    def test_heatmap_member(self) -> None:
        assert DisplayMode.HEATMAP == "heatmap"

    def test_progress_member(self) -> None:
        assert DisplayMode.PROGRESS == "progress"

    def test_heatmap_from_value(self) -> None:
        assert DisplayMode("heatmap") is DisplayMode.HEATMAP

    def test_progress_from_value(self) -> None:
        assert DisplayMode("progress") is DisplayMode.PROGRESS


class TestWorkspaceRegionFields:
    """WorkspaceRegion accepts heatmap and progress fields."""

    def test_heatmap_fields(self) -> None:
        region = WorkspaceRegion(
            name="heat",
            source="Score",
            display=DisplayMode.HEATMAP,
            heatmap_rows="student",
            heatmap_columns="subject",
            heatmap_value="avg_score",
            heatmap_thresholds=[0.4, 0.6],
        )
        assert region.heatmap_rows == "student"
        assert region.heatmap_columns == "subject"
        assert region.heatmap_value == "avg_score"
        assert region.heatmap_thresholds == [0.4, 0.6]

    def test_progress_fields(self) -> None:
        region = WorkspaceRegion(
            name="prog",
            source="Manuscript",
            display=DisplayMode.PROGRESS,
            progress_stages=["uploaded", "queued", "processing", "marked", "reviewed"],
            progress_complete_at="reviewed",
        )
        assert region.progress_stages == [
            "uploaded",
            "queued",
            "processing",
            "marked",
            "reviewed",
        ]
        assert region.progress_complete_at == "reviewed"

    def test_defaults_are_empty(self) -> None:
        region = WorkspaceRegion(name="basic", source="Task")
        assert region.heatmap_rows is None
        assert region.heatmap_columns is None
        assert region.heatmap_value is None
        assert region.heatmap_thresholds == []
        assert region.progress_stages == []
        assert region.progress_complete_at is None


class TestLexerTokens:
    """Lexer recognises the new heatmap/progress keywords."""

    @pytest.mark.parametrize(
        "keyword,expected_type",
        [
            ("rows", TokenType.ROWS),
            ("columns", TokenType.COLUMNS),
            ("value", TokenType.VALUE),
            ("thresholds", TokenType.THRESHOLDS),
            ("stages", TokenType.STAGES),
            ("complete_at", TokenType.COMPLETE_AT),
        ],
    )
    def test_keyword_tokens(self, keyword: str, expected_type: TokenType) -> None:
        lexer = Lexer(keyword, Path("test.dz"))
        tokens = lexer.tokenize()
        # First non-special token should be our keyword
        kw_tokens = [t for t in tokens if t.type not in (TokenType.NEWLINE, TokenType.EOF)]
        assert len(kw_tokens) >= 1
        assert kw_tokens[0].type == expected_type


class TestParserHeatmap:
    """Parser handles display: heatmap with rows/columns/value/thresholds."""

    def test_parse_heatmap_region(self) -> None:
        dsl = textwrap.dedent("""\
            module test_app
            app test "Test"

            entity Score "Score":
              id: uuid pk
              student: str(100) required
              subject: str(100) required
              avg_score: decimal(10,2) required

            workspace dashboard "Dashboard":
              heat:
                source: Score
                display: heatmap
                rows: student
                columns: subject
                value: avg_score
                thresholds: [0, 0]
        """)
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dz"))
        ws = fragment.workspaces[0]
        region = ws.regions[0]
        assert region.display == DisplayMode.HEATMAP
        assert region.heatmap_rows == "student"
        assert region.heatmap_columns == "subject"
        assert region.heatmap_value == "avg_score"
        assert region.heatmap_thresholds == [0.0, 0.0]

    def test_parse_heatmap_dotted_paths(self) -> None:
        dsl = textwrap.dedent("""\
            module test_app
            app test "Test"

            entity Score "Score":
              id: uuid pk
              value: decimal(10,2) required

            workspace dashboard "Dashboard":
              heat:
                source: Score
                display: heatmap
                rows: manuscript.student
                columns: manuscript.subject
                value: value
                thresholds: [0, 0]
        """)
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dz"))
        region = fragment.workspaces[0].regions[0]
        assert region.heatmap_rows == "manuscript.student"
        assert region.heatmap_columns == "manuscript.subject"


class TestParserProgress:
    """Parser handles display: progress with stages/complete_at."""

    def test_parse_progress_region(self) -> None:
        dsl = textwrap.dedent("""\
            module test_app
            app test "Test"

            entity Manuscript "Manuscript":
              id: uuid pk
              status: str(50) required

            workspace dashboard "Dashboard":
              pipeline:
                source: Manuscript
                display: progress
                group_by: status
                stages: [uploaded, queued, processing, marked, reviewed]
                complete_at: reviewed
        """)
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dz"))
        ws = fragment.workspaces[0]
        region = ws.regions[0]
        assert region.display == DisplayMode.PROGRESS
        assert region.progress_stages == [
            "uploaded",
            "queued",
            "processing",
            "marked",
            "reviewed",
        ]
        assert region.progress_complete_at == "reviewed"
        assert region.group_by == "status"

    def test_parse_progress_without_complete_at(self) -> None:
        dsl = textwrap.dedent("""\
            module test_app
            app test "Test"

            entity Task "Task":
              id: uuid pk
              status: str(50) required

            workspace dashboard "Dashboard":
              pipeline:
                source: Task
                display: progress
                stages: [todo, doing, done]
        """)
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dz"))
        region = fragment.workspaces[0].regions[0]
        assert region.progress_stages == ["todo", "doing", "done"]
        assert region.progress_complete_at is None
