"""
SLA runtime enforcement — timer tracking, breach detection, escalation.

Listens to entity lifecycle events (via CRUDService callbacks) and tracks
SLA timers in memory.  A periodic background task checks for tier
transitions and executes breach actions (field updates + notifications).

Architecture:

    EntityEventBus ──→ SLAManager.on_entity_event() ──→ in-memory timers
                                                              ↑
    Background task (check_interval) ─────────────────────────┘
            │
            ├─ tier transition? → execute breach actions
            └─ no change → skip

Business hours are respected when configured.  Timer state is held in
memory; persistence is planned for a follow-up release.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, tzinfo
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dazzle.core.ir.sla import SLAConditionSpec, SLATierSpec

logger = logging.getLogger("dazzle.sla")

# Day-name to weekday number (Monday=0 … Sunday=6)
_DAY_MAP: dict[str, int] = {
    "mon": 0,
    "tue": 1,
    "wed": 2,
    "thu": 3,
    "fri": 4,
    "sat": 5,
    "sun": 6,
}

_UNIT_SECONDS: dict[str, int] = {
    "seconds": 1,
    "minutes": 60,
    "hours": 3600,
    "days": 86400,
}


# ---------------------------------------------------------------------------
# Timer dataclass
# ---------------------------------------------------------------------------


@dataclass
class SLATimer:
    """In-memory SLA timer for a single entity record."""

    sla_name: str
    entity_name: str
    entity_id: str
    started_at: float  # unix timestamp
    paused_at: float | None = None
    accumulated_seconds: float = 0.0
    current_tier: str = "ok"
    completed_at: float | None = None


# ---------------------------------------------------------------------------
# Business-hours helpers
# ---------------------------------------------------------------------------


def parse_schedule(schedule: str) -> tuple[set[int], tuple[int, int], tuple[int, int]]:
    """Parse ``"Mon-Fri 09:00-17:00"`` into (weekdays, start_hm, end_hm).

    Returns:
        (weekday_set, (start_hour, start_min), (end_hour, end_min))
    """
    parts = schedule.strip().split()
    if len(parts) < 2:
        # Fallback: Mon-Fri 09:00-17:00
        return ({0, 1, 2, 3, 4}, (9, 0), (17, 0))

    day_part, time_part = parts[0], parts[1]

    # Parse days: "Mon-Fri" or "Mon,Tue,Wed"
    weekdays: set[int] = set()
    if "-" in day_part:
        start_day, end_day = day_part.lower().split("-", 1)
        s = _DAY_MAP.get(start_day[:3], 0)
        e = _DAY_MAP.get(end_day[:3], 4)
        for d in range(s, e + 1):
            weekdays.add(d)
    else:
        for day_name in day_part.lower().split(","):
            weekdays.add(_DAY_MAP.get(day_name.strip()[:3], 0))

    # Parse times: "09:00-17:00"
    t_start, t_end = "09:00", "17:00"
    if "-" in time_part:
        t_start, t_end = time_part.split("-", 1)

    def _hm(t: str) -> tuple[int, int]:
        h, m = t.split(":")
        return (int(h), int(m))

    return (weekdays, _hm(t_start), _hm(t_end))


def business_seconds(
    start_ts: float,
    end_ts: float,
    schedule: str,
    tz_name: str = "UTC",
) -> float:
    """Calculate seconds between *start_ts* and *end_ts* within business hours.

    Walks day-by-day through the calendar, summing only the time that falls
    inside the schedule window on qualifying weekdays.
    """
    tz: tzinfo
    try:
        from zoneinfo import ZoneInfo

        tz = ZoneInfo(tz_name)
    except Exception:
        tz = UTC

    weekdays, (sh, sm), (eh, em) = parse_schedule(schedule)
    start = datetime.fromtimestamp(start_ts, tz=tz)
    end = datetime.fromtimestamp(end_ts, tz=tz)

    if start >= end:
        return 0.0

    total = 0.0
    # Iterate day by day
    current_date = start.date()
    end_date = end.date()

    while current_date <= end_date:
        if current_date.weekday() in weekdays:
            day_start = datetime(
                current_date.year, current_date.month, current_date.day, sh, sm, tzinfo=tz
            )
            day_end = datetime(
                current_date.year, current_date.month, current_date.day, eh, em, tzinfo=tz
            )

            effective_start = max(day_start, start)
            effective_end = min(day_end, end)

            if effective_start < effective_end:
                total += (effective_end - effective_start).total_seconds()

        current_date += timedelta(days=1)

    return total


# ---------------------------------------------------------------------------
# SLA Manager
# ---------------------------------------------------------------------------


class SLAManager:
    """Manages SLA lifecycle: event handling, breach detection, escalation."""

    def __init__(
        self,
        sla_specs: list[Any],
        services: dict[str, Any] | None = None,
        check_interval: int = 300,
    ) -> None:
        from dazzle.core.ir.sla import SLASpec

        self._slas: dict[str, SLASpec] = {s.name: s for s in sla_specs}
        # Index by entity name for fast lookup
        self._sla_by_entity: dict[str, list[SLASpec]] = {}
        for s in sla_specs:
            self._sla_by_entity.setdefault(s.entity, []).append(s)
        self._timers: dict[str, SLATimer] = {}  # "sla_name:entity_id" → timer
        self._services = services or {}
        self._check_interval = check_interval
        self._shutdown = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    # -- Properties ----------------------------------------------------------

    @property
    def active_timer_count(self) -> int:
        return sum(1 for t in self._timers.values() if t.completed_at is None)

    def get_timer(self, sla_name: str, entity_id: str) -> SLATimer | None:
        return self._timers.get(f"{sla_name}:{entity_id}")

    # -- Lifecycle -----------------------------------------------------------

    async def start(self) -> None:
        """Start the periodic breach-check background task."""
        if self._task is not None:
            return
        self._shutdown.clear()
        self._task = asyncio.create_task(self._check_loop())
        logger.info(
            "SLA manager started — tracking %d SLA(s), check every %ds",
            len(self._slas),
            self._check_interval,
        )

    async def shutdown(self) -> None:
        """Stop the background task gracefully."""
        self._shutdown.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    # -- Event handler -------------------------------------------------------

    async def on_entity_event(
        self,
        entity_name: str,
        entity_id: str,
        data: dict[str, Any],
        old_data: dict[str, Any] | None = None,
    ) -> None:
        """Handle an entity create/update event.

        Checks all SLAs for the entity and starts/pauses/completes timers.
        """
        slas = self._sla_by_entity.get(entity_name)
        if not slas:
            return

        now = time.time()
        for sla in slas:
            key = f"{sla.name}:{entity_id}"

            # 1. completes_when — highest priority
            if sla.completes_when and self._matches(sla.completes_when, data, old_data):
                timer = self._timers.get(key)
                if timer and timer.completed_at is None:
                    timer.completed_at = now
                    logger.info("SLA %s completed for %s:%s", sla.name, entity_name, entity_id)
                continue

            # 2. pauses_when
            if sla.pauses_when and self._matches(sla.pauses_when, data, old_data):
                timer = self._timers.get(key)
                if timer and timer.paused_at is None and timer.completed_at is None:
                    timer.accumulated_seconds += now - timer.started_at
                    timer.paused_at = now
                    logger.debug("SLA %s paused for %s:%s", sla.name, entity_name, entity_id)
                continue

            # 3. starts_when
            if sla.starts_when and self._matches(sla.starts_when, data, old_data):
                if key not in self._timers or self._timers[key].completed_at is not None:
                    self._timers[key] = SLATimer(
                        sla_name=sla.name,
                        entity_name=entity_name,
                        entity_id=entity_id,
                        started_at=now,
                    )
                    logger.info("SLA %s started for %s:%s", sla.name, entity_name, entity_id)

            # 4. Un-pause: was paused but pause condition no longer holds
            timer = self._timers.get(key)
            if timer and timer.paused_at is not None and timer.completed_at is None:
                if sla.pauses_when and not self._matches_state(sla.pauses_when, data):
                    timer.paused_at = None
                    timer.started_at = now  # restart clock from now
                    logger.debug("SLA %s resumed for %s:%s", sla.name, entity_name, entity_id)

    # -- Condition matching --------------------------------------------------

    @staticmethod
    def _matches(
        cond: SLAConditionSpec,
        data: dict[str, Any],
        old_data: dict[str, Any] | None = None,
    ) -> bool:
        """Check if *data* (with optional *old_data*) matches a condition.

        ``->`` (transition): field changed TO value.
        ``=`` / ``==``: field currently equals value.
        """
        field_val = str(data.get(cond.field, ""))
        if cond.operator == "->":
            old_val = str((old_data or {}).get(cond.field, "")) if old_data else ""
            return field_val == cond.value and old_val != cond.value
        # equals
        return field_val == cond.value

    @staticmethod
    def _matches_state(cond: SLAConditionSpec, data: dict[str, Any]) -> bool:
        """Check current state only (ignores operator — always equality)."""
        return str(data.get(cond.field, "")) == cond.value

    # -- Elapsed time --------------------------------------------------------

    def _tier_seconds(self, tier: SLATierSpec) -> float:
        duration = tier.duration_value
        # ParamRef: extract the default value
        if hasattr(duration, "default"):
            duration = duration.default or 0
        return int(duration) * _UNIT_SECONDS.get(tier.duration_unit, 3600)

    def _elapsed(self, timer: SLATimer) -> float:
        """Calculate effective elapsed seconds for a timer."""
        if timer.paused_at is not None:
            return timer.accumulated_seconds

        sla = self._slas.get(timer.sla_name)
        raw_start = timer.started_at
        now = time.time()
        raw = timer.accumulated_seconds + (now - raw_start)

        if sla and sla.business_hours and sla.business_hours.schedule:
            bh = sla.business_hours
            # BusinessHoursSpec declares schedule/timezone as str | ParamRef.
            # Resolve ParamRefs to their default value before handing to
            # business_seconds — the parse layer expects a concrete str.
            # Mirrors the _tier_seconds pattern for duration_value. (#841)
            schedule = bh.schedule.default if hasattr(bh.schedule, "default") else bh.schedule
            timezone_ = bh.timezone.default if hasattr(bh.timezone, "default") else bh.timezone
            biz = business_seconds(raw_start, now, schedule, timezone_)
            return timer.accumulated_seconds + biz

        return raw

    def _determine_tier(self, elapsed: float, sla: Any) -> str:
        """Return the highest tier whose duration threshold has been exceeded."""
        current = "ok"
        for tier in sorted(sla.tiers, key=lambda t: self._tier_seconds(t)):
            if elapsed >= self._tier_seconds(tier):
                current = tier.name
        return current

    # -- Breach checking -----------------------------------------------------

    async def check_breaches(self) -> int:
        """Check all active timers for tier transitions.  Returns count of transitions."""
        transitions = 0
        for _key, timer in list(self._timers.items()):
            if timer.completed_at is not None or timer.paused_at is not None:
                continue
            sla = self._slas.get(timer.sla_name)
            if not sla:
                continue

            elapsed = self._elapsed(timer)
            new_tier = self._determine_tier(elapsed, sla)

            if new_tier != timer.current_tier:
                old_tier = timer.current_tier
                timer.current_tier = new_tier
                transitions += 1
                logger.info(
                    "SLA %s tier %s → %s for %s:%s (%.0fs elapsed)",
                    sla.name,
                    old_tier,
                    new_tier,
                    timer.entity_name,
                    timer.entity_id,
                    elapsed,
                )
                if new_tier in ("breach", "critical"):
                    await self._execute_breach_actions(timer, sla)

        return transitions

    # -- Breach actions ------------------------------------------------------

    async def _execute_breach_actions(self, timer: SLATimer, sla: Any) -> None:
        """Execute on_breach actions: field assignments + notify."""
        if not sla.on_breach:
            return

        # Field assignments: update the tracked entity
        for fa in sla.on_breach.field_assignments:
            # field_path is "Entity.field" — extract field name after dot
            field_name = fa.field_path.rsplit(".", 1)[-1]
            service = self._services.get(timer.entity_name)
            if service:
                try:
                    await service.execute(
                        action="update",
                        record_id=timer.entity_id,
                        data={field_name: fa.value},
                    )
                    logger.info(
                        "SLA %s breach action: set %s.%s = %s on %s",
                        sla.name,
                        timer.entity_name,
                        field_name,
                        fa.value,
                        timer.entity_id,
                    )
                except Exception:
                    logger.exception(
                        "SLA %s breach action failed: %s.%s on %s",
                        sla.name,
                        timer.entity_name,
                        field_name,
                        timer.entity_id,
                    )

        # Notify role (log for now — notification pipeline is a follow-up)
        if sla.on_breach.notify_role:
            logger.warning(
                "SLA %s BREACH — notify %s for %s:%s (tier: %s)",
                sla.name,
                sla.on_breach.notify_role,
                timer.entity_name,
                timer.entity_id,
                timer.current_tier,
            )

    # -- Background loop -----------------------------------------------------

    async def _check_loop(self) -> None:
        """Periodically check for SLA breaches."""
        while not self._shutdown.is_set():
            try:
                await asyncio.wait_for(self._shutdown.wait(), timeout=self._check_interval)
                break  # shutdown requested
            except TimeoutError:
                pass  # interval elapsed — run check

            try:
                transitions = await self.check_breaches()
                if transitions:
                    logger.info("SLA breach check: %d tier transition(s)", transitions)
            except Exception:
                logger.exception("SLA breach check failed")
