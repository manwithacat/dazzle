"""#1144 part 3 phase 1: aggregate-expression primary on cohort_strip
lenses (IR + parser only).

The IR + parser are wired so DSL authors can author the shape today;
runtime execution lands in subsequent slices and raises a clear
``NotImplementedError`` on render. Tests pin the IR shape, parser
syntax, mutex contract, and the "runtime not wired" surface.
"""

from __future__ import annotations

import pytest

from dazzle.back.runtime.workspace_card_data import _build_cohort_cells
from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.errors import ParseError
from dazzle.core.ir.conditions import ViaCondition
from dazzle.core.ir.workspaces import (
    CohortStripConfig,
    CohortStripLens,
    CompositePrimaryPart,
    CompositePrimarySpec,
    LensAggregatePrimary,
)


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
    spec = LensAggregatePrimary(aggregate="avg(MarkingResult.score)")
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
            primary_aggregate=LensAggregatePrimary(aggregate="avg(x)"),
        )


def test_aggregate_primary_mutex_with_composite() -> None:
    with pytest.raises(ValueError, match="mutually exclusive"):
        CohortStripLens(
            id="x",
            label="X",
            primary_composite=CompositePrimarySpec(parts=[CompositePrimaryPart(field="a")]),
            primary_aggregate=LensAggregatePrimary(aggregate="avg(x)"),
        )


def test_aggregate_primary_carries_optional_via_and_where() -> None:
    """The IR composes a ViaCondition and ConditionExpr — reusing
    the existing scope-grammar shapes (#530)."""
    spec = LensAggregatePrimary(
        aggregate="avg(MarkingResult.score)",
        via=ViaCondition(junction_entity="ClassEnrolment", bindings=[]),
    )
    assert spec.via is not None
    assert spec.via.junction_entity == "ClassEnrolment"


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def test_parses_minimal_aggregate_primary() -> None:
    lens = _parse_lens(
        """          primary_aggregate:
            aggregate: "avg(MarkingResult.score)"
"""
    )
    assert lens.primary_aggregate is not None
    assert lens.primary_aggregate.aggregate == "avg(MarkingResult.score)"
    assert lens.primary_aggregate.via is None
    assert lens.primary_aggregate.where is None


def test_parses_aggregate_with_via_clause() -> None:
    """The via: value reuses the scope junction-binding grammar."""
    lens = _parse_lens(
        """          primary_aggregate:
            aggregate: "avg(MarkingResult.score)"
            via: ClassEnrolment(student_profile = id)
"""
    )
    via = lens.primary_aggregate.via
    assert via is not None
    assert via.junction_entity == "ClassEnrolment"
    assert len(via.bindings) == 1
    assert via.bindings[0].junction_field == "student_profile"


def test_parses_aggregate_with_where_predicate() -> None:
    lens = _parse_lens(
        """          primary_aggregate:
            aggregate: "avg(score)"
            where: latest_for_event = true
"""
    )
    assert lens.primary_aggregate.where is not None


def test_aggregate_required() -> None:
    with pytest.raises(ParseError, match="requires an `aggregate:`"):
        _parse_lens(
            """          primary_aggregate:
            where: x = 1
"""
        )


def test_unknown_aggregate_key_rejected() -> None:
    with pytest.raises(ParseError, match="Unknown primary_aggregate key"):
        _parse_lens(
            """          primary_aggregate:
            aggregate: "avg(x)"
            bogus: nope
"""
        )


def test_aggregate_and_scalar_rejected_at_parse_time() -> None:
    """The IR validator surfaces through the parser wrap."""
    with pytest.raises((ParseError, ValueError), match="mutually exclusive"):
        _parse_lens(
            """          primary: score
          primary_aggregate:
            aggregate: "avg(x)"
"""
        )


# ---------------------------------------------------------------------------
# Runtime surface — clear "not yet wired" error
# ---------------------------------------------------------------------------


def test_runtime_raises_not_implemented_for_aggregate_primary() -> None:
    """Phase 1 ships IR + parser only. The renderer raises a clear
    error so authors who declare `primary_aggregate:` learn the
    limitation at request time, not via empty cells."""
    lens = CohortStripLens(
        id="x",
        label="X",
        primary_aggregate=LensAggregatePrimary(aggregate="avg(score)"),
    )
    config = CohortStripConfig(member_via="member_id", lenses=[lens])
    with pytest.raises(NotImplementedError, match="primary_aggregate runtime not wired"):
        _build_cohort_cells(
            items=[{"id": "m1", "member_id": "m1"}],
            config=config,
            active_lens_id="x",
        )
