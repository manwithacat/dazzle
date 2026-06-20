"""#1144 part 3: aggregate-expression primary on cohort_strip lenses.

Phase 1 shipped IR + parser; phase 2 (this Slice 1f) migrated the IR
field from a string to the typed :class:`AggregateRef` per ADR-0024.
The runtime still raises ``NotImplementedError`` — Slice 3 of the
overall migration wires it up.

These tests pin: typed IR shape, parser grammar, mutex contract, and
the "runtime not wired" surface.
"""

from __future__ import annotations

import pytest

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.errors import ParseError
from dazzle.core.ir import AggregateRef
from dazzle.core.ir.conditions import ViaCondition
from dazzle.core.ir.workspaces import (
    CohortStripConfig,
    CohortStripLens,
    CompositePrimaryPart,
    CompositePrimarySpec,
    LensAggregatePrimary,
)
from dazzle.http.runtime.workspace_card_data import _build_cohort_cells


def _parse_lens(lens_body: str) -> object:
    src = f"""module ops
app demo_app "Demo"

entity Member "Member":
  id: uuid pk
  score: int

workspace dash "Dash":
  members:
    source: Member
    display: cohort_strip
    cohort_strip_config:
      member_via: id
      lenses:
        - id: attainment
          label: "Attainment"
{lens_body}
"""
    result = parse_dsl(src, "test.dsl")
    fragment = result[5]
    return fragment.workspaces[0].regions[0].cohort_strip_config.lenses[0]


# ---------------------------------------------------------------------------
# IR shape
# ---------------------------------------------------------------------------


def test_lens_with_aggregate_primary_constructs() -> None:
    spec = LensAggregatePrimary(
        aggregate=AggregateRef(func="avg", entity="MarkingResult", column="score"),
    )
    lens = CohortStripLens(id="x", label="X", primary_aggregate=spec)
    assert lens.primary_aggregate is spec
    assert lens.primary == ""
    assert lens.primary_composite is None


def test_aggregate_primary_mutex_with_scalar() -> None:
    with pytest.raises(ValueError, match="mutually exclusive"):
        CohortStripLens(
            id="x",
            label="X",
            primary="score",
            primary_aggregate=LensAggregatePrimary(
                aggregate=AggregateRef(func="avg", column="x"),
            ),
        )


def test_aggregate_primary_mutex_with_composite() -> None:
    with pytest.raises(ValueError, match="mutually exclusive"):
        CohortStripLens(
            id="x",
            label="X",
            primary_composite=CompositePrimarySpec(parts=[CompositePrimaryPart(field="a")]),
            primary_aggregate=LensAggregatePrimary(
                aggregate=AggregateRef(func="avg", column="x"),
            ),
        )


def test_aggregate_primary_carries_optional_via() -> None:
    """``via:`` rides at the LensAggregatePrimary level; the aggregate's
    own ``where:`` rides inside the AggregateRef (ADR-0024)."""
    spec = LensAggregatePrimary(
        aggregate=AggregateRef(func="avg", entity="MarkingResult", column="score"),
        via=ViaCondition(junction_entity="ClassEnrolment", bindings=[]),
    )
    assert spec.via is not None
    assert spec.via.junction_entity == "ClassEnrolment"
    assert spec.aggregate.entity == "MarkingResult"
    assert spec.aggregate.column == "score"


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def test_parses_minimal_aggregate_primary() -> None:
    lens = _parse_lens(
        """          primary_aggregate:
            aggregate: avg(MarkingResult.score)
"""
    )
    assert lens.primary_aggregate is not None
    agg = lens.primary_aggregate.aggregate
    assert isinstance(agg, AggregateRef)
    assert agg.func == "avg"
    assert agg.entity == "MarkingResult"
    assert agg.column == "score"
    assert lens.primary_aggregate.via is None


def test_parses_aggregate_with_via_clause() -> None:
    """The via: value reuses the scope junction-binding grammar."""
    lens = _parse_lens(
        """          primary_aggregate:
            aggregate: avg(MarkingResult.score)
            via: ClassEnrolment(student_profile = id)
"""
    )
    via = lens.primary_aggregate.via
    assert via is not None
    assert via.junction_entity == "ClassEnrolment"
    assert len(via.bindings) == 1
    assert via.bindings[0].junction_field == "student_profile"


def test_parses_aggregate_format_key() -> None:
    """#1300: `format:` threads into LensAggregatePrimary.format (mirrors
    bar_track's track_format) for per-lens render formatting."""
    lens = _parse_lens(
        """          primary_aggregate:
            aggregate: avg(MarkingResult.score)
            format: ".1f"
"""
    )
    assert lens.primary_aggregate is not None
    assert lens.primary_aggregate.format == ".1f"


