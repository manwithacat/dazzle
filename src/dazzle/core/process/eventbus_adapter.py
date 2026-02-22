"""EventBusProcessAdapter - ProcessAdapter using native event bus.

Replaces Celery with the Dazzle event bus for process orchestration.
Uses event-driven patterns instead of task queue polling:

- Process execution: publish to ``process.execute`` topic, consumer picks up
- Human task timeouts: delayed events published at task creation time
- Task completion: subscriber on ``process.task_completed`` resumes process
- Scheduled triggers: lightweight cron publisher loop

Requires Redis (for both event bus and state store). Eliminates the need
for Celery worker processes, Beat scheduler, and Flower monitoring.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from dazzle.core.ir.process import ProcessSpec, ScheduleSpec
from dazzle.core.process.adapter import (
    ProcessAdapter,
    ProcessRun,
    ProcessStatus,
    ProcessTask,
    TaskStatus,
)
from dazzle.core.process.celery_state import ProcessStateStore

if TYPE_CHECKING:
    from dazzle.core.ir.appspec import AppSpec

logger = logging.getLogger(__name__)

# Event type constants
PROCESS_EXECUTE = "process.execution.requested"
PROCESS_RESUME = "process.execution.resume"
TASK_TIMEOUT = "process.task.timeout"
TASK_COMPLETED = "process.task.completed"
SCHEDULE_TRIGGER = "process.schedule.triggered"


class EventBusProcessAdapter(ProcessAdapter):
    """ProcessAdapter using the native Dazzle event bus.

    This adapter publishes events instead of queuing Celery tasks.
    A background consumer loop processes events and executes steps.

    Architecture:
        start_process() → publish PROCESS_EXECUTE → consumer executes steps
        complete_task() → publish TASK_COMPLETED → consumer resumes process
        human_task created → publish delayed TASK_TIMEOUT → consumer escalates
        schedule due → publish SCHEDULE_TRIGGER → consumer starts process
    """

    def __init__(
        self,
        redis_url: str | None = None,
        store: ProcessStateStore | None = None,
    ):
        self._store = store or ProcessStateStore(redis_url=redis_url)
        self._redis_url = redis_url
        self._initialized = False
        self._consumer_task: asyncio.Task[None] | None = None
        self._scheduler_task: asyncio.Task[None] | None = None
        self._shutdown_event = asyncio.Event()
        self._schedules: dict[str, dict[str, Any]] = {}

    async def initialize(self) -> None:
        """Start background consumer and scheduler loops."""
        if self._initialized:
            return

        logger.info("EventBusProcessAdapter initializing")

        # Start the process execution consumer
        self._consumer_task = asyncio.create_task(
            self._consumer_loop(), name="eventbus-process-consumer"
        )

        # Start the scheduler for cron/interval triggers
        self._scheduler_task = asyncio.create_task(
            self._scheduler_loop(), name="eventbus-process-scheduler"
        )

        self._initialized = True
        logger.info("EventBusProcessAdapter initialized")

    async def shutdown(self) -> None:
        """Graceful shutdown of consumer and scheduler loops."""
        logger.info("EventBusProcessAdapter shutting down")
        self._shutdown_event.set()

        for task in [self._consumer_task, self._scheduler_task]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    # -----------------------------------------------------------------------
    # Process Registration
    # -----------------------------------------------------------------------

    async def register_process(self, spec: ProcessSpec) -> None:
        self._store.register_process(spec)
        logger.debug(f"Registered process: {spec.name}")

    async def register_schedule(self, spec: ScheduleSpec) -> None:
        self._store.register_schedule(spec)
        self._schedules[spec.name] = {
            "name": spec.name,
            "process_name": getattr(spec, "process_name", spec.name),
            "cron": getattr(spec, "cron", None),
            "interval_seconds": getattr(spec, "interval_seconds", None),
        }
        logger.debug(f"Registered schedule: {spec.name}")

    async def register_entity_meta(self, entity_name: str, meta: dict[str, Any]) -> None:
        self._store.save_entity_meta(entity_name, meta)
        logger.debug(f"Registered entity metadata: {entity_name}")

    # -----------------------------------------------------------------------
    # Process Lifecycle
    # -----------------------------------------------------------------------

    async def start_process(
        self,
        process_name: str,
        inputs: dict[str, Any],
        idempotency_key: str | None = None,
        dsl_version: str | None = None,
    ) -> str:
        if idempotency_key:
            existing = self._find_run_by_idempotency_key(idempotency_key)
            if existing:
                logger.info(f"Returning existing run {existing.run_id} for idempotency key")
                return existing.run_id

        run_id = str(uuid.uuid4())
        run = ProcessRun(
            run_id=run_id,
            process_name=process_name,
            process_version="v1",
            dsl_version=dsl_version or "0.1",
            status=ProcessStatus.PENDING,
            inputs=inputs,
            idempotency_key=idempotency_key,
        )
        self._store.save_run(run)

        logger.info(f"Starting process {process_name} run {run_id}")
        await self._publish_event(PROCESS_EXECUTE, run_id, {"run_id": run_id})
        return run_id

    def _find_run_by_idempotency_key(self, key: str) -> ProcessRun | None:
        for run in self._store.list_runs(limit=1000):
            if run.idempotency_key == key:
                return run
        return None

    async def get_run(self, run_id: str) -> ProcessRun | None:
        return self._store.get_run(run_id)

    async def list_runs(
        self,
        process_name: str | None = None,
        status: ProcessStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ProcessRun]:
        return self._store.list_runs(
            process_name=process_name, status=status, limit=limit, offset=offset
        )

    async def cancel_process(self, run_id: str, reason: str) -> None:
        run = self._store.get_run(run_id)
        if run and run.status not in (
            ProcessStatus.COMPLETED,
            ProcessStatus.FAILED,
            ProcessStatus.CANCELLED,
        ):
            run.status = ProcessStatus.CANCELLED
            run.error = f"Cancelled: {reason}"
            run.completed_at = datetime.now(UTC)
            run.updated_at = datetime.now(UTC)
            self._store.save_run(run)
            logger.info(f"Cancelled process run {run_id}: {reason}")

    async def suspend_process(self, run_id: str) -> None:
        run = self._store.get_run(run_id)
        if run and run.status == ProcessStatus.RUNNING:
            run.status = ProcessStatus.SUSPENDED
            run.updated_at = datetime.now(UTC)
            self._store.save_run(run)
            logger.info(f"Suspended process run {run_id}")

    async def resume_process(self, run_id: str) -> None:
        run = self._store.get_run(run_id)
        if run and run.status == ProcessStatus.SUSPENDED:
            run.status = ProcessStatus.PENDING
            run.updated_at = datetime.now(UTC)
            self._store.save_run(run)
            await self._publish_event(PROCESS_EXECUTE, run_id, {"run_id": run_id})
            logger.info(f"Resumed process run {run_id}")

    # -----------------------------------------------------------------------
    # Signals
    # -----------------------------------------------------------------------

    async def signal_process(
        self,
        run_id: str,
        signal_name: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        run = self._store.get_run(run_id)
        if not run:
            logger.warning(f"Signal {signal_name} sent to unknown run {run_id}")
            return

        run.context[f"signal_{signal_name}"] = payload or {}
        run.updated_at = datetime.now(UTC)
        self._store.save_run(run)

        if run.status == ProcessStatus.WAITING:
            run.status = ProcessStatus.PENDING
            self._store.save_run(run)
            await self._publish_event(PROCESS_EXECUTE, run_id, {"run_id": run_id})

        logger.info(f"Signal {signal_name} sent to run {run_id}")

    # -----------------------------------------------------------------------
    # Human Tasks
    # -----------------------------------------------------------------------

    async def get_task(self, task_id: str) -> ProcessTask | None:
        return self._store.get_task(task_id)

    async def list_tasks(
        self,
        run_id: str | None = None,
        assignee_id: str | None = None,
        status: TaskStatus | None = None,
        limit: int = 100,
    ) -> list[ProcessTask]:
        return self._store.list_tasks(
            run_id=run_id, assignee_id=assignee_id, status=status, limit=limit
        )

    async def complete_task(
        self,
        task_id: str,
        outcome: str,
        outcome_data: dict[str, Any] | None = None,
        completed_by: str | None = None,
    ) -> None:
        task = self._store.get_task(task_id)
        if not task:
            logger.warning(f"Task {task_id} not found")
            return

        if task.status in (TaskStatus.COMPLETED, TaskStatus.CANCELLED, TaskStatus.EXPIRED):
            logger.warning(f"Task {task_id} already in terminal state: {task.status}")
            return

        task.status = TaskStatus.COMPLETED
        task.outcome = outcome
        task.outcome_data = outcome_data
        task.completed_at = datetime.now(UTC)
        if completed_by:
            task.assignee_id = completed_by
        self._store.save_task(task)

        logger.info(f"Task {task_id} completed with outcome: {outcome}")

        # Publish event to resume the parent process
        await self._publish_event(
            TASK_COMPLETED,
            task_id,
            {"task_id": task_id, "outcome": outcome, "outcome_data": outcome_data},
        )

    async def reassign_task(
        self,
        task_id: str,
        new_assignee_id: str,
        reason: str | None = None,
    ) -> None:
        del reason
        task = self._store.get_task(task_id)
        if not task:
            logger.warning(f"Task {task_id} not found")
            return

        old_assignee = task.assignee_id
        task.assignee_id = new_assignee_id
        task.status = TaskStatus.ASSIGNED
        self._store.save_task(task)
        logger.info(f"Task {task_id} reassigned from {old_assignee} to {new_assignee_id}")

    # -----------------------------------------------------------------------
    # Version Management
    # -----------------------------------------------------------------------

    async def list_runs_by_version(
        self,
        dsl_version: str,
        status: ProcessStatus | None = None,
        limit: int = 100,
    ) -> list[ProcessRun]:
        return self._store.list_runs_by_version(dsl_version=dsl_version, status=status, limit=limit)

    async def count_active_runs_by_version(self, dsl_version: str) -> int:
        return self._store.count_active_runs_by_version(dsl_version)

    # -----------------------------------------------------------------------
    # Schedule sync
    # -----------------------------------------------------------------------

    def sync_schedules_from_appspec(self, appspec: AppSpec) -> int:
        count = 0
        for schedule in appspec.schedules:
            self._store.register_schedule(schedule)
            self._schedules[schedule.name] = {
                "name": schedule.name,
                "process_name": getattr(schedule, "process_name", schedule.name),
                "cron": getattr(schedule, "cron", None),
                "interval_seconds": getattr(schedule, "interval_seconds", None),
            }
            logger.info(f"Registered schedule '{schedule.name}'")
            count += 1
        return count

    # -----------------------------------------------------------------------
    # Event publishing
    # -----------------------------------------------------------------------

    async def _publish_event(
        self,
        event_type: str,
        key: str,
        payload: dict[str, Any],
        *,
        deliver_at: datetime | None = None,
    ) -> None:
        """Publish an event to the event bus.

        Falls back to direct execution if the event bus is not available
        (e.g., in unit tests or when running without the full stack).
        """
        try:
            from dazzle_back.events.envelope import EventEnvelope

            if deliver_at:
                envelope = EventEnvelope.create_delayed(
                    event_type=event_type,
                    key=key,
                    payload=payload,
                    deliver_at=deliver_at,
                    producer="dazzle-process",
                )
            else:
                envelope = EventEnvelope.create(
                    event_type=event_type,
                    key=key,
                    payload=payload,
                    producer="dazzle-process",
                )

            from dazzle_back.events.framework import get_framework

            framework = get_framework()
            if framework and framework._bus:
                await framework._bus.publish(envelope.topic, envelope)
                logger.debug(f"Published {event_type} for key={key}")
                return
        except Exception as e:
            logger.warning(f"Event bus not available, falling back to direct execution: {e}")

        # Fallback: handle directly in the current async context
        await self._handle_event_directly(event_type, payload)

    async def _handle_event_directly(self, event_type: str, payload: dict[str, Any]) -> None:
        """Handle an event directly when the bus is not available."""
        if event_type == PROCESS_EXECUTE or event_type == PROCESS_RESUME:
            run_id = payload.get("run_id")
            if run_id:
                await asyncio.get_event_loop().run_in_executor(
                    None, self._execute_process_sync, run_id
                )
        elif event_type == TASK_COMPLETED:
            task_id = payload.get("task_id")
            outcome = payload.get("outcome", "")
            outcome_data = payload.get("outcome_data")
            if task_id:
                await self._handle_task_completed(task_id, outcome, outcome_data)
        elif event_type == TASK_TIMEOUT:
            task_id = payload.get("task_id")
            if task_id:
                await asyncio.get_event_loop().run_in_executor(
                    None, self._handle_task_timeout_sync, task_id
                )

    # -----------------------------------------------------------------------
    # Consumer loop
    # -----------------------------------------------------------------------

    async def _consumer_loop(self) -> None:
        """Background loop that consumes process events from the bus.

        Subscribes to process.* topics and dispatches to handlers.
        Falls back to polling Redis for pending runs if the bus is unavailable.
        """
        logger.info("Process consumer loop starting")

        while not self._shutdown_event.is_set():
            try:
                # Poll for pending process runs
                await self._poll_pending_runs()
                # Poll for delayed events that are now due
                await self._poll_delayed_events()
                # Wait before next poll
                await asyncio.sleep(1.0)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Consumer loop error: {e}")
                await asyncio.sleep(5.0)

        logger.info("Process consumer loop stopped")

    async def _poll_pending_runs(self) -> None:
        """Check for pending process runs and execute them."""
        pending_runs = self._store.list_runs(status=ProcessStatus.PENDING, limit=10)
        for run in pending_runs:
            try:
                await asyncio.get_event_loop().run_in_executor(
                    None, self._execute_process_sync, run.run_id
                )
            except Exception as e:
                logger.error(f"Failed to execute process {run.run_id}: {e}")

    async def _poll_delayed_events(self) -> None:
        """Check for delayed task timeout events that are now due."""
        # Check for tasks that need timeout processing
        try:
            r = self._store._redis
            # Scan for pending tasks nearing timeout
            for key in r.scan_iter("task:*"):
                if key.startswith("task:idx:"):
                    continue
                task_id = key.replace("task:", "")
                task = self._store.get_task(task_id)
                if task and task.status in (
                    TaskStatus.PENDING,
                    TaskStatus.ASSIGNED,
                    TaskStatus.ESCALATED,
                ):
                    if datetime.now(UTC) > task.due_at:
                        await asyncio.get_event_loop().run_in_executor(
                            None, self._handle_task_timeout_sync, task_id
                        )
        except Exception as e:
            logger.debug(f"Delayed event poll error: {e}")

    # -----------------------------------------------------------------------
    # Scheduler loop
    # -----------------------------------------------------------------------

    async def _scheduler_loop(self) -> None:
        """Background loop for cron/interval schedule triggers."""
        logger.info("Process scheduler loop starting")
        last_check: dict[str, datetime] = {}

        while not self._shutdown_event.is_set():
            try:
                now = datetime.now(UTC)
                for name, schedule in self._schedules.items():
                    interval = schedule.get("interval_seconds")
                    if interval:
                        last = last_check.get(name)
                        if last is None or (now - last).total_seconds() >= interval:
                            last_check[name] = now
                            await self._trigger_schedule(name, schedule)

                    cron = schedule.get("cron")
                    if cron:
                        if self._cron_matches(cron, now):
                            last = last_check.get(name)
                            if last is None or (now - last).total_seconds() >= 60:
                                last_check[name] = now
                                await self._trigger_schedule(name, schedule)

                await asyncio.sleep(30.0)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Scheduler loop error: {e}")
                await asyncio.sleep(60.0)

        logger.info("Process scheduler loop stopped")

    async def _trigger_schedule(self, name: str, schedule: dict[str, Any]) -> None:
        """Trigger a scheduled process."""
        process_name = schedule.get("process_name", name)
        spec = self._store.get_process_spec(process_name)
        if not spec:
            logger.warning(f"Schedule {name}: process {process_name} not found")
            return

        run_id = str(uuid.uuid4())
        run = ProcessRun(
            run_id=run_id,
            process_name=process_name,
            status=ProcessStatus.PENDING,
            inputs={"triggered_by": "schedule", "schedule_name": name},
        )
        self._store.save_run(run)
        self._store.set_schedule_last_run(name, datetime.now(UTC))

        await self._publish_event(PROCESS_EXECUTE, run_id, {"run_id": run_id})
        logger.info(f"Triggered scheduled process {process_name} run {run_id}")

    @staticmethod
    def _cron_matches(cron: str, now: datetime) -> bool:
        """Simple cron matching (minute hour dom month dow)."""
        parts = cron.split()
        if len(parts) < 5:
            return False

        def _match(pattern: str, value: int) -> bool:
            if pattern == "*":
                return True
            if pattern.isdigit():
                return int(pattern) == value
            if "/" in pattern:
                _, step = pattern.split("/", 1)
                return value % int(step) == 0
            if "," in pattern:
                return str(value) in pattern.split(",")
            return False

        return (
            _match(parts[0], now.minute)
            and _match(parts[1], now.hour)
            and _match(parts[2], now.day)
            and _match(parts[3], now.month)
            and _match(parts[4], now.weekday())
        )

    # -----------------------------------------------------------------------
    # Sync execution helpers (run in thread pool)
    # -----------------------------------------------------------------------

    def _execute_process_sync(self, run_id: str) -> None:
        """Execute a process synchronously (called from thread pool)."""
        from dazzle.core.process.step_executor import execute_process_steps, fail_run

        run = self._store.get_run(run_id)
        if not run:
            logger.error(f"Process run {run_id} not found")
            return

        if run.status not in (ProcessStatus.PENDING, ProcessStatus.WAITING):
            return

        def on_task_created(task_id: str, timeout_seconds: float) -> None:
            """Schedule a delayed timeout event for a new human task."""
            # We can't publish async from sync context, so store the timeout
            # info and let the consumer loop handle it via polling.
            logger.info(
                f"Human task {task_id} created, timeout in {timeout_seconds}s "
                "(handled by consumer poll)"
            )

        try:
            execute_process_steps(
                self._store,
                run,
                on_task_created=on_task_created,
            )
        except Exception as e:
            logger.exception(f"Process {run_id} execution failed: {e}")
            run = self._store.get_run(run_id)
            if run and run.status not in (ProcessStatus.FAILED, ProcessStatus.COMPLETED):
                fail_run(self._store, run, str(e))

    async def _handle_task_completed(
        self, task_id: str, outcome: str, outcome_data: dict[str, Any] | None
    ) -> None:
        """Resume a process after task completion."""
        task = self._store.get_task(task_id)
        if not task:
            logger.warning(f"Task {task_id} not found for resume")
            return

        run = self._store.get_run(task.run_id)
        if not run:
            logger.warning(f"Run {task.run_id} not found for task {task_id}")
            return

        # Store outcome in context
        run.context[f"{task.step_name}_outcome"] = outcome
        if outcome_data:
            run.context[f"{task.step_name}_data"] = outcome_data
        run.status = ProcessStatus.PENDING
        run.updated_at = datetime.now(UTC)
        self._store.save_run(run)

        # Re-execute from where it left off
        await self._publish_event(PROCESS_EXECUTE, run.run_id, {"run_id": run.run_id})

    def _handle_task_timeout_sync(self, task_id: str) -> None:
        """Handle task timeout synchronously."""
        from dazzle.core.process.step_executor import check_task_timeout

        result = check_task_timeout(self._store, task_id)
        if result.get("needs_followup"):
            logger.info(
                f"Task {task_id} escalated, will check again in {result['followup_seconds']}s"
            )
