"""#1146 part 1: composite-card body interpolation for day_timeline.

Pre-fix the slot body was hard-coded to `""` with a TODO. Each slot
body is now the `_interpolate_card_template` expansion of
`DayTimelineConfig.card` against the row dict — same `{{ field }}`
grammar as `profile_card` / `task_inbox` templates.
"""

from __future__ import annotations

import datetime as _dt

from dazzle.core.ir.workspaces import DayTimelineConfig
from dazzle.http.runtime.workspace_card_data import _build_day_timeline_slots

_NOW = _dt.datetime(2026, 5, 10, 11, 0, tzinfo=_dt.UTC)


def _config(card: str = "") -> DayTimelineConfig:
    return DayTimelineConfig(starts_at="starts_at", ends_at="ends_at", card=card)


def _item(item_id: str = "p1", **extra) -> dict:
    return {"id": item_id, "starts_at": _NOW, "ends_at": _NOW, **extra}


def test_body_interpolates_single_field() -> None:
    items = [_item(subject="Maths")]
    slots = _build_day_timeline_slots(items=items, config=_config(card="{{ subject }}"), now=_NOW)
    assert slots[0]["body"] == "Maths"


def test_body_interpolates_multiple_fields() -> None:
    items = [_item(subject="Physics", teacher="Mr Khan")]
    slots = _build_day_timeline_slots(
        items=items,
        config=_config(card="{{ subject }} — {{ teacher }}"),
        now=_NOW,
    )
    assert slots[0]["body"] == "Physics — Mr Khan"


def test_body_handles_dotted_path() -> None:
    """Dotted paths walk nested dicts — useful when an FK is hydrated
    with a sub-dict (e.g. `subject.name`)."""
    items = [_item(subject={"name": "Chemistry", "code": "CHM"})]
    slots = _build_day_timeline_slots(
        items=items, config=_config(card="{{ subject.name }}"), now=_NOW
    )
    assert slots[0]["body"] == "Chemistry"


def test_body_graceful_when_field_missing() -> None:
    """Unresolved paths render as empty string — the rest of the
    template still produces useful output."""
    items = [_item(subject="History")]  # no teacher
    slots = _build_day_timeline_slots(
        items=items,
        config=_config(card="{{ subject }} — {{ teacher }}"),
        now=_NOW,
    )
    assert slots[0]["body"] == "History — "


def test_body_empty_when_card_not_set() -> None:
    """Regression guard: when DSL doesn't declare `card:`, the body
    stays empty — matches pre-#1146-part-1 behaviour."""
    items = [_item(subject="Maths")]
    slots = _build_day_timeline_slots(items=items, config=_config(), now=_NOW)
    assert slots[0]["body"] == ""


def test_body_per_row_independent() -> None:
    """Two rows produce two independently-interpolated bodies — no
    cross-row state leakage."""
    items = [
        _item(item_id="p1", subject="Maths"),
        {
            "id": "p2",
            "starts_at": _NOW + _dt.timedelta(hours=1),
            "ends_at": _NOW + _dt.timedelta(hours=2),
            "subject": "French",
        },
    ]
    slots = _build_day_timeline_slots(items=items, config=_config(card="{{ subject }}"), now=_NOW)
    bodies = {s["slot_id"]: s["body"] for s in slots}
    assert bodies["p1"] == "Maths"
    assert bodies["p2"] == "French"
