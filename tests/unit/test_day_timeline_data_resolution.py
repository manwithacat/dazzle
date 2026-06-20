"""Issue #1016 (v0.67.14): regression tests for the day_timeline
data resolution layer.

Covers `_build_day_timeline_slots` — the helper that shapes
already-scoped source rows into day_timeline slot dicts. The active
slot is determined by comparing `now` against each row's [starts_at,
ends_at] window. At most one slot may be marked "active".
"""

from __future__ import annotations

import datetime as _dt

from dazzle.core.ir.workspaces import DayTimelineConfig
from dazzle.http.runtime.workspace_card_data import _build_day_timeline_slots


def _config(*, starts_at: str = "starts_at", ends_at: str = "ends_at") -> DayTimelineConfig:
    return DayTimelineConfig(starts_at=starts_at, ends_at=ends_at)


_NOW = _dt.datetime(2026, 5, 10, 11, 0, tzinfo=_dt.UTC)


def _item(item_id: str, starts: str | _dt.datetime, ends: str | _dt.datetime, **extra) -> dict:
    return {"id": item_id, "starts_at": starts, "ends_at": ends, **extra}


def test_returns_empty_when_no_items() -> None:
    slots = _build_day_timeline_slots(items=[], config=_config(), now=_NOW)
    assert slots == []


def test_returns_empty_when_config_missing() -> None:
    slots = _build_day_timeline_slots(items=[_item("1", _NOW, _NOW)], config=None, now=_NOW)
    assert slots == []


def test_skips_rows_with_missing_starts_at() -> None:
    items = [
        {"id": "p1", "starts_at": _NOW, "ends_at": _NOW},
        {"id": "p2", "ends_at": _NOW},  # missing starts_at
    ]
    slots = _build_day_timeline_slots(items=items, config=_config(), now=_NOW)
    assert len(slots) == 1


def test_skips_rows_without_id() -> None:
    items = [
        _item("p1", _NOW, _NOW),
        _item("", _NOW, _NOW),
        {"id": None, "starts_at": _NOW, "ends_at": _NOW},
    ]
    slots = _build_day_timeline_slots(items=items, config=_config(), now=_NOW)
    assert len(slots) == 1


def test_active_slot_is_one_whose_window_contains_now() -> None:
    items = [
        _item(
            "p1",
            _dt.datetime(2026, 5, 10, 9, 0, tzinfo=_dt.UTC),
            _dt.datetime(2026, 5, 10, 10, 0, tzinfo=_dt.UTC),
        ),  # before
        _item(
            "p2",
            _dt.datetime(2026, 5, 10, 10, 30, tzinfo=_dt.UTC),
            _dt.datetime(2026, 5, 10, 11, 30, tzinfo=_dt.UTC),
        ),  # active
        _item(
            "p3",
            _dt.datetime(2026, 5, 10, 12, 0, tzinfo=_dt.UTC),
            _dt.datetime(2026, 5, 10, 13, 0, tzinfo=_dt.UTC),
        ),  # after
    ]
    slots = _build_day_timeline_slots(items=items, config=_config(), now=_NOW)
    by_id = {s["slot_id"]: s for s in slots}
    assert by_id["p1"]["position"] == "before"
    assert by_id["p2"]["position"] == "active"
    assert by_id["p3"]["position"] == "after"


def test_at_most_one_slot_active() -> None:
    """Defensive: even if windows overlap such that two would
    contain `now`, only the first matched is marked active."""
    items = [
        _item(
            "p1",
            _dt.datetime(2026, 5, 10, 10, 0, tzinfo=_dt.UTC),
            _dt.datetime(2026, 5, 10, 12, 0, tzinfo=_dt.UTC),
        ),
        _item(
            "p2",
            _dt.datetime(2026, 5, 10, 10, 30, tzinfo=_dt.UTC),
            _dt.datetime(2026, 5, 10, 11, 30, tzinfo=_dt.UTC),
        ),
    ]
    slots = _build_day_timeline_slots(items=items, config=_config(), now=_NOW)
    actives = [s for s in slots if s["position"] == "active"]
    assert len(actives) == 1


