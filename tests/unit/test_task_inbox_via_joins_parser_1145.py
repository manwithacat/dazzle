"""#1145 part 2: parser tests for `as_task.via:` cross-entity
alias maps."""

from __future__ import annotations

from typing import Any

import pytest

from dazzle.core.errors import ParseError
from tests.unit.helpers.dsl import region_config


def parse_inbox(body: str) -> Any:
    return region_config(
        entity='entity Item "Item":\n  id: uuid pk\n  name: str(100)\n',
        display="task_inbox",
        body=body,
    )


def _as_task(extra: str) -> str:
    return (
        "sources:\n  - source: Item\n    as_task:\n"
        '      icon: pupil\n      title: "{{ x.y }}"\n' + extra
    )


@pytest.mark.parametrize(
    ("via_block", "expected"),
    [
        pytest.param(
            "      via:\n        student: behaviour_student.student_profile\n",
            {"student": "behaviour_student.student_profile"},
            id="single-alias",
        ),
        pytest.param(
            "      via:\n        pupil: student_profile\n        year: year_group\n",
            {"pupil": "student_profile", "year": "year_group"},
            id="multiple-aliases",
        ),
        pytest.param(
            # e.g. BehaviourIncident → BehaviourStudent → StudentProfile
            "      via:\n        deep: a.b.c.d.e\n",
            {"deep": "a.b.c.d.e"},
            id="long-dotted-path",
        ),
        pytest.param(
            # No behaviour change for pre-#1145-part-2 templates.
            "",
            {},
            id="absent-means-empty",
        ),
    ],
)
def test_parses_via_joins(via_block: str, expected: dict[str, str]) -> None:
    cfg = parse_inbox(_as_task(via_block))
    assert cfg.sources[0].as_task.via_joins == expected


def test_unknown_as_task_key_rejected() -> None:
    """The valid-keys set was extended with `via` in #1145 part 2;
    other keys still raise."""
    with pytest.raises(ParseError, match="Unknown as_task key"):
        parse_inbox(_as_task("      bogus: nope\n"))
