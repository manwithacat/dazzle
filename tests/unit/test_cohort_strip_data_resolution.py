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


# ── empty guards ──


@pytest.mark.parametrize(
    ("items", "config"),
    [
        pytest.param([], _config(), id="no-items"),
        pytest.param([{"id": "1", "score": 50}], None, id="config-missing"),
    ],
)
def test_returns_empty(items: list[dict], config: CohortStripConfig | None) -> None:
    cells = _build_cohort_cells(items=items, config=config, active_lens_id="score")
    assert cells == []


def test_skips_rows_without_id() -> None:
    cells = _build_cohort_cells(
        items=[{"id": "p1", "score": 50}, {"score": 30}, {"id": "", "score": 70}],
        config=_config(),
        active_lens_id="score",
    )
    assert len(cells) == 1
    assert cells[0]["member_id"] == "p1"


# ── member_name resolution priority chain ──
# Rungs: (1) FK resolved upstream into a dict → its __display__ key;
# (2) `_inject_display_names` `<field>_display` sibling key;
# (3) source entity's display_field (#1299: self-referential `member_via: id`
#     has no sibling — the label must come from display_field, not the UUID);
# (4) the row's own `name` field when member_via wasn't FK-resolved;
# (5) raw-id fallback when no display_field either (#1299: no regression).


@pytest.mark.parametrize(
    ("items", "member_via", "source_display_field", "expected"),
    [
        pytest.param(
            [
                {
                    "id": "p1",
                    "score": 78,
                    "profile": {"id": "prof1", "__display__": "Alice Wong"},
                }
            ],
            "profile",
            "",
            "Alice Wong",
            id="p1-fk-display-dict",
        ),
        pytest.param(
            [{"id": "p1", "score": 78, "profile": "prof1", "profile_display": "Alice"}],
            "profile",
            "",
            "Alice",
            id="p2-display-sibling",
        ),
        pytest.param(
            [
                {
                    "id": "p1",
                    "score": 1,
                    "profile": "x",
                    "profile_display": "Alice",
                    "form_name": "10A",
                }
            ],
            "profile",
            "form_name",
            "Alice",
            id="p2-sibling-beats-p3-display-field-#1299",
        ),
        pytest.param(
            [{"id": "0f9a-2b1c-uuid", "form_name": "10A", "score": 78}],
            "id",
            "form_name",
            "10A",
            id="p3-self-ref-display-field-#1299",
        ),
        pytest.param(
            [{"id": "p1", "score": 78, "profile": None, "name": "Bob"}],
            "profile",
            "",
            "Bob",
            id="p4-name-field-when-fk-unresolved",
        ),
        pytest.param(
            [{"id": "u1", "score": 1}],
            "id",
            "",
            "u1",
            id="p5-raw-id-when-no-display-field-#1299",
        ),
    ],
)
def test_member_name_resolution_priority(
    items: list[dict], member_via: str, source_display_field: str, expected: str
) -> None:
    cells = _build_cohort_cells(
        items=items,
        config=_config(member_via=member_via),
        active_lens_id="score",
        source_display_field=source_display_field,
    )
    assert cells[0]["member_name"] == expected


# ── primary value extraction from the active lens ──

_TWO_LENSES = [
    {"id": "score", "label": "Score", "primary": "score"},
    {"id": "att", "label": "Attendance", "primary": "att_pct"},
]


@pytest.mark.parametrize(
    ("items", "lenses", "active_lens_id", "expected"),
    [
        pytest.param(
            [{"id": "p1", "score": 78, "att_pct": 92}],
            _TWO_LENSES,
            "att",
            "92",
            id="active-lens-field",
        ),
        # Unknown active lens → first declared lens (score) wins.
        pytest.param(
            [{"id": "p1", "score": 50, "att_pct": 90}],
            _TWO_LENSES,
            "ghost-lens",
            "50",
            id="unknown-lens-falls-back-to-first-declared",
        ),
        # Row missing the lens's primary field → handled gracefully as "".
        pytest.param(
            [{"id": "p1", "name": "Alice"}],
            None,
            "score",
            "",
            id="missing-primary-field-renders-empty",
        ),
    ],
)
def test_primary_value_extraction(
    items: list[dict], lenses: list[dict] | None, active_lens_id: str, expected: str
) -> None:
    cells = _build_cohort_cells(
        items=items,
        config=_config(lenses=lenses),
        active_lens_id=active_lens_id,
    )
    assert cells[0]["primary_value"] == expected


# ── tone banding against the lens threshold ──

