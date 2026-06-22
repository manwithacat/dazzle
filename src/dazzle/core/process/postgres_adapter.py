"""PostgresProcessAdapter — ProcessAdapter using Postgres as the durable queue.

Architecture
============
"State tables ARE the queue."  ``process_runs`` / ``process_tasks`` carry
queue columns (``status``, ``deliver_at``, ``claimed_by``, ``lease_expires_at``,
``attempts``).  A ``claim_due_runs`` call (backed by ``claim_due_work`` with
``FOR UPDATE SKIP LOCKED``) atomically claims due rows; ``LISTEN/NOTIFY`` is a
best-effort latency hint over the durable polled table.

Run state machine
-----------------
::

    PENDING ──claim──► (claimed) ──execute_process_steps──► RUNNING
        │                                                        │
        │                             ┌──────────────────────────┤
        │                             │  step completes          │  all steps done
        │                             ▼                          ▼
        │                           RUNNING ──────────────► COMPLETED (terminal)
        │                             │
        │              human task     │  exception
        │              step hit       │
        │                │            ▼
        │                │          FAILED (terminal — mark_run_retry or dead)
        │                ▼
        │             WAITING  ← lease released; claimed_by cleared
        │                │          (NOT reclaimable — status not in claim set)
        │                │
        │      complete_task() → re_enqueue_run() → status='pending'
        │                │
        └────────────────┘   (re-enters claim loop → RUNNING → COMPLETED)

        CANCELLED (terminal — set by cancel_process; never reclaimed)

Crash-during-execution / at-least-once
---------------------------------------
``execute_process_steps`` sets ``status='running'`` on the domain row **while
the lease is still held**.  If the worker crashes:

* Row is left ``status='running'`` with expired lease.
* ``claim_due_runs`` in ``PgProcessStateStore`` resets expired-lease
  ``running`` rows to ``pending`` *before* calling ``claim_due_work``
  (see ``pg_state.py:claim_due_runs``).  The reclaim predicate is
  ``status='running' AND lease_expires_at <= now() AND attempts < max``.
* The reclaimed run re-enters ``execute_process_steps`` which **skips already-
  completed steps** via the checkpoint in ``run.context`` (Task 4 /
  ``step_executor.py``).  Side-effects fire exactly once per step.
* Terminal states (``completed`` / ``failed`` / ``cancelled`` / ``dead``) and
  ``waiting`` / ``suspended`` are never matched by the reclaim condition.

WAITING → lease release
-----------------------
When a human-task step is hit, ``execute_process_steps`` returns
``{"status": "waiting"}``.  The adapter then:

1. Releases the lease (clears ``claimed_by`` / ``lease_expires_at``),
   leaving ``status='waiting'``.
2. The claim loop will NOT pick it up (no match on ``status='waiting'``).
3. ``complete_task`` stores the outcome and calls ``store.re_enqueue_run``
   (``status → 'pending'``, ``deliver_at → now()``).
4. The next poll claims and resumes the run.

NOTIFY latency hint
--------------------
``start_process`` sends a sync ``NOTIFY process_run`` so a waiting consumer
wakes immediately.  The consumer loop maintains **one shared async LISTEN
connection** (``psycopg.AsyncConnection``) and waits on whichever fires first:
the NOTIFY or the ``poll_interval`` timeout.  If LISTEN/NOTIFY fails, the poll
floor guarantees eventual execution.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from dazzle.core.process.process_state import ProcessStateStore

from dazzle.core.ir.process import ProcessSpec, ScheduleSpec
from dazzle.core.process.adapter import (
    ProcessAdapter,
    ProcessRun,
    ProcessStatus,
    ProcessTask,
    TaskStatus,
)
from dazzle.core.process.pg_state import PgProcessStateStore
from dazzle.core.process.step_executor import check_task_timeout, execute_process_steps, fail_run

logger = logging.getLogger(__name__)

# Channel name used for NOTIFY / LISTEN.
_NOTIFY_CHANNEL = "process_run"


def _resolve_param_ref(value: Any) -> Any:
    """Unwrap a ParamRef to its default (mirrors EventBusProcessAdapter)."""
    if hasattr(value, "default"):
        return value.default
    return value


class PostgresProcessAdapter(ProcessAdapter):
    """ProcessAdapter backed by Postgres claim/lease + optional NOTIFY hint.

    ``__init__(dsn, store=None)``

    * *dsn* — Postgres connection string (``postgresql://...``).
    * *store* — optional ``PgProcessStateStore`` instance; one is created
      from *dsn* if not supplied.

    All public methods are ``async``; sync store / executor calls are
    wrapped via ``asyncio.to_thread`` (same pattern as
    ``EventBusProcessAdapter``).
    """

    def __init__(
        self,
        dsn: str,
        store: PgProcessStateStore | None = None,
    ) -> None:
        self._dsn = dsn
        self._store = store or PgProcessStateStore(dsn)
        self._initialized = False
        self._consumer_task: asyncio.Task[None] | None = None
        self._scheduler_task: asyncio.Task[None] | None = None
        self._shutdown_event = asyncio.Event()
        self._schedules: dict[str, dict[str, Any]] = {}
        # Notify event — set when a LISTEN fires so the poll wakes early.
        self._notify_event: asyncio.Event = asyncio.Event()
        # Config knobs (can be overridden by tests / subclasses).
        self._poll_interval: float = 2.0
        self._lease_seconds: int = 60
        self._batch_size: int = 5
        self._worker_id: str = f"worker-{uuid.uuid4().hex[:8]}"

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    async def initialize(self) -> None:
        """Start background consumer and scheduler loops."""
        if self._initialized:
            return

        logger.info("PostgresProcessAdapter initializing (worker=%s)", self._worker_id)

        self._consumer_task = asyncio.create_task(self._consumer_loop(), name="pg-process-consumer")
        self._scheduler_task = asyncio.create_task(
            self._scheduler_loop(), name="pg-process-scheduler"
        )

        self._initialized = True
        logger.info("PostgresProcessAdapter initialized")

    async def shutdown(self) -> None:
        """Graceful shutdown — cancel consumer and scheduler loops."""
        logger.info("PostgresProcessAdapter shutting down")
        self._shutdown_event.set()
        self._notify_event.set()  # Wake the consumer so it can exit cleanly.

        for task in [self._consumer_task, self._scheduler_task]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    # -------------------------------------------------------------------------
    # Process Registration
    # -------------------------------------------------------------------------

    async def register_process(self, spec: ProcessSpec) -> None:
        await asyncio.to_thread(self._store.register_process, spec)
        logger.debug("Registered process: %s", spec.name)

    async def register_schedule(self, spec: ScheduleSpec) -> None:
        await asyncio.to_thread(self._store.register_schedule, spec)
        self._schedules[spec.name] = {
            "name": spec.name,
            "process_name": getattr(spec, "process_name", spec.name),
            "cron": _resolve_param_ref(getattr(spec, "cron", None)),
            "interval_seconds": _resolve_param_ref(getattr(spec, "interval_seconds", None)),
        }
        logger.debug("Registered schedule: %s", spec.name)

    async def register_entity_meta(self, entity_name: str, meta: dict[str, Any]) -> None:
        await asyncio.to_thread(self._store.save_entity_meta, entity_name, meta)
        logger.debug("Registered entity metadata: %s", entity_name)

    # -------------------------------------------------------------------------
    # Process Lifecycle
    # -------------------------------------------------------------------------

    async def start_process(
        self,
        process_name: str,
        inputs: dict[str, Any],
        idempotency_key: str | None = None,
        dsl_version: str | None = None,
    ) -> str:
        if idempotency_key:
            existing = await asyncio.to_thread(self._find_run_by_idempotency_key, idempotency_key)
            if existing:
                logger.info("Returning existing run %s for idempotency key", existing.run_id)
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
        await asyncio.to_thread(self._store.save_run, run)

        logger.info("Starting process %s run %s", process_name, run_id)

        # Best-effort NOTIFY to wake the consumer immediately.
        await self._notify()
        return run_id

    def _find_run_by_idempotency_key(self, key: str) -> ProcessRun | None:
        for run in self._store.list_runs(limit=1000):
            if run.idempotency_key == key:
                return run
        return None

    async def get_run(self, run_id: str) -> ProcessRun | None:
        return await asyncio.to_thread(self._store.get_run, run_id)

    async def list_runs(
        self,
        process_name: str | None = None,
        status: ProcessStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ProcessRun]:
        return await asyncio.to_thread(
            self._store.list_runs,
            process_name=process_name,
            status=status,
            limit=limit,
            offset=offset,
        )

    async def cancel_process(self, run_id: str, reason: str) -> None:
        run = await asyncio.to_thread(self._store.get_run, run_id)
        if run and run.status not in (
            ProcessStatus.COMPLETED,
            ProcessStatus.FAILED,
            ProcessStatus.CANCELLED,
        ):
            run.status = ProcessStatus.CANCELLED
            run.error = f"Cancelled: {reason}"
            run.completed_at = datetime.now(UTC)
            run.updated_at = datetime.now(UTC)
            await asyncio.to_thread(self._store.save_run, run)
            logger.info("Cancelled process run %s: %s", run_id, reason)

    async def suspend_process(self, run_id: str) -> None:
        run = await asyncio.to_thread(self._store.get_run, run_id)
        if run and run.status == ProcessStatus.RUNNING:
            run.status = ProcessStatus.SUSPENDED
            run.updated_at = datetime.now(UTC)
            await asyncio.to_thread(self._store.save_run, run)
            logger.info("Suspended process run %s", run_id)

    async def resume_process(self, run_id: str) -> None:
        run = await asyncio.to_thread(self._store.get_run, run_id)
        if run and run.status == ProcessStatus.SUSPENDED:
            run.status = ProcessStatus.PENDING
            run.updated_at = datetime.now(UTC)
            await asyncio.to_thread(self._store.save_run, run)
            await self._notify()
            logger.info("Resumed process run %s", run_id)

    # -------------------------------------------------------------------------
    # Signals
    # -------------------------------------------------------------------------

    async def signal_process(
        self,
        run_id: str,
        signal_name: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        run = await asyncio.to_thread(self._store.get_run, run_id)
        if not run:
            logger.warning("Signal %s sent to unknown run %s", signal_name, run_id)
            return

        run.context[f"signal_{signal_name}"] = payload or {}
        run.updated_at = datetime.now(UTC)
        await asyncio.to_thread(self._store.save_run, run)

        if run.status == ProcessStatus.WAITING:
            run.status = ProcessStatus.PENDING
            await asyncio.to_thread(self._store.save_run, run)
            await self._notify()

        logger.info("Signal %s sent to run %s", signal_name, run_id)

    # -------------------------------------------------------------------------
    # Human Tasks
    # -------------------------------------------------------------------------

    async def get_task(self, task_id: str) -> ProcessTask | None:
        return await asyncio.to_thread(self._store.get_task, task_id)

    async def list_tasks(
        self,
        run_id: str | None = None,
        assignee_id: str | None = None,
        status: TaskStatus | None = None,
        limit: int = 100,
    ) -> list[ProcessTask]:
        return await asyncio.to_thread(
            self._store.list_tasks,
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
        task = await asyncio.to_thread(self._store.get_task, task_id)
        if not task:
            logger.warning("Task %s not found", task_id)
            return

        if task.status in (TaskStatus.COMPLETED, TaskStatus.CANCELLED, TaskStatus.EXPIRED):
            logger.warning("Task %s already in terminal state: %s", task_id, task.status)
            return

        task.status = TaskStatus.COMPLETED
        task.outcome = outcome
        task.outcome_data = outcome_data
        task.completed_at = datetime.now(UTC)
        if completed_by:
            task.assignee_id = completed_by
        await asyncio.to_thread(self._store.save_task, task)

        logger.info("Task %s completed with outcome: %s", task_id, outcome)

        # Store outcome in parent run context so the resumed run can read it.
        run = await asyncio.to_thread(self._store.get_run, task.run_id)
        if run:
            run.context[f"{task.step_name}_outcome"] = outcome
            if outcome_data:
                run.context[f"{task.step_name}_data"] = outcome_data
            run.updated_at = datetime.now(UTC)
            await asyncio.to_thread(self._store.save_run, run)

        # Re-enqueue the parked WAITING run so the next poll picks it up.
        await asyncio.to_thread(self._store.re_enqueue_run, task.run_id)
        await self._notify()

    async def reassign_task(
        self,
        task_id: str,
        new_assignee_id: str,
        reason: str | None = None,
    ) -> None:
        del reason
        task = await asyncio.to_thread(self._store.get_task, task_id)
        if not task:
            logger.warning("Task %s not found", task_id)
            return

        old_assignee = task.assignee_id
        task.assignee_id = new_assignee_id
        task.status = TaskStatus.ASSIGNED
        await asyncio.to_thread(self._store.save_task, task)
        logger.info("Task %s reassigned from %s to %s", task_id, old_assignee, new_assignee_id)

    # -------------------------------------------------------------------------
    # Version Management
    # -------------------------------------------------------------------------

    async def list_runs_by_version(
        self,
        dsl_version: str,
        status: ProcessStatus | None = None,
        limit: int = 100,
    ) -> list[ProcessRun]:
        return await asyncio.to_thread(
            self._store.list_runs_by_version,
            dsl_version=dsl_version,
            status=status,
            limit=limit,
        )

    async def count_active_runs_by_version(self, dsl_version: str) -> int:
        return await asyncio.to_thread(self._store.count_active_runs_by_version, dsl_version)

    # -------------------------------------------------------------------------
    # NOTIFY helper
    # -------------------------------------------------------------------------

    async def _notify(self) -> None:
        """Send a best-effort NOTIFY to wake sleeping consumers.

        Uses a transient async psycopg connection so we don't need to
        hold a long-lived connection just for NOTIFY.  Failures are
        swallowed — NOTIFY is a latency hint; the poll floor is the
        durability guarantee.
        """
        try:
            import psycopg  # noqa: PLC0415

            async with await psycopg.AsyncConnection.connect(self._dsn) as conn:
                await conn.execute(f"NOTIFY {_NOTIFY_CHANNEL}")
        except Exception as exc:
            logger.warning("NOTIFY failed (non-fatal): %s", exc)

        # Also wake our in-process consumer immediately.
        self._notify_event.set()

    # -------------------------------------------------------------------------
    # Consumer loop
    # -------------------------------------------------------------------------

    async def _consumer_loop(self) -> None:
        """Durable consumer loop: poll + LISTEN/NOTIFY hint.

        One LISTEN connection is shared for the lifetime of the loop.
        Between claim batches the loop waits on whichever fires first:
        - A NOTIFY on ``process_run`` (set via ``_notify_event``).
        - The ``_poll_interval`` timeout.

        The LISTEN path is best-effort; the poll guarantees liveness.
        """
        logger.info("Postgres process consumer loop starting (worker=%s)", self._worker_id)

        listen_task: asyncio.Task[None] | None = None
        try:
            listen_task = asyncio.create_task(self._listen_loop(), name="pg-process-listen")
        except Exception as exc:
            logger.warning("Could not start LISTEN task: %s", exc)

        while not self._shutdown_event.is_set():
            try:
                await self._claim_and_execute_batch()

                # Wait for next poll or NOTIFY, whichever is first.
                self._notify_event.clear()
                try:
                    await asyncio.wait_for(
                        asyncio.shield(self._notify_event_wait()),
                        timeout=self._poll_interval,
                    )
                except TimeoutError:
                    pass

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Consumer loop error: %s", exc)
                await asyncio.sleep(5.0)

        if listen_task and not listen_task.done():
            listen_task.cancel()
            try:
                await listen_task
            except (asyncio.CancelledError, Exception):
                pass

        logger.info("Postgres process consumer loop stopped")

    async def _notify_event_wait(self) -> None:
        """Async wait on the notify event."""
        while not self._notify_event.is_set() and not self._shutdown_event.is_set():
            await asyncio.sleep(0.05)

    async def _listen_loop(self) -> None:
        """Maintain a persistent LISTEN connection and set _notify_event on arrival."""
        try:
            import psycopg  # noqa: PLC0415

            async with await psycopg.AsyncConnection.connect(self._dsn, autocommit=True) as conn:
                await conn.execute(f"LISTEN {_NOTIFY_CHANNEL}")
                logger.debug("LISTEN %s active", _NOTIFY_CHANNEL)
                while not self._shutdown_event.is_set():
                    gen = conn.notifies(timeout=self._poll_interval)
                    async for _notify in gen:
                        logger.debug("NOTIFY received on %s", _NOTIFY_CHANNEL)
                        self._notify_event.set()
                        break
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.warning("LISTEN loop ended: %s", exc)

    async def _claim_and_execute_batch(self) -> None:
        """Claim a batch of due runs and execute each in a thread."""
        runs: list[ProcessRun] = await asyncio.to_thread(
            self._store.claim_due_runs,
            self._worker_id,
            self._lease_seconds,
            self._batch_size,
        )
        for run in runs:
            try:
                await asyncio.to_thread(self._execute_process_sync, run.run_id)
            except Exception as exc:
                logger.error("Failed to execute process %s: %s", run.run_id, exc)

        # Also handle task timeouts.
        await self._poll_task_timeouts()

    async def _poll_task_timeouts(self) -> None:
        """Check for expired human tasks and escalate/expire them."""
        try:
            tasks = await asyncio.to_thread(
                self._store.list_tasks,
                status=TaskStatus.PENDING,
                limit=50,
            )
            tasks += await asyncio.to_thread(
                self._store.list_tasks,
                status=TaskStatus.ASSIGNED,
                limit=50,
            )
            tasks += await asyncio.to_thread(
                self._store.list_tasks,
                status=TaskStatus.ESCALATED,
                limit=50,
            )
            now = datetime.now(UTC)
            for task in tasks:
                if now > task.due_at:
                    await asyncio.to_thread(
                        check_task_timeout,
                        cast("ProcessStateStore", self._store),
                        task.task_id,
                    )
        except Exception as exc:
            logger.warning("Task timeout poll error: %s", exc)

    # -------------------------------------------------------------------------
    # Sync execution helper (called from thread pool)
    # -------------------------------------------------------------------------

    def _execute_process_sync(self, run_id: str) -> None:
        """Execute a process run synchronously (called via asyncio.to_thread)."""
        run = self._store.get_run(run_id)
        if not run:
            logger.error("Process run %s not found", run_id)
            return

        # Only execute runs that are claimable / re-entered from WAITING.
        # 'claimed' maps to 'running' in _row_to_run so we check RUNNING here.
        if run.status not in (ProcessStatus.PENDING, ProcessStatus.RUNNING, ProcessStatus.WAITING):
            logger.debug("Skipping run %s in status %s", run_id, run.status)
            return

        def on_task_created(task_id: str, timeout_seconds: float) -> None:
            """Record task timeout in process_tasks (picked up by poll)."""
            logger.info(
                "Human task %s created, timeout in %ss (poll will check)",
                task_id,
                timeout_seconds,
            )

        try:
            result = execute_process_steps(
                cast("ProcessStateStore", self._store),
                run,
                on_task_created=on_task_created,
            )

            status = result.get("status")
            if status == "completed":
                # execute_process_steps already called save_run with COMPLETED;
                # mark_run_done flips the queue status so it's not reclaimed.
                self._store.mark_run_done(run_id)
            elif status == "waiting":
                # Release the lease so the run is parked until complete_task
                # calls re_enqueue_run.  Clearing claimed_by + lease_expires_at
                # means the crash-reclaim predicate won't match a legitimately
                # parked waiting run.
                import psycopg as _psycopg  # noqa: PLC0415

                with _psycopg.connect(self._store._dsn) as conn, conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE process_runs
                        SET claimed_by = NULL, lease_expires_at = NULL
                        WHERE run_id = %s
                        """,
                        (run_id,),
                    )
                    conn.commit()
                logger.info("Run %s parked at WAITING (lease released)", run_id)
            # status == "failed" is already handled by execute_process_steps
            # (via fail_run); no further action needed here.

        except Exception as exc:
            logger.exception("Process %s execution failed: %s", run_id, exc)
            run = self._store.get_run(run_id)
            if run and run.status not in (ProcessStatus.FAILED, ProcessStatus.COMPLETED):
                fail_run(cast("ProcessStateStore", self._store), run, str(exc))
            # Let claim_due_runs retry on next tick (attempts < max_attempts).
            self._store.mark_run_retry(run_id, str(exc))

    # -------------------------------------------------------------------------
    # Scheduler loop
    # -------------------------------------------------------------------------

    async def _scheduler_loop(self) -> None:
        """Background cron/interval schedule trigger loop."""
        logger.info("Postgres process scheduler loop starting")
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
            except Exception as exc:
                logger.warning("Scheduler loop error: %s", exc, exc_info=True)
                await asyncio.sleep(60.0)

        logger.info("Postgres process scheduler loop stopped")

    async def _trigger_schedule(self, name: str, schedule: dict[str, Any]) -> None:
        """Trigger a scheduled process by inserting a due run."""
        process_name = schedule.get("process_name", name)
        spec = await asyncio.to_thread(self._store.get_process_spec, process_name)
        if not spec:
            logger.warning("Schedule %s: process %s not found", name, process_name)
            return

        run_id = str(uuid.uuid4())
        run = ProcessRun(
            run_id=run_id,
            process_name=process_name,
            status=ProcessStatus.PENDING,
            inputs={"triggered_by": "schedule", "schedule_name": name},
        )
        await asyncio.to_thread(self._store.save_run, run)
        await asyncio.to_thread(self._store.set_schedule_last_run, name, datetime.now(UTC))
        await self._notify()
        logger.info("Triggered scheduled process %s run %s", process_name, run_id)

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
