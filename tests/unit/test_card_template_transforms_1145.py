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


@pytest.mark.parametrize(
    ("template", "item", "expected"),
    [
        # minutes_until -----------------------------------------------------
        pytest.param(
            "{{ t | minutes_until }}",
            {"t": "10:05"},  # 5 minutes ahead of fixed_now
            "in 5 minutes",
            id="minutes_until-future-minutes",
        ),
        pytest.param(
            "{{ t | minutes_until }}",
            {"t": "10:01"},
            "in 1 minute",
            id="minutes_until-one-minute-singular",
        ),
        pytest.param(
            "{{ t | minutes_until }}",
            {"t": "10:00"},
            "now",
            id="minutes_until-now-when-within-a-minute",
        ),
        pytest.param(
            "{{ t | minutes_until }}",
            {"t": "12:00"},  # 2 hours ahead
            "in 2 hours",
            id="minutes_until-hours-format",
        ),
        pytest.param(
            "{{ t | minutes_until }}",
            {"t": "08:00"},  # earlier today
            "earlier today",
            id="minutes_until-past-same-day",
        ),
        pytest.param(
            "{{ t | minutes_until }}",
            {"t": "2026-05-15T10:00:00+00:00"},  # 4 days ago
            "overdue",
            id="minutes_until-past-different-day",
        ),
        # age ---------------------------------------------------------------
        pytest.param(
            "{{ t | age }}",
            {"t": "09:50"},  # 10 minutes ago
            "10 minutes ago",
            id="age-minutes-ago",
        ),
        pytest.param(
            "{{ t | age }}",
            {"t": "07:00"},  # 3 hours ago
            "3 hours ago",
            id="age-hours-ago",
        ),
        pytest.param(
            "{{ t | age }}",
            {"t": "2026-05-15T10:00:00+00:00"},
            "4 days ago",
            id="age-days-ago",
        ),
        # until -------------------------------------------------------------
        pytest.param(
            "{{ due | until }}",
            {"due": "2026-05-19T18:00:00+00:00"},
            "due today",
            id="until-today",
        ),
        pytest.param(
            "{{ due | until }}",
            {"due": "2026-05-20T10:00:00+00:00"},
            "due tomorrow",
            id="until-tomorrow",
        ),
        pytest.param(
            "{{ due | until }}",
            {"due": "2026-05-26T10:00:00+00:00"},  # 7 days ahead
            "due in 7 days",
            id="until-future-days",
        ),
        pytest.param(
            "{{ due | until }}",
            {"due": "2026-05-18T10:00:00+00:00"},
            "overdue",
            id="until-overdue-one-day",
        ),
        pytest.param(
            "{{ due | until }}",
            {"due": "2026-05-12T10:00:00+00:00"},  # 7 days ago
            "overdue by 7 days",
            id="until-overdue-many-days",
        ),
        # Edge cases ---------------------------------------------------------
        pytest.param(
            "{{ t | bogus_xform }}",
            {"t": "10:30"},
            "10:30",
            # Unknown transform name = no-transform: render the raw field
            # (graceful degradation matches the rest of the template grammar).
            id="unknown-transform-falls-back-to-raw-value",
        ),
        pytest.param(
            "{{ name }}",
            {"name": "Alice"},
            "Alice",
            # Regression guard — bare `{{ field }}` renders the raw value
            # the same as pre-#1145.
            id="no-transform-unchanged",
        ),
        pytest.param(
            "{{ t | minutes_until }}",
            {},
            "",
            # Unresolvable field path + transform = empty string — same
            # graceful-degradation contract as missing fields.
            id="transform-on-missing-field-renders-empty",
        ),
        pytest.param(
            "{{ period.start_time | minutes_until }}",
            {"period": {"start_time": "10:15"}},
            "in 15 minutes",
            # Dotted path + transform composes — the resolved nested value
            # feeds the transform.
            id="dotted-path-with-transform",
        ),
        pytest.param(
            "Register {{ name }} ({{ start | minutes_until }})",
            {"name": "Maths", "start": "10:30"},
            "Register Maths (in 30 minutes)",
            # Bare fields + a transformed field in one template — the
            # transform suffix is per-placeholder.
            id="mixed-template-with-field-and-transform",
        ),
    ],
)
def test_interpolate_card_template(fixed_now, template: str, item: dict, expected: str) -> None:
    """One (template, item, expected) row per transform contract, all
    stated relative to ``fixed_now`` (2026-05-19 10:00 UTC)."""
    assert _wcd._interpolate_card_template(template, item) == expected


def test_age_within_a_minute_is_just_now(fixed_now) -> None:
    item = {"t": fixed_now}
    assert _wcd._interpolate_card_template("{{ t | age }}", item) == "just now"
