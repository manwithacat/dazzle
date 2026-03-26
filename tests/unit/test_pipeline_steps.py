"""Tests for pipeline step composition."""

from pathlib import Path

from dazzle.mcp.server.handlers.pipeline import _build_quality_steps


class TestBuildQualitySteps:
    def test_includes_rhythm_gaps_step(self) -> None:
        """Pipeline includes rhythm(gaps) as an optional quality step."""
        steps, _ = _build_quality_steps(Path("/fake"))
        step_names = [s.name for s in steps]
        assert "rhythm(gaps)" in step_names

    def test_rhythm_gaps_is_optional(self) -> None:
        """rhythm(gaps) step is marked optional."""
        steps, _ = _build_quality_steps(Path("/fake"))
        gaps_step = next(s for s in steps if s.name == "rhythm(gaps)")
        assert gaps_step.optional is True
