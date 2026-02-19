"""
Unit tests for cron schedule evaluation and schedule integration.

Tests the _cron_match_field and _cron_due functions in lite_helpers,
and the ProcessManager schedule registration flow.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from dazzle.core.process.lite_helpers import _cron_due, _cron_match_field


class TestCronMatchField:
    """Tests for individual cron field matching."""

    def test_wildcard_matches_any(self) -> None:
        assert _cron_match_field("*", 0, 0, 59) is True
        assert _cron_match_field("*", 30, 0, 59) is True
        assert _cron_match_field("*", 59, 0, 59) is True

    def test_exact_value(self) -> None:
        assert _cron_match_field("5", 5, 0, 59) is True
        assert _cron_match_field("5", 6, 0, 59) is False
        assert _cron_match_field("0", 0, 0, 59) is True

    def test_comma_list(self) -> None:
        assert _cron_match_field("1,5,10", 5, 0, 59) is True
        assert _cron_match_field("1,5,10", 3, 0, 59) is False
        assert _cron_match_field("0,30", 30, 0, 59) is True

    def test_range(self) -> None:
        assert _cron_match_field("1-5", 3, 0, 59) is True
        assert _cron_match_field("1-5", 1, 0, 59) is True
        assert _cron_match_field("1-5", 5, 0, 59) is True
        assert _cron_match_field("1-5", 6, 0, 59) is False

    def test_step_with_wildcard(self) -> None:
        assert _cron_match_field("*/5", 0, 0, 59) is True
        assert _cron_match_field("*/5", 5, 0, 59) is True
        assert _cron_match_field("*/5", 15, 0, 59) is True
        assert _cron_match_field("*/5", 3, 0, 59) is False

    def test_step_with_range(self) -> None:
        assert _cron_match_field("1-10/3", 1, 0, 59) is True
        assert _cron_match_field("1-10/3", 4, 0, 59) is True
        assert _cron_match_field("1-10/3", 7, 0, 59) is True
        assert _cron_match_field("1-10/3", 2, 0, 59) is False
        assert _cron_match_field("1-10/3", 11, 0, 59) is False

    def test_hours(self) -> None:
        assert _cron_match_field("8", 8, 0, 23) is True
        assert _cron_match_field("8", 9, 0, 23) is False

    def test_day_of_month(self) -> None:
        assert _cron_match_field("1", 1, 1, 31) is True
        assert _cron_match_field("15", 15, 1, 31) is True


class TestCronDue:
    """Tests for the full cron due evaluation."""

    def test_daily_at_8am(self) -> None:
        """Cron '0 8 * * *' should fire at 8:00 AM."""
        last_run = datetime(2026, 2, 18, 8, 0, 0, tzinfo=UTC)
        # 24 hours later at 8:00 AM — should fire
        now = datetime(2026, 2, 19, 8, 0, 0, tzinfo=UTC)
        assert _cron_due("0 8 * * *", last_run, now) is True

    def test_daily_at_8am_not_yet(self) -> None:
        """Cron '0 8 * * *' should NOT fire at 7:59 AM."""
        last_run = datetime(2026, 2, 18, 8, 0, 0, tzinfo=UTC)
        now = datetime(2026, 2, 19, 7, 59, 0, tzinfo=UTC)
        assert _cron_due("0 8 * * *", last_run, now) is False

    def test_every_five_minutes(self) -> None:
        """Cron '*/5 * * * *' should fire every 5 minutes."""
        last_run = datetime(2026, 2, 18, 10, 0, 0, tzinfo=UTC)
        now = datetime(2026, 2, 18, 10, 5, 0, tzinfo=UTC)
        assert _cron_due("*/5 * * * *", last_run, now) is True

    def test_every_five_minutes_not_yet(self) -> None:
        """Cron '*/5 * * * *' should NOT fire after 3 minutes."""
        last_run = datetime(2026, 2, 18, 10, 0, 0, tzinfo=UTC)
        now = datetime(2026, 2, 18, 10, 3, 0, tzinfo=UTC)
        assert _cron_due("*/5 * * * *", last_run, now) is False

    def test_too_recent(self) -> None:
        """If less than 60 seconds since last run, never fires."""
        last_run = datetime(2026, 2, 18, 10, 0, 0, tzinfo=UTC)
        now = datetime(2026, 2, 18, 10, 0, 30, tzinfo=UTC)
        assert _cron_due("* * * * *", last_run, now) is False

    def test_every_minute(self) -> None:
        """Cron '* * * * *' fires every minute."""
        last_run = datetime(2026, 2, 18, 10, 0, 0, tzinfo=UTC)
        now = datetime(2026, 2, 18, 10, 1, 0, tzinfo=UTC)
        assert _cron_due("* * * * *", last_run, now) is True

    def test_specific_weekday(self) -> None:
        """Cron '0 9 * * 1' fires at 9 AM on Monday (isoweekday 1 → cron 1)."""
        # 2026-02-16 is a Monday
        last_run = datetime(2026, 2, 9, 9, 0, 0, tzinfo=UTC)  # Previous Monday
        now = datetime(2026, 2, 16, 9, 0, 0, tzinfo=UTC)  # This Monday
        assert _cron_due("0 9 * * 1", last_run, now) is True

    def test_specific_weekday_wrong_day(self) -> None:
        """Cron '0 9 * * 1' should NOT fire on Tuesday."""
        # 2026-02-17 is a Tuesday
        last_run = datetime(2026, 2, 16, 9, 0, 0, tzinfo=UTC)
        now = datetime(2026, 2, 17, 9, 0, 0, tzinfo=UTC)  # Tuesday
        assert _cron_due("0 9 * * 1", last_run, now) is False

    def test_invalid_cron_returns_false(self) -> None:
        """Invalid cron expression should return False."""
        last_run = datetime(2026, 2, 18, 10, 0, 0, tzinfo=UTC)
        now = datetime(2026, 2, 18, 11, 0, 0, tzinfo=UTC)
        assert _cron_due("bad", last_run, now) is False

    def test_window_cap_at_24_hours(self) -> None:
        """Cron '0 8 * * *' fires even after 48-hour gap (capped at 24h window)."""
        last_run = datetime(2026, 2, 16, 8, 0, 0, tzinfo=UTC)
        now = datetime(2026, 2, 18, 9, 0, 0, tzinfo=UTC)  # 49 hours later
        assert _cron_due("0 8 * * *", last_run, now) is True

    def test_hourly(self) -> None:
        """Cron '0 * * * *' fires at top of every hour."""
        last_run = datetime(2026, 2, 18, 10, 0, 0, tzinfo=UTC)
        now = datetime(2026, 2, 18, 11, 0, 0, tzinfo=UTC)
        assert _cron_due("0 * * * *", last_run, now) is True

    def test_first_of_month(self) -> None:
        """Cron '0 0 1 * *' fires at midnight on the 1st."""
        last_run = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
        now = datetime(2026, 2, 1, 0, 0, 0, tzinfo=UTC)
        assert _cron_due("0 0 1 * *", last_run, now) is True


class TestProcessManagerScheduleRegistration:
    """Tests that ProcessManager correctly registers schedules."""

    @pytest.mark.asyncio
    async def test_schedule_registered_on_initialize(self) -> None:
        """Schedule specs are passed to adapter on initialize."""
        from unittest.mock import AsyncMock

        from dazzle.core.ir.process import ScheduleSpec
        from dazzle_back.runtime.process_manager import ProcessManager

        sched = ScheduleSpec(
            name="daily_check",
            process="check_deadlines",
            cron="0 8 * * *",
        )

        adapter = AsyncMock()
        adapter.register_process = AsyncMock()
        adapter.register_schedule = AsyncMock()

        mgr = ProcessManager(adapter=adapter, schedule_specs=[sched])
        await mgr.initialize()

        adapter.register_schedule.assert_called_once_with(sched)

    @pytest.mark.asyncio
    async def test_multiple_schedules_registered(self) -> None:
        """Multiple schedule specs are all registered."""
        from unittest.mock import AsyncMock

        from dazzle.core.ir.process import ScheduleSpec
        from dazzle_back.runtime.process_manager import ProcessManager

        scheds = [
            ScheduleSpec(name="daily", process="daily_job", cron="0 8 * * *"),
            ScheduleSpec(name="hourly", process="hourly_job", cron="0 * * * *"),
        ]

        adapter = AsyncMock()
        adapter.register_process = AsyncMock()
        adapter.register_schedule = AsyncMock()

        mgr = ProcessManager(adapter=adapter, schedule_specs=scheds)
        await mgr.initialize()

        assert adapter.register_schedule.call_count == 2
