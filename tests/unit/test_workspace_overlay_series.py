"""Tests for ``overlay_series:`` parsing post-ADR-0024 migration.

The legacy ``aggregate_expr: str`` field on :class:`OverlaySeriesSpec`
has been replaced with a typed :class:`AggregateRef` (Slice 1c). These
tests pin the new shape — parser produces typed IR, runtime stringifier
round-trips it for the legacy ``_compute_bucketed_aggregates`` interface.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.ir import AggregateRef
from dazzle.core.ir.workspaces import OverlaySeriesSpec


def _parse(src: str) -> object:
    return parse_dsl(src, Path("test.dsl"))[5]


_OVERLAY_DSL = """module t
app t "Test"
entity Mark:
  id: uuid pk
  scaled_mark: float
workspace dash "Dash":
  trend:
    display: line_chart
    source: Mark
    group_by: created_at
    aggregate:
      total: count(Mark)
    overlay_series:
      - label: "Cohort avg"
        source: Mark
        aggregate: avg(scaled_mark)
      - label: "Cross-entity"
        aggregate: avg(MarkingResult.score where latest = true)
"""


def test_parser_produces_typed_aggregate_ref() -> None:
    fragment = _parse(_OVERLAY_DSL)
    region = fragment.workspaces[0].regions[0]
    overlays = region.overlay_series
    assert len(overlays) == 2

    first = overlays[0]
    assert first.label == "Cohort avg"
    assert isinstance(first.aggregate, AggregateRef)
    assert first.aggregate.func == "avg"
    assert first.aggregate.entity is None
    assert first.aggregate.column == "scaled_mark"

    second = overlays[1]
    assert second.aggregate.func == "avg"
    assert second.aggregate.entity == "MarkingResult"
    assert second.aggregate.column == "score"
    assert second.aggregate.where is not None


def test_aggregate_required() -> None:
    """An overlay without ``aggregate:`` is a parse error."""
    src = """module t
app t "Test"
workspace dash "Dash":
  trend:
    display: line_chart
    overlay_series:
      - label: "Missing"
"""
    from dazzle.core.errors import ParseError

    with pytest.raises(ParseError):
        _parse(src)


def test_overlay_aggregate_passes_typed() -> None:
    """Post-Slice 1f: the overlay's aggregate flows end-to-end as a
    typed AggregateRef — runtime no longer round-trips through a string."""
    fragment = _parse(_OVERLAY_DSL)
    overlays = fragment.workspaces[0].regions[0].overlay_series
    for ov in overlays:
        assert isinstance(ov.aggregate, AggregateRef)
        assert ov.aggregate.func in {"count", "sum", "avg", "min", "max"}


def test_overlayseriesspec_requires_aggregate() -> None:
    """The IR field ``aggregate`` is required at construction time."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        OverlaySeriesSpec(label="X")  # type: ignore[call-arg]


def test_overlayseriesspec_frozen() -> None:
    from pydantic import ValidationError

    spec = OverlaySeriesSpec(
        label="X",
        aggregate=AggregateRef(func="count", entity="Task"),
    )
    with pytest.raises(ValidationError):
        spec.label = "Y"  # type: ignore[misc]
