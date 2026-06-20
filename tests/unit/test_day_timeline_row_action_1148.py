"""#1148 part 3 (day_timeline): wire `row_action:` into the slot
data layer + renderer.

Pre-part-3 day_timeline slots had no action affordance — the
canonical case (e.g. "Mark register" button per lesson slot) had
to fall back to a Python route override. After #1148 part 3, each
slot carries a pre-rendered button when the region declares
`row_action:`, with the same `_eval_row_condition` +
`_render_row_action_button` contract as the list path.
"""

from __future__ import annotations

import datetime as _dt

from dazzle.core.ir.conditions import (
    Comparison,
    ComparisonOperator,
    ConditionExpr,
    ConditionValue,
)
from dazzle.core.ir.workspaces import DayTimelineConfig, RowActionSpec
from dazzle.http.runtime.workspace_card_data import _build_day_timeline_slots

_NOW = _dt.datetime(2026, 5, 19, 10, 0, tzinfo=_dt.UTC)


def _config(card: str = "") -> DayTimelineConfig:
    return DayTimelineConfig(starts_at="starts_at", ends_at="ends_at", card=card)


def _item(item_id: str = "p1", **extra) -> dict:
    return {"id": item_id, "starts_at": _NOW, "ends_at": _NOW, **extra}


def test_no_row_action_emits_empty_action_html() -> None:
    """Regression guard — region without row_action: keeps slot
    `action_html` empty; no behaviour change for day_timeline
    configs that don't opt into the affordance."""
    slots = _build_day_timeline_slots(items=[_item()], config=_config(), now=_NOW)
    assert slots[0]["action_html"] == ""


def test_row_action_emits_button_per_slot() -> None:
    row_action = RowActionSpec(
        label="Mark register",
        action_id="register_mark",
        bind={"slot_id": "id"},
    )
    slots = _build_day_timeline_slots(
        items=[_item("p1", subject="Maths"), _item("p2", subject="French")],
        config=_config(),
        now=_NOW,
        row_action=row_action,
    )
    assert all('data-dz-row-action="register_mark"' in s["action_html"] for s in slots)
    # Two distinct slot ids round-trip via the JSON args.
    assert "p1" in slots[0]["action_html"]
    assert "p2" in slots[1]["action_html"]


def test_visible_when_false_suppresses_button_for_that_slot() -> None:
    """A slot whose visible_when evaluates falsy gets empty
    action_html — sibling slots are unaffected."""
    row_action = RowActionSpec(
        label="Mark register",
        action_id="register_mark",
        bind={"slot_id": "id"},
        visible_when=ConditionExpr(
            comparison=Comparison(
                field="marked",
                operator=ComparisonOperator.EQUALS,
                value=ConditionValue(literal=False),
            )
        ),
    )
    slots = _build_day_timeline_slots(
        items=[
            _item("p1", marked=False),  # button visible
            _item("p2", marked=True),  # button hidden
        ],
        config=_config(),
        now=_NOW,
        row_action=row_action,
    )
    bs = {s["slot_id"]: s["action_html"] for s in slots}
    assert "data-dz-row-action" in bs["p1"]
    assert bs["p2"] == ""


def test_button_carries_day_timeline_class_token() -> None:
    """The day_timeline class lets project CSS position the button
    inside the slot card (different layout from the list-cell
    button). Pins the class so CSS authors can target it."""
    row_action = RowActionSpec(
        label="Resolve",
        action_id="resolve",
        bind={"id": "id"},
    )
    slots = _build_day_timeline_slots(
        items=[_item()], config=_config(), now=_NOW, row_action=row_action
    )
    assert "dz-day-timeline-slot-action-btn" in slots[0]["action_html"]


def test_renderer_emits_action_div_around_pre_rendered_button() -> None:
    """End-to-end via the adapter + renderer: the button HTML
    appears inside the slot's action div."""
    from dazzle.render.fragment.region import WorkspaceRegionAdapter
    from dazzle.render.fragment.renderer import FragmentRenderer

    class _R:
        name = "today"
        title = None
        display = "day_timeline"
        empty_message = None

    region = _R()
    ctx = {
        "day_timeline_slots": [
            {
                "slot_id": "p1",
                "label": "Period 1",
                "position": "active",
                "body": "Maths",
                "action_html": '<button data-dz-row-action="x">Y</button>',
            }
        ]
    }
    out = FragmentRenderer().render(WorkspaceRegionAdapter().build(region, ctx))
    assert "dz-day-timeline-slot-action" in out
    assert 'data-dz-row-action="x"' in out


def test_renderer_omits_action_div_when_empty() -> None:
    """No action_html → no action div in the rendered slot. Keeps
    the markup minimal for slots that don't carry an action."""
    from dazzle.render.fragment.region import WorkspaceRegionAdapter
    from dazzle.render.fragment.renderer import FragmentRenderer

    class _R:
        name = "today"
        title = None
        display = "day_timeline"
        empty_message = None

    region = _R()
    ctx = {
        "day_timeline_slots": [
            {
                "slot_id": "p1",
                "label": "Period 1",
                "position": "active",
                "body": "Maths",
                "action_html": "",
            }
        ]
    }
    out = FragmentRenderer().render(WorkspaceRegionAdapter().build(region, ctx))
    assert "dz-day-timeline-slot-action" not in out
