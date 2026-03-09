"""Tests for SLA runtime enforcement manager."""

from __future__ import annotations

import time
from datetime import UTC
from unittest.mock import AsyncMock

import pytest

from dazzle.core.ir.process import FieldAssignment
from dazzle.core.ir.sla import (
    BusinessHoursSpec,
    SLABreachActionSpec,
    SLAConditionSpec,
    SLASpec,
    SLATierSpec,
)
from dazzle_back.runtime.sla_manager import (
    SLAManager,
    SLATimer,
    business_seconds,
    parse_schedule,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_sla(
    name: str = "ticket_response",
    entity: str = "SupportTicket",
    starts_field: str = "status",
    starts_op: str = "->",
    starts_value: str = "open",
    pauses_field: str | None = "status",
    pauses_value: str | None = "on_hold",
    completes_field: str | None = "status",
    completes_value: str | None = "resolved",
    tiers: list[SLATierSpec] | None = None,
    business_hours: BusinessHoursSpec | None = None,
    on_breach: SLABreachActionSpec | None = None,
) -> SLASpec:
    return SLASpec(
        name=name,
        entity=entity,
        starts_when=SLAConditionSpec(field=starts_field, operator=starts_op, value=starts_value),
        pauses_when=(
            SLAConditionSpec(field=pauses_field, operator="=", value=pauses_value)
            if pauses_field and pauses_value
            else None
        ),
        completes_when=(
            SLAConditionSpec(field=completes_field, operator=starts_op, value=completes_value)
            if completes_field and completes_value
            else None
        ),
        tiers=tiers
        or [
            SLATierSpec(name="warning", duration_value=4, duration_unit="hours"),
            SLATierSpec(name="breach", duration_value=8, duration_unit="hours"),
            SLATierSpec(name="critical", duration_value=24, duration_unit="hours"),
        ],
        business_hours=business_hours,
        on_breach=on_breach,
    )


# ---------------------------------------------------------------------------
# parse_schedule
# ---------------------------------------------------------------------------


class TestParseSchedule:
    def test_mon_fri(self) -> None:
        weekdays, start, end = parse_schedule("Mon-Fri 09:00-17:00")
        assert weekdays == {0, 1, 2, 3, 4}
        assert start == (9, 0)
        assert end == (17, 0)

    def test_custom_days(self) -> None:
        weekdays, start, end = parse_schedule("Mon-Wed 08:30-16:30")
        assert weekdays == {0, 1, 2}
        assert start == (8, 30)
        assert end == (16, 30)

    def test_comma_separated(self) -> None:
        weekdays, _, _ = parse_schedule("Mon,Wed,Fri 09:00-17:00")
        assert weekdays == {0, 2, 4}

    def test_fallback_on_bad_input(self) -> None:
        weekdays, start, end = parse_schedule("invalid")
        assert weekdays == {0, 1, 2, 3, 4}
        assert start == (9, 0)
        assert end == (17, 0)


# ---------------------------------------------------------------------------
# business_seconds
# ---------------------------------------------------------------------------


class TestBusinessSeconds:
    def test_same_day_within_hours(self) -> None:
        from datetime import datetime

        # Wednesday 10:00 to 12:00 UTC = 2h within Mon-Fri 09:00-17:00
        start = datetime(2026, 3, 4, 10, 0, tzinfo=UTC).timestamp()
        end = datetime(2026, 3, 4, 12, 0, tzinfo=UTC).timestamp()
        result = business_seconds(start, end, "Mon-Fri 09:00-17:00", "UTC")
        assert result == 7200.0

    def test_weekend_excluded(self) -> None:
        from datetime import datetime

        # Saturday 10:00 to Sunday 15:00 = 0 business seconds
        start = datetime(2026, 3, 7, 10, 0, tzinfo=UTC).timestamp()
        end = datetime(2026, 3, 8, 15, 0, tzinfo=UTC).timestamp()
        result = business_seconds(start, end, "Mon-Fri 09:00-17:00", "UTC")
        assert result == 0.0

    def test_overnight_only_counts_business_hours(self) -> None:
        from datetime import datetime

        # Wednesday 16:00 to Thursday 10:00 = 1h Wed + 1h Thu = 2h
        start = datetime(2026, 3, 4, 16, 0, tzinfo=UTC).timestamp()
        end = datetime(2026, 3, 5, 10, 0, tzinfo=UTC).timestamp()
        result = business_seconds(start, end, "Mon-Fri 09:00-17:00", "UTC")
        assert result == 7200.0

    def test_start_after_end_returns_zero(self) -> None:
        result = business_seconds(1000.0, 500.0, "Mon-Fri 09:00-17:00", "UTC")
        assert result == 0.0


# ---------------------------------------------------------------------------
# SLATimer
# ---------------------------------------------------------------------------


class TestSLATimer:
    def test_defaults(self) -> None:
        timer = SLATimer(
            sla_name="test",
            entity_name="Ticket",
            entity_id="123",
            started_at=1000.0,
        )
        assert timer.current_tier == "ok"
        assert timer.paused_at is None
        assert timer.completed_at is None
        assert timer.accumulated_seconds == 0.0


# ---------------------------------------------------------------------------
# SLAManager — condition matching
# ---------------------------------------------------------------------------


class TestConditionMatching:
    def test_transition_operator(self) -> None:
        cond = SLAConditionSpec(field="status", operator="->", value="open")
        result = SLAManager._matches(cond, {"status": "open"}, {"status": "draft"})
        assert result is True

    def test_transition_no_change(self) -> None:
        cond = SLAConditionSpec(field="status", operator="->", value="open")
        result = SLAManager._matches(cond, {"status": "open"}, {"status": "open"})
        assert result is False

    def test_transition_no_old_data(self) -> None:
        cond = SLAConditionSpec(field="status", operator="->", value="open")
        result = SLAManager._matches(cond, {"status": "open"}, None)
        assert result is True

    def test_equals_operator(self) -> None:
        cond = SLAConditionSpec(field="status", operator="=", value="on_hold")
        result = SLAManager._matches(cond, {"status": "on_hold"}, None)
        assert result is True

    def test_equals_mismatch(self) -> None:
        cond = SLAConditionSpec(field="status", operator="=", value="on_hold")
        result = SLAManager._matches(cond, {"status": "open"}, None)
        assert result is False

    def test_matches_state(self) -> None:
        cond = SLAConditionSpec(field="status", operator="->", value="on_hold")
        assert SLAManager._matches_state(cond, {"status": "on_hold"}) is True
        assert SLAManager._matches_state(cond, {"status": "open"}) is False


# ---------------------------------------------------------------------------
# SLAManager — timer lifecycle
# ---------------------------------------------------------------------------


class TestTimerLifecycle:
    @pytest.fixture()
    def sla(self) -> SLASpec:
        return _make_sla()

    @pytest.fixture()
    def mgr(self, sla: SLASpec) -> SLAManager:
        return SLAManager(sla_specs=[sla])

    @pytest.mark.asyncio()
    async def test_start_timer(self, mgr: SLAManager) -> None:
        await mgr.on_entity_event("SupportTicket", "t1", {"status": "open"}, {"status": "draft"})
        timer = mgr.get_timer("ticket_response", "t1")
        assert timer is not None
        assert timer.current_tier == "ok"
        assert timer.completed_at is None

    @pytest.mark.asyncio()
    async def test_pause_timer(self, mgr: SLAManager) -> None:
        await mgr.on_entity_event("SupportTicket", "t1", {"status": "open"}, {"status": "draft"})
        await mgr.on_entity_event("SupportTicket", "t1", {"status": "on_hold"}, {"status": "open"})
        timer = mgr.get_timer("ticket_response", "t1")
        assert timer is not None
        assert timer.paused_at is not None

    @pytest.mark.asyncio()
    async def test_resume_timer(self, mgr: SLAManager) -> None:
        await mgr.on_entity_event("SupportTicket", "t1", {"status": "open"}, {"status": "draft"})
        await mgr.on_entity_event("SupportTicket", "t1", {"status": "on_hold"}, {"status": "open"})
        # Un-pause: status no longer matches pause condition
        await mgr.on_entity_event("SupportTicket", "t1", {"status": "open"}, {"status": "on_hold"})
        timer = mgr.get_timer("ticket_response", "t1")
        assert timer is not None
        assert timer.paused_at is None

    @pytest.mark.asyncio()
    async def test_complete_timer(self, mgr: SLAManager) -> None:
        await mgr.on_entity_event("SupportTicket", "t1", {"status": "open"}, {"status": "draft"})
        await mgr.on_entity_event("SupportTicket", "t1", {"status": "resolved"}, {"status": "open"})
        timer = mgr.get_timer("ticket_response", "t1")
        assert timer is not None
        assert timer.completed_at is not None

    @pytest.mark.asyncio()
    async def test_ignore_unrelated_entity(self, mgr: SLAManager) -> None:
        await mgr.on_entity_event("OtherEntity", "x1", {"status": "open"}, {"status": "draft"})
        assert mgr.active_timer_count == 0

    @pytest.mark.asyncio()
    async def test_no_double_start(self, mgr: SLAManager) -> None:
        await mgr.on_entity_event("SupportTicket", "t1", {"status": "open"}, {"status": "draft"})
        timer1 = mgr.get_timer("ticket_response", "t1")
        started = timer1.started_at

        # Same event again — should NOT restart
        await mgr.on_entity_event("SupportTicket", "t1", {"status": "open"}, {"status": "draft"})
        timer2 = mgr.get_timer("ticket_response", "t1")
        assert timer2.started_at == started


# ---------------------------------------------------------------------------
# SLAManager — elapsed & tier detection
# ---------------------------------------------------------------------------


class TestElapsedAndTiers:
    def test_determine_tier_ok(self) -> None:
        sla = _make_sla()
        mgr = SLAManager(sla_specs=[sla])
        assert mgr._determine_tier(0, sla) == "ok"
        assert mgr._determine_tier(3600, sla) == "ok"  # 1h < 4h warning

    def test_determine_tier_warning(self) -> None:
        sla = _make_sla()
        mgr = SLAManager(sla_specs=[sla])
        assert mgr._determine_tier(14400, sla) == "warning"  # 4h = warning
        assert mgr._determine_tier(20000, sla) == "warning"  # between 4h and 8h

    def test_determine_tier_breach(self) -> None:
        sla = _make_sla()
        mgr = SLAManager(sla_specs=[sla])
        assert mgr._determine_tier(28800, sla) == "breach"  # 8h = breach
        assert mgr._determine_tier(50000, sla) == "breach"  # between 8h and 24h

    def test_determine_tier_critical(self) -> None:
        sla = _make_sla()
        mgr = SLAManager(sla_specs=[sla])
        assert mgr._determine_tier(86400, sla) == "critical"  # 24h

    def test_elapsed_paused_returns_accumulated(self) -> None:
        sla = _make_sla()
        mgr = SLAManager(sla_specs=[sla])
        timer = SLATimer(
            sla_name="ticket_response",
            entity_name="SupportTicket",
            entity_id="t1",
            started_at=time.time() - 1000,
            paused_at=time.time() - 500,
            accumulated_seconds=500.0,
        )
        mgr._timers["ticket_response:t1"] = timer
        assert mgr._elapsed(timer) == 500.0


# ---------------------------------------------------------------------------
# SLAManager — breach detection
# ---------------------------------------------------------------------------


class TestBreachDetection:
    @pytest.mark.asyncio()
    async def test_tier_transition_detected(self) -> None:
        sla = _make_sla(
            tiers=[SLATierSpec(name="warning", duration_value=1, duration_unit="seconds")]
        )
        mgr = SLAManager(sla_specs=[sla])
        # Manually insert a timer that's been running > 1s
        mgr._timers["ticket_response:t1"] = SLATimer(
            sla_name="ticket_response",
            entity_name="SupportTicket",
            entity_id="t1",
            started_at=time.time() - 10,
        )
        transitions = await mgr.check_breaches()
        assert transitions == 1
        assert mgr._timers["ticket_response:t1"].current_tier == "warning"

    @pytest.mark.asyncio()
    async def test_no_transition_when_timer_ok(self) -> None:
        sla = _make_sla(
            tiers=[SLATierSpec(name="warning", duration_value=999, duration_unit="hours")]
        )
        mgr = SLAManager(sla_specs=[sla])
        mgr._timers["ticket_response:t1"] = SLATimer(
            sla_name="ticket_response",
            entity_name="SupportTicket",
            entity_id="t1",
            started_at=time.time(),
        )
        transitions = await mgr.check_breaches()
        assert transitions == 0

    @pytest.mark.asyncio()
    async def test_completed_timer_skipped(self) -> None:
        sla = _make_sla(
            tiers=[SLATierSpec(name="warning", duration_value=1, duration_unit="seconds")]
        )
        mgr = SLAManager(sla_specs=[sla])
        mgr._timers["ticket_response:t1"] = SLATimer(
            sla_name="ticket_response",
            entity_name="SupportTicket",
            entity_id="t1",
            started_at=time.time() - 100,
            completed_at=time.time(),
        )
        transitions = await mgr.check_breaches()
        assert transitions == 0


# ---------------------------------------------------------------------------
# SLAManager — breach actions
# ---------------------------------------------------------------------------


class TestBreachActions:
    @pytest.mark.asyncio()
    async def test_field_assignment_on_breach(self) -> None:
        mock_service = AsyncMock()
        sla = _make_sla(
            tiers=[SLATierSpec(name="breach", duration_value=1, duration_unit="seconds")],
            on_breach=SLABreachActionSpec(
                field_assignments=[
                    FieldAssignment(field_path="SupportTicket.escalated", value="true")
                ],
                notify_role="support_lead",
            ),
        )
        mgr = SLAManager(sla_specs=[sla], services={"SupportTicket": mock_service})
        mgr._timers["ticket_response:t1"] = SLATimer(
            sla_name="ticket_response",
            entity_name="SupportTicket",
            entity_id="t1",
            started_at=time.time() - 10,
        )

        await mgr.check_breaches()

        mock_service.execute.assert_called_once_with(
            action="update",
            record_id="t1",
            data={"escalated": "true"},
        )

    @pytest.mark.asyncio()
    async def test_breach_action_failure_does_not_crash(self) -> None:
        mock_service = AsyncMock()
        mock_service.execute.side_effect = RuntimeError("DB error")
        sla = _make_sla(
            tiers=[SLATierSpec(name="breach", duration_value=1, duration_unit="seconds")],
            on_breach=SLABreachActionSpec(
                field_assignments=[
                    FieldAssignment(field_path="SupportTicket.escalated", value="true")
                ],
            ),
        )
        mgr = SLAManager(sla_specs=[sla], services={"SupportTicket": mock_service})
        mgr._timers["ticket_response:t1"] = SLATimer(
            sla_name="ticket_response",
            entity_name="SupportTicket",
            entity_id="t1",
            started_at=time.time() - 10,
        )

        # Should not raise
        transitions = await mgr.check_breaches()
        assert transitions == 1


# ---------------------------------------------------------------------------
# SLAManager — start / shutdown
# ---------------------------------------------------------------------------


class TestStartShutdown:
    @pytest.mark.asyncio()
    async def test_start_and_shutdown(self) -> None:
        sla = _make_sla()
        mgr = SLAManager(sla_specs=[sla])
        await mgr.start()
        assert mgr._task is not None
        await mgr.shutdown()
        assert mgr._task is None

    @pytest.mark.asyncio()
    async def test_double_start_is_noop(self) -> None:
        sla = _make_sla()
        mgr = SLAManager(sla_specs=[sla])
        await mgr.start()
        task1 = mgr._task
        await mgr.start()
        assert mgr._task is task1
        await mgr.shutdown()

    @pytest.mark.asyncio()
    async def test_active_timer_count(self) -> None:
        sla = _make_sla()
        mgr = SLAManager(sla_specs=[sla])

        await mgr.on_entity_event("SupportTicket", "t1", {"status": "open"}, {"status": "draft"})
        assert mgr.active_timer_count == 1

        await mgr.on_entity_event("SupportTicket", "t1", {"status": "resolved"}, {"status": "open"})
        assert mgr.active_timer_count == 0
