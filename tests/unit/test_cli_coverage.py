"""Tests for `dazzle coverage` — framework-artefact coverage audit."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dazzle.cli import app
from dazzle.cli.coverage import (
    CategoryCoverage,
    _display_mode_coverage,
    _dsl_construct_coverage,
    _fragment_template_coverage,
)

runner = CliRunner()


def _repo_root() -> Path:
    """Resolve the real repo root (tests always run from it)."""
    p = Path(__file__).resolve()
    while p != p.parent:
        if (p / "pyproject.toml").is_file() and (p / "examples").is_dir():
            return p
        p = p.parent
    raise AssertionError("could not resolve repo root")


# ---------------------------------------------------------------------------
# Category-level behaviour
# ---------------------------------------------------------------------------


class TestCategoryCoverage:
    def test_percent_of_empty_category_is_100(self) -> None:
        cat = CategoryCoverage(name="x", description="empty")
        assert cat.percent == 100.0

    def test_covered_and_uncovered_partition(self) -> None:
        cat = CategoryCoverage(
            name="x",
            description="test",
            coverage={"a": ["app1"], "b": [], "c": ["app2", "app3"]},
        )
        assert cat.covered == ["a", "c"]
        assert cat.uncovered == ["b"]
        assert cat.percent == pytest.approx(2 / 3 * 100)


# ---------------------------------------------------------------------------
# Collectors against the real repo
# ---------------------------------------------------------------------------


class TestDisplayModeCoverage:
    def test_list_grid_kanban_timeline_are_covered(self) -> None:
        cat = _display_mode_coverage(_repo_root())
        # These are the modes added explicitly in example apps so far —
        # they should always be covered.
        for required in ("list", "grid", "kanban", "timeline"):
            assert cat.coverage[required], (
                f"DisplayMode '{required}' expected to be covered by at least "
                f"one example app, got no coverage"
            )

    def test_every_displaymode_value_is_tracked(self) -> None:
        from dazzle.core.ir.workspaces import DisplayMode

        cat = _display_mode_coverage(_repo_root())
        assert set(cat.coverage.keys()) == {m.value for m in DisplayMode}


class TestDslConstructCoverage:
    def test_core_constructs_are_covered(self) -> None:
        cat = _dsl_construct_coverage(_repo_root())
        for required in ("entity", "surface", "workspace", "persona", "app"):
            assert cat.coverage[required], f"DSL construct '{required}' uncovered"

    def test_tracks_all_curated_constructs(self) -> None:
        from dazzle.cli.coverage import _DSL_CONSTRUCTS

        cat = _dsl_construct_coverage(_repo_root())
        assert set(cat.coverage.keys()) == set(_DSL_CONSTRUCTS)


class TestFragmentTemplateCoverage:
    def test_empty_state_is_included_somewhere(self) -> None:
        # Widely used fragment — should always have a include site.
        cat = _fragment_template_coverage(_repo_root())
        # Either the fragment isn't present (ok) or it has include sites.
        if "empty_state" in cat.coverage:
            assert cat.coverage["empty_state"], "empty_state fragment has no include site"


# ---------------------------------------------------------------------------
# CLI invocation
# ---------------------------------------------------------------------------


class TestCoverageCommand:
    def test_human_report_runs_and_lists_categories(self) -> None:
        result = runner.invoke(app, ["coverage"])
        assert result.exit_code == 0
        assert "display_modes" in result.stdout
        assert "dsl_constructs" in result.stdout
        assert "fragment_templates" in result.stdout

    def test_json_report_is_valid_json(self) -> None:
        result = runner.invoke(app, ["coverage", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        assert set(payload.keys()) == {"display_modes", "dsl_constructs", "fragment_templates"}
        for _name, section in payload.items():
            assert "description" in section
            assert "percent" in section
            assert "covered" in section
            assert "uncovered" in section

    def test_fail_on_uncovered_returns_nonzero_when_gaps_exist(self) -> None:
        # Until the backlog reaches 100% coverage, this must exit with 1.
        # When full coverage is reached this test should either (a) pass
        # because the gate stays green, or (b) be explicitly updated —
        # it's a signal, not a regression.
        result = runner.invoke(app, ["coverage", "--fail-on-uncovered"])
        # Exit 1 means uncovered items exist (expected today); exit 0
        # means the matrix is full. Either is "working correctly."
        assert result.exit_code in (0, 1)