_THRESHOLD_LENS = [{"id": "score", "label": "Score", "primary": "score", "threshold": 85}]


@pytest.mark.parametrize(
    ("items", "lenses", "expected_tones"),
    [
        pytest.param(
            [{"id": "p1", "score": 90}, {"id": "p2", "score": 85}],
            _THRESHOLD_LENS,
            ["good", "good"],
            id="good-at-or-above-threshold",
        ),
        # 80 / 85 ≈ 94% → within warn band.
        pytest.param(
            [{"id": "p1", "score": 80}],
            _THRESHOLD_LENS,
            ["warn"],
            id="warn-within-10pct-below-threshold",
        ),
        # 50 / 85 ≈ 59% → bad.
        pytest.param(
            [{"id": "p1", "score": 50}],
            _THRESHOLD_LENS,
            ["bad"],
            id="bad-below-warn-band",
        ),
        # No threshold on the default lens → neutral.
        pytest.param(
            [{"id": "p1", "score": 30}],
            None,
            ["neutral"],
            id="neutral-when-no-threshold",
        ),
        # Non-numeric primary can't be compared — defensive neutral.
        pytest.param(
            [{"id": "p1", "score": "active"}],
            _THRESHOLD_LENS,
            ["neutral"],
            id="neutral-when-primary-not-numeric",
        ),
    ],
)
def test_tone_banding(
    items: list[dict], lenses: list[dict] | None, expected_tones: list[str]
) -> None:
    cells = _build_cohort_cells(
        items=items,
        config=_config(lenses=lenses),
        active_lens_id="score",
    )
    assert [cell["tone"] for cell in cells] == expected_tones


# ── avatar initials ──


@pytest.mark.parametrize(
    ("items", "member_via", "expected"),
    [
        pytest.param(
            [{"id": "p1", "score": 78, "profile_display": "Alice Wong"}],
            "profile",
            "AW",
            id="initials-from-member-name",
        ),
        pytest.param(
            [{"id": "p1", "score": 78}],
            "missing",
            "",
            id="empty-when-no-name",
        ),
    ],
)
def test_avatar_initials(items: list[dict], member_via: str, expected: str) -> None:
    cells = _build_cohort_cells(
        items=items,
        config=_config(member_via=member_via),
        active_lens_id="score",
    )
    assert cells[0]["avatar_initials"] == expected


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


@pytest.mark.parametrize(
    ("fmt", "items", "aggregate_values", "source_display_field", "expected"),
    [
        # #1300: an `avg` lens with no format knob no longer emits the raw
        # '7.7500000000000000' — it default-rounds to '7.75'.
        pytest.param(
            "",
            [{"id": "m1", "form_name": "10A"}],
            {"m1": "7.7500000000000000"},
            "form_name",
            "7.75",
            id="default-round-trims-raw-float-#1300",
        ),
        pytest.param(
            "",
            [{"id": "m1"}],
            {"m1": 8.0},
            "",
            "8",
            id="default-round-integral-drops-decimal",
        ),
        # #1300: an explicit `format:` spec wins over default-round.
        pytest.param(
            ".1f",
            [{"id": "m1"}],
            {"m1": 7.74},
            "",
            "7.7",
            id="format-spec-overrides-default-round-#1300",
        ),
        # str.format template form (`{...}`) is honoured, beating default-round.
        pytest.param(
            "{:.0f}%",
            [{"id": "m1"}],
            {"m1": 92.4},
            "",
            "92%",
            id="format-template-form",
        ),
        # Missing aggregate value (query returned no row) → empty cell.
        pytest.param(
            "",
            [{"id": "m1"}],
            {},
            "",
            "",
            id="empty-value-renders-empty",
        ),
    ],
)
def test_aggregate_primary_formatting(
    fmt: str,
    items: list[dict],
    aggregate_values: dict[str, object],
    source_display_field: str,
    expected: str,
) -> None:
    cells = _build_cohort_cells(
        items=items,
        config=_agg_config(fmt),
        active_lens_id="att",
        source_display_field=source_display_field,
        cohort_aggregate_values=aggregate_values,
    )
    assert cells[0]["primary_value"] == expected


def test_aggregate_invalid_format_falls_back_to_raw(caplog: pytest.LogCaptureFixture) -> None:
    """An invalid format spec warns and renders the raw value — never raises."""
    cells = _build_cohort_cells(
        items=[{"id": "m1"}],
        config=_agg_config(fmt="garbage"),
        active_lens_id="att",
        cohort_aggregate_values={"m1": 5.5},
    )
    assert cells[0]["primary_value"] == "5.5"


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
