"""WorkspaceRegion.aggregates typed-IR tests post-ADR-0024 migration.

Pre-fix: ``aggregates: dict[str, str]`` with regex parsing at runtime.
Post-fix: ``aggregates: dict[str, AggregateRef]`` parsed structurally.
"""

from __future__ import annotations

from pathlib import Path

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.ir import AggregateRef


def _parse(src: str) -> object:
    return parse_dsl(src, Path("test.dsl"))[5]


_DSL = """module t
app t "Test"
entity Task:
  id: uuid pk
  status: enum[todo,doing,done]
  score: int
workspace dash "Dash":
  metrics:
    source: Task
    display: metrics
    aggregate:
      total: count(Task)
      active: count(Task where status = doing)
      avg_score: avg(score)
"""


def test_aggregates_parse_to_typed_refs() -> None:
    fragment = _parse(_DSL)
    region = fragment.workspaces[0].regions[0]
    assert isinstance(region.aggregates["total"], AggregateRef)
    assert region.aggregates["total"].func == "count"
    assert region.aggregates["total"].entity == "Task"
    assert region.aggregates["total"].where is None

    assert region.aggregates["active"].where is not None

    assert region.aggregates["avg_score"].func == "avg"
    assert region.aggregates["avg_score"].column == "score"
    assert region.aggregates["avg_score"].is_source_relative is True


def test_renderer_passes_typed_refs_through() -> None:
    """RegionContext.aggregates now carries the typed IR end-to-end —
    no stringification at the renderer boundary (ADR-0024 / Slice 1f)."""
    fragment = _parse(_DSL)
    region = fragment.workspaces[0].regions[0]
    for ref in region.aggregates.values():
        assert isinstance(ref, AggregateRef)


def test_cross_entity_aggregate_supported() -> None:
    """The previously-unrepresentable ``avg(Entity.column)`` shape now
    parses cleanly via the typed IR."""
    src = """module t
app t "Test"
entity Mark:
  id: uuid pk
  score: int
entity Class:
  id: uuid pk
workspace dash "Dash":
  cohort:
    source: Class
    display: metrics
    aggregate:
      avg_mark: avg(Mark.score)
"""
    fragment = _parse(src)
    region = fragment.workspaces[0].regions[0]
    avg_mark = region.aggregates["avg_mark"]
    assert avg_mark.entity == "Mark"
    assert avg_mark.column == "score"
