"""CeleryProcessAdapter - ProcessAdapter implementation using Celery.

This adapter provides production-ready process execution for cloud platforms
like Heroku using Celery for task execution and Redis for state storage.

Key differences from LiteProcessAdapter:
- Uses Celery worker pool instead of in-process asyncio
- Stores state in Redis instead of SQLite
- Supports horizontal scaling (multiple workers)
- Survives dyno restarts (state in Redis, tasks in queue)

Requirements:
- Redis server (REDIS_URL environment variable)
- Celery worker running with: celery -A <app>.celery worker -l info --beat

Usage:
    from dazzle.core.process.celery_adapter import CeleryProcessAdapter

    adapter = CeleryProcessAdapter()
    await adapter.initialize()

    run_id = await adapter.start_process("my_process", {"entity_id": "123"})
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from dazzle.core.ir.process import ProcessSpec, ScheduleSpec
from dazzle.core.process.adapter import (
    ProcessAdapter,
    ProcessRun,
    ProcessStatus,
    ProcessTask,
    TaskStatus,
)
from dazzle.core.process.celery_state import ProcessStateStore

logger = logging.getLogger(__name__)


class CeleryProcessAdapter(ProcessAdapter):
    """ProcessAdapter implementation using Celery for task execution.

    This adapter:
    - Registers processes and schedules in Redis
    - Queues process execution to Celery workers
    - Stores run/task state in Redis
    - Uses Celery beat for cron schedules
    """

    def __init__(
        self,
        redis_url: str | None = None,
        db_path: str | None = None,  # Ignored - for LiteProcessAdapter compatibility
        store: ProcessStateStore | None = None,
    ):
        """Initialize the adapter.

        Args:
            redis_url: Redis connection URL. If not provided, uses REDIS_URL env var.
            db_path: Ignored - for compatibility with LiteProcessAdapter signature.
            store: Optional pre-configured ProcessStateStore for testing.
        """
        del db_path  # Not used - we use Redis
        self._store = store or ProcessStateStore(redis_url=redis_url)
        self._initialized = False
        self._beat_schedule: dict[str, dict] = {}

    async def initialize(self) -> None:
        """Initialize the adapter.

        Sets up Celery beat schedule for registered schedules.
        """
        if self._initialized:
            return

        logger.info("CeleryProcessAdapter initializing")
        self._update_beat_schedule()
        self._initialized = True
        logger.info("CeleryProcessAdapter initialized")

    async def shutdown(self) -> None:
        """Graceful shutdown.

        Note: Running Celery tasks will complete or be requeued.
        """
        logger.info("CeleryProcessAdapter shutting down")

    def _update_beat_schedule(self) -> None:
        """Update Celery beat schedule with registered schedules."""
        try:
            from celery.schedules import crontab

            from dazzle.core.process.celery_tasks import celery_app

            for schedule in self._store.list_schedule_specs():
                cron = schedule.get("cron")
                interval = schedule.get("interval_seconds")
                name = schedule.get("name")

                if cron:
                    try:
                        parts = cron.split()
                        if len(parts) >= 5:
                            cron_schedule = crontab(
                                minute=parts[0],
                                hour=parts[1],
                                day_of_month=parts[2],
                                month_of_year=parts[3],
                                day_of_week=parts[4],
                            )
                            self._beat_schedule[f"schedule_{name}"] = {
                                "task": "dazzle.core.process.celery_tasks.trigger_scheduled_process",
                                "schedule": cron_schedule,
                                "args": [name],
                            }
                    except Exception as e:
                        logger.warning(f"Failed to parse cron for {name}: {e}")

                elif interval:
                    self._beat_schedule[f"schedule_{name}"] = {
                        "task": "dazzle.core.process.celery_tasks.trigger_scheduled_process",
                        "schedule": float(interval),
                        "args": [name],
                    }

            celery_app.conf.beat_schedule = self._beat_schedule
            logger.info(f"Updated beat schedule with {len(self._beat_schedule)} entries")

        except ImportError:
            logger.warning("Celery not available - beat schedules will not be configured")

    # Process Registration

    async def register_process(self, spec: ProcessSpec) -> None:
        """Register a process definition."""
        self._store.register_process(spec)
        logger.debug(f"Registered process: {spec.name}")

    async def register_schedule(self, spec: ScheduleSpec) -> None:
        """Register a scheduled job."""
        self._store.register_schedule(spec)
        logger.debug(f"Registered schedule: {spec.name}")

        if self._initialized:
            self._update_beat_schedule()

    # Process Lifecycle

    async def start_process(
        self,
        process_name: str,
        inputs: dict[str, Any],
        idempotency_key: str | None = None,
        dsl_version: str | None = None,
    ) -> str:
        """Start a process instance.

        Creates a ProcessRun and queues execution to Celery.
        """
        # Check idempotency
        if idempotency_key:
            existing = self._find_run_by_idempotency_key(idempotency_key)
            if existing:
                logger.info(f"Returning existing run {existing.run_id} for idempotency key")
                return existing.run_id

        # Create run
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

        # Queue to Celery
        try:
            from dazzle.core.process.celery_tasks import execute_process

            execute_process.delay(run_id)
        except ImportError:
            logger.warning("Celery tasks not available - run queued but won't execute")

        return run_id

    def _find_run_by_idempotency_key(self, key: str) -> ProcessRun | None:
        """Find a run by idempotency key."""
        for run in self._store.list_runs(limit=1000):
            if run.idempotency_key == key:
                return run
        return None

    async def get_run(self, run_id: str) -> ProcessRun | None:
        """Get a process run by ID."""
        return self._store.get_run(run_id)

    async def list_runs(
        self,
        process_name: str | None = None,
        status: ProcessStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ProcessRun]:
        """List process runs with optional filters."""
        return self._store.list_runs(
            process_name=process_name,
            status=status,
            limit=limit,
            offset=offset,
        )

    async def cancel_process(self, run_id: str, reason: str) -> None:
        """Cancel a running process."""
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
        """Suspend a running process."""
        run = self._store.get_run(run_id)
        if run and run.status == ProcessStatus.RUNNING:
            run.status = ProcessStatus.SUSPENDED
            run.updated_at = datetime.now(UTC)
            self._store.save_run(run)
            logger.info(f"Suspended process run {run_id}")

    async def resume_process(self, run_id: str) -> None:
        """Resume a suspended process."""
        run = self._store.get_run(run_id)
        if run and run.status == ProcessStatus.SUSPENDED:
            run.status = ProcessStatus.PENDING
            run.updated_at = datetime.now(UTC)
            self._store.save_run(run)

            try:
                from dazzle.core.process.celery_tasks import execute_process

                execute_process.delay(run_id)
            except ImportError:
                pass
            logger.info(f"Resumed process run {run_id}")

    # Signals

    async def signal_process(
        self,
        run_id: str,
        signal_name: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Send a signal to a running process."""
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
            try:
                from dazzle.core.process.celery_tasks import execute_process

                execute_process.delay(run_id)
            except ImportError:
                pass

        logger.info(f"Signal {signal_name} sent to run {run_id}")

    # Human Tasks

    async def get_task(self, task_id: str) -> ProcessTask | None:
        """Get a human task by ID."""
        return self._store.get_task(task_id)

    async def list_tasks(
        self,
        run_id: str | None = None,
        assignee_id: str | None = None,
        status: TaskStatus | None = None,
        limit: int = 100,
    ) -> list[ProcessTask]:
        """List human tasks with optional filters."""
        return self._store.list_tasks(
            run_id=run_id,
            assignee_id=assignee_id,
            status=status,
            limit=limit,
        )

    async def complete_task(
        self,
        task_id: str,
        outcome: str,
        outcome_data: dict[str, Any] | None = None,
        completed_by: str | None = None,
    ) -> None:
        """Complete a human task with the selected outcome."""
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

        try:
            from dazzle.core.process.celery_tasks import resume_process_after_task

            resume_process_after_task.delay(task_id, outcome, outcome_data)
        except ImportError:
            pass

    async def reassign_task(
        self,
        task_id: str,
        new_assignee_id: str,
        reason: str | None = None,
    ) -> None:
        """Reassign a human task to another user."""
        del reason  # Not used currently
        task = self._store.get_task(task_id)
        if not task:
            logger.warning(f"Task {task_id} not found")
            return

        old_assignee = task.assignee_id
        task.assignee_id = new_assignee_id
        task.status = TaskStatus.ASSIGNED
        self._store.save_task(task)

        logger.info(f"Task {task_id} reassigned from {old_assignee} to {new_assignee_id}")

    # Version Management

    async def list_runs_by_version(
        self,
        dsl_version: str,
        status: ProcessStatus | None = None,
        limit: int = 100,
    ) -> list[ProcessRun]:
        """List runs for a specific DSL version."""
        return self._store.list_runs_by_version(
            dsl_version=dsl_version,
            status=status,
            limit=limit,
        )

    async def count_active_runs_by_version(self, dsl_version: str) -> int:
        """Count active (non-terminal) runs for a DSL version."""
        return self._store.count_active_runs_by_version(dsl_version)
