"""Tests for rhythm linker validation."""

from pathlib import Path

import pytest

from dazzle.core.dsl_parser_impl import parse_dsl


def _build_appspec(dsl: str):
    """Parse DSL and build appspec."""
    from dazzle.core.ir import ModuleIR
    from dazzle.core.linker import build_appspec

    mod_name, app_name, app_title, app_config, uses, fragment = parse_dsl(dsl, Path("test.dsl"))
    module = ModuleIR(
        name=mod_name or "test",
        file=Path("test.dsl"),
        app_name=app_name,
        app_title=app_title,
        app_config=app_config,
        uses=uses,
        fragment=fragment,
    )
    return build_appspec([module], module.name)


def test_rhythm_collected_in_appspec():
    dsl = """\
module test_app
app test "Test"

persona new_user "New User":
  goals:
    - "Learn things"

entity Course "Course":
  id: uuid pk
  title: str(200) required

surface course_list "Courses":
  uses entity Course
  mode: list
  section main:
    field title "Title"

rhythm onboarding "Onboarding":
  persona: new_user

  phase discovery:
    scene browse "Browse":
      on: course_list
"""
    appspec = _build_appspec(dsl)
    assert len(appspec.rhythms) == 1
    assert appspec.rhythms[0].name == "onboarding"


def test_rhythm_invalid_persona_error():
    dsl = """\
module test_app
app test "Test"

surface course_list "Courses":
  mode: list
  section main:
    field title "Title"

entity Course "Course":
  id: uuid pk
  title: str(200) required

rhythm onboarding "Onboarding":
  persona: nonexistent_persona

  phase discovery:
    scene browse "Browse":
      on: course_list
"""
    with pytest.raises(Exception, match="persona|nonexistent"):
        _build_appspec(dsl)


def test_rhythm_invalid_surface_error():
    dsl = """\
module test_app
app test "Test"

persona new_user "New User":
  goals:
    - "Learn things"

rhythm onboarding "Onboarding":
  persona: new_user

  phase discovery:
    scene browse "Browse":
      on: nonexistent_surface
"""
    with pytest.raises(Exception, match="surface|nonexistent"):
        _build_appspec(dsl)


def test_rhythm_invalid_entity_error():
    dsl = """\
module test_app
app test "Test"

persona new_user "New User":
  goals:
    - "Learn things"

surface course_list "Courses":
  mode: list
  section main:
    field title "Title"

rhythm onboarding "Onboarding":
  persona: new_user

  phase discovery:
    scene enroll "Enroll":
      on: course_list
      entity: NonexistentEntity
"""
    with pytest.raises(Exception, match="entity|Nonexistent"):
        _build_appspec(dsl)


def test_rhythm_duplicate_scene_name_error():
    dsl = """\
module test_app
app test "Test"

persona new_user "New User":
  goals:
    - "Learn things"

surface course_list "Courses":
  mode: list
  section main:
    field title "Title"

rhythm onboarding "Onboarding":
  persona: new_user

  phase discovery:
    scene browse "Browse":
      on: course_list

  phase engagement:
    scene browse "Browse Again":
      on: course_list
"""
    with pytest.raises(Exception, match="[Dd]uplicate.*scene|scene.*browse"):
        _build_appspec(dsl)


def test_rhythm_story_reference_hyphenated():
    """Quoted hyphenated story IDs resolve correctly in linker."""
    dsl = """\
module test_app
app test "Test"

persona new_user "New User":
  goals:
    - "Learn things"

entity Course "Course":
  id: uuid pk
  title: str(200) required

surface course_list "Courses":
  uses entity Course
  mode: list
  section main:
    field title "Title"

story ST-020 "Browse available courses":
  actor: new_user
  trigger: user_click

  then:
    - "User sees courses"

rhythm onboarding "Onboarding":
  persona: new_user

  phase discovery:
    scene browse "Browse":
      on: course_list
      story: "ST-020"
"""
    appspec = _build_appspec(dsl)
    scene = appspec.rhythms[0].phases[0].scenes[0]
    assert scene.story == "ST-020"


def test_rhythm_invalid_story_reference_error():
    dsl = """\
module test_app
app test "Test"

persona new_user "New User":
  goals:
    - "Learn things"

surface course_list "Courses":
  mode: list
  section main:
    field title "Title"

rhythm onboarding "Onboarding":
  persona: new_user

  phase discovery:
    scene browse "Browse":
      on: course_list
      story: "ST-999"
"""
    with pytest.raises(Exception, match="story|ST-999"):
        _build_appspec(dsl)
