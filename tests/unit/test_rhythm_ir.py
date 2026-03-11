"""Tests for rhythm IR types."""

import pytest
from pydantic import ValidationError

from dazzle.core.ir.rhythm import (
    Gap,
    GapsReport,
    GapsSummary,
    LifecycleReport,
    LifecycleStep,
    PhaseKind,
    PhaseSpec,
    RhythmSpec,
    SceneDimensionScore,
    SceneEvaluation,
    SceneSpec,
)


def test_scene_spec_minimal():
    scene = SceneSpec(name="browse", surface="course_list")
    assert scene.name == "browse"
    assert scene.surface == "course_list"
    assert scene.actions == []
    assert scene.entity is None
    assert scene.expects is None
    assert scene.story is None
    assert scene.title is None


def test_scene_spec_full():
    scene = SceneSpec(
        name="enroll",
        title="Enroll in Course",
        surface="course_detail",
        actions=["submit"],
        entity="Enrollment",
        expects="enrollment_confirmed",
        story="enroll_story",
    )
    assert scene.title == "Enroll in Course"
    assert scene.actions == ["submit"]
    assert scene.entity == "Enrollment"
    assert scene.expects == "enrollment_confirmed"
    assert scene.story == "enroll_story"


def test_scene_spec_frozen():
    scene = SceneSpec(name="browse", surface="course_list")
    try:
        scene.name = "other"
        assert False, "Should have raised"
    except Exception:
        pass


def test_phase_spec():
    scenes = [
        SceneSpec(name="browse", surface="course_list"),
        SceneSpec(name="enroll", surface="course_detail"),
    ]
    phase = PhaseSpec(name="discovery", scenes=scenes)
    assert phase.name == "discovery"
    assert len(phase.scenes) == 2


def test_rhythm_spec_minimal():
    rhythm = RhythmSpec(name="onboarding", persona="new_user")
    assert rhythm.name == "onboarding"
    assert rhythm.persona == "new_user"
    assert rhythm.cadence is None
    assert rhythm.phases == []
    assert rhythm.title is None


def test_rhythm_spec_full():
    rhythm = RhythmSpec(
        name="onboarding",
        title="New User Onboarding",
        persona="new_user",
        cadence="quarterly",
        phases=[
            PhaseSpec(
                name="discovery",
                scenes=[SceneSpec(name="browse", surface="course_list")],
            ),
            PhaseSpec(
                name="mastery",
                scenes=[SceneSpec(name="progress", surface="dashboard")],
            ),
        ],
    )
    assert rhythm.title == "New User Onboarding"
    assert rhythm.cadence == "quarterly"
    assert len(rhythm.phases) == 2
    assert rhythm.phases[0].scenes[0].name == "browse"


def test_phase_kind_enum_values():
    assert PhaseKind.ONBOARDING.value == "onboarding"
    assert PhaseKind.ACTIVE.value == "active"
    assert PhaseKind.PERIODIC.value == "periodic"
    assert PhaseKind.AMBIENT.value == "ambient"
    assert PhaseKind.OFFBOARDING.value == "offboarding"


def test_phase_spec_kind_none_by_default():
    phase = PhaseSpec(name="test", scenes=[])
    assert phase.kind is None


def test_phase_spec_kind_set():
    phase = PhaseSpec(name="test", kind=PhaseKind.AMBIENT, scenes=[])
    assert phase.kind == PhaseKind.AMBIENT


def test_phase_spec_kind_frozen():
    phase = PhaseSpec(name="test", kind=PhaseKind.ACTIVE, scenes=[])
    with pytest.raises(ValidationError):
        phase.kind = PhaseKind.AMBIENT


# --- Task 4: Evaluation models ---


def test_scene_dimension_score_creation():
    score = SceneDimensionScore(
        dimension="arrival",
        score="pass",
        evidence="Page loaded successfully",
        root_cause=None,
    )
    assert score.dimension == "arrival"
    assert score.score == "pass"


def test_scene_dimension_score_with_root_cause():
    score = SceneDimensionScore(
        dimension="action",
        score="fail",
        evidence="Submit button not found",
        root_cause="Missing story: create_task",
    )
    assert score.root_cause == "Missing story: create_task"


def test_scene_evaluation_creation():
    dims = [
        SceneDimensionScore(dimension="arrival", score="pass", evidence="ok"),
        SceneDimensionScore(dimension="orientation", score="pass", evidence="ok"),
        SceneDimensionScore(dimension="action", score="fail", evidence="no button"),
        SceneDimensionScore(dimension="completion", score="skip", evidence="n/a"),
        SceneDimensionScore(dimension="confidence", score="skip", evidence="n/a"),
    ]
    ev = SceneEvaluation(
        scene_name="browse",
        phase_name="discovery",
        dimensions=dims,
        gap_type="capability",
        story_ref="browse_courses",
    )
    assert ev.gap_type == "capability"
    assert len(ev.dimensions) == 5


# --- Task 5: Gap models ---


def test_gap_creation():
    gap = Gap(
        kind="capability",
        severity="blocking",
        scene="browse",
        phase="discovery",
        rhythm="onboarding",
        persona="new_user",
        story_ref="browse_courses",
        surface_ref="course_list",
        description="Story 'browse_courses' is DRAFT",
    )
    assert gap.kind == "capability"
    assert gap.severity == "blocking"


def test_gaps_summary():
    summary = GapsSummary(
        total=3,
        by_kind={"capability": 2, "ambient": 1},
        by_severity={"blocking": 2, "advisory": 1},
        by_persona={"new_user": 3},
    )
    assert summary.total == 3


def test_gaps_report():
    gap = Gap(
        kind="ambient",
        severity="advisory",
        scene=None,
        phase=None,
        rhythm="onboarding",
        persona="new_user",
        story_ref=None,
        surface_ref=None,
        description="No ambient phase for persona 'new_user'",
    )
    report = GapsReport(
        gaps=[gap],
        summary=GapsSummary(
            total=1,
            by_kind={"ambient": 1},
            by_severity={"advisory": 1},
            by_persona={"new_user": 1},
        ),
        roadmap_order=[gap],
    )
    assert len(report.gaps) == 1
    assert report.roadmap_order[0].kind == "ambient"


# --- Task 6: Lifecycle models ---


def test_lifecycle_step():
    step = LifecycleStep(
        step=1,
        name="model_domain",
        status="complete",
        evidence="5 entities with fields and relationships",
        suggestions=[],
    )
    assert step.status == "complete"


def test_lifecycle_report():
    steps = [
        LifecycleStep(
            step=1, name="model_domain", status="complete", evidence="ok", suggestions=[]
        ),
        LifecycleStep(
            step=2,
            name="write_stories",
            status="not_started",
            evidence="",
            suggestions=["Run story propose"],
        ),
    ]
    report = LifecycleReport(steps=steps, current_focus="write_stories", maturity="new_domain")
    assert report.maturity == "new_domain"
    assert report.current_focus == "write_stories"
