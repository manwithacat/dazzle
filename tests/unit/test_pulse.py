"""Tests for the pulse (founder-ready health report) handler."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import pytest

from dazzle.mcp.server.handlers.pulse import (
    _compliance_score,
    _composite_health,
    _content_score,
    _coverage_score,
    _founder_decisions,
    _progress_bar,
    _quality_score,
    _recent_wins,
    _render_markdown,
    _security_score,
    _ux_score,
    run_pulse_handler,
)

# ---------------------------------------------------------------------------
# Fixtures — realistic mock data for each source
# ---------------------------------------------------------------------------


def _pipeline_data(
    passed: int = 10,
    total: int = 10,
    status: str = "passed",
) -> dict[str, Any]:
    return {
        "status": status,
        "summary": {
            "total_steps": total,
            "passed": passed,
            "failed": total - passed,
            "skipped": 0,
        },
        "steps": [
            {
                "step": 1,
                "operation": "dsl(validate)",
                "status": "passed",
                "result": {"project_path": "/projects/acme"},
            },
        ],
        "top_issues": [],
    }


def _stories_data(
    total: int = 20,
    covered: int = 15,
    partial: int = 3,
    uncovered: int = 2,
) -> dict[str, Any]:
    return {
        "total_stories": total,
        "covered": covered,
        "partial": partial,
        "uncovered": uncovered,
        "coverage_percent": (covered / total * 100) if total else 0,
    }


def _coherence_data(score: int = 80, errors: int = 0, warnings: int = 2) -> dict[str, Any]:
    return {
        "score": score,
        "is_coherent": errors == 0,
        "error_count": errors,
        "warning_count": warnings,
        "suggestion_count": 3,
        "issues": [],
    }


def _policy_data(allow: int = 100, deny: int = 10, default_deny: int = 40) -> dict[str, Any]:
    total = allow + deny + default_deny
    return {
        "matrix": [],
        "summary": {
            "total_combinations": total,
            "allow": allow,
            "explicit_deny": deny,
            "default_deny": default_deny,
        },
    }


def _compliance_data(
    pii: int = 5,
    financial: int = 3,
    health: int = 0,
    frameworks: list[str] | None = None,
    suggestions: int = 4,
) -> dict[str, Any]:
    if frameworks is None:
        frameworks = ["GDPR", "PCI-DSS"]
    return {
        "pii_fields": [{"entity": "User", "field": f"f{i}"} for i in range(pii)],
        "financial_fields": [{"entity": "Payment", "field": f"f{i}"} for i in range(financial)],
        "health_fields": [{"entity": "Patient", "field": f"f{i}"} for i in range(health)],
        "recommended_frameworks": frameworks,
        "classification_suggestions": [{"entity": "e"} for _ in range(suggestions)],
    }


# ---------------------------------------------------------------------------
# Individual axis score tests
# ---------------------------------------------------------------------------


class TestRadarAxes:
    """Test individual radar axis calculations."""

    def test_quality_score_all_passing(self) -> None:
        assert _quality_score(_pipeline_data(passed=10, total=10)) == 100.0

    def test_quality_score_partial(self) -> None:
        assert _quality_score(_pipeline_data(passed=7, total=10)) == 70.0

    def test_quality_score_empty(self) -> None:
        assert _quality_score({}) == 0.0

    def test_coverage_score(self) -> None:
        assert _coverage_score(_stories_data(total=20, covered=15)) == 75.0

    def test_coverage_score_error(self) -> None:
        assert _coverage_score({"error": "failed"}) == 0.0

    def test_content_score(self) -> None:
        assert _content_score(_coherence_data(score=85)) == 85.0

    def test_content_score_error(self) -> None:
        assert _content_score({"error": "no sitespec"}) == 0.0

    def test_security_score(self) -> None:
        # 100 allow + 10 deny = 110 covered out of 150 total
        score = _security_score(_policy_data(allow=100, deny=10, default_deny=40))
        assert score == pytest.approx(73.3, abs=0.1)

    def test_security_score_empty(self) -> None:
        assert _security_score({}) == 0.0

    def test_compliance_score_no_sensitive_fields(self) -> None:
        data = _compliance_data(pii=0, financial=0, health=0)
        assert _compliance_score(data) == 100.0

    def test_compliance_score_with_suggestions(self) -> None:
        data = _compliance_data(pii=5, financial=3, suggestions=4)
        # 4 suggestions / 8 fields = 50%
        assert _compliance_score(data) == 50.0

    def test_compliance_score_error(self) -> None:
        assert _compliance_score({"error": "failed"}) == 0.0

    def test_ux_score_no_errors(self) -> None:
        # score=80, 0 errors, 2 warnings → 80 - 6 = 74
        assert _ux_score(_coherence_data(score=80, errors=0, warnings=2)) == 74.0

    def test_ux_score_with_errors(self) -> None:
        # score=80, 3 errors, 1 warning → 80 - 30 - 3 = 47
        assert _ux_score(_coherence_data(score=80, errors=3, warnings=1)) == 47.0

    def test_ux_score_floor_at_zero(self) -> None:
        assert _ux_score(_coherence_data(score=10, errors=5, warnings=5)) == 0.0


# ---------------------------------------------------------------------------
# Composite health score
# ---------------------------------------------------------------------------


class TestCompositeHealth:
    """Test the weighted composite score."""

    def test_perfect_scores(self) -> None:
        radar = dict.fromkeys(
            ("quality", "coverage", "content", "security", "compliance", "ux"), 100.0
        )
        assert _composite_health(radar) == 100.0

    def test_zero_scores(self) -> None:
        radar = dict.fromkeys(
            ("quality", "coverage", "content", "security", "compliance", "ux"), 0.0
        )
        assert _composite_health(radar) == 0.0

    def test_mixed_scores(self) -> None:
        radar = {
            "quality": 100.0,
            "coverage": 75.0,
            "content": 80.0,
            "security": 70.0,
            "compliance": 50.0,
            "ux": 60.0,
        }
        # 100*0.20 + 75*0.25 + 80*0.15 + 70*0.15 + 50*0.10 + 60*0.15
        expected = 20 + 18.75 + 12 + 10.5 + 5 + 9
        assert _composite_health(radar) == pytest.approx(expected, abs=0.1)


# ---------------------------------------------------------------------------
# Founder decisions
# ---------------------------------------------------------------------------


class TestFounderDecisions:
    """Test the decision identification logic."""

    def test_partial_stories_generate_decision(self) -> None:
        decisions = _founder_decisions(
            _stories_data(partial=5, uncovered=3),
            _coherence_data(errors=0),
            _policy_data(),
        )
        assert any("stories need work" in d["question"] for d in decisions)

    def test_coherence_errors_generate_decision(self) -> None:
        decisions = _founder_decisions(
            _stories_data(),
            _coherence_data(errors=4),
            _policy_data(),
        )
        assert any("broken element" in d["question"] for d in decisions)

    def test_no_decisions_when_everything_fine(self) -> None:
        decisions = _founder_decisions(
            _stories_data(partial=0, uncovered=0),
            _coherence_data(errors=0),
            _policy_data(default_deny=5),
        )
        assert len(decisions) == 0

    def test_high_default_deny_generates_decision(self) -> None:
        decisions = _founder_decisions(
            _stories_data(partial=0, uncovered=0),
            _coherence_data(errors=0),
            _policy_data(default_deny=20),
        )
        assert any("permission" in d["question"] for d in decisions)


# ---------------------------------------------------------------------------
# Recent wins
# ---------------------------------------------------------------------------


class TestRecentWins:
    """Test the wins identification logic."""

    def test_all_pipeline_passing(self) -> None:
        wins = _recent_wins(_pipeline_data(passed=10, total=10), _stories_data(), _policy_data())
        assert any("quality checks passing" in w for w in wins)

    def test_high_story_coverage(self) -> None:
        wins = _recent_wins(_pipeline_data(), _stories_data(total=10, covered=9), _policy_data())
        assert any("customer journeys working" in w for w in wins)

    def test_security_configured(self) -> None:
        wins = _recent_wins(_pipeline_data(), _stories_data(), _policy_data(allow=50))
        assert any("Access rules" in w for w in wins)


# ---------------------------------------------------------------------------
# Progress bar
# ---------------------------------------------------------------------------


class TestProgressBar:
    """Test ASCII progress bar rendering."""

    def test_full(self) -> None:
        assert _progress_bar(100, width=10) == "[##########]"

    def test_empty(self) -> None:
        assert _progress_bar(0, width=10) == "[----------]"

    def test_half(self) -> None:
        assert _progress_bar(50, width=10) == "[#####-----]"


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------


class TestMarkdownRendering:
    """Test the markdown report generation."""

    def test_contains_project_name(self) -> None:
        md = _render_markdown(
            project_name="Acme",
            health_score=78.0,
            radar=dict.fromkeys(
                ("quality", "coverage", "content", "security", "compliance", "ux"), 80.0
            ),
            needs_input=[],
            recent_wins=[],
            blockers=[],
            stories_data=_stories_data(),
            pipeline_data=_pipeline_data(),
        )
        assert "Acme" in md
        assert "78% Launch Ready" in md

    def test_contains_radar(self) -> None:
        md = _render_markdown(
            project_name="Test",
            health_score=50.0,
            radar={
                "quality": 90.0,
                "coverage": 60.0,
                "content": 40.0,
                "security": 50.0,
                "compliance": 30.0,
                "ux": 70.0,
            },
            needs_input=[],
            recent_wins=[],
            blockers=[],
            stories_data=_stories_data(),
            pipeline_data=_pipeline_data(),
        )
        assert "Readiness Radar" in md
        assert "Quality" in md
        assert "Coverage" in md

    def test_contains_decisions(self) -> None:
        md = _render_markdown(
            project_name="Test",
            health_score=50.0,
            radar=dict.fromkeys(
                ("quality", "coverage", "content", "security", "compliance", "ux"), 50.0
            ),
            needs_input=[{"category": "priority", "question": "Which stories matter?"}],
            recent_wins=[],
            blockers=[],
            stories_data=_stories_data(),
            pipeline_data=_pipeline_data(),
        )
        assert "What Needs Your Input" in md
        assert "Which stories matter?" in md

    def test_contains_wins(self) -> None:
        md = _render_markdown(
            project_name="Test",
            health_score=90.0,
            radar=dict.fromkeys(
                ("quality", "coverage", "content", "security", "compliance", "ux"), 90.0
            ),
            needs_input=[],
            recent_wins=["All 10 quality checks passing"],
            blockers=[],
            stories_data=_stories_data(),
            pipeline_data=_pipeline_data(),
        )
        assert "Recent Wins" in md
        assert "All 10 quality checks passing" in md

    def test_contains_blockers(self) -> None:
        md = _render_markdown(
            project_name="Test",
            health_score=50.0,
            radar=dict.fromkeys(
                ("quality", "coverage", "content", "security", "compliance", "ux"), 50.0
            ),
            needs_input=[],
            recent_wins=[],
            blockers=["dsl(lint): parser crash"],
            stories_data=_stories_data(),
            pipeline_data=_pipeline_data(),
        )
        assert "Blocked" in md
        assert "parser crash" in md


# ---------------------------------------------------------------------------
# Integration: run_pulse_handler with mocked collectors
# ---------------------------------------------------------------------------


class TestRunPulseHandler:
    """Test the main handler with mocked data collectors."""

    @patch("dazzle.mcp.server.handlers.pulse._collect_compliance")
    @patch("dazzle.mcp.server.handlers.pulse._collect_policy")
    @patch("dazzle.mcp.server.handlers.pulse._collect_coherence")
    @patch("dazzle.mcp.server.handlers.pulse._collect_stories")
    @patch("dazzle.mcp.server.handlers.pulse._collect_pipeline")
    def test_returns_valid_json(
        self,
        mock_pipeline: Any,
        mock_stories: Any,
        mock_coherence: Any,
        mock_policy: Any,
        mock_compliance: Any,
        tmp_path: Any,
    ) -> None:
        mock_pipeline.return_value = _pipeline_data()
        mock_stories.return_value = _stories_data()
        mock_coherence.return_value = _coherence_data()
        mock_policy.return_value = _policy_data()
        mock_compliance.return_value = _compliance_data()

        result = run_pulse_handler(tmp_path, {"operation": "run"})
        data = json.loads(result)

        assert data["status"] == "complete"
        assert "health_score" in data
        assert "radar" in data
        assert "markdown" in data
        assert isinstance(data["health_score"], float)
        assert isinstance(data["radar"], dict)
        assert isinstance(data["markdown"], str)
        assert data["duration_ms"] > 0

    @patch("dazzle.mcp.server.handlers.pulse._collect_compliance")
    @patch("dazzle.mcp.server.handlers.pulse._collect_policy")
    @patch("dazzle.mcp.server.handlers.pulse._collect_coherence")
    @patch("dazzle.mcp.server.handlers.pulse._collect_stories")
    @patch("dazzle.mcp.server.handlers.pulse._collect_pipeline")
    def test_radar_has_all_axes(
        self,
        mock_pipeline: Any,
        mock_stories: Any,
        mock_coherence: Any,
        mock_policy: Any,
        mock_compliance: Any,
        tmp_path: Any,
    ) -> None:
        mock_pipeline.return_value = _pipeline_data()
        mock_stories.return_value = _stories_data()
        mock_coherence.return_value = _coherence_data()
        mock_policy.return_value = _policy_data()
        mock_compliance.return_value = _compliance_data()

        result = run_pulse_handler(tmp_path, {"operation": "run"})
        data = json.loads(result)

        expected_axes = {"quality", "coverage", "content", "security", "compliance", "ux"}
        assert set(data["radar"].keys()) == expected_axes

    @patch("dazzle.mcp.server.handlers.pulse._collect_compliance")
    @patch("dazzle.mcp.server.handlers.pulse._collect_policy")
    @patch("dazzle.mcp.server.handlers.pulse._collect_coherence")
    @patch("dazzle.mcp.server.handlers.pulse._collect_stories")
    @patch("dazzle.mcp.server.handlers.pulse._collect_pipeline")
    def test_handles_all_errors_gracefully(
        self,
        mock_pipeline: Any,
        mock_stories: Any,
        mock_coherence: Any,
        mock_policy: Any,
        mock_compliance: Any,
        tmp_path: Any,
    ) -> None:
        """When all sources fail, pulse still returns a valid report."""
        mock_pipeline.return_value = {"error": "no dsl"}
        mock_stories.return_value = {"error": "no stories"}
        mock_coherence.return_value = {"error": "no sitespec"}
        mock_policy.return_value = {"error": "no policy"}
        mock_compliance.return_value = {"error": "no compliance"}

        result = run_pulse_handler(tmp_path, {"operation": "run"})
        data = json.loads(result)

        assert data["status"] == "complete"
        assert data["health_score"] == 0.0
        assert all(v == 0.0 for v in data["radar"].values())
