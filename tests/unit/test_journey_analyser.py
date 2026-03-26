"""Tests for cross-persona pattern analyser."""

from datetime import UTC, datetime

from dazzle.agent.journey_analyser import analyse_sessions
from dazzle.agent.journey_models import (
    AnalysisReport,
    DeadEnd,
    JourneySession,
    JourneyStep,
    NavBreak,
    Recommendation,
    Verdict,
)


def _step(
    persona: str = "teacher",
    phase: str = "explore",
    step_number: int = 1,
    action: str = "navigate",
    target: str = "/app/tasks",
    url_before: str = "/app/",
    url_after: str = "/app/tasks",
    expectation: str = "see tasks",
    observation: str = "tasks visible",
    verdict: Verdict = Verdict.PASS,
    reasoning: str = "ok",
    story_id: str | None = None,
) -> JourneyStep:
    """Helper to build a JourneyStep with sensible defaults."""
    return JourneyStep(
        persona=persona,
        phase=phase,
        step_number=step_number,
        action=action,
        target=target,
        url_before=url_before,
        url_after=url_after,
        expectation=expectation,
        observation=observation,
        verdict=verdict,
        reasoning=reasoning,
        story_id=story_id,
        timestamp=datetime(2026, 3, 20, tzinfo=UTC),
    )


def _session(persona: str, steps: list[JourneyStep]) -> JourneySession:
    return JourneySession.from_steps(persona=persona, steps=steps, run_date="2026-03-20")


# ---- Empty / edge cases ----


class TestEmptySessions:
    def test_no_sessions(self) -> None:
        report = analyse_sessions([])
        assert isinstance(report, AnalysisReport)
        assert report.cross_persona_patterns == []
        assert report.dead_ends == []
        assert report.nav_breaks == []
        assert report.recommendations == []
        assert report.personas_analysed == 0
        assert report.total_steps == 0

    def test_single_persona_no_scope_patterns(self) -> None:
        """A single persona cannot produce scope-leak patterns (need 2+)."""
        session = _session(
            "teacher",
            [
                _step(persona="teacher", observation="5 rows displayed", target="/app/tasks"),
            ],
        )
        report = analyse_sessions([session])
        scope_patterns = [p for p in report.cross_persona_patterns if "scope" in p.title.lower()]
        assert scope_patterns == []


# ---- Scope leak detection ----


class TestScopeLeakDetection:
    def test_scope_leak_different_row_counts(self) -> None:
        """Persona A sees 5 rows, persona B sees 0 rows => scope issue."""
        teacher_session = _session(
            "teacher",
            [
                _step(
                    persona="teacher",
                    target="/app/tasks",
                    observation="Table loaded with 5 rows visible",
                    verdict=Verdict.PASS,
                ),
            ],
        )
        student_session = _session(
            "student",
            [
                _step(
                    persona="student",
                    target="/app/tasks",
                    observation="Table shows 0 rows, list is empty",
                    verdict=Verdict.PASS,
                ),
            ],
        )
        report = analyse_sessions([teacher_session, student_session])
        scope_patterns = [p for p in report.cross_persona_patterns if "scope" in p.title.lower()]
        assert len(scope_patterns) >= 1
        pattern = scope_patterns[0]
        assert pattern.id.startswith("CPP-")
        assert set(pattern.affected_personas) == {"teacher", "student"}

    def test_scope_leak_populated_vs_empty(self) -> None:
        """One persona sees data, another sees 'empty'."""
        s1 = _session(
            "admin",
            [
                _step(persona="admin", target="/app/orders", observation="Showing 12 rows"),
            ],
        )
        s2 = _session(
            "viewer",
            [
                _step(persona="viewer", target="/app/orders", observation="The list is empty"),
            ],
        )
        report = analyse_sessions([s1, s2])
        scope_patterns = [p for p in report.cross_persona_patterns if "scope" in p.title.lower()]
        assert len(scope_patterns) >= 1


# ---- FK UUID detection ----


