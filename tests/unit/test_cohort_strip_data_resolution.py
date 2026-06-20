"""Issue #1018 (v0.67.13): regression tests for the cohort_strip
data resolution layer in workspace_rendering.

Covers `_build_cohort_cells` — the helper that shapes already-scoped
source rows into the dict shape the cohort_strip adapter consumes.
RBAC scope is enforced upstream by the row-fetch query; this layer
just shapes.
"""

from __future__ import annotations

import pytest

from dazzle.core.ir.aggregates import AggregateRef
from dazzle.core.ir.workspaces import (
    CohortStripConfig,
    CohortStripLens,
    LensAggregatePrimary,
)
from dazzle.http.runtime.workspace_card_data import (
    _apply_format_spec,
    _build_cohort_cells,
    _default_round_numeric,
)


def _config(*, member_via: str = "profile", lenses: list[dict] | None = None) -> CohortStripConfig:
    lens_data = lenses or [
        {"id": "score", "label": "Score", "primary": "score"},
    ]
    return CohortStripConfig(
        member_via=member_via,
        lenses=[CohortStripLens(**spec) for spec in lens_data],
    )


def test_returns_empty_when_no_items() -> None:
    cells = _build_cohort_cells(items=[], config=_config(), active_lens_id="score")
    assert cells == []


def test_returns_empty_when_config_missing() -> None:
    cells = _build_cohort_cells(
        items=[{"id": "1", "score": 50}], config=None, active_lens_id="score"
    )
    assert cells == []


def test_skips_rows_without_id() -> None:
    cells = _build_cohort_cells(
        items=[{"id": "p1", "score": 50}, {"score": 30}, {"id": "", "score": 70}],
        config=_config(),
        active_lens_id="score",
    )
    assert len(cells) == 1
    assert cells[0]["member_id"] == "p1"


def test_resolves_member_name_from_fk_display_dict() -> None:
    """When the FK was resolved upstream into a dict, use its
    __display__ key (or canonical fallback)."""
    cells = _build_cohort_cells(
        items=[
            {
                "id": "p1",
                "score": 78,
                "profile": {"id": "prof1", "__display__": "Alice Wong"},
            }
        ],
        config=_config(member_via="profile"),
        active_lens_id="score",
    )
    assert cells[0]["member_name"] == "Alice Wong"


def test_resolves_member_name_from_display_sibling() -> None:
    """When _inject_display_names produced a `<field>_display`
    sibling key, use that."""
    cells = _build_cohort_cells(
        items=[{"id": "p1", "score": 78, "profile": "prof1", "profile_display": "Alice"}],
        config=_config(member_via="profile"),
        active_lens_id="score",
    )
    assert cells[0]["member_name"] == "Alice"


def test_falls_back_to_name_field_when_fk_unresolved() -> None:
    """When member_via wasn't FK-resolved (no display dict, no
    sibling), fall through to the row's own `name` field."""
    cells = _build_cohort_cells(
        items=[{"id": "p1", "score": 78, "profile": None, "name": "Bob"}],
        config=_config(member_via="profile"),
        active_lens_id="score",
    )
    assert cells[0]["member_name"] == "Bob"


def test_extracts_primary_value_from_active_lens_field() -> None:
    cells = _build_cohort_cells(
        items=[{"id": "p1", "score": 78, "att_pct": 92}],
        config=_config(
            lenses=[
                {"id": "score", "label": "Score", "primary": "score"},
                {"id": "att", "label": "Attendance", "primary": "att_pct"},
            ]
        ),
        active_lens_id="att",
    )
    assert cells[0]["primary_value"] == "92"


def test_unknown_active_lens_falls_back_to_first_declared() -> None:
    cells = _build_cohort_cells(
        items=[{"id": "p1", "score": 50, "att_pct": 90}],
        config=_config(
            lenses=[
                {"id": "score", "label": "Score", "primary": "score"},
                {"id": "att", "label": "Attendance", "primary": "att_pct"},
            ]
        ),
        active_lens_id="ghost-lens",
    )
    # First lens (score) wins.
    assert cells[0]["primary_value"] == "50"


