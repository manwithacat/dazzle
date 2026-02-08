"""
LiteProcessAdapter - In-process workflow harness using SQLite and asyncio.

This adapter provides process execution for development and simple deployments
without requiring Temporal infrastructure.

Features:
- SQLite persistence for workflow state
- asyncio-based step execution
- Timer support via asyncio
- Retry with configurable backoff
- Basic saga compensation
- Schedule execution via background task

Limitations:
- No cross-process durability (restarts lose in-flight state)
- Human tasks use polling (no push signals)
- Simpler retry semantics than Temporal
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import aiosqlite

from dazzle.core.ir.process import (
    CompensationSpec,
    OverlapPolicy,
    ProcessSpec,
    ProcessStepSpec,
    RetryBackoff,
    RetryConfig,
    ScheduleSpec,
    StepKind,
)

from .adapter import ProcessAdapter, ProcessRun, ProcessStatus, ProcessTask, TaskStatus
from .context import ProcessContext

logger = logging.getLogger(__name__)


class ProcessStepFailed(Exception):
    """Raised when a process step fails after all retries."""

    def __init__(self, step_name: str, message: str):
        self.step_name = step_name
        super().__init__(f"Step '{step_name}' failed: {message}")


class ProcessCancelled(Exception):
    """Raised when a process is cancelled."""

    pass


# Type alias for service handlers
ServiceHandler = Callable[[dict[str, Any]], Coroutine[Any, Any, dict[str, Any]]]
SendHandler = Callable[[str, str, dict[str, Any]], Coroutine[Any, Any, None]]
EventHandler = Callable[[str, dict[str, Any]], Coroutine[Any, Any, None]]


class LiteProcessAdapter(ProcessAdapter):
    """
    In-process workflow harness using SQLite and asyncio.

    Usage:
        adapter = LiteProcessAdapter(db_path=Path(".dazzle/process.db"))
        await adapter.initialize()

        await adapter.register_process(my_process_spec)
        run_id = await adapter.start_process("my_process", {"order_id": "123"})

        # Later...
        run = await adapter.get_run(run_id)
        print(run.status)
    """

    def __init__(
        self,
        db_path: Path | str = ":memory:",
        poll_interval: float = 5.0,
        scheduler_interval: float = 60.0,
        database_url: str | None = None,
    ):
        """
        Initialize the adapter.

        Args:
            db_path: Path to SQLite database, or ":memory:" for in-memory
            poll_interval: Seconds between human task polls
            scheduler_interval: Seconds between schedule checks
            database_url: PostgreSQL connection URL (takes precedence over db_path)
        """
        self._db_path = str(db_path)
        self._database_url = database_url
        self._use_postgres = bool(database_url)
        self._poll_interval = poll_interval
        self._scheduler_interval = scheduler_interval

        # Registries
        self._process_registry: dict[str, ProcessSpec] = {}
        self._schedule_registry: dict[str, ScheduleSpec] = {}

        # Running tasks
        self._running: dict[str, asyncio.Task[None]] = {}
        self._scheduler_task: asyncio.Task[None] | None = None

        # Handlers (inject via set_* methods)
        self._service_handlers: dict[str, ServiceHandler] = {}
        self._send_handler: SendHandler | None = None
        self._event_handler: EventHandler | None = None

        # Database connection (created in initialize)
        self._db: aiosqlite.Connection | None = None

        # Shutdown flag
        self._shutting_down = False

    # Handler injection
    def set_service_handler(self, service_name: str, handler: ServiceHandler) -> None:
        """Register a handler for a service call."""
        self._service_handlers[service_name] = handler

    def set_send_handler(self, handler: SendHandler) -> None:
        """Register a handler for sending messages."""
        self._send_handler = handler

    def set_event_handler(self, handler: EventHandler) -> None:
        """Register a handler for emitting events."""
        self._event_handler = handler

    # Lifecycle
    async def initialize(self) -> None:
        """Initialize database and start background tasks."""
        if self._use_postgres:
            import asyncpg

            pg_url = self._database_url
            if pg_url and pg_url.startswith("postgres://"):
                pg_url = pg_url.replace("postgres://", "postgresql://", 1)

            pg_conn = await asyncpg.connect(pg_url)
            try:
                # Load and execute PostgreSQL schema
                schema_path = Path(__file__).parent / "schema_postgres.sql"
                if schema_path.exists():
                    schema = schema_path.read_text()
                    await pg_conn.execute(schema)
            finally:
                await pg_conn.close()

            logger.warning(
                "LiteProcessAdapter: PostgreSQL schema initialized. "
                "Full async Postgres support for process operations is work-in-progress; "
                "runtime operations still use aiosqlite interface."
            )

            # Fall through to SQLite initialization for runtime operations.
            # The Postgres schema is set up for persistence, but the in-memory
            # process execution still uses aiosqlite.
            self._db = await aiosqlite.connect(":memory:")
            self._db.row_factory = aiosqlite.Row

            # Load SQLite schema into memory for runtime use
            schema_path_sqlite = Path(__file__).parent / "schema.sql"
            if schema_path_sqlite.exists():
                schema = schema_path_sqlite.read_text()
                await self._db.executescript(schema)
                await self._db.commit()
        else:
            self._db = await aiosqlite.connect(self._db_path)
            self._db.row_factory = aiosqlite.Row

            # Load and execute schema
            schema_path = Path(__file__).parent / "schema.sql"
            if schema_path.exists():
                schema = schema_path.read_text()
                await self._db.executescript(schema)
                await self._db.commit()

        # Start scheduler
        self._scheduler_task = asyncio.create_task(self._run_scheduler())

        # Resume suspended processes
        await self._resume_suspended_processes()

        logger.info(f"LiteProcessAdapter initialized with db: {self._db_path}")

    async def shutdown(self) -> None:
        """Graceful shutdown."""
        self._shutting_down = True

        # Cancel scheduler
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass

        # Suspend running processes
        for run_id, task in list(self._running.items()):
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            await self._suspend_run(run_id)

        # Close database
        if self._db:
            await self._db.close()

        logger.info("LiteProcessAdapter shutdown complete")

    # Process Registration
    async def register_process(self, spec: ProcessSpec) -> None:
        """Register a process definition."""
        self._process_registry[spec.name] = spec
        logger.debug(f"Registered process: {spec.name}")

    async def register_schedule(self, spec: ScheduleSpec) -> None:
        """Register a scheduled job."""
        self._schedule_registry[spec.name] = spec

        # Initialize schedule state if not exists
        if self._db:
            await self._db.execute(
                """
                INSERT OR IGNORE INTO schedule_runs (schedule_name)
                VALUES (?)
                """,
                (spec.name,),
            )
            await self._db.commit()

        logger.debug(f"Registered schedule: {spec.name}")

    # Process Lifecycle
    async def start_process(
        self,
        process_name: str,
        inputs: dict[str, Any],
        idempotency_key: str | None = None,
        dsl_version: str | None = None,
    ) -> str:
        """Start a process instance."""
        spec = self._process_registry.get(process_name)
        if not spec:
            raise ValueError(f"Unknown process: {process_name}")

        # Check idempotency
        if idempotency_key:
            existing = await self._get_run_by_idempotency_key(idempotency_key)
            if existing:
                logger.debug(f"Returning existing run for idempotency key: {idempotency_key}")
                return existing.run_id

        # Check overlap policy
        if spec.overlap_policy != OverlapPolicy.ALLOW:
            running = await self.list_runs(
                process_name=process_name,
                status=ProcessStatus.RUNNING,
                limit=1,
            )
            if running:
                if spec.overlap_policy == OverlapPolicy.SKIP:
                    logger.debug(f"Skipping process {process_name}: already running")
                    return running[0].run_id
                elif spec.overlap_policy == OverlapPolicy.CANCEL_PREVIOUS:
                    await self.cancel_process(running[0].run_id, "New instance started")

        # Create run
        run_id = str(uuid.uuid4())
        run = ProcessRun(
            run_id=run_id,
            process_name=process_name,
            dsl_version=dsl_version or "0.1",
            inputs=inputs,
            idempotency_key=idempotency_key,
        )

        # Persist
        await self._save_run(run)

        # Start execution task
        task = asyncio.create_task(self._execute_process(run_id, spec, inputs))
        self._running[run_id] = task

        logger.info(f"Started process {process_name} with run_id: {run_id}")
        return run_id

    async def get_run(self, run_id: str) -> ProcessRun | None:
        """Get a process run by ID."""
        if not self._db:
            return None

        async with self._db.execute(
            "SELECT * FROM process_runs WHERE run_id = ?",
            (run_id,),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return self._row_to_run(row)
        return None

    async def list_runs(
        self,
        process_name: str | None = None,
        status: ProcessStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ProcessRun]:
        """List process runs with optional filters."""
        if not self._db:
            return []

        query = "SELECT * FROM process_runs WHERE 1=1"
        params: list[Any] = []

        if process_name:
            query += " AND process_name = ?"
            params.append(process_name)
        if status:
            query += " AND status = ?"
            params.append(status.value)

        query += " ORDER BY started_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        runs = []
        async with self._db.execute(query, params) as cursor:
            async for row in cursor:
                runs.append(self._row_to_run(row))
        return runs

    async def cancel_process(self, run_id: str, reason: str) -> None:
        """Cancel a running process."""
        # Cancel the task if running
        task = self._running.get(run_id)
        if task:
            task.cancel()
            del self._running[run_id]

        # Update status
        await self._update_run_status(run_id, ProcessStatus.CANCELLED, error=reason)
        await self._emit_event("ProcessCancelled", run_id, reason=reason)

        logger.info(f"Cancelled process {run_id}: {reason}")

    async def suspend_process(self, run_id: str) -> None:
        """Suspend a running process."""
        task = self._running.get(run_id)
        if task:
            task.cancel()
            del self._running[run_id]

        await self._suspend_run(run_id)

    async def resume_process(self, run_id: str) -> None:
        """Resume a suspended process."""
        run = await self.get_run(run_id)
        if not run or run.status != ProcessStatus.SUSPENDED:
            return

        spec = self._process_registry.get(run.process_name)
        if not spec:
            logger.error(f"Cannot resume {run_id}: process {run.process_name} not registered")
            return

        # Restart from current step
        task = asyncio.create_task(
            self._execute_process(run_id, spec, run.inputs, resume_from=run.current_step)
        )
        self._running[run_id] = task

    # Signals
    async def signal_process(
        self,
        run_id: str,
        signal_name: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Send a signal to a running process."""
        if not self._db:
            return

        signal_id = str(uuid.uuid4())
        await self._db.execute(
            """
            INSERT INTO process_signals (signal_id, run_id, signal_name, payload)
            VALUES (?, ?, ?, ?)
            """,
            (signal_id, run_id, signal_name, json.dumps(payload or {})),
        )
        await self._db.commit()

        logger.debug(f"Signal {signal_name} sent to process {run_id}")

    # Human Tasks
    async def get_task(self, task_id: str) -> ProcessTask | None:
        """Get a human task by ID."""
        if not self._db:
            return None

        async with self._db.execute(
            "SELECT * FROM process_tasks WHERE task_id = ?",
            (task_id,),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return self._row_to_task(row)
        return None

    async def list_tasks(
        self,
        run_id: str | None = None,
        assignee_id: str | None = None,
        status: TaskStatus | None = None,
        limit: int = 100,
    ) -> list[ProcessTask]:
        """List human tasks with optional filters."""
        if not self._db:
            return []

        query = "SELECT * FROM process_tasks WHERE 1=1"
        params: list[Any] = []

        if run_id:
            query += " AND run_id = ?"
            params.append(run_id)
        if assignee_id:
            query += " AND assignee_id = ?"
            params.append(assignee_id)
        if status:
            query += " AND status = ?"
            params.append(status.value)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        tasks = []
        async with self._db.execute(query, params) as cursor:
            async for row in cursor:
                tasks.append(self._row_to_task(row))
        return tasks

    async def complete_task(
        self,
        task_id: str,
        outcome: str,
        outcome_data: dict[str, Any] | None = None,
        completed_by: str | None = None,
    ) -> None:
        """Complete a human task."""
        if not self._db:
            return

        await self._db.execute(
            """
            UPDATE process_tasks
            SET status = ?, outcome = ?, outcome_data = ?,
                completed_at = CURRENT_TIMESTAMP, completed_by = ?
            WHERE task_id = ?
            """,
            (
                TaskStatus.COMPLETED.value,
                outcome,
                json.dumps(outcome_data or {}),
                completed_by,
                task_id,
            ),
        )
        await self._db.commit()

        logger.info(f"Task {task_id} completed with outcome: {outcome}")

    async def reassign_task(
        self,
        task_id: str,
        new_assignee_id: str,
        reason: str | None = None,
    ) -> None:
        """Reassign a human task."""
        if not self._db:
            return

        await self._db.execute(
            """
            UPDATE process_tasks
            SET assignee_id = ?, status = ?
            WHERE task_id = ?
            """,
            (new_assignee_id, TaskStatus.ASSIGNED.value, task_id),
        )
        await self._db.commit()

        logger.info(f"Task {task_id} reassigned to {new_assignee_id}")

    # Version Management
    async def list_runs_by_version(
        self,
        dsl_version: str,
        status: ProcessStatus | None = None,
        limit: int = 100,
    ) -> list[ProcessRun]:
        """List runs for a specific DSL version."""
        if not self._db:
            return []

        query = "SELECT * FROM process_runs WHERE dsl_version = ?"
        params: list[Any] = [dsl_version]

        if status:
            query += " AND status = ?"
            params.append(status.value)

        query += " ORDER BY started_at DESC LIMIT ?"
        params.append(limit)

        runs = []
        async with self._db.execute(query, params) as cursor:
            async for row in cursor:
                runs.append(self._row_to_run(row))
        return runs

    async def count_active_runs_by_version(
        self,
        dsl_version: str,
    ) -> int:
        """Count active (non-terminal) runs for a DSL version."""
        if not self._db:
            return 0

        async with self._db.execute(
            """
            SELECT COUNT(*) as count FROM process_runs
            WHERE dsl_version = ?
              AND status IN ('pending', 'running', 'suspended', 'waiting', 'draining')
            """,
            (dsl_version,),
        ) as cursor:
            row = await cursor.fetchone()
            return row["count"] if row else 0

    # Internal: Process Execution
    async def _execute_process(
        self,
        run_id: str,
        spec: ProcessSpec,
        inputs: dict[str, Any],
        resume_from: str | None = None,
    ) -> None:
        """Execute process steps."""
        context = ProcessContext(inputs=inputs)
        # Store run_id in context for signal lookups
        context.set_variable("run_id", run_id)
        completed_steps: list[str] = []

        try:
            # Update status to running
            await self._update_run_status(run_id, ProcessStatus.RUNNING)

            if not resume_from:
                await self._emit_event("ProcessStarted", run_id, process_name=spec.name)

            # Find starting point
            steps = spec.steps
            start_idx = 0
            if resume_from:
                for i, step in enumerate(steps):
                    if step.name == resume_from:
                        start_idx = i
                        break

            # Execute steps
            i = start_idx
            while i < len(steps):
                if self._shutting_down:
                    raise ProcessCancelled("Shutdown in progress")

                step = steps[i]

                # Handle condition steps
                if step.kind == StepKind.CONDITION:
                    if context.evaluate_condition(step.condition or ""):
                        next_step = step.on_true
                    else:
                        next_step = step.on_false

                    if next_step == "complete":
                        break
                    elif next_step == "fail":
                        raise ProcessStepFailed(step.name, "Condition branch to fail")
                    elif next_step:
                        # Find the step index
                        for j, s in enumerate(steps):
                            if s.name == next_step:
                                i = j
                                break
                        else:
                            raise ProcessStepFailed(step.name, f"Unknown step: {next_step}")
                        continue

                # Update current step
                context.set_current_step(step.name)
                await self._update_run(run_id, current_step=step.name, context=context)

                # Execute the step
                result = await self._execute_step(run_id, step, context, spec)
                completed_steps.append(step.name)

                # Record step output
                context.update_step(step.name, result)
                await self._record_step_execution(
                    run_id, step.name, step.kind.value, "completed", result
                )

                await self._emit_event(
                    "ProcessStepCompleted",
                    run_id,
                    step_name=step.name,
                    process_name=spec.name,
                )

                # Handle flow control
                if step.on_success:
                    if step.on_success == "complete":
                        break
                    # Find next step
                    for j, s in enumerate(steps):
                        if s.name == step.on_success:
                            i = j
                            continue
                    else:
                        i += 1
                else:
                    i += 1

            # Process completed
            outputs = context.outputs
            await self._complete_run(run_id, outputs)
            await self._emit_event(
                "ProcessCompleted",
                run_id,
                process_name=spec.name,
                outputs=outputs,
            )

            logger.info(f"Process {run_id} completed successfully")

        except ProcessCancelled:
            # Already handled
            pass

        except asyncio.CancelledError:
            # Task cancelled (shutdown or cancel_process)
            pass

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Process {run_id} failed: {error_msg}")

            # Run compensations
            await self._run_compensations(run_id, spec, completed_steps, context)

            # Update status
            await self._fail_run(run_id, error_msg)
            await self._emit_event(
                "ProcessFailed",
                run_id,
                process_name=spec.name,
                error=error_msg,
            )

        finally:
            # Remove from running tasks
            if run_id in self._running:
                del self._running[run_id]

    async def _execute_step(
        self,
        run_id: str,
        step: ProcessStepSpec,
        context: ProcessContext,
        spec: ProcessSpec,
    ) -> dict[str, Any]:
        """Execute a single step with retry logic."""
        retry = step.retry or RetryConfig()
        last_error: str | None = None

        for attempt in range(retry.max_attempts):
            try:
                # Apply timeout
                result = await asyncio.wait_for(
                    self._execute_step_impl(run_id, step, context, spec),
                    timeout=step.timeout_seconds,
                )
                return result

            except TimeoutError:
                last_error = f"Step timed out after {step.timeout_seconds}s"

            except ProcessStepFailed:
                raise

            except Exception as e:
                last_error = str(e)

            # Record failed attempt
            await self._record_step_execution(
                run_id, step.name, step.kind.value, "failed", error=last_error, attempt=attempt + 1
            )

            # Retry if not last attempt
            if attempt < retry.max_attempts - 1:
                delay = self._calculate_backoff(retry, attempt)
                logger.debug(f"Step {step.name} attempt {attempt + 1} failed, retrying in {delay}s")
                await asyncio.sleep(delay)

        raise ProcessStepFailed(step.name, last_error or "Unknown error")

    async def _execute_step_impl(
        self,
        run_id: str,
        step: ProcessStepSpec,
        context: ProcessContext,
        spec: ProcessSpec,
    ) -> dict[str, Any]:
        """Execute step implementation by kind."""
        # Build step inputs
        step_inputs: dict[str, Any] = {}
        for mapping in step.inputs:
            value = context.resolve(mapping.source)
            step_inputs[mapping.target] = value

        if step.kind == StepKind.SERVICE:
            return await self._execute_service_step(step, step_inputs, context)

        elif step.kind == StepKind.SEND:
            return await self._execute_send_step(step, step_inputs, context)

        elif step.kind == StepKind.WAIT:
            return await self._execute_wait_step(step, context)

        elif step.kind == StepKind.HUMAN_TASK:
            return await self._execute_human_task_step(run_id, step, context)

        elif step.kind == StepKind.SUBPROCESS:
            return await self._execute_subprocess_step(step, step_inputs)

        elif step.kind == StepKind.PARALLEL:
            return await self._execute_parallel_step(run_id, step, context, spec)

        else:
            return {}

    async def _execute_service_step(
        self,
        step: ProcessStepSpec,
        inputs: dict[str, Any],
        context: ProcessContext,
    ) -> dict[str, Any]:
        """Execute a service call step."""
        service_name = step.service
        if not service_name:
            raise ProcessStepFailed(step.name, "No service specified")

        handler = self._service_handlers.get(service_name)
        if not handler:
            logger.warning(f"No handler for service {service_name}, using no-op")
            return {}

        return await handler(inputs)

    async def _execute_send_step(
        self,
        step: ProcessStepSpec,
        inputs: dict[str, Any],
        context: ProcessContext,
    ) -> dict[str, Any]:
        """Execute a message send step."""
        if not step.channel or not step.message:
            raise ProcessStepFailed(step.name, "No channel or message specified")

        if self._send_handler:
            await self._send_handler(step.channel, step.message, inputs)

        return {"sent": True, "channel": step.channel, "message": step.message}

    async def _execute_wait_step(
        self,
        step: ProcessStepSpec,
        context: ProcessContext,
    ) -> dict[str, Any]:
        """Execute a wait step (duration or signal)."""
        if step.wait_duration_seconds:
            await asyncio.sleep(step.wait_duration_seconds)
            return {"waited_seconds": step.wait_duration_seconds}

        if step.wait_for_signal:
            # Poll for signal
            run_id = context.get_variable("run_id")
            deadline = datetime.now(UTC) + timedelta(seconds=step.timeout_seconds)
            while datetime.now(UTC) < deadline:
                signal = await self._check_signal(run_id, step.wait_for_signal)
                if signal:
                    return {"signal": step.wait_for_signal, "payload": signal}
                await asyncio.sleep(self._poll_interval)

            raise ProcessStepFailed(
                step.name, f"Timeout waiting for signal: {step.wait_for_signal}"
            )

        return {}

    async def _execute_human_task_step(
        self,
        run_id: str,
        step: ProcessStepSpec,
        context: ProcessContext,
    ) -> dict[str, Any]:
        """Execute a human task step."""
        if not step.human_task:
            raise ProcessStepFailed(step.name, "No human_task configuration")

        task_config = step.human_task

        # Resolve assignee
        assignee_id = None
        if task_config.assignee_expression:
            assignee_id = context.resolve(task_config.assignee_expression)

        # Resolve entity path
        entity_id = ""
        entity_name = ""
        if task_config.entity_path:
            entity_id = context.resolve(f"{task_config.entity_path}.id") or ""
            # Extract entity name from path (e.g., "inputs.expense_report" -> "expense_report")
            parts = task_config.entity_path.split(".")
            entity_name = parts[-1] if parts else ""

        # Create task
        task_id = str(uuid.uuid4())
        due_at = datetime.now(UTC) + timedelta(seconds=step.timeout_seconds)

        await self._create_task(
            task_id=task_id,
            run_id=run_id,
            step_name=step.name,
            surface_name=task_config.surface,
            entity_name=entity_name,
            entity_id=entity_id,
            assignee_id=assignee_id,
            assignee_role=task_config.assignee_role,
            due_at=due_at,
        )

        await self._emit_event(
            "HumanTaskAssigned",
            run_id,
            task_id=task_id,
            step_name=step.name,
            surface=task_config.surface,
        )

        # Poll for completion
        escalation_seconds = task_config.escalation_timeout_seconds or step.timeout_seconds
        escalation_time = datetime.now(UTC) + timedelta(seconds=escalation_seconds)

        while datetime.now(UTC) < due_at:
            task = await self.get_task(task_id)
            if not task:
                raise ProcessStepFailed(step.name, "Task not found")

            if task.status == TaskStatus.COMPLETED:
                # Apply outcome
                outcome = task.outcome or "completed"
                outcome_data = task.outcome_data or {}

                # Find matching outcome config and apply sets
                for outcome_config in task_config.outcomes:
                    if outcome_config.name == outcome:
                        for _assignment in outcome_config.sets:
                            # Apply field assignment (would need entity service integration)
                            pass
                        break

                return {"outcome": outcome, "task_id": task_id, **outcome_data}

            # Check escalation
            if datetime.now(UTC) > escalation_time and not task.escalated_at:
                await self._escalate_task(task_id)

            await asyncio.sleep(self._poll_interval)

        raise ProcessStepFailed(step.name, "Human task timed out")

    async def _execute_subprocess_step(
        self,
        step: ProcessStepSpec,
        inputs: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a subprocess step."""
        if not step.subprocess:
            raise ProcessStepFailed(step.name, "No subprocess specified")

        # Start subprocess and wait for completion
        run_id = await self.start_process(step.subprocess, inputs)

        # Poll for completion
        while True:
            run = await self.get_run(run_id)
            if not run:
                raise ProcessStepFailed(step.name, "Subprocess not found")

            if run.status == ProcessStatus.COMPLETED:
                return {"subprocess_run_id": run_id, "outputs": run.outputs or {}}

            if run.status in (ProcessStatus.FAILED, ProcessStatus.CANCELLED):
                raise ProcessStepFailed(step.name, f"Subprocess {run.status.value}: {run.error}")

            await asyncio.sleep(self._poll_interval)

    async def _execute_parallel_step(
        self,
        run_id: str,
        step: ProcessStepSpec,
        context: ProcessContext,
        spec: ProcessSpec,
    ) -> dict[str, Any]:
        """Execute parallel steps."""
        if not step.parallel_steps:
            return {}

        # Create tasks for each parallel step
        tasks = []
        for parallel_step in step.parallel_steps:
            task = asyncio.create_task(self._execute_step(run_id, parallel_step, context, spec))
            tasks.append((parallel_step.name, task))

        # Wait for all with policy
        results: dict[str, Any] = {}
        errors: list[str] = []

        if step.parallel_policy.value == "fail_fast":
            # Fail on first error
            done, pending = await asyncio.wait(
                [t for _, t in tasks],
                return_when=asyncio.FIRST_EXCEPTION,
            )

            # Cancel pending
            for task in pending:
                task.cancel()

            # Collect results
            for name, task in tasks:
                if task.done():
                    try:
                        results[name] = task.result()
                    except Exception as e:
                        errors.append(f"{name}: {e}")
        else:
            # Wait for all
            await asyncio.gather(*[t for _, t in tasks], return_exceptions=True)

            for name, task in tasks:
                try:
                    results[name] = task.result()
                except Exception as e:
                    errors.append(f"{name}: {e}")

        if errors:
            raise ProcessStepFailed(step.name, f"Parallel failures: {'; '.join(errors)}")

        return results

    # Internal: Compensation
    async def _run_compensations(
        self,
        run_id: str,
        spec: ProcessSpec,
        completed_steps: list[str],
        context: ProcessContext,
    ) -> None:
        """Run compensation handlers for completed steps in reverse order."""
        if not spec.compensations:
            return

        await self._update_run_status(run_id, ProcessStatus.COMPENSATING)

        # Build compensation map
        comp_map: dict[str, CompensationSpec] = {}
        for comp in spec.compensations:
            comp_map[comp.name] = comp

        # Run compensations in reverse order
        for step_name in reversed(completed_steps):
            step = spec.get_step(step_name)
            if step and step.compensate_with:
                compensation = comp_map.get(step.compensate_with)
                if compensation:
                    try:
                        await self._run_compensation(run_id, compensation, context)
                    except Exception as e:
                        logger.error(f"Compensation {compensation.name} failed: {e}")

    async def _run_compensation(
        self,
        run_id: str,
        comp: CompensationSpec,
        context: ProcessContext,
    ) -> None:
        """Run a single compensation handler."""
        if comp.service:
            handler = self._service_handlers.get(comp.service)
            if handler:
                # Build inputs
                inputs: dict[str, Any] = {}
                for mapping in comp.inputs:
                    inputs[mapping.target] = context.resolve(mapping.source)

                await asyncio.wait_for(
                    handler(inputs),
                    timeout=comp.timeout_seconds,
                )

    # Internal: Scheduling
    async def _run_scheduler(self) -> None:
        """Background task to check and run scheduled processes."""
        while True:
            try:
                await asyncio.sleep(self._scheduler_interval)
                if self._shutting_down:
                    break

                now = datetime.now(UTC)

                # Check scheduled processes
                for name, spec in self._schedule_registry.items():
                    if await self._should_run_schedule(spec, now):
                        try:
                            run_id = await self.start_process(name, {})
                            await self._update_schedule_run(name, run_id)
                        except Exception as e:
                            await self._record_schedule_error(name, str(e))

                # Check for task escalations
                await self._check_pending_escalations()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Scheduler error: {e}")

    async def _should_run_schedule(self, spec: ScheduleSpec, now: datetime) -> bool:
        """Check if a schedule should run now."""
        if not self._db:
            return False

        async with self._db.execute(
            "SELECT last_run_at, next_run_at FROM schedule_runs WHERE schedule_name = ?",
            (spec.name,),
        ) as cursor:
            row = await cursor.fetchone()

        if not row:
            return True

        last_run = row["last_run_at"]
        if last_run:
            last_run = datetime.fromisoformat(last_run)

            # Check interval
            if spec.interval_seconds:
                return (now - last_run).total_seconds() >= spec.interval_seconds

            # Cron would need croniter library
            if spec.cron:
                # Simplified: just check if enough time has passed (minimum 1 hour)
                return (now - last_run).total_seconds() >= 3600

        return True

    # Internal: Database Operations
    async def _save_run(self, run: ProcessRun) -> None:
        """Save a process run to the database."""
        if not self._db:
            return

        await self._db.execute(
            """
            INSERT INTO process_runs
            (run_id, process_name, process_version, dsl_version, status,
             current_step, inputs, context, outputs, error, idempotency_key,
             started_at, updated_at, completed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run.run_id,
                run.process_name,
                run.process_version,
                run.dsl_version,
                run.status.value,
                run.current_step,
                json.dumps(run.inputs),
                json.dumps(run.context),
                json.dumps(run.outputs) if run.outputs else None,
                run.error,
                run.idempotency_key,
                run.started_at.isoformat(),
                run.updated_at.isoformat(),
                run.completed_at.isoformat() if run.completed_at else None,
            ),
        )
        await self._db.commit()

    async def _update_run(
        self,
        run_id: str,
        current_step: str | None = None,
        context: ProcessContext | None = None,
    ) -> None:
        """Update run with current step and context."""
        if not self._db:
            return

        updates = ["updated_at = CURRENT_TIMESTAMP"]
        params: list[Any] = []

        if current_step is not None:
            updates.append("current_step = ?")
            params.append(current_step)

        if context is not None:
            updates.append("context = ?")
            params.append(json.dumps(context.to_dict()))

        params.append(run_id)

        await self._db.execute(
            f"UPDATE process_runs SET {', '.join(updates)} WHERE run_id = ?",
            params,
        )
        await self._db.commit()

    async def _update_run_status(
        self,
        run_id: str,
        status: ProcessStatus,
        error: str | None = None,
    ) -> None:
        """Update run status."""
        if not self._db:
            return

        await self._db.execute(
            """
            UPDATE process_runs
            SET status = ?, error = ?, updated_at = CURRENT_TIMESTAMP
            WHERE run_id = ?
            """,
            (status.value, error, run_id),
        )
        await self._db.commit()

    async def _complete_run(self, run_id: str, outputs: dict[str, Any]) -> None:
        """Mark run as completed."""
        if not self._db:
            return

        await self._db.execute(
            """
            UPDATE process_runs
            SET status = ?, outputs = ?, completed_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE run_id = ?
            """,
            (ProcessStatus.COMPLETED.value, json.dumps(outputs), run_id),
        )
        await self._db.commit()

    async def _fail_run(self, run_id: str, error: str) -> None:
        """Mark run as failed."""
        if not self._db:
            return

        await self._db.execute(
            """
            UPDATE process_runs
            SET status = ?, error = ?, completed_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE run_id = ?
            """,
            (ProcessStatus.FAILED.value, error, run_id),
        )
        await self._db.commit()

    async def _suspend_run(self, run_id: str) -> None:
        """Mark run as suspended."""
        await self._update_run_status(run_id, ProcessStatus.SUSPENDED)

    async def _get_run_by_idempotency_key(self, key: str) -> ProcessRun | None:
        """Get run by idempotency key."""
        if not self._db:
            return None

        async with self._db.execute(
            "SELECT * FROM process_runs WHERE idempotency_key = ?",
            (key,),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return self._row_to_run(row)
        return None

    async def _resume_suspended_processes(self) -> None:
        """Resume any suspended processes on startup."""
        runs = await self.list_runs(status=ProcessStatus.SUSPENDED)
        for run in runs:
            await self.resume_process(run.run_id)

    async def _create_task(
        self,
        task_id: str,
        run_id: str,
        step_name: str,
        surface_name: str,
        entity_name: str,
        entity_id: str,
        assignee_id: str | None,
        assignee_role: str | None,
        due_at: datetime,
    ) -> None:
        """Create a human task record."""
        if not self._db:
            return

        await self._db.execute(
            """
            INSERT INTO process_tasks
            (task_id, run_id, step_name, surface_name, entity_name, entity_id,
             assignee_id, assignee_role, due_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                run_id,
                step_name,
                surface_name,
                entity_name,
                entity_id,
                assignee_id,
                assignee_role,
                due_at.isoformat(),
            ),
        )
        await self._db.commit()

    async def _escalate_task(self, task_id: str) -> None:
        """Mark task as escalated."""
        if not self._db:
            return

        await self._db.execute(
            """
            UPDATE process_tasks
            SET status = ?, escalated_at = CURRENT_TIMESTAMP
            WHERE task_id = ?
            """,
            (TaskStatus.ESCALATED.value, task_id),
        )
        await self._db.commit()

    async def _check_pending_escalations(self) -> None:
        """
        Check all pending tasks for escalation.

        Called periodically by the scheduler to escalate overdue tasks.
        """
        if not self._db:
            return

        now = datetime.now(UTC).isoformat()

        # Find pending tasks past their due date that haven't been escalated
        async with self._db.execute(
            """
            SELECT task_id, run_id, step_name
            FROM process_tasks
            WHERE status = ?
              AND escalated_at IS NULL
              AND due_at < ?
            """,
            (TaskStatus.PENDING.value, now),
        ) as cursor:
            tasks = await cursor.fetchall()

        for task in tasks:
            try:
                await self._escalate_task(task["task_id"])
                logger.info(
                    f"Escalated task {task['task_id']} "
                    f"(run={task['run_id']}, step={task['step_name']})"
                )
            except Exception as e:
                logger.error(f"Failed to escalate task {task['task_id']}: {e}")

    async def _check_signal(self, run_id: str, signal_name: str) -> dict[str, Any] | None:
        """Check for an unprocessed signal."""
        if not self._db:
            return None

        async with self._db.execute(
            """
            SELECT signal_id, payload FROM process_signals
            WHERE run_id = ? AND signal_name = ? AND processed = FALSE
            LIMIT 1
            """,
            (run_id, signal_name),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                # Mark as processed
                await self._db.execute(
                    """
                    UPDATE process_signals
                    SET processed = TRUE, processed_at = CURRENT_TIMESTAMP
                    WHERE signal_id = ?
                    """,
                    (row["signal_id"],),
                )
                await self._db.commit()
                payload: dict[str, Any] = json.loads(row["payload"])
                return payload
        return None

    async def _record_step_execution(
        self,
        run_id: str,
        step_name: str,
        step_kind: str,
        status: str,
        outputs: dict[str, Any] | None = None,
        error: str | None = None,
        attempt: int = 1,
    ) -> None:
        """Record step execution for audit."""
        if not self._db:
            return

        execution_id = str(uuid.uuid4())
        await self._db.execute(
            """
            INSERT INTO step_executions
            (execution_id, run_id, step_name, step_kind, attempt, status,
             outputs, error, completed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                execution_id,
                run_id,
                step_name,
                step_kind,
                attempt,
                status,
                json.dumps(outputs) if outputs else None,
                error,
            ),
        )
        await self._db.commit()

    async def _update_schedule_run(self, schedule_name: str, run_id: str) -> None:
        """Update schedule run tracking."""
        if not self._db:
            return

        await self._db.execute(
            """
            UPDATE schedule_runs
            SET last_run_at = CURRENT_TIMESTAMP, last_run_id = ?,
                run_count = run_count + 1, updated_at = CURRENT_TIMESTAMP
            WHERE schedule_name = ?
            """,
            (run_id, schedule_name),
        )
        await self._db.commit()

    async def _record_schedule_error(self, schedule_name: str, error: str) -> None:
        """Record schedule execution error."""
        if not self._db:
            return

        await self._db.execute(
            """
            UPDATE schedule_runs
            SET error_count = error_count + 1, last_error = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE schedule_name = ?
            """,
            (error, schedule_name),
        )
        await self._db.commit()

    async def _emit_event(self, schema_name: str, run_id: str, **kwargs: Any) -> None:
        """Emit a process lifecycle event."""
        if not self._db:
            return

        event_data = {
            "schema": schema_name,
            "run_id": run_id,
            "t_event": datetime.now(UTC).isoformat(),
            **kwargs,
        }

        # Store event
        event_id = str(uuid.uuid4())
        process_name = kwargs.get("process_name", "")
        await self._db.execute(
            """
            INSERT INTO process_events
            (event_id, run_id, process_name, schema_name, event_data)
            VALUES (?, ?, ?, ?, ?)
            """,
            (event_id, run_id, process_name, schema_name, json.dumps(event_data)),
        )
        await self._db.commit()

        # Call event handler if registered
        if self._event_handler:
            try:
                await self._event_handler(schema_name, event_data)
            except Exception as e:
                logger.error(f"Event handler error: {e}")

    # Helpers
    def _calculate_backoff(self, retry: RetryConfig, attempt: int) -> float:
        """Calculate backoff delay for retry."""
        if retry.backoff == RetryBackoff.FIXED:
            return float(retry.initial_interval_seconds)

        elif retry.backoff == RetryBackoff.LINEAR:
            return float(retry.initial_interval_seconds * (attempt + 1))

        else:  # EXPONENTIAL
            delay = retry.initial_interval_seconds * (retry.backoff_coefficient**attempt)
            return min(delay, retry.max_interval_seconds)

    def _row_to_run(self, row: aiosqlite.Row) -> ProcessRun:
        """Convert database row to ProcessRun."""
        return ProcessRun(
            run_id=row["run_id"],
            process_name=row["process_name"],
            process_version=row["process_version"],
            dsl_version=row["dsl_version"],
            status=ProcessStatus(row["status"]),
            current_step=row["current_step"],
            inputs=json.loads(row["inputs"]),
            context=json.loads(row["context"]),
            outputs=json.loads(row["outputs"]) if row["outputs"] else None,
            error=row["error"],
            idempotency_key=row["idempotency_key"],
            started_at=datetime.fromisoformat(row["started_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            completed_at=(
                datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None
            ),
        )

    def _row_to_task(self, row: aiosqlite.Row) -> ProcessTask:
        """Convert database row to ProcessTask."""
        return ProcessTask(
            task_id=row["task_id"],
            run_id=row["run_id"],
            step_name=row["step_name"],
            surface_name=row["surface_name"],
            entity_name=row["entity_name"],
            entity_id=row["entity_id"],
            assignee_id=row["assignee_id"],
            assignee_role=row["assignee_role"],
            status=TaskStatus(row["status"]),
            outcome=row["outcome"],
            outcome_data=json.loads(row["outcome_data"]) if row["outcome_data"] else None,
            due_at=datetime.fromisoformat(row["due_at"]),
            escalated_at=(
                datetime.fromisoformat(row["escalated_at"]) if row["escalated_at"] else None
            ),
            completed_at=(
                datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None
            ),
            created_at=datetime.fromisoformat(row["created_at"]),
        )