class TestFkUuidDetection:
    def test_uuid_in_observation(self) -> None:
        session = _session(
            "teacher",
            [
                _step(
                    persona="teacher",
                    target="/app/tasks/create",
                    observation="Field 'assigned_to' shows raw UUID instead of display name",
                    verdict=Verdict.FAIL,
                ),
            ],
        )
        report = analyse_sessions([session])
        fk_patterns = [
            p
            for p in report.cross_persona_patterns
            if "uuid" in p.title.lower() or "fk" in p.title.lower()
        ]
        assert len(fk_patterns) >= 1

    def test_text_input_for_ref_field(self) -> None:
        session = _session(
            "teacher",
            [
                _step(
                    persona="teacher",
                    target="/app/tasks/create",
                    observation="Reference field rendered as plain text input, expects manual ID entry",
                    verdict=Verdict.FAIL,
                ),
            ],
        )
        report = analyse_sessions([session])
        fk_patterns = [
            p
            for p in report.cross_persona_patterns
            if "uuid" in p.title.lower() or "fk" in p.title.lower()
        ]
        assert len(fk_patterns) >= 1


# ---- Navigation gap detection ----


class TestNavigationGap:
    def test_blocked_step_produces_pattern(self) -> None:
        session = _session(
            "teacher",
            [
                _step(
                    persona="teacher",
                    target="/app/reports",
                    verdict=Verdict.BLOCKED,
                    observation="Page returned 403",
                    reasoning="Cannot access reports",
                ),
            ],
        )
        report = analyse_sessions([session])
        nav_patterns = [
            p
            for p in report.cross_persona_patterns
            if "navigation" in p.title.lower() or "blocked" in p.title.lower()
        ]
        assert len(nav_patterns) >= 1


# ---- Common failures (systemic) ----


class TestCommonFailures:
    def test_three_personas_fail_same_entity_is_systemic(self) -> None:
        sessions = []
        for persona in ["teacher", "student", "admin"]:
            sessions.append(
                _session(
                    persona,
                    [
                        _step(
                            persona=persona,
                            target="/app/assignments",
                            verdict=Verdict.FAIL,
                            observation="Page crashed with error 500",
                        ),
                    ],
                )
            )
        report = analyse_sessions(sessions)
        systemic = [p for p in report.cross_persona_patterns if len(p.affected_personas) >= 3]
        assert len(systemic) >= 1
        assert systemic[0].severity in ("high", "critical")

    def test_two_personas_fail_not_systemic(self) -> None:
        """Two personas failing is not enough for systemic threshold."""
        sessions = []
        for persona in ["teacher", "student"]:
            sessions.append(
                _session(
                    persona,
                    [
                        _step(
                            persona=persona,
                            target="/app/assignments",
                            verdict=Verdict.FAIL,
                            observation="Page crashed",
                        ),
                    ],
                )
            )
        report = analyse_sessions(sessions)
        systemic = [p for p in report.cross_persona_patterns if len(p.affected_personas) >= 3]
        assert systemic == []


# ---- Dead-end extraction ----


class TestDeadEnds:
    def test_dead_end_verdict_produces_dead_end(self) -> None:
        session = _session(
            "teacher",
            [
                _step(
                    persona="teacher",
                    target="/app/tasks/detail",
                    verdict=Verdict.DEAD_END,
                    observation="No back button or navigation, stuck on page",
                    story_id="story-1",
                ),
            ],
        )
        report = analyse_sessions([session])
        assert len(report.dead_ends) == 1
        de = report.dead_ends[0]
        assert isinstance(de, DeadEnd)
        assert de.id.startswith("DE-")
        assert de.persona == "teacher"
        assert de.page == "/app/tasks/detail"
        assert de.story == "story-1"

    def test_multiple_dead_ends(self) -> None:
        session = _session(
            "student",
            [
                _step(
                    persona="student",
                    target="/app/tasks/detail",
                    verdict=Verdict.DEAD_END,
                    observation="Stuck",
                    step_number=1,
                ),
                _step(
                    persona="student",
                    target="/app/grades",
                    verdict=Verdict.DEAD_END,
                    observation="No way out",
                    step_number=2,
                ),
            ],
        )
        report = analyse_sessions([session])
        assert len(report.dead_ends) == 2
        ids = [de.id for de in report.dead_ends]
        assert ids[0] != ids[1]


# ---- Nav break extraction ----


