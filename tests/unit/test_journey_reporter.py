"""Tests for the E2E journey HTML report renderer."""

from datetime import UTC, datetime
from pathlib import Path

from dazzle.agent.journey_models import (
    AnalysisReport,
    CrossPersonaPattern,
    DeadEnd,
    JourneySession,
    JourneyStep,
    NavBreak,
    Recommendation,
    Verdict,
)
from dazzle.agent.journey_reporter import render_report

# ── helpers ──────────────────────────────────────────────────────────


def _make_step(
    persona: str = "teacher",
    verdict: Verdict = Verdict.PASS,
    step_number: int = 1,
    story_id: str | None = None,
) -> JourneyStep:
    return JourneyStep(
        persona=persona,
        phase="explore",
        step_number=step_number,
        action="navigate",
        target="/app/tasks",
        url_before="/app/",
        url_after="/app/tasks",
        expectation="Page loads with task list",
        observation="Task list rendered correctly",
        verdict=verdict,
        reasoning="All elements present",
        story_id=story_id,
        timestamp=datetime(2026, 3, 20, tzinfo=UTC),
    )


def _make_analysis(
    *,
    patterns: list[CrossPersonaPattern] | None = None,
    dead_ends: list[DeadEnd] | None = None,
    nav_breaks: list[NavBreak] | None = None,
    recommendations: list[Recommendation] | None = None,
    personas_analysed: int = 2,
    total_steps: int = 5,
    total_stories: int = 3,
) -> AnalysisReport:
    return AnalysisReport(
        run_id="run-001",
        dazzle_version="0.44.0",
        deployment_url="http://localhost:3000",
        personas_analysed=personas_analysed,
        personas_failed=[],
        total_steps=total_steps,
        total_stories=total_stories,
        verdict_counts={"pass": 3, "fail": 1, "partial": 1},
        cross_persona_patterns=patterns or [],
        dead_ends=dead_ends or [],
        nav_breaks=nav_breaks or [],
        scope_leaks=[],
        recommendations=recommendations or [],
    )


# ── tests ────────────────────────────────────────────────────────────


