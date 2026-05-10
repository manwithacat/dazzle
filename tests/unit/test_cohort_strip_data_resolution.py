"""Issue #1018 (v0.67.13): regression tests for the cohort_strip
data resolution layer in workspace_rendering.

Covers `_build_cohort_cells` — the helper that shapes already-scoped
source rows into the dict shape the cohort_strip adapter consumes.
RBAC scope is enforced upstream by the row-fetch query; this layer
just shapes.
"""

from __future__ import annotations

from dazzle.core.ir.workspaces import CohortStripConfig, CohortStripLens
from dazzle_back.runtime.workspace_rendering import _build_cohort_cells


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