def test_tone_good_when_at_or_above_threshold() -> None:
    cells = _build_cohort_cells(
        items=[{"id": "p1", "score": 90}, {"id": "p2", "score": 85}],
        config=_config(
            lenses=[{"id": "score", "label": "Score", "primary": "score", "threshold": 85}]
        ),
        active_lens_id="score",
    )
    assert cells[0]["tone"] == "good"
    assert cells[1]["tone"] == "good"


def test_tone_warn_when_within_10pct_below_threshold() -> None:
    cells = _build_cohort_cells(
        items=[{"id": "p1", "score": 80}],
        config=_config(
            lenses=[{"id": "score", "label": "Score", "primary": "score", "threshold": 85}]
        ),
        active_lens_id="score",
    )
    # 80 / 85 ≈ 94% → within warn band.
    assert cells[0]["tone"] == "warn"


def test_tone_bad_when_below_warn_band() -> None:
    cells = _build_cohort_cells(
        items=[{"id": "p1", "score": 50}],
        config=_config(
            lenses=[{"id": "score", "label": "Score", "primary": "score", "threshold": 85}]
        ),
        active_lens_id="score",
    )
    # 50 / 85 ≈ 59% → bad.
    assert cells[0]["tone"] == "bad"


def test_tone_neutral_when_no_threshold() -> None:
    cells = _build_cohort_cells(
        items=[{"id": "p1", "score": 30}],
        config=_config(),  # no threshold on default lens
        active_lens_id="score",
    )
    assert cells[0]["tone"] == "neutral"


def test_tone_neutral_when_primary_not_numeric() -> None:
    cells = _build_cohort_cells(
        items=[{"id": "p1", "score": "active"}],
        config=_config(
            lenses=[{"id": "score", "label": "Score", "primary": "score", "threshold": 85}]
        ),
        active_lens_id="score",
    )
    # Non-numeric primary can't be compared — defensive neutral.
    assert cells[0]["tone"] == "neutral"


def test_avatar_initials_from_member_name() -> None:
    cells = _build_cohort_cells(
        items=[{"id": "p1", "score": 78, "profile_display": "Alice Wong"}],
        config=_config(member_via="profile"),
        active_lens_id="score",
    )
    assert cells[0]["avatar_initials"] == "AW"


def test_avatar_initials_empty_when_no_name() -> None:
    cells = _build_cohort_cells(
        items=[{"id": "p1", "score": 78}],
        config=_config(member_via="missing"),
        active_lens_id="score",
    )
    assert cells[0]["avatar_initials"] == ""


def test_handles_items_with_missing_primary_field_gracefully() -> None:
    cells = _build_cohort_cells(
        items=[{"id": "p1", "name": "Alice"}],  # no `score` field
        config=_config(),
        active_lens_id="score",
    )
    assert cells[0]["primary_value"] == ""


# ── #1299: self-referential member_via resolves to source display_field ──


def test_member_name_from_display_field_when_member_via_is_self() -> None:
    """#1299: `member_via: id` (self-referential) has no `<field>_display`
    sibling — the scalar value is the row's own UUID. The label must come
    from the source entity's display_field, not the UUID."""
    cells = _build_cohort_cells(
        items=[{"id": "0f9a-2b1c-uuid", "form_name": "10A", "score": 78}],
        config=_config(member_via="id"),
        active_lens_id="score",
        source_display_field="form_name",
    )
    assert cells[0]["member_name"] == "10A"


def test_member_name_falls_back_to_raw_id_when_no_display_field() -> None:
    """No source_display_field → unchanged raw-id fallback (no regression)."""
    cells = _build_cohort_cells(
        items=[{"id": "u1", "score": 1}],
        config=_config(member_via="id"),
        active_lens_id="score",
        source_display_field="",
    )
    assert cells[0]["member_name"] == "u1"


def test_fk_display_sibling_wins_over_source_display_field() -> None:
    """Priority: `<member_via>_display` sibling (2) beats display_field (3)."""
    cells = _build_cohort_cells(
        items=[
            {
                "id": "p1",
                "score": 1,
                "profile": "x",
                "profile_display": "Alice",
                "form_name": "10A",
            }
        ],
        config=_config(member_via="profile"),
        active_lens_id="score",
        source_display_field="form_name",
    )
    assert cells[0]["member_name"] == "Alice"


