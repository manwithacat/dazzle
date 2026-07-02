"""Issue #1016 (v0.67.14): regression tests for the day_timeline
data resolution layer.

Covers `_build_day_timeline_slots` — the helper that shapes
already-scoped source rows into day_timeline slot dicts. The active
slot is determined by comparing `now` against each row's [starts_at,
ends_at] window. At most one slot may be marked "active".
"""

from __future__ import annotations

import datetime as _dt

import pytest

from dazzle.core.ir.workspaces import DayTimelineConfig
from dazzle.http.runtime.workspace_card_data import _build_day_timeline_slots


def _config(*, starts_at: str = "starts_at", ends_at: str = "ends_at") -> DayTimelineConfig:
    return DayTimelineConfig(starts_at=starts_at, ends_at=ends_at)


_NOW = _dt.datetime(2026, 5, 10, 11, 0, tzinfo=_dt.UTC)


def _item(item_id: str, starts: str | _dt.datetime, ends: str | _dt.datetime, **extra) -> dict:
    return {"id": item_id, "starts_at": starts, "ends_at": ends, **extra}


# ── empty guards ──


@pytest.mark.parametrize(
    ("items", "config"),
    [
        pytest.param([], _config(), id="no-items"),
        pytest.param([_item("1", _NOW, _NOW)], None, id="config-missing"),
    ],
)
def test_returns_empty(items: list[dict], config: DayTimelineConfig | None) -> None:
    slots = _build_day_timeline_slots(items=items, config=config, now=_NOW)
    assert slots == []


# ── invalid-row skipping (bad rows dropped, valid rows kept) ──


@pytest.mark.parametrize(
    ("items", "expected_count"),
    [
        pytest.param(
            [
                {"id": "p1", "starts_at": _NOW, "ends_at": _NOW},
                {"id": "p2", "ends_at": _NOW},  # missing starts_at
            ],
            1,
            id="missing-starts-at",
        ),
        pytest.param(
            [
                _item("p1", _NOW, _NOW),
                _item("", _NOW, _NOW),
                {"id": None, "starts_at": _NOW, "ends_at": _NOW},
            ],
            1,
            id="missing-or-empty-id",
        ),
        pytest.param(
            [_item("p1", "not-a-date", _NOW)],
            0,
            id="invalid-iso-string",
        ),
    ],
)
def test_skips_invalid_rows(items: list[dict], expected_count: int) -> None:
    slots = _build_day_timeline_slots(items=items, config=_config(), now=_NOW)
    assert len(slots) == expected_count


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


# ── active-slot cardinality ──


@pytest.mark.parametrize(
    ("items", "expected_active_count"),
    [
        # Defensive: even if windows overlap such that two would contain
        # `now`, only the first matched is marked active.
        pytest.param(
            [
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
            ],
            1,
            id="overlapping-windows-at-most-one-active",
        ),
        # Before-school / after-school / weekend → no slot active,
        # all positioned relative to `now`.
        pytest.param(
            [
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
            ],
            0,
            id="now-outside-all-windows-none-active",
        ),
    ],
)
def test_active_slot_count(items: list[dict], expected_active_count: int) -> None:
    slots = _build_day_timeline_slots(items=items, config=_config(), now=_NOW)
    actives = [s for s in slots if s["position"] == "active"]
    assert len(actives) == expected_active_count


# ── timestamp coercion (non-datetime representations still resolve) ──


@pytest.mark.parametrize(
    "items",
    [
        # Source rows often arrive with ISO strings rather than datetime
        # objects — both should work.
        pytest.param(
            [_item("p1", "2026-05-10T10:30:00+00:00", "2026-05-10T11:30:00+00:00")],
            id="iso-string-timestamps-parse",
        ),
        # Defensive: naive datetimes shouldn't crash the aware-vs-naive
        # comparison — coerce to UTC.
        pytest.param(
            [_item("p1", _dt.datetime(2026, 5, 10, 10, 30), _dt.datetime(2026, 5, 10, 11, 30))],
            id="naive-datetime-treated-as-utc",
        ),
    ],
)
def test_timestamp_coercion_resolves_active_slot(items: list[dict]) -> None:
    slots = _build_day_timeline_slots(items=items, config=_config(), now=_NOW)
    assert len(slots) == 1
    assert slots[0]["position"] == "active"


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


# ── label fallback chain (name → title → message) ──


@pytest.mark.parametrize(
    ("extra", "expected"),
    [
        pytest.param({"name": "Morning briefing"}, "Morning briefing", id="name-field"),
        pytest.param({"message": "API 5xx alert"}, "API 5xx alert", id="title-then-message"),
    ],
)
def test_label_fallback(extra: dict, expected: str) -> None:
    items = [
        _item(
            "p1",
            _dt.datetime(2026, 5, 10, 9, 0, tzinfo=_dt.UTC),
            _dt.datetime(2026, 5, 10, 10, 0, tzinfo=_dt.UTC),
            **extra,
        ),
    ]
    slots = _build_day_timeline_slots(items=items, config=_config(), now=_NOW)
    assert slots[0]["label"] == expected
