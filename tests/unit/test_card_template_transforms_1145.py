"""#1145 part 1: time-arithmetic transforms in `{{ field | transform }}`
templates.

Pre-fix `_interpolate_card_template` only did field substitution —
the `as_task` `meta:` line of an inbox chip could not say "in 5
minutes" relative to a TIME or DATETIME column. After #1145 part 1,
three registered transforms close the gap:

- `minutes_until` — clock-granularity "in N minutes" / "now" / "earlier today" / "overdue"
- `age` — "N minutes ago" / "N hours ago" / "N days ago"
- `until` — day-granularity "due today" / "due in N days" / "overdue by N days"

Tests pin the format AegisMark's `_minutes_until` helper already
produces — the migration target.
"""

from __future__ import annotations

import datetime as _dt

import pytest

from dazzle.http.runtime import workspace_card_data as _wcd


@pytest.fixture
def fixed_now(monkeypatch: pytest.MonkeyPatch) -> _dt.datetime:
    """Pin ``now`` to a known instant so the transform outputs are
    deterministic. All test rows are stated relative to this."""
    now = _dt.datetime(2026, 5, 19, 10, 0, tzinfo=_dt.UTC)
    monkeypatch.setattr(_wcd, "_now_utc", lambda: now)
    return now


# ---------------------------------------------------------------------------
# minutes_until
# ---------------------------------------------------------------------------


def test_minutes_until_future_minutes(fixed_now) -> None:
    item = {"t": "10:05"}  # 5 minutes ahead of fixed_now
    result = _wcd._interpolate_card_template("{{ t | minutes_until }}", item)
    assert result == "in 5 minutes"


def test_minutes_until_one_minute_singular(fixed_now) -> None:
    item = {"t": "10:01"}
    assert _wcd._interpolate_card_template("{{ t | minutes_until }}", item) == "in 1 minute"


def test_minutes_until_now_when_within_a_minute(fixed_now) -> None:
    item = {"t": "10:00"}
    assert _wcd._interpolate_card_template("{{ t | minutes_until }}", item) == "now"


def test_minutes_until_hours_format(fixed_now) -> None:
    item = {"t": "12:00"}  # 2 hours ahead
    assert _wcd._interpolate_card_template("{{ t | minutes_until }}", item) == "in 2 hours"


def test_minutes_until_past_same_day(fixed_now) -> None:
    item = {"t": "08:00"}  # earlier today
    assert _wcd._interpolate_card_template("{{ t | minutes_until }}", item) == "earlier today"


def test_minutes_until_past_different_day(fixed_now) -> None:
    item = {"t": "2026-05-15T10:00:00+00:00"}  # 4 days ago
    assert _wcd._interpolate_card_template("{{ t | minutes_until }}", item) == "overdue"


# ---------------------------------------------------------------------------
# age
# ---------------------------------------------------------------------------


def test_age_within_a_minute_is_just_now(fixed_now) -> None:
    item = {"t": fixed_now}
    assert _wcd._interpolate_card_template("{{ t | age }}", item) == "just now"


def test_age_minutes_ago(fixed_now) -> None:
    item = {"t": "09:50"}  # 10 minutes ago
    assert _wcd._interpolate_card_template("{{ t | age }}", item) == "10 minutes ago"


def test_age_hours_ago(fixed_now) -> None:
    item = {"t": "07:00"}  # 3 hours ago
    assert _wcd._interpolate_card_template("{{ t | age }}", item) == "3 hours ago"


def test_age_days_ago(fixed_now) -> None:
    item = {"t": "2026-05-15T10:00:00+00:00"}
    assert _wcd._interpolate_card_template("{{ t | age }}", item) == "4 days ago"


# ---------------------------------------------------------------------------
# until
# ---------------------------------------------------------------------------


def test_until_today(fixed_now) -> None:
    item = {"due": "2026-05-19T18:00:00+00:00"}
    assert _wcd._interpolate_card_template("{{ due | until }}", item) == "due today"


def test_until_tomorrow(fixed_now) -> None:
    item = {"due": "2026-05-20T10:00:00+00:00"}
    assert _wcd._interpolate_card_template("{{ due | until }}", item) == "due tomorrow"


def test_until_future_days(fixed_now) -> None:
    item = {"due": "2026-05-26T10:00:00+00:00"}  # 7 days ahead
    assert _wcd._interpolate_card_template("{{ due | until }}", item) == "due in 7 days"


def test_until_overdue_one_day(fixed_now) -> None:
    item = {"due": "2026-05-18T10:00:00+00:00"}
    assert _wcd._interpolate_card_template("{{ due | until }}", item) == "overdue"


def test_until_overdue_many_days(fixed_now) -> None:
    item = {"due": "2026-05-12T10:00:00+00:00"}  # 7 days ago
    assert _wcd._interpolate_card_template("{{ due | until }}", item) == "overdue by 7 days"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_unknown_transform_falls_back_to_raw_value(fixed_now) -> None:
    """An unknown transform name is treated as no-transform — render
    the raw field. Graceful degradation matches the rest of the
    template grammar."""
    item = {"t": "10:30"}
    assert _wcd._interpolate_card_template("{{ t | bogus_xform }}", item) == "10:30"


def test_no_transform_unchanged(fixed_now) -> None:
    """Regression guard — bare `{{ field }}` (no transform) renders
    the raw value the same as pre-#1145."""
    item = {"name": "Alice"}
    assert _wcd._interpolate_card_template("{{ name }}", item) == "Alice"


def test_transform_on_missing_field_renders_empty(fixed_now) -> None:
    """If the field path doesn't resolve, transforms produce empty
    string — same graceful-degradation contract as missing fields."""
    item: dict = {}
    assert _wcd._interpolate_card_template("{{ t | minutes_until }}", item) == ""


def test_dotted_path_with_transform(fixed_now) -> None:
    """Dotted path + transform composes — the resolved nested value
    feeds the transform."""
    item = {"period": {"start_time": "10:15"}}
    assert (
        _wcd._interpolate_card_template("{{ period.start_time | minutes_until }}", item)
        == "in 15 minutes"
    )


def test_mixed_template_with_field_and_transform(fixed_now) -> None:
    """A template with both bare fields and a transformed field
    renders correctly — the transform suffix is per-placeholder."""
    item = {"name": "Maths", "start": "10:30"}
    out = _wcd._interpolate_card_template("Register {{ name }} ({{ start | minutes_until }})", item)
    assert out == "Register Maths (in 30 minutes)"
