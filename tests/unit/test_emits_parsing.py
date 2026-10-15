"""#1392 item 3 P1 — the `emits:` surface clause parses into SurfaceSpec.emits."""

from __future__ import annotations

import pytest

from tests.unit.helpers.dsl import parse_fragment

_DSL = """module t
app t "T"
entity Task "Task":
  id: uuid pk
  title: str(80)
surface task_detail "Detail":
  uses entity Task
  mode: view
  section main:
    field title "Title"
surface task_create "New":
  uses entity Task
  mode: create
  section main:
    field title "Title"
surface task_board "Board":
  uses entity Task
  mode: custom
  render: kanban_viewer
  emits: [task_detail, task_create]
"""


@pytest.mark.parametrize(
    ("surface", "expected"),
    [
        pytest.param("task_board", ("task_detail", "task_create"), id="declared-in-order"),
        pytest.param("task_detail", (), id="absent-defaults-empty"),
    ],
)
def test_emits_clause(surface: str, expected: tuple[str, ...]) -> None:
    surfaces = {s.name: s for s in parse_fragment(_DSL).surfaces}
    assert surfaces[surface].emits == expected
