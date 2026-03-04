"""
Unit tests for ProcessManager schedule registration.
"""

from __future__ import annotations

import pytest


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
