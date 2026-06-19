"""#1392 item 3 P1 — the `emits:` surface clause parses into SurfaceSpec.emits."""

from __future__ import annotations

from pathlib import Path

from dazzle.core.dsl_parser_impl import parse_dsl

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


def _surfaces(dsl: str):
    n, a, t, c, u, frag = parse_dsl(dsl, Path("t.dsl"))
    return {s.name: s for s in frag.surfaces}


def test_emits_clause_parses_into_tuple() -> None:
    board = _surfaces(_DSL)["task_board"]
    assert board.emits == ("task_detail", "task_create")


def test_absent_emits_defaults_empty() -> None:
    assert _surfaces(_DSL)["task_detail"].emits == ()