class TestNavBreaks:
    def test_nav_break_verdict_produces_nav_break(self) -> None:
        session = _session(
            "teacher",
            [
                _step(
                    persona="teacher",
                    target="/app/settings",
                    verdict=Verdict.NAV_BREAK,
                    observation="Link leads to 404 page",
                ),
            ],
        )
        report = analyse_sessions([session])
        assert len(report.nav_breaks) == 1
        nb = report.nav_breaks[0]
        assert isinstance(nb, NavBreak)
        assert nb.id.startswith("NB-")
        assert "teacher" in nb.affected_personas

    def test_same_nav_break_across_personas_merged(self) -> None:
        """If two personas hit the same broken nav target, they merge."""
        s1 = _session(
            "teacher",
            [
                _step(
                    persona="teacher",
                    target="/app/settings",
                    verdict=Verdict.NAV_BREAK,
                    observation="404",
                ),
            ],
        )
        s2 = _session(
            "student",
            [
                _step(
                    persona="student",
                    target="/app/settings",
                    verdict=Verdict.NAV_BREAK,
                    observation="404",
                ),
            ],
        )
        report = analyse_sessions([s1, s2])
        assert len(report.nav_breaks) == 1
        nb = report.nav_breaks[0]
        assert set(nb.affected_personas) == {"teacher", "student"}


# ---- Recommendation generation ----


class TestRecommendations:
    def test_patterns_produce_recommendations(self) -> None:
        """Any patterns should produce at least one recommendation."""
        session = _session(
            "teacher",
            [
                _step(
                    persona="teacher",
                    target="/app/tasks/create",
                    observation="Field shows raw UUID",
                    verdict=Verdict.FAIL,
                ),
            ],
        )
        report = analyse_sessions([session])
        assert len(report.recommendations) >= 1
        rec = report.recommendations[0]
        assert isinstance(rec, Recommendation)
        assert rec.priority >= 1
        assert rec.effort != ""

    def test_recommendations_sorted_by_priority(self) -> None:
        """Recommendations should be sorted by priority (1 = highest)."""
        sessions = [
            _session(
                "teacher",
                [
                    _step(
                        persona="teacher",
                        target="/app/tasks/create",
                        observation="UUID displayed",
                        verdict=Verdict.FAIL,
                    ),
                    _step(
                        persona="teacher",
                        target="/app/reports",
                        verdict=Verdict.BLOCKED,
                        observation="403 forbidden",
                    ),
                ],
            ),
        ]
        report = analyse_sessions(sessions)
        if len(report.recommendations) >= 2:
            priorities = [r.priority for r in report.recommendations]
            assert priorities == sorted(priorities)


# ---- Report metadata ----


class TestReportMetadata:
    def test_report_counts(self) -> None:
        s1 = _session(
            "teacher",
            [
                _step(persona="teacher", step_number=1),
                _step(persona="teacher", step_number=2),
            ],
        )
        s2 = _session(
            "student",
            [
                _step(persona="student", step_number=1),
            ],
        )
        report = analyse_sessions([s1, s2])
        assert report.personas_analysed == 2
        assert report.total_steps == 3

    def test_custom_version_and_url(self) -> None:
        report = analyse_sessions(
            [], dazzle_version="1.0.0", deployment_url="http://localhost:8000"
        )
        assert report.dazzle_version == "1.0.0"
        assert report.deployment_url == "http://localhost:8000"

    def test_sequential_pattern_ids(self) -> None:
        """Pattern IDs should be sequential CPP-001, CPP-002, etc."""
        sessions = [
            _session(
                "teacher",
                [
                    _step(
                        persona="teacher",
                        target="/app/tasks/create",
                        observation="UUID shown",
                        verdict=Verdict.FAIL,
                    ),
                    _step(
                        persona="teacher",
                        target="/app/reports",
                        verdict=Verdict.BLOCKED,
                        observation="Blocked",
                    ),
                ],
            ),
        ]
        report = analyse_sessions(sessions)
        if len(report.cross_persona_patterns) >= 2:
            ids = [p.id for p in report.cross_persona_patterns]
            for i, pid in enumerate(ids, 1):
                assert pid == f"CPP-{i:03d}"
