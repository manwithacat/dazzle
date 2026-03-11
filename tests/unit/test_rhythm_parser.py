"""Tests for rhythm DSL parser."""

from pathlib import Path

import pytest

from dazzle.core.dsl_parser_impl import parse_dsl


def test_parse_minimal_rhythm():
    dsl = """\
module test_app
app test "Test"

rhythm onboarding "New User Onboarding":
  persona: new_user

  phase discovery:
    scene browse "Browse Courses":
      on: course_list
"""
    _mod, _app, _title, _config, _uses, fragment = parse_dsl(dsl, Path("test.dsl"))
    assert len(fragment.rhythms) == 1
    rhythm = fragment.rhythms[0]
    assert rhythm.name == "onboarding"
    assert rhythm.title == "New User Onboarding"
    assert rhythm.persona == "new_user"
    assert len(rhythm.phases) == 1
    assert rhythm.phases[0].name == "discovery"
    assert len(rhythm.phases[0].scenes) == 1
    scene = rhythm.phases[0].scenes[0]
    assert scene.name == "browse"
    assert scene.title == "Browse Courses"
    assert scene.surface == "course_list"


def test_parse_rhythm_with_cadence():
    dsl = """\
module test_app
app test "Test"

rhythm onboarding "Onboarding":
  persona: new_user
  cadence: "quarterly"

  phase discovery:
    scene browse "Browse":
      on: course_list
"""
    _mod, _app, _title, _config, _uses, fragment = parse_dsl(dsl, Path("test.dsl"))
    rhythm = fragment.rhythms[0]
    assert rhythm.cadence == "quarterly"


def test_parse_scene_with_all_fields():
    dsl = """\
module test_app
app test "Test"

rhythm onboarding "Onboarding":
  persona: new_user

  phase engagement:
    scene enroll "Enroll in Course":
      on: course_detail
      action: submit, browse
      entity: Enrollment
      expects: "enrollment_confirmed"
      story: enroll_story
"""
    _mod, _app, _title, _config, _uses, fragment = parse_dsl(dsl, Path("test.dsl"))
    scene = fragment.rhythms[0].phases[0].scenes[0]
    assert scene.surface == "course_detail"
    assert scene.actions == ["submit", "browse"]
    assert scene.entity == "Enrollment"
    assert scene.expects == "enrollment_confirmed"
    assert scene.story == "enroll_story"


def test_parse_multiple_phases():
    dsl = """\
module test_app
app test "Test"

rhythm onboarding "Onboarding":
  persona: new_user

  phase discovery:
    scene browse "Browse":
      on: course_list

  phase engagement:
    scene enroll "Enroll":
      on: course_detail
    scene study "Study":
      on: module_view

  phase mastery:
    scene progress "Check Progress":
      on: dashboard
"""
    _mod, _app, _title, _config, _uses, fragment = parse_dsl(dsl, Path("test.dsl"))
    rhythm = fragment.rhythms[0]
    assert len(rhythm.phases) == 3
    assert rhythm.phases[0].name == "discovery"
    assert len(rhythm.phases[0].scenes) == 1
    assert rhythm.phases[1].name == "engagement"
    assert len(rhythm.phases[1].scenes) == 2
    assert rhythm.phases[2].name == "mastery"
    assert len(rhythm.phases[2].scenes) == 1


def test_parse_rhythm_missing_persona_raises():
    dsl = """\
module test_app
app test "Test"

rhythm onboarding "Onboarding":
  phase discovery:
    scene browse "Browse":
      on: course_list
"""
    with pytest.raises(Exception, match="persona"):
        parse_dsl(dsl, Path("test.dsl"))


def test_parse_phase_with_kind():
    dsl = """\
module test_app
app test "Test"

rhythm onboarding "Onboarding":
  persona: new_user

  phase setup:
    kind: onboarding
    scene browse "Browse":
      on: course_list
"""
    _mod, _app, _title, _config, _uses, fragment = parse_dsl(dsl, Path("test.dsl"))
    phase = fragment.rhythms[0].phases[0]
    assert phase.kind is not None
    assert phase.kind.value == "onboarding"


def test_parse_phase_kind_all_values():
    for kind_val in ["onboarding", "active", "periodic", "ambient", "offboarding"]:
        dsl = f"""\
module test_app
app test "Test"

rhythm r "R":
  persona: user

  phase p:
    kind: {kind_val}
    scene s "S":
      on: surf
"""
        _mod, _app, _title, _config, _uses, fragment = parse_dsl(dsl, Path("test.dsl"))
        assert fragment.rhythms[0].phases[0].kind is not None
        assert fragment.rhythms[0].phases[0].kind.value == kind_val


def test_parse_phase_without_kind_is_none():
    dsl = """\
module test_app
app test "Test"

rhythm onboarding "Onboarding":
  persona: new_user

  phase discovery:
    scene browse "Browse":
      on: course_list
"""
    _mod, _app, _title, _config, _uses, fragment = parse_dsl(dsl, Path("test.dsl"))
    assert fragment.rhythms[0].phases[0].kind is None


def test_parse_phase_invalid_kind_ignored():
    dsl = """\
module test_app
app test "Test"

rhythm r "R":
  persona: user

  phase p:
    kind: nonexistent
    scene s "S":
      on: surf
"""
    _mod, _app, _title, _config, _uses, fragment = parse_dsl(dsl, Path("test.dsl"))
    assert fragment.rhythms[0].phases[0].kind is None


def test_parse_scene_missing_on_raises():
    dsl = """\
module test_app
app test "Test"

rhythm onboarding "Onboarding":
  persona: new_user

  phase discovery:
    scene browse "Browse":
      action: browse
"""
    with pytest.raises(Exception, match="on"):
        parse_dsl(dsl, Path("test.dsl"))
