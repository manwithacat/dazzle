"""#1146 part 2: `as_of:` date-anchor composition for HH:MM timetables.

Pre-fix `_to_dt` only accepted full datetimes — schools' timetable
rows that store TIME (e.g. `15:30`) + DATE in separate fields had
no way to compose them, so day_timeline silently dropped every row.
After #1146 part 2, `DayTimelineConfig.as_of` names the date anchor
(`"today"` or a row field) and the runtime composes
`date + time → datetime`.
"""

from __future__ import annotations

import datetime as _dt

from dazzle.core.ir.workspaces import DayTimelineConfig
from dazzle.http.runtime.workspace_card_data import _build_day_timeline_slots

_NOW = _dt.datetime(2026, 5, 10, 11, 0, tzinfo=_dt.UTC)


def _config(as_of: str = "") -> DayTimelineConfig:
    return DayTimelineConfig(starts_at="start_time", ends_at="end_time", as_of=as_of)


def test_as_of_today_composes_hhmm_with_today() -> None:
    """`as_of: today` composes HH:MM time strings with the current
    UTC date — the canonical HH:MM timetable shape."""
    items = [
        {"id": "p1", "start_time": "10:30", "end_time": "11:30"},
    ]
    slots = _build_day_timeline_slots(items=items, config=_config(as_of="today"), now=_NOW)
    # Row is no longer dropped; it renders.
    assert len(slots) == 1
    assert slots[0]["slot_id"] == "p1"


def test_as_of_field_composes_with_per_row_date() -> None:
    """`as_of: schedule_date` reads the date from each row's named
    field — different rows can carry different dates."""
    items = [
        {
            "id": "p1",
            "start_time": "09:00",
            "end_time": "10:00",
            "schedule_date": "2026-05-10",
        },
        {
            "id": "p2",
            "start_time": "11:00",
            "end_time": "12:00",
            "schedule_date": "2026-05-11",
        },
    ]
    slots = _build_day_timeline_slots(items=items, config=_config(as_of="schedule_date"), now=_NOW)
    assert {s["slot_id"] for s in slots} == {"p1", "p2"}


def test_as_of_accepts_time_objects() -> None:
    """Postgres-backed TIME columns arrive as `datetime.time` — the
    composition path must handle the type-correct value too."""
    items = [
        {
            "id": "p1",
            "start_time": _dt.time(14, 0),
            "end_time": _dt.time(15, 0),
        },
    ]
    slots = _build_day_timeline_slots(items=items, config=_config(as_of="today"), now=_NOW)
    assert len(slots) == 1


def test_no_as_of_drops_hhmm_rows_as_before() -> None:
    """Regression guard: without `as_of:`, HH:MM strings still fail
    to parse — matches pre-#1146-part-2 behaviour. (Authors with
    timetable schemas now need to declare `as_of:` explicitly.)"""
    items = [
        {"id": "p1", "start_time": "10:30", "end_time": "11:30"},
    ]
    slots = _build_day_timeline_slots(items=items, config=_config(), now=_NOW)
    assert slots == []


def test_as_of_with_unparseable_date_drops_row() -> None:
    """If the row's date field is missing or unparseable, the
    composition can't happen — the row drops with no exception."""
    items = [
        {
            "id": "p1",
            "start_time": "10:30",
            "end_time": "11:30",
            "schedule_date": "garbage",
        },
    ]
    slots = _build_day_timeline_slots(items=items, config=_config(as_of="schedule_date"), now=_NOW)
    assert slots == []


def test_full_datetime_still_works_with_as_of_set() -> None:
    """When the field carries a full datetime (e.g. a non-timetable
    surface that opted into `as_of:` by mistake), the existing
    datetime parsing wins — `as_of:` is only consulted when the
    value is a TIME or HH:MM string."""
    items = [
        {
            "id": "p1",
            "start_time": "2026-05-10T10:30:00+00:00",
            "end_time": "2026-05-10T11:30:00+00:00",
        },
    ]
    slots = _build_day_timeline_slots(items=items, config=_config(as_of="today"), now=_NOW)
    assert len(slots) == 1
