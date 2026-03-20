"""Tests for journey testing data models."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from dazzle.agent.journey_models import (
    AnalysisReport,
    CrossPersonaPattern,
    DeadEnd,
    JourneySession,
    JourneyStep,
    NavBreak,
    NavigationTarget,
    Recommendation,
    Verdict,
)

# ---------------------------------------------------------------------------
# Verdict enum
# ---------------------------------------------------------------------------


class TestVerdict:
    def test_all_members(self) -> None:
        expected = {
            "pass",
            "partial",
            "fail",
            "blocked",
            "dead_end",
            "scope_leak",
            "confusing",
            "nav_break",
            "timeout",
        }
        assert {v.value for v in Verdict} == expected

    def test_str_enum(self) -> None:
        assert str(Verdict.PASS) == "pass"
        assert Verdict("fail") == Verdict.FAIL


# ---------------------------------------------------------------------------
# JourneyStep
# ---------------------------------------------------------------------------


def _make_step(**overrides) -> JourneyStep:
    defaults = {
        "persona": "teacher",
        "phase": "explore",
        "step_number": 1,
        "action": "navigate",
        "target": "/app/tasks",
        "url_before": "/app/",
        "url_after": "/app/tasks",
        "expectation": "Task list loads",
        "observation": "Task list with 5 rows",
        "verdict": Verdict.PASS,
        "reasoning": "Page loaded correctly",
        "timestamp": datetime(2026, 3, 20, 10, 0, 0, tzinfo=UTC),
    }
    defaults.update(overrides)
    return JourneyStep(**defaults)


class TestJourneyStep:
    def test_construction(self) -> None:
        step = _make_step()
        assert step.persona == "teacher"
        assert step.phase == "explore"
        assert step.story_id is None
        assert step.screenshot_path is None

    def test_with_story_id(self) -> None:
        step = _make_step(story_id="ST-001", phase="verify")
        assert step.story_id == "ST-001"

    def test_json_round_trip(self) -> None:
        step = _make_step(screenshot_path="screenshots/teacher-001.png")
        data = json.loads(step.model_dump_json())
        restored = JourneyStep.model_validate(data)
        assert restored == step

    def test_frozen(self) -> None:
        step = _make_step()
        with pytest.raises(ValidationError):
            step.persona = "admin"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# JourneySession
# ---------------------------------------------------------------------------


class TestJourneySession:
    def test_from_steps(self) -> None:
        steps = [
            _make_step(step_number=1, verdict=Verdict.PASS),
            _make_step(step_number=2, verdict=Verdict.PASS),
            _make_step(step_number=3, verdict=Verdict.FAIL),
            _make_step(
                step_number=4,
                verdict=Verdict.PARTIAL,
                story_id="ST-001",
                phase="verify",
            ),
        ]
        session = JourneySession.from_steps(
            persona="teacher",
            steps=steps,
            run_date="2026-03-20",
        )
        assert session.persona == "teacher"
        assert session.verdict_counts["pass"] == 2
        assert session.verdict_counts["fail"] == 1
        assert session.verdict_counts["partial"] == 1
        assert session.stories_attempted == 1
        assert len(session.steps) == 4

    def test_stories_covered(self) -> None:
        steps = [
            _make_step(story_id="ST-001", phase="verify", verdict=Verdict.PASS),
            _make_step(story_id="ST-001", phase="verify", step_number=2, verdict=Verdict.PASS),
            _make_step(story_id="ST-002", phase="verify", verdict=Verdict.FAIL),
        ]
        session = JourneySession.from_steps(
            persona="teacher",
            steps=steps,
            run_date="2026-03-20",
        )
        assert session.stories_attempted == 2
        # stories_covered = stories where all steps passed or partial
        assert session.stories_covered == 1

    def test_empty_steps(self) -> None:
        session = JourneySession.from_steps(
            persona="teacher",
            steps=[],
            run_date="2026-03-20",
        )
        assert session.stories_attempted == 0
        assert session.stories_covered == 0
        assert all(v == 0 for v in session.verdict_counts.values())

    def test_json_round_trip(self) -> None:
        steps = [_make_step()]
        session = JourneySession.from_steps(
            persona="teacher",
            steps=steps,
            run_date="2026-03-20",
        )
        data = json.loads(session.model_dump_json())
        restored = JourneySession.model_validate(data)
        assert restored.persona == session.persona
        assert restored.verdict_counts == session.verdict_counts


# ---------------------------------------------------------------------------
# CrossPersonaPattern
# ---------------------------------------------------------------------------


class TestCrossPersonaPattern:
    def test_construction(self) -> None:
        cpp = CrossPersonaPattern(
            id="CPP-001",
            title="Scope filtering issue",
            severity="critical",
            affected_personas=["teacher", "student"],
            description="Teacher sees zero rows",
            evidence=["Step 3: empty list"],
            recommendation="Check scope rules",
        )
        assert cpp.severity == "critical"
        assert len(cpp.affected_personas) == 2

    def test_invalid_severity(self) -> None:
        with pytest.raises(ValidationError):
            CrossPersonaPattern(
                id="CPP-001",
                title="Test",
                severity="invalid",  # type: ignore[arg-type]
                affected_personas=[],
                description="",
                evidence=[],
                recommendation="",
            )


# ---------------------------------------------------------------------------
# DeadEnd, NavBreak, Recommendation
# ---------------------------------------------------------------------------


class TestDeadEnd:
    def test_construction(self) -> None:
        de = DeadEnd(
            id="DE-001",
            persona="teacher",
            page="/app/tasks",
            story="ST-001",
            description="No link to create page",
        )
        assert de.page == "/app/tasks"
        assert de.story == "ST-001"

    def test_no_story(self) -> None:
        de = DeadEnd(
            id="DE-002",
            persona="admin",
            page="/app/",
            story=None,
            description="Dead end in explore",
        )
        assert de.story is None


class TestNavBreak:
    def test_construction(self) -> None:
        nb = NavBreak(
            id="NB-001",
            description="Missing sidebar link",
            affected_personas=["teacher", "admin"],
            workaround="Direct URL navigation",
        )
        assert len(nb.affected_personas) == 2

    def test_no_workaround(self) -> None:
        nb = NavBreak(
            id="NB-002",
            description="Broken link",
            affected_personas=["student"],
            workaround=None,
        )
        assert nb.workaround is None


class TestRecommendation:
    def test_construction(self) -> None:
        rec = Recommendation(
            priority=1,
            title="Fix scope rules",
            description="Teacher cannot see tasks",
            effort="quick_fix",
            affected_entities=["Task"],
        )
        assert rec.effort == "quick_fix"
        assert rec.priority == 1


# ---------------------------------------------------------------------------
# AnalysisReport
# ---------------------------------------------------------------------------


class TestAnalysisReport:
    def test_construction(self) -> None:
        report = AnalysisReport(
            run_id="2026-03-20",
            dazzle_version="0.44.0",
            deployment_url="http://localhost:3000",
            personas_analysed=3,
            personas_failed=["governor"],
            total_steps=42,
            total_stories=8,
            verdict_counts={"pass": 20, "fail": 5},
            cross_persona_patterns=[],
            dead_ends=[],
            nav_breaks=[],
            scope_leaks=[],
            recommendations=[],
        )
        assert report.personas_analysed == 3
        assert report.personas_failed == ["governor"]

    def test_json_round_trip(self) -> None:
        cpp = CrossPersonaPattern(
            id="CPP-001",
            title="Issue",
            severity="high",
            affected_personas=["a"],
            description="desc",
            evidence=["e1"],
            recommendation="fix",
        )
        report = AnalysisReport(
            run_id="2026-03-20",
            dazzle_version="0.44.0",
            deployment_url="http://localhost:3000",
            personas_analysed=1,
            personas_failed=[],
            total_steps=1,
            total_stories=0,
            verdict_counts={"pass": 1},
            cross_persona_patterns=[cpp],
            dead_ends=[],
            nav_breaks=[],
            scope_leaks=[],
            recommendations=[],
        )
        data = json.loads(report.model_dump_json())
        restored = AnalysisReport.model_validate(data)
        assert len(restored.cross_persona_patterns) == 1
        assert restored.cross_persona_patterns[0].id == "CPP-001"


# ---------------------------------------------------------------------------
# NavigationTarget
# ---------------------------------------------------------------------------


class TestNavigationTarget:
    def test_construction(self) -> None:
        nt = NavigationTarget(
            url="/app/tasks",
            entity_name="Task",
            surface_mode="list",
            expectation="Task list page",
        )
        assert nt.url == "/app/tasks"
        assert nt.surface_mode == "list"

    def test_frozen(self) -> None:
        nt = NavigationTarget(
            url="/app/tasks",
            entity_name="Task",
            surface_mode="list",
            expectation="List",
        )
        with pytest.raises(ValidationError):
            nt.url = "/other"  # type: ignore[misc]
