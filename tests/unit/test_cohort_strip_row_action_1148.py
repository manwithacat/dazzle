"""#1148 part 4 (cohort_strip, final): wire `row_action:` into the
cell data layer + renderer.

Pre-part-4 cohort_strip cells had no per-row action affordance —
the canonical case (e.g. "Issue commendation" per pupil cell) had
to fall back to a Python route override. After #1148 part 4, each
cell carries a pre-rendered button when the region declares
`row_action:`, with the same `_eval_row_condition` +
`_render_row_action_button` contract as list + day_timeline.

Closes #1148. status_list is excluded (static IR entries, not
source-bound rows).
"""

from __future__ import annotations

from dazzle.core.ir.conditions import (
    Comparison,
    ComparisonOperator,
    ConditionExpr,
    ConditionValue,
)
from dazzle.core.ir.workspaces import (
    CohortStripConfig,
    CohortStripLens,
    RowActionSpec,
)
from dazzle.http.runtime.workspace_card_data import _build_cohort_cells


def _lens() -> CohortStripLens:
    return CohortStripLens(id="score", label="Score", primary="score")


def _config() -> CohortStripConfig:
    return CohortStripConfig(member_via="member_id", lenses=[_lens()])


def _row(member_id: str, **extra) -> dict:
    return {"id": member_id, "member_id": member_id, **extra}


def test_no_row_action_emits_empty_action_html() -> None:
    cells = _build_cohort_cells(
        items=[_row("m1", score=80)],
        config=_config(),
        active_lens_id="score",
    )
    assert cells[0]["action_html"] == ""


def test_row_action_emits_button_per_cell() -> None:
    row_action = RowActionSpec(
        label="Commend",
        action_id="issue_commendation",
        bind={"pupil_id": "id"},
    )
    cells = _build_cohort_cells(
        items=[_row("m1", score=80), _row("m2", score=90)],
        config=_config(),
        active_lens_id="score",
        row_action=row_action,
    )
    assert all('data-dz-row-action="issue_commendation"' in c["action_html"] for c in cells)
    assert "m1" in cells[0]["action_html"]
    assert "m2" in cells[1]["action_html"]


def test_row_action_emits_url_data_attr_when_route_known() -> None:
    """#1233 — when the action_id resolves in row_action_routes, the
    button carries data-dz-row-action-url so the client handler can POST."""
    row_action = RowActionSpec(
        label="Commend",
        action_id="issue_commendation",
        bind={"pupil_id": "id"},
    )
    cells = _build_cohort_cells(
        items=[_row("m1", score=80)],
        config=_config(),
        active_lens_id="score",
        row_action=row_action,
        row_action_routes={"issue_commendation": "/commendations"},
    )
    assert 'data-dz-row-action-url="/commendations"' in cells[0]["action_html"]


def test_row_action_omits_url_data_attr_when_route_unknown() -> None:
    """#1233 — no matching CREATE surface in the AppSpec → no URL attr.
    Pre-existing button shape preserved; JS handler emits console.warn."""
    row_action = RowActionSpec(
        label="Commend",
        action_id="issue_commendation",
        bind={"pupil_id": "id"},
    )
    cells = _build_cohort_cells(
        items=[_row("m1", score=80)],
        config=_config(),
        active_lens_id="score",
        row_action=row_action,
        # No matching entry — simulates a custom action_id not declared
        # as a CREATE surface (the gap the JS handler warns about).
        row_action_routes={},
    )
    assert "data-dz-row-action-url" not in cells[0]["action_html"]


def test_visible_when_false_suppresses_button_for_that_cell() -> None:
    row_action = RowActionSpec(
        label="Commend",
        action_id="commend",
        bind={"id": "id"},
        visible_when=ConditionExpr(
            comparison=Comparison(
                field="commended",
                operator=ComparisonOperator.EQUALS,
                value=ConditionValue(literal=False),
            )
        ),
    )
    cells = _build_cohort_cells(
        items=[
            _row("m1", score=80, commended=False),
            _row("m2", score=90, commended=True),
        ],
        config=_config(),
        active_lens_id="score",
        row_action=row_action,
    )
    bs = {c["member_id"]: c["action_html"] for c in cells}
    assert "data-dz-row-action" in bs["m1"]
    assert bs["m2"] == ""


def test_button_carries_cohort_strip_class_token() -> None:
    """Class token lets CSS position the button inside the cell —
    different layout from list cell + day_timeline slot."""
    row_action = RowActionSpec(label="Act", action_id="act", bind={"id": "id"})
    cells = _build_cohort_cells(
        items=[_row("m1", score=80)],
        config=_config(),
        active_lens_id="score",
        row_action=row_action,
    )
    assert "dz-cohort-strip-cell-action-btn" in cells[0]["action_html"]


def test_renderer_emits_action_div_around_pre_rendered_button() -> None:
    """End-to-end via the adapter + renderer."""
    from dazzle.render.fragment.region import WorkspaceRegionAdapter
    from dazzle.render.fragment.renderer import FragmentRenderer

    cfg = _config()

    class _R:
        name = "cohort"
        title = None
        display = "cohort_strip"
        empty_message = None
        cohort_strip_config = cfg

    ctx = {
        "cohort_endpoint": "/api/cohort",
        "cohort_active_lens": "score",
        "cohort_cells": [
            {
                "member_id": "m1",
                "member_name": "Alice",
                "primary_value": "80",
                "action_html": '<button data-dz-row-action="x">Y</button>',
            }
        ],
    }
    out = FragmentRenderer().render(WorkspaceRegionAdapter().build(_R(), ctx))
    assert "dz-cohort-strip-cell-action" in out
    assert 'data-dz-row-action="x"' in out


def test_renderer_omits_action_div_when_empty() -> None:
    from dazzle.render.fragment.region import WorkspaceRegionAdapter
    from dazzle.render.fragment.renderer import FragmentRenderer

    cfg = _config()

    class _R:
        name = "cohort"
        title = None
        display = "cohort_strip"
        empty_message = None
        cohort_strip_config = cfg

    ctx = {
        "cohort_endpoint": "/api/cohort",
        "cohort_active_lens": "score",
        "cohort_cells": [
            {
                "member_id": "m1",
                "member_name": "Alice",
                "primary_value": "80",
                "action_html": "",
            }
        ],
    }
    out = FragmentRenderer().render(WorkspaceRegionAdapter().build(_R(), ctx))
    assert "dz-cohort-strip-cell-action" not in out
