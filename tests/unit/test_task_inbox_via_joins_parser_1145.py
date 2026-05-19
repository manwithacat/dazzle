"""#1145 part 2: parser tests for `as_task.via:` cross-entity
alias maps."""

from __future__ import annotations

import pytest

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.errors import ParseError


def _parse(body: str) -> object:
    src = f"""module ops
app demo_app "Demo"

entity Item "Item":
  id: uuid pk
  state: str(50)
  name: str(100)

workspace dash "Dash":
  inbox:
    source: Item
    display: task_inbox
    task_inbox_config:
{body}
"""
    result = parse_dsl(src, "test.dsl")
    fragment = result[5]
    return fragment.workspaces[0].regions[0].task_inbox_config


def test_parses_via_block_single_alias() -> None:
    cfg = _parse(
        """      sources:
        - source: Item
          as_task:
            icon: pupil
            title: "Follow up with {{ student.forename }}"
            via:
              student: behaviour_student.student_profile
"""
    )
    src = cfg.sources[0]
    assert src.as_task is not None
    assert src.as_task.via_joins == {"student": "behaviour_student.student_profile"}


def test_parses_via_block_multiple_aliases() -> None:
    cfg = _parse(
        """      sources:
        - source: Item
          as_task:
            icon: pupil
            title: "{{ pupil.forename }} ({{ year.label }})"
            via:
              pupil: student_profile
              year: year_group
"""
    )
    via = cfg.sources[0].as_task.via_joins
    assert via == {"pupil": "student_profile", "year": "year_group"}


def test_parses_via_with_long_dotted_path() -> None:
    """Dotted paths with multiple segments — e.g.
    `BehaviourIncident → BehaviourStudent → StudentProfile`."""
    cfg = _parse(
        """      sources:
        - source: Item
          as_task:
            icon: pupil
            title: "{{ deep.value }}"
            via:
              deep: a.b.c.d.e
"""
    )
    assert cfg.sources[0].as_task.via_joins == {"deep": "a.b.c.d.e"}


def test_via_absent_means_empty_dict() -> None:
    """Regression guard: `as_task:` without `via:` declared keeps
    via_joins empty — no behaviour change for pre-#1145-part-2
    templates."""
    cfg = _parse(
        """      sources:
        - source: Item
          as_task:
            icon: pupil
            title: "Hello"
"""
    )
    assert cfg.sources[0].as_task.via_joins == {}


def test_unknown_as_task_key_rejected() -> None:
    """The valid-keys set was extended with `via` in #1145 part 2;
    other keys still raise."""
    with pytest.raises(ParseError, match="Unknown as_task key"):
        _parse(
            """      sources:
        - source: Item
          as_task:
            icon: pupil
            title: "x"
            bogus: nope
"""
        )
