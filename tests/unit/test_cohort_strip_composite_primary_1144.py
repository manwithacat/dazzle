"""#1144 part 2: composite primary (tuple display) on cohort_strip lenses.

Pre-fix `CohortStripLens.primary` was a single field — every
AO-breakdown / +pos/-neg / multi-value cell forced a route override.
After #1144 part 2, `primary_composite:` carries a list of parts and
a separator; the renderer joins resolved part values into one cell.

Combined with #1144 part 1 (tone_bands), DSL authors can now express
the cohort_strip's "tuple of metrics with banded colours" shape
without dropping to a custom view.
"""

from __future__ import annotations

import pytest

from dazzle.core.ir.workspaces import (
    CohortStripConfig,
    CohortStripLens,
    CompositePrimaryPart,
    CompositePrimarySpec,
)
from dazzle.http.runtime.workspace_card_data import _build_cohort_cells


def _config(*, lens: CohortStripLens) -> CohortStripConfig:
    return CohortStripConfig(member_via="member_id", lenses=[lens])


def _row(member_id: str, **extra) -> dict:
    return {"id": member_id, "member_id": member_id, **extra}


# ---------------------------------------------------------------------------
# Composite rendering
# ---------------------------------------------------------------------------


def test_composite_joins_parts_with_default_separator() -> None:
    """AO breakdown — three fields joined by ' / '."""
    lens = CohortStripLens(
        id="ao",
        label="AO breakdown",
        primary_composite=CompositePrimarySpec(
            parts=[
                CompositePrimaryPart(field="ao1_score"),
                CompositePrimaryPart(field="ao2_score"),
                CompositePrimaryPart(field="ao3_score"),
            ]
        ),
    )
    cells = _build_cohort_cells(
        items=[_row("m1", ao1_score=45, ao2_score=52, ao3_score=38)],
        config=_config(lens=lens),
        active_lens_id="ao",
    )
    assert cells[0]["primary_value"] == "45 / 52 / 38"


def test_composite_with_custom_separator() -> None:
    """Behaviour counter — +pos / -neg pair joined by a slash."""
    lens = CohortStripLens(
        id="behaviour",
        label="Behaviour",
        primary_composite=CompositePrimarySpec(
            parts=[
                CompositePrimaryPart(field="pos_count"),
                CompositePrimaryPart(field="neg_count"),
            ],
            separator=" | ",
        ),
    )
    cells = _build_cohort_cells(
        items=[_row("m1", pos_count=12, neg_count=3)],
        config=_config(lens=lens),
        active_lens_id="behaviour",
    )
    assert cells[0]["primary_value"] == "12 | 3"


def test_composite_missing_field_renders_empty_segment() -> None:
    """Graceful degradation — a missing field part becomes empty
    string; the separator still goes between."""
    lens = CohortStripLens(
        id="ao",
        label="AO",
        primary_composite=CompositePrimarySpec(
            parts=[
                CompositePrimaryPart(field="ao1_score"),
                CompositePrimaryPart(field="ao2_score"),
                CompositePrimaryPart(field="ao3_score"),
            ]
        ),
    )
    cells = _build_cohort_cells(
        items=[_row("m1", ao1_score=45, ao3_score=38)],  # ao2 missing
        config=_config(lens=lens),
        active_lens_id="ao",
    )
    assert cells[0]["primary_value"] == "45 /  / 38"


def test_composite_single_part() -> None:
    """One-part composite is valid — degenerate but the validator
    only rejects zero parts. Renders as that single value, no
    separator."""
    lens = CohortStripLens(
        id="x",
        label="X",
        primary_composite=CompositePrimarySpec(parts=[CompositePrimaryPart(field="score")]),
    )
    cells = _build_cohort_cells(
        items=[_row("m1", score=42)],
        config=_config(lens=lens),
        active_lens_id="x",
    )
    assert cells[0]["primary_value"] == "42"


# ---------------------------------------------------------------------------
# Mutual exclusion + validators
# ---------------------------------------------------------------------------


def test_scalar_and_composite_mutually_exclusive() -> None:
    """`primary:` and `primary_composite:` can't both be set on
    one lens — caught at IR construction."""
    with pytest.raises(ValueError, match="mutually exclusive"):
        CohortStripLens(
            id="x",
            label="X",
            primary="score",
            primary_composite=CompositePrimarySpec(parts=[CompositePrimaryPart(field="score")]),
        )


def test_lens_requires_some_primary_form() -> None:
    """A lens with neither `primary:` nor `primary_composite:` is
    rejected at IR construction."""
    with pytest.raises(ValueError, match="requires exactly one"):
        CohortStripLens(id="x", label="X")


def test_composite_empty_parts_rejected() -> None:
    """Empty `parts:` list is a parse-time error — the IR
    validator on CompositePrimarySpec surfaces it before render."""
    with pytest.raises(ValueError, match="at least one part"):
        CompositePrimarySpec(parts=[])


# ---------------------------------------------------------------------------
# Back-compat
# ---------------------------------------------------------------------------


def test_scalar_primary_unchanged() -> None:
    """Regression guard — lenses using the bare `primary:` field
    behave exactly as before."""
    lens = CohortStripLens(id="score", label="Score", primary="score")
    cells = _build_cohort_cells(
        items=[_row("m1", score=42)],
        config=_config(lens=lens),
        active_lens_id="score",
    )
    assert cells[0]["primary_value"] == "42"


def test_composite_with_per_part_tone_field_is_preserved_in_ir() -> None:
    """`tone:` per part is captured in the IR — rendering use of
    the per-part tone is rendering-layer follow-up, but the field
    round-trips through construction."""
    spec = CompositePrimarySpec(
        parts=[
            CompositePrimaryPart(field="pos_count", tone="good"),
            CompositePrimaryPart(field="neg_count", tone="bad"),
        ],
    )
    assert spec.parts[0].tone == "good"
    assert spec.parts[1].tone == "bad"
