"""Tests for #953 cycle 7 — cron parser + matcher.

Cycle 6 wired entity-event triggers; cycle 7 ships the cron-side
primitive the cycle-7b scheduler loop will use to decide when to
enqueue purely-scheduled jobs.

Tests cover:

  * `parse_cron` — `*`, `*/N`, literal int, all 5 fields,
    invalid-format / out-of-bounds rejection
  * `cron_matches` — datetime → bool for every field
  * `due_jobs` — multi-job dispatch + last-fired dedupe
  * POSIX weekday convention (0 = Sunday)
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from dazzle_back.runtime.cron import (
    CronParseError,
    cron_matches,
    due_jobs,
    parse_cron,
)

# ---------------------------------------------------------------------------
# parse_cron — wildcard / step / literal
# ---------------------------------------------------------------------------


class TestParseCronWildcard:
    def test_all_wildcards(self):
        c = parse_cron("* * * * *")
        assert len(c.minute) == 60
        assert len(c.hour) == 24
        assert len(c.day) == 31
        assert len(c.month) == 12
        assert len(c.weekday) == 7

    def test_minute_zero_in_wildcard(self):
        c = parse_cron("* * * * *")
        assert 0 in c.minute
        assert 59 in c.minute


class TestParseCronStep:
    def test_minute_step_5(self):
        c = parse_cron("*/5 * * * *")
        assert c.minute == frozenset({0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55})

    def test_hour_step_6(self):
        c = parse_cron("0 */6 * * *")
        assert c.hour == frozenset({0, 6, 12, 18})

    def test_step_zero_rejected(self):
        with pytest.raises(CronParseError, match="step must be > 0"):
            parse_cron("*/0 * * * *")

    def test_step_negative_rejected(self):
        with pytest.raises(CronParseError, match="must be a positive integer"):
            parse_cron("*/-1 * * * *")


class TestParseCronLiteral:
    def test_minute_literal(self):
        c = parse_cron("30 * * * *")
        assert c.minute == frozenset({30})

    def test_hour_one(self):
        # `cron("0 1 * * *")` from the spec — 01:00 daily.
        c = parse_cron("0 1 * * *")
        assert c.minute == frozenset({0})
        assert c.hour == frozenset({1})

    def test_out_of_bounds_rejected(self):
        with pytest.raises(CronParseError, match="out of bounds"):
            parse_cron("60 * * * *")  # minute max is 59
        with pytest.raises(CronParseError, match="out of bounds"):
            parse_cron("* 24 * * *")  # hour max is 23
        with pytest.raises(CronParseError, match="out of bounds"):
            parse_cron("* * 32 * *")  # day max is 31
        with pytest.raises(CronParseError, match="out of bounds"):
            parse_cron("* * * 13 *")  # month max is 12


class TestParseCronErrors:
    def test_wrong_field_count(self):
        with pytest.raises(CronParseError, match="must have 5 fields"):
            parse_cron("0 1 * *")
        with pytest.raises(CronParseError, match="must have 5 fields"):
            parse_cron("0 1 * * * *")

    def test_non_string_input(self):
        with pytest.raises(CronParseError, match="Expected str"):
            parse_cron(None)  # type: ignore[arg-type]

    def test_unsupported_form_rejected(self):
        # Comma-lists / ranges out of scope for cycle 7.
        with pytest.raises(CronParseError, match="only"):
            parse_cron("1,5,10 * * * *")
        with pytest.raises(CronParseError, match="only"):
            parse_cron("1-5 * * * *")


# ---------------------------------------------------------------------------
# cron_matches
# ---------------------------------------------------------------------------


def _at(*, year=2026, month=5, day=4, hour=0, minute=0, weekday=None):
    """Build a UTC datetime; assert the weekday if supplied so test
    intent is explicit."""
    dt = datetime(year, month, day, hour, minute, tzinfo=UTC)
    if weekday is not None:
        # POSIX 0=Sunday … 6=Saturday; Python datetime: 0=Mon … 6=Sun.
        actual = (dt.weekday() + 1) % 7
        assert actual == weekday, f"expected weekday {weekday}, got {actual}"
    return dt


class TestCronMatchesEveryField:
    def test_minute_matches(self):
        c = parse_cron("30 * * * *")
        assert cron_matches(c, _at(minute=30)) is True
        assert cron_matches(c, _at(minute=29)) is False

    def test_hour_matches(self):
        c = parse_cron("0 1 * * *")
        assert cron_matches(c, _at(hour=1)) is True
        assert cron_matches(c, _at(hour=2)) is False

    def test_day_matches(self):
        c = parse_cron("0 0 15 * *")
        assert cron_matches(c, _at(day=15)) is True
        assert cron_matches(c, _at(day=16)) is False

    def test_month_matches(self):
        c = parse_cron("0 0 1 6 *")
        assert cron_matches(c, _at(year=2026, month=6, day=1)) is True
        assert cron_matches(c, _at(year=2026, month=7, day=1)) is False

    def test_weekday_posix_sunday(self):
        # 2026-05-03 is a Sunday → POSIX weekday 0.
        c = parse_cron("0 0 * * 0")
        assert cron_matches(c, _at(year=2026, month=5, day=3, weekday=0)) is True
        # Monday → POSIX 1, no match.
        assert cron_matches(c, _at(year=2026, month=5, day=4, weekday=1)) is False

    def test_weekday_posix_saturday(self):
        # 2026-05-02 is a Saturday → POSIX weekday 6.
        c = parse_cron("0 0 * * 6")
        assert cron_matches(c, _at(year=2026, month=5, day=2, weekday=6)) is True

    def test_step_minute_only_matches_multiples(self):
        c = parse_cron("*/15 * * * *")
        assert cron_matches(c, _at(minute=0)) is True
        assert cron_matches(c, _at(minute=15)) is True
        assert cron_matches(c, _at(minute=14)) is False


# ---------------------------------------------------------------------------
# due_jobs
# ---------------------------------------------------------------------------


class TestDueJobs:
    def test_empty_jobs_returns_empty(self):
        assert due_jobs([], now=_at(), last_fired_minute={}) == []

    def test_matching_job_due(self):
        c = parse_cron("0 1 * * *")
        result = due_jobs(
            [("daily_summary", c)],
            now=_at(hour=1, minute=0),
            last_fired_minute={},
        )
        assert result == ["daily_summary"]

    def test_non_matching_job_skipped(self):
        c = parse_cron("0 1 * * *")
        result = due_jobs(
            [("daily_summary", c)],
            now=_at(hour=2, minute=0),
            last_fired_minute={},
        )
        assert result == []

    def test_already_fired_this_minute_dedupes(self):
        c = parse_cron("0 1 * * *")
        already = _at(hour=1, minute=0)
        result = due_jobs(
            [("daily_summary", c)],
            now=already,
            last_fired_minute={"daily_summary": already.replace(second=0, microsecond=0)},
        )
        assert result == []

    def test_fired_a_different_minute_does_not_dedupe(self):
        c = parse_cron("0 1 * * *")
        result = due_jobs(
            [("daily_summary", c)],
            now=_at(hour=1, minute=0),
            last_fired_minute={
                "daily_summary": _at(hour=1, minute=0).replace(day=3),  # yesterday's fire
            },
        )
        assert result == ["daily_summary"]

    def test_multiple_jobs_subset_due(self):
        every_minute = parse_cron("* * * * *")
        only_at_two = parse_cron("0 2 * * *")
        result = due_jobs(
            [("a", every_minute), ("b", only_at_two)],
            now=_at(hour=1, minute=0),
            last_fired_minute={},
        )
        assert result == ["a"]

    def test_seconds_truncated_for_dedupe_key(self):
        # `now` carries seconds, but the dedupe key is the minute —
        # re-call within the same minute (different second) should
        # still return empty when last_fired_minute is set.
        c = parse_cron("* * * * *")
        now_with_seconds = datetime(2026, 5, 4, 1, 0, 30, tzinfo=UTC)
        truncated = now_with_seconds.replace(second=0, microsecond=0)
        result = due_jobs(
            [("x", c)],
            now=now_with_seconds,
            last_fired_minute={"x": truncated},
        )
        assert result == []