class TestRenderReport:
    """Tests for render_report()."""

    def test_produces_html_file(self, tmp_path: Path) -> None:
        """render_report writes an HTML file to the output path."""
        steps = [_make_step()]
        session = JourneySession.from_steps(persona="teacher", steps=steps, run_date="2026-03-20")
        analysis = _make_analysis()
        out = tmp_path / "report.html"

        render_report([session], analysis, out)

        assert out.exists()
        content = out.read_text()
        assert "<!DOCTYPE html>" in content or "<html" in content

    def test_contains_persona_names(self, tmp_path: Path) -> None:
        """Report HTML includes persona names from sessions."""
        sessions = [
            JourneySession.from_steps(
                persona="teacher",
                steps=[_make_step(persona="teacher")],
                run_date="2026-03-20",
            ),
            JourneySession.from_steps(
                persona="student",
                steps=[_make_step(persona="student")],
                run_date="2026-03-20",
            ),
        ]
        analysis = _make_analysis()
        out = tmp_path / "report.html"

        render_report(sessions, analysis, out)

        content = out.read_text()
        assert "teacher" in content
        assert "student" in content

    def test_contains_verdict_counts(self, tmp_path: Path) -> None:
        """Report HTML includes verdict count numbers."""
        steps = [
            _make_step(verdict=Verdict.PASS, step_number=1),
            _make_step(verdict=Verdict.PASS, step_number=2),
            _make_step(verdict=Verdict.FAIL, step_number=3),
        ]
        session = JourneySession.from_steps(persona="teacher", steps=steps, run_date="2026-03-20")
        analysis = _make_analysis(
            total_steps=3,
        )
        out = tmp_path / "report.html"

        render_report([session], analysis, out)

        content = out.read_text()
        # The analysis-level verdict counts should appear
        assert "pass" in content.lower()
        assert "fail" in content.lower()

    def test_contains_cross_persona_patterns(self, tmp_path: Path) -> None:
        """Report HTML includes cross-persona pattern IDs and titles."""
        pattern = CrossPersonaPattern(
            id="CPP-001",
            title="Navigation inconsistency",
            severity="high",
            affected_personas=["teacher", "student"],
            description="Both personas hit a broken nav link",
            evidence=["Step 3 in teacher session", "Step 2 in student session"],
            recommendation="Fix the sidebar link",
        )
        session = JourneySession.from_steps(
            persona="teacher",
            steps=[_make_step()],
            run_date="2026-03-20",
        )
        analysis = _make_analysis(patterns=[pattern])
        out = tmp_path / "report.html"

        render_report([session], analysis, out)

        content = out.read_text()
        assert "CPP-001" in content
        assert "Navigation inconsistency" in content

    def test_contains_dead_ends(self, tmp_path: Path) -> None:
        """Report HTML includes dead-end entries."""
        dead_end = DeadEnd(
            id="DE-001",
            persona="teacher",
            page="/app/settings",
            story=None,
            description="Settings page has no back button",
        )
        session = JourneySession.from_steps(
            persona="teacher",
            steps=[_make_step()],
            run_date="2026-03-20",
        )
        analysis = _make_analysis(dead_ends=[dead_end])
        out = tmp_path / "report.html"

        render_report([session], analysis, out)

        content = out.read_text()
        assert "DE-001" in content
        assert "Settings page has no back button" in content

    def test_contains_nav_breaks(self, tmp_path: Path) -> None:
        """Report HTML includes nav-break entries."""
        nav_break = NavBreak(
            id="NB-001",
            description="Sidebar link to reports returns 404",
            affected_personas=["teacher"],
            workaround="Use direct URL",
        )
        session = JourneySession.from_steps(
            persona="teacher",
            steps=[_make_step()],
            run_date="2026-03-20",
        )
        analysis = _make_analysis(nav_breaks=[nav_break])
        out = tmp_path / "report.html"

        render_report([session], analysis, out)

        content = out.read_text()
        assert "NB-001" in content
        assert "Sidebar link to reports returns 404" in content

    def test_contains_recommendations(self, tmp_path: Path) -> None:
        """Report HTML includes recommendation titles and priorities."""
        rec = Recommendation(
            priority=1,
            title="Fix broken navigation",
            description="Several nav links return 404",
            effort="low",
            affected_entities=["Task", "Report"],
        )
        session = JourneySession.from_steps(
            persona="teacher",
            steps=[_make_step()],
            run_date="2026-03-20",
        )
        analysis = _make_analysis(recommendations=[rec])
        out = tmp_path / "report.html"

        render_report([session], analysis, out)

        content = out.read_text()
        assert "Fix broken navigation" in content
        assert "low" in content.lower()

    def test_empty_sessions_shows_no_data_message(self, tmp_path: Path) -> None:
        """Empty sessions produce a report with a 'No journey data' message."""
        analysis = _make_analysis(personas_analysed=0, total_steps=0, total_stories=0)
        out = tmp_path / "report.html"

        render_report([], analysis, out)

        content = out.read_text()
        assert "No journey data" in content

    def test_summary_stats_present(self, tmp_path: Path) -> None:
        """Report includes summary stats at the top."""
        session = JourneySession.from_steps(
            persona="teacher",
            steps=[_make_step()],
            run_date="2026-03-20",
        )
        analysis = _make_analysis(personas_analysed=2, total_steps=5, total_stories=3)
        out = tmp_path / "report.html"

        render_report([session], analysis, out)

        content = out.read_text()
        # Summary stats should be present
        assert "2" in content  # personas_analysed
        assert "5" in content  # total_steps
        assert "3" in content  # total_stories

    def test_verdict_color_badges(self, tmp_path: Path) -> None:
        """Report uses different CSS classes/colors for different verdicts."""
        steps = [
            _make_step(verdict=Verdict.PASS, step_number=1),
            _make_step(verdict=Verdict.FAIL, step_number=2),
            _make_step(verdict=Verdict.PARTIAL, step_number=3),
            _make_step(verdict=Verdict.BLOCKED, step_number=4),
        ]
        session = JourneySession.from_steps(persona="teacher", steps=steps, run_date="2026-03-20")
        analysis = _make_analysis()
        out = tmp_path / "report.html"

        render_report([session], analysis, out)

        content = out.read_text()
        # Each verdict value should appear in the HTML as badge text
        assert "pass" in content.lower()
        assert "fail" in content.lower()
        assert "partial" in content.lower()
        assert "blocked" in content.lower()

    def test_self_contained_inline_css(self, tmp_path: Path) -> None:
        """Report HTML is self-contained with inline CSS, no external links."""
        session = JourneySession.from_steps(
            persona="teacher",
            steps=[_make_step()],
            run_date="2026-03-20",
        )
        analysis = _make_analysis()
        out = tmp_path / "report.html"

        render_report([session], analysis, out)

        content = out.read_text()
        assert "<style>" in content
        # Should NOT have external stylesheet links
        assert 'rel="stylesheet"' not in content

    def test_severity_badges_on_patterns(self, tmp_path: Path) -> None:
        """Cross-persona patterns show severity badges."""
        pattern = CrossPersonaPattern(
            id="CPP-002",
            title="Scope leak detected",
            severity="critical",
            affected_personas=["teacher"],
            description="Teacher can see student-only data",
            evidence=["Step 5"],
            recommendation="Review scope rules",
        )
        session = JourneySession.from_steps(
            persona="teacher",
            steps=[_make_step()],
            run_date="2026-03-20",
        )
        analysis = _make_analysis(patterns=[pattern])
        out = tmp_path / "report.html"

        render_report([session], analysis, out)

        content = out.read_text()
        assert "critical" in content.lower()