def test_aggregate_format_defaults_to_empty() -> None:
    """No `format:` → empty (renderer applies its default-round)."""
    lens = _parse_lens(
        """          primary_aggregate:
            aggregate: avg(MarkingResult.score)
"""
    )
    assert lens.primary_aggregate.format == ""


def test_parses_aggregate_with_share() -> None:
    """#1216: share: names the pivot entity that both the cohort source
    row and the aggregated row reference. No `via:` required."""
    lens = _parse_lens(
        """          primary_aggregate:
            aggregate: avg(MarkingResult.score)
            share: StudentProfile
"""
    )
    spec = lens.primary_aggregate
    assert spec.share == "StudentProfile"
    assert spec.via is None


def test_share_optional_defaults_none() -> None:
    """#1216: existing primary_aggregate blocks unchanged — share defaults None."""
    lens = _parse_lens(
        """          primary_aggregate:
            aggregate: avg(MarkingResult.score)
            via: ClassEnrolment(student_profile = id)
"""
    )
    assert lens.primary_aggregate.share is None


def test_share_and_via_mutually_exclusive() -> None:
    """#1216: `share:` and `via:` are different operations — refuse to
    combine them rather than guess intent."""
    with pytest.raises(ParseError, match="cannot combine"):
        _parse_lens(
            """          primary_aggregate:
            aggregate: avg(MarkingResult.score)
            via: ClassEnrolment(student_profile = id)
            share: StudentProfile
"""
        )


def test_parses_aggregate_with_inner_where_predicate() -> None:
    """Row-level predicates ride inside the AggregateRef's own
    ``where:`` (ADR-0024) — no separate top-level ``where:`` key."""
    lens = _parse_lens(
        """          primary_aggregate:
            aggregate: avg(score where latest_for_event = true)
"""
    )
    agg = lens.primary_aggregate.aggregate
    assert agg.where is not None
    assert agg.where.comparison is not None
    assert agg.where.comparison.field == "latest_for_event"


def test_aggregate_required() -> None:
    with pytest.raises(ParseError, match="requires an `aggregate:`"):
        _parse_lens(
            """          primary_aggregate:
            via: ClassEnrolment(student_profile = id)
"""
        )


def test_unknown_aggregate_key_rejected() -> None:
    with pytest.raises(ParseError, match="Unknown primary_aggregate key"):
        _parse_lens(
            """          primary_aggregate:
            aggregate: avg(x)
            bogus: nope
"""
        )


def test_aggregate_and_scalar_rejected_at_parse_time() -> None:
    """The IR validator surfaces through the parser wrap."""
    with pytest.raises((ParseError, ValueError), match="mutually exclusive"):
        _parse_lens(
            """          primary: score
          primary_aggregate:
            aggregate: avg(x)
"""
        )


# ---------------------------------------------------------------------------
# Runtime surface — clear "not yet wired" error
# ---------------------------------------------------------------------------


def test_renderer_uses_aggregate_values_when_provided() -> None:
    """Phase 2 wires runtime execution: per-member aggregate values
    resolved upstream are threaded into _build_cohort_cells via
    `cohort_aggregate_values=`. The cell's primary_value reflects
    the resolved aggregate."""
    lens = CohortStripLens(
        id="x",
        label="X",
        primary_aggregate=LensAggregatePrimary(
            aggregate=AggregateRef(func="avg", column="score"),
        ),
    )
    config = CohortStripConfig(member_via="member_id", lenses=[lens])
    cells = _build_cohort_cells(
        items=[{"id": "m1", "member_id": "m1"}, {"id": "m2", "member_id": "m2"}],
        config=config,
        active_lens_id="x",
        cohort_aggregate_values={"m1": 6.5, "m2": 4.2},
    )
    assert len(cells) == 2
    assert cells[0]["primary_value"] == "6.5"
    assert cells[1]["primary_value"] == "4.2"


def test_renderer_handles_missing_aggregate_value_gracefully() -> None:
    """When the per-member query failed (or returned no rows) and
    the member is absent from `cohort_aggregate_values`, the cell
    renders without a value rather than crashing."""
    lens = CohortStripLens(
        id="x",
        label="X",
        primary_aggregate=LensAggregatePrimary(
            aggregate=AggregateRef(func="count", entity="Mark"),
        ),
    )
    config = CohortStripConfig(member_via="member_id", lenses=[lens])
    cells = _build_cohort_cells(
        items=[{"id": "m1", "member_id": "m1"}],
        config=config,
        active_lens_id="x",
        cohort_aggregate_values={},
    )
    assert len(cells) == 1
    assert cells[0]["primary_value"] == ""
