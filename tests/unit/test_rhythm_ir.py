"""Tests for rhythm IR types."""

import pytest
from pydantic import ValidationError

from dazzle.core.ir.rhythm import PhaseKind, PhaseSpec, RhythmSpec, SceneSpec


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
