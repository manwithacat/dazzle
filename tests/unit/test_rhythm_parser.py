"""Tests for rhythm DSL parser."""

from __future__ import annotations

import pytest

from dazzle.core.errors import ParseError
from tests.unit.helpers.dsl import parse_fragment

_HEAD = 'module test_app\napp test "Test"\n\n'


def _rhythm(body: str):  # noqa: ANN202
    """Parse a module holding one rhythm and return it."""
    return parse_fragment(_HEAD + body).rhythms[0]


def _phase(phase_keys: str):  # noqa: ANN202
    """Parse a one-phase, one-scene rhythm whose phase carries ``phase_keys``."""
    return _rhythm(
        'rhythm r "R":\n  persona: user\n\n  phase p:\n'
        f"{phase_keys}"
        '    scene s "S":\n      on: surf\n'
    ).phases[0]


def _scene(scene_keys: str):  # noqa: ANN202
    """Parse a one-scene rhythm whose scene carries ``scene_keys``."""
    return (
        _rhythm(
            'rhythm onboarding "Onboarding":\n  persona: new_user\n\n'
            '  phase engagement:\n    scene enroll "Enroll":\n'
            f"{scene_keys}"
        )
        .phases[0]
        .scenes[0]
    )


def test_parse_minimal_rhythm() -> None:
    fragment = parse_fragment(
        _HEAD + 'rhythm onboarding "New User Onboarding":\n  persona: new_user\n\n'
        '  phase discovery:\n    scene browse "Browse Courses":\n      on: course_list\n'
    )
    assert len(fragment.rhythms) == 1
    rhythm = fragment.rhythms[0]
    assert (rhythm.name, rhythm.title, rhythm.persona) == (
        "onboarding",
        "New User Onboarding",
        "new_user",
    )
    assert [p.name for p in rhythm.phases] == ["discovery"]
    scene = rhythm.phases[0].scenes[0]
    assert (scene.name, scene.title, scene.surface) == ("browse", "Browse Courses", "course_list")
    assert len(rhythm.phases[0].scenes) == 1


def test_parse_rhythm_with_cadence() -> None:
    rhythm = _rhythm(
        'rhythm onboarding "Onboarding":\n  persona: new_user\n  cadence: "quarterly"\n\n'
        '  phase discovery:\n    scene browse "Browse":\n      on: course_list\n'
    )
    assert rhythm.cadence == "quarterly"


def test_parse_scene_with_all_fields() -> None:
    scene = _scene(
        "      on: course_detail\n"
        "      action: submit, browse\n"
        "      entity: Enrollment\n"
        '      expects: "enrollment_confirmed"\n'
        "      story: enroll_story\n"
    )
    assert scene.surface == "course_detail"
    assert scene.actions == ["submit", "browse"]
    assert scene.entity == "Enrollment"
    assert scene.expects == "enrollment_confirmed"
    assert scene.story == "enroll_story"


@pytest.mark.parametrize(
    ("story_src", "expected"),
    [
        # Regression: the lexer splits `ST-019` into IDENTIFIER '-' NUMBER and
        # the scene parser read only the leading identifier, so every
        # `story: ST-nnn` resolved to `ST` and failed link-time validation.
        pytest.param("ST-019", "ST-019", id="compound-id-unquoted"),
        pytest.param('"ST-020"', "ST-020", id="compound-id-quoted"),
        pytest.param("enroll_story", "enroll_story", id="bare-identifier"),
    ],
)
def test_parse_scene_story_reference(story_src: str, expected: str) -> None:
    scene = _scene(f"      on: course_detail\n      story: {story_src}\n")
    assert scene.story == expected


def test_parse_scene_thin_form_omits_on_when_story_cited() -> None:
    """A scene citing a story may omit `on:` — the surface is derived at link
    time (#1559 slice 3), so parsing leaves it None rather than raising."""
    scene = _scene("      story: ST-001\n")
    assert scene.surface is None
    assert scene.story == "ST-001"


def test_parse_multiple_phases() -> None:
    rhythm = _rhythm(
        'rhythm onboarding "Onboarding":\n  persona: new_user\n\n'
        '  phase discovery:\n    scene browse "Browse":\n      on: course_list\n\n'
        '  phase engagement:\n    scene enroll "Enroll":\n      on: course_detail\n'
        '    scene study "Study":\n      on: module_view\n\n'
        '  phase mastery:\n    scene progress "Check Progress":\n      on: dashboard\n'
    )
    assert [(p.name, len(p.scenes)) for p in rhythm.phases] == [
        ("discovery", 1),
        ("engagement", 2),
        ("mastery", 1),
    ]


@pytest.mark.parametrize(
    ("phase_keys", "expected_kind", "expected_cadence"),
    [
        *(
            pytest.param(f"    kind: {kind}\n", kind, None, id=f"kind-{kind}")
            for kind in ("onboarding", "active", "periodic", "ambient", "offboarding", "gate")
        ),
        pytest.param("", None, None, id="no-kind-no-cadence"),
        pytest.param("    kind: nonexistent\n", None, None, id="invalid-kind-ignored"),
        pytest.param(
            '    kind: ambient\n    cadence: "ad-hoc, between deadlines"\n',
            "ambient",
            "ad-hoc, between deadlines",
            id="kind-and-cadence",
        ),
        pytest.param(
            '    cadence: "January-March"\n', None, "January-March", id="cadence-without-kind"
        ),
    ],
)
def test_parse_phase_kind_and_cadence(
    phase_keys: str, expected_kind: str | None, expected_cadence: str | None
) -> None:
    phase = _phase(phase_keys)
    assert (phase.kind.value if phase.kind else None) == expected_kind
    assert phase.cadence == expected_cadence


def test_parse_phase_depends_on() -> None:
    rhythm = _rhythm(
        'rhythm fiscal "Fiscal Year":\n  persona: director\n\n'
        '  phase onboarding:\n    kind: gate\n    scene welcome "Welcome":\n      on: welcome_page\n\n'
        "  phase q1:\n    kind: periodic\n    depends_on: onboarding\n"
        '    scene review "Q1 Review":\n      on: dashboard\n'
    )
    assert [p.depends_on for p in rhythm.phases] == [None, "onboarding"]


@pytest.mark.parametrize(
    ("body", "error"),
    [
        pytest.param(
            'rhythm onboarding "Onboarding":\n  phase discovery:\n'
            '    scene browse "Browse":\n      on: course_list\n',
            "Rhythm missing required 'persona' field",
            id="missing-persona",
        ),
        pytest.param(
            'rhythm onboarding "Onboarding":\n  persona: new_user\n\n  phase discovery:\n'
            '    scene browse "Browse":\n      action: browse\n',
            "Scene missing required 'on' field",
            id="scene-missing-on-without-story",
        ),
    ],
)
def test_parse_rhythm_rejects(body: str, error: str) -> None:
    with pytest.raises(ParseError, match=error):
        parse_fragment(_HEAD + body)