def test_iso_string_timestamps_parse() -> None:
    """Source rows often arrive with ISO strings rather than
    datetime objects — both should work."""
    items = [
        _item(
            "p1",
            "2026-05-10T10:30:00+00:00",
            "2026-05-10T11:30:00+00:00",
        ),
    ]
    slots = _build_day_timeline_slots(items=items, config=_config(), now=_NOW)
    assert len(slots) == 1
    assert slots[0]["position"] == "active"


def test_naive_datetime_treated_as_utc() -> None:
    """Defensive: naive datetimes shouldn't crash the
    aware-vs-naive comparison — coerce to UTC."""
    naive_now = _dt.datetime(2026, 5, 10, 10, 30)
    naive_end = _dt.datetime(2026, 5, 10, 11, 30)
    items = [_item("p1", naive_now, naive_end)]
    slots = _build_day_timeline_slots(items=items, config=_config(), now=_NOW)
    assert slots[0]["position"] == "active"


def test_no_active_when_now_outside_all_windows() -> None:
    """Before-school / after-school / weekend → no slot active,
    all positioned relative to `now`."""
    items = [
        _item(
            "morning",
            _dt.datetime(2026, 5, 10, 8, 0, tzinfo=_dt.UTC),
            _dt.datetime(2026, 5, 10, 9, 0, tzinfo=_dt.UTC),
        ),
        _item(
            "evening",
            _dt.datetime(2026, 5, 10, 16, 0, tzinfo=_dt.UTC),
            _dt.datetime(2026, 5, 10, 17, 0, tzinfo=_dt.UTC),
        ),
    ]
    slots = _build_day_timeline_slots(items=items, config=_config(), now=_NOW)
    actives = [s for s in slots if s["position"] == "active"]
    assert len(actives) == 0


def test_slots_returned_chronologically() -> None:
    """Adapter trusts upstream sort order; helper sorts."""
    items = [
        _item(
            "late",
            _dt.datetime(2026, 5, 10, 13, 0, tzinfo=_dt.UTC),
            _dt.datetime(2026, 5, 10, 14, 0, tzinfo=_dt.UTC),
        ),
        _item(
            "early",
            _dt.datetime(2026, 5, 10, 9, 0, tzinfo=_dt.UTC),
            _dt.datetime(2026, 5, 10, 10, 0, tzinfo=_dt.UTC),
        ),
        _item(
            "mid",
            _dt.datetime(2026, 5, 10, 11, 0, tzinfo=_dt.UTC),
            _dt.datetime(2026, 5, 10, 12, 0, tzinfo=_dt.UTC),
        ),
    ]
    slots = _build_day_timeline_slots(items=items, config=_config(), now=_NOW)
    assert [s["slot_id"] for s in slots] == ["early", "mid", "late"]


def test_label_falls_back_to_name_field() -> None:
    items = [
        _item(
            "p1",
            _dt.datetime(2026, 5, 10, 9, 0, tzinfo=_dt.UTC),
            _dt.datetime(2026, 5, 10, 10, 0, tzinfo=_dt.UTC),
            name="Morning briefing",
        ),
    ]
    slots = _build_day_timeline_slots(items=items, config=_config(), now=_NOW)
    assert slots[0]["label"] == "Morning briefing"


def test_label_falls_back_to_title_then_message() -> None:
    items = [
        _item(
            "p1",
            _dt.datetime(2026, 5, 10, 9, 0, tzinfo=_dt.UTC),
            _dt.datetime(2026, 5, 10, 10, 0, tzinfo=_dt.UTC),
            message="API 5xx alert",
        ),
    ]
    slots = _build_day_timeline_slots(items=items, config=_config(), now=_NOW)
    assert slots[0]["label"] == "API 5xx alert"


def test_invalid_iso_string_skips_row() -> None:
    items = [_item("p1", "not-a-date", _NOW)]
    slots = _build_day_timeline_slots(items=items, config=_config(), now=_NOW)
    assert slots == []