# ── #1300: aggregate primary formatting (default-round + format knob) ──


def _agg_config(fmt: str = "") -> CohortStripConfig:
    return CohortStripConfig(
        member_via="id",
        lenses=[
            CohortStripLens(
                id="att",
                label="Attainment",
                primary_aggregate=LensAggregatePrimary(
                    aggregate=AggregateRef(func="avg", column="score"),
                    format=fmt,
                ),
            )
        ],
    )


def test_aggregate_default_round_trims_raw_float() -> None:
    """#1300: an `avg` lens with no format knob no longer emits the raw
    '7.7500000000000000' — it default-rounds to '7.75'."""
    cells = _build_cohort_cells(
        items=[{"id": "m1", "form_name": "10A"}],
        config=_agg_config(),
        active_lens_id="att",
        source_display_field="form_name",
        cohort_aggregate_values={"m1": "7.7500000000000000"},
    )
    assert cells[0]["primary_value"] == "7.75"


def test_aggregate_default_round_integral_drops_decimal() -> None:
    cells = _build_cohort_cells(
        items=[{"id": "m1"}],
        config=_agg_config(),
        active_lens_id="att",
        cohort_aggregate_values={"m1": 8.0},
    )
    assert cells[0]["primary_value"] == "8"


def test_aggregate_format_spec_overrides_default_round() -> None:
    """#1300: an explicit `format:` spec wins over default-round."""
    cells = _build_cohort_cells(
        items=[{"id": "m1"}],
        config=_agg_config(fmt=".1f"),
        active_lens_id="att",
        cohort_aggregate_values={"m1": 7.74},
    )
    assert cells[0]["primary_value"] == "7.7"


def test_aggregate_format_template_form() -> None:
    """str.format template form (`{...}`) is honoured, beating default-round."""
    cells = _build_cohort_cells(
        items=[{"id": "m1"}],
        config=_agg_config(fmt="{:.0f}%"),
        active_lens_id="att",
        cohort_aggregate_values={"m1": 92.4},
    )
    assert cells[0]["primary_value"] == "92%"


def test_aggregate_invalid_format_falls_back_to_raw(caplog: pytest.LogCaptureFixture) -> None:
    """An invalid format spec warns and renders the raw value — never raises."""
    cells = _build_cohort_cells(
        items=[{"id": "m1"}],
        config=_agg_config(fmt="garbage"),
        active_lens_id="att",
        cohort_aggregate_values={"m1": 5.5},
    )
    assert cells[0]["primary_value"] == "5.5"


def test_aggregate_empty_value_renders_empty() -> None:
    """Missing aggregate value (query returned no row) → empty cell."""
    cells = _build_cohort_cells(
        items=[{"id": "m1"}],
        config=_agg_config(),
        active_lens_id="att",
        cohort_aggregate_values={},
    )
    assert cells[0]["primary_value"] == ""


# ── shared format helpers (also used by bar_track via track_format) ──


@pytest.mark.parametrize(
    ("value", "expected"),
    [("7.7500000000000000", "7.75"), (8.0, "8"), (7.3333, "7.33"), (7.5, "7.5"), (0, "0")],
)
def test_default_round_numeric(value: object, expected: str) -> None:
    assert _default_round_numeric(value) == expected


def test_default_round_passes_non_numeric_through() -> None:
    assert _default_round_numeric("active") == "active"


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_default_round_handles_non_finite_without_crashing(value: float) -> None:
    """nan/inf would blow up int(round(...)) — must render raw, not raise."""
    assert _default_round_numeric(value) == str(value)


@pytest.mark.parametrize(
    ("value", "spec", "expected"),
    [(7.74, ".1f", "7.7"), (92.4, "{:.0f}%", "92%"), (1234.5, ",.0f", "1,234"), (5.0, "", "5.0")],
)
def test_apply_format_spec(value: float, spec: str, expected: str) -> None:
    assert _apply_format_spec(value, spec) == expected


def test_apply_format_spec_invalid_returns_raw() -> None:
    assert _apply_format_spec(5.5, "garbage") == "5.5"
