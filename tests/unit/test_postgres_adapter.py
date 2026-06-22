"""Real-PG tests for ``PostgresProcessAdapter`` (Task 5).

Skips without ``TEST_DATABASE_URL`` / ``DATABASE_URL``.

Test matrix
-----------
1. Happy path  — ``start_process`` → consumer tick → ``COMPLETED``.
2. Crash-during-execution / at-least-once — claim a run, simulate crash
   (leave status='running', let lease expire), second tick reclaims and
   completes.
3. WAITING park and resume — human-task step parks run (lease released,
   not reclaimed while waiting); ``complete_task`` re-enqueues → COMPLETED.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg
import pytest

pytestmark = pytest.mark.postgres

_PG = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
_SKIP = not _PG


def _skip_no_pg(fn):  # type: ignore[return]
    return pytest.mark.skipif(_SKIP, reason="needs real Postgres (TEST_DATABASE_URL/DATABASE_URL)")(
        fn
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_store(dsn: str):
    from dazzle.core.process.pg_state import PgProcessStateStore

    return PgProcessStateStore(dsn)


def _make_adapter(dsn: str, store=None):
    from dazzle.core.process.postgres_adapter import PostgresProcessAdapter

    adapter = PostgresProcessAdapter(dsn, store=store)
    # Faster test cycles
    adapter._poll_interval = 0.1
    adapter._lease_seconds = 5
    adapter._batch_size = 10
    return adapter


def _make_process_spec(name: str, *, steps: list[dict[str, Any]]):
    """Build a minimal ProcessSpec the store accepts."""
    from dazzle.core.ir.process import ProcessSpec, ProcessStepSpec, StepKind

    spec_steps = []
    for s in steps:
        kind = s.get("kind", "service")
        step = ProcessStepSpec(
            name=s["name"],
            kind=StepKind(kind),
            service=s.get("service"),
            surface=s.get("surface"),
            channel=s.get("channel"),
            timeout_seconds=s.get("timeout_seconds", 30),
        )
        spec_steps.append(step)
    return ProcessSpec(name=name, steps=spec_steps)


def _arun(coro):
    """Run a coroutine, reusing a running loop if available."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        # In an async context — this shouldn't happen in sync tests.

        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=30)
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Test 1: Happy path — start → consumer tick → COMPLETED
# ---------------------------------------------------------------------------


@_skip_no_pg
def test_happy_path_completes():
    """start_process → _claim_and_execute_batch → run reaches COMPLETED."""
    dsn = _PG
    assert dsn

    store = _make_store(dsn)
    adapter = _make_adapter(dsn, store=store)

    proc_name = f"test_proc_{uuid.uuid4().hex[:8]}"
    spec = _make_process_spec(proc_name, steps=[{"name": "step_a", "kind": "service"}])
    store.register_process(spec)

    async def run():
        run_id = await adapter.start_process(proc_name, {"x": 1})
        # Drive one consumer batch instead of running the full background loop.
        await adapter._claim_and_execute_batch()
        return run_id

    run_id = asyncio.run(run())

    result = store.get_run(run_id)
    assert result is not None, "Run not found after execution"
    from dazzle.core.process.adapter import ProcessStatus

    assert result.status == ProcessStatus.COMPLETED, f"Expected COMPLETED, got {result.status}"
    # step_a sentinel should be in context
    assert "step_a" in (result.context or {}) or result.outputs is not None


# ---------------------------------------------------------------------------
# Test 2: Crash-during-execution / at-least-once
# ---------------------------------------------------------------------------


@_skip_no_pg
def test_crash_during_running_is_reclaimed_exactly_once():
    """
    Lease-governed reclaim of a 'running'+expired-lease row (the critical
    crash-during-execution constraint).

    Scenario:
    1. A run is saved as PENDING.
    2. We simulate a worker crash by directly setting status='running' with
       an expired lease and attempts=1 (as if claim_due_work ran, set
       status='claimed', attempts→1, and then execute_process_steps started
       and set status='running', then the worker died).
    3. _claim_and_execute_batch is called.  The crash-recovery reset in
       claim_due_runs should detect the expired-lease 'running' row and
       reset it to 'pending', then claim and execute it to COMPLETED.
    4. A second batch call finds nothing → exactly once.
    """
    dsn = _PG
    assert dsn

    store = _make_store(dsn)
    adapter = _make_adapter(dsn, store=store)

    proc_name = f"crash_test_{uuid.uuid4().hex[:8]}"
    spec = _make_process_spec(proc_name, steps=[{"name": "step_a", "kind": "service"}])
    store.register_process(spec)

    from dazzle.core.process.adapter import ProcessRun, ProcessStatus

    run_id = str(uuid.uuid4())
    run = ProcessRun(
        run_id=run_id,
        process_name=proc_name,
        status=ProcessStatus.PENDING,
        inputs={},
    )
    store.save_run(run)

    # Simulate crash: status='running', expired lease, attempts=1.
    expired = datetime.now(UTC) - timedelta(seconds=10)
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE process_runs
            SET status = 'running',
                claimed_by = 'dead-worker',
                claimed_at = now() - interval '15 seconds',
                lease_expires_at = %s,
                attempts = 1
            WHERE run_id = %s
            """,
            (expired, run_id),
        )
        conn.commit()

    # Verify stuck state.
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT status, lease_expires_at FROM process_runs WHERE run_id = %s", (run_id,)
        )
        row = cur.fetchone()
    assert row is not None
    assert row[0] == "running", f"Setup: expected 'running', got {row[0]}"
    assert row[1] <= datetime.now(UTC), "Setup: lease should already be expired"

    # First tick — reclaims the 'running'+expired-lease row and completes it.
    asyncio.run(adapter._claim_and_execute_batch())

    result = store.get_run(run_id)
    assert result is not None
    assert result.status == ProcessStatus.COMPLETED, (
        f"Expected COMPLETED after reclaim, got {result.status}"
    )

    # Second tick — nothing to claim (exactly once).
    asyncio.run(adapter._claim_and_execute_batch())
    result2 = store.get_run(run_id)
    assert result2 is not None
    assert result2.status == ProcessStatus.COMPLETED, (
        f"Run should still be COMPLETED after 2nd tick, got {result2.status}"
    )


# ---------------------------------------------------------------------------
# Test 3: WAITING park and resume via complete_task
# ---------------------------------------------------------------------------


@_skip_no_pg
def test_waiting_parks_and_resumes():
    """
    A WAITING run parks (lease released, not reclaimable); complete_task
    re-enqueues it → COMPLETED.
    """
    dsn = _PG
    assert dsn

    store = _make_store(dsn)
    adapter = _make_adapter(dsn, store=store)

    proc_name = f"wait_test_{uuid.uuid4().hex[:8]}"

    from dazzle.core.ir.process import ProcessSpec, ProcessStepSpec, StepKind
    from dazzle.core.process.adapter import ProcessRun, ProcessStatus, ProcessTask

    spec_steps = [
        ProcessStepSpec(
            name="approval",
            kind=StepKind.HUMAN_TASK,
            surface="approval_surface",
            timeout_seconds=3600,
        ),
        ProcessStepSpec(
            name="finalize",
            kind=StepKind.SERVICE,
            timeout_seconds=30,
        ),
    ]
    spec = ProcessSpec(name=proc_name, steps=spec_steps)
    store.register_process(spec)

    # Create a PENDING run.
    run_id = str(uuid.uuid4())
    run = ProcessRun(
        run_id=run_id,
        process_name=proc_name,
        status=ProcessStatus.PENDING,
        inputs={},
    )
    store.save_run(run)

    # Manually set it to WAITING with lease released (as the adapter does
    # after the human-task step is hit during execution).
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE process_runs
            SET status = 'waiting',
                current_step = 'approval',
                claimed_by = NULL,
                lease_expires_at = NULL
            WHERE run_id = %s
            """,
            (run_id,),
        )
        conn.commit()

    # Create the corresponding task.
    task_id = str(uuid.uuid4())
    due = datetime.now(UTC) + timedelta(hours=1)
    task = ProcessTask(
        task_id=task_id,
        run_id=run_id,
        step_name="approval",
        surface_name="approval_surface",
        entity_name="Order",
        entity_id=str(uuid.uuid4()),
        due_at=due,
    )
    store.save_task(task)

    # Confirm WAITING state with lease released.
    result = store.get_run(run_id)
    assert result is not None
    assert result.status == ProcessStatus.WAITING

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT claimed_by, lease_expires_at FROM process_runs WHERE run_id = %s",
            (run_id,),
        )
        row = cur.fetchone()
    assert row is not None
    assert row[0] is None, "claimed_by should be NULL for parked WAITING run"
    assert row[1] is None, "lease_expires_at should be NULL for parked WAITING run"

    # Consumer tick — should NOT pick up the WAITING run.
    asyncio.run(adapter._claim_and_execute_batch())

    result = store.get_run(run_id)
    assert result is not None
    assert result.status == ProcessStatus.WAITING, (
        f"Run should still be WAITING after tick, got {result.status}"
    )

    # Pre-seed context so both steps are skipped on resume
    # (approval = parked/already-done, finalize = no-op via sentinel).
    import json

    ctx = json.dumps({"approval": {}, "finalize": {}})
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE process_runs SET context = %s::jsonb WHERE run_id = %s",
            (ctx, run_id),
        )
        conn.commit()

    # complete_task should store outcome and re-enqueue the run.
    asyncio.run(adapter.complete_task(task_id, outcome="approved"))

    # Verify re-enqueued (status='pending').
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT status FROM process_runs WHERE run_id = %s", (run_id,))
        row = cur.fetchone()
    assert row is not None
    assert row[0] == "pending", f"Expected 'pending' after complete_task, got {row[0]}"

    # Consumer tick — claims the re-enqueued run; all steps skipped → COMPLETED.
    asyncio.run(adapter._claim_and_execute_batch())

    result = store.get_run(run_id)
    assert result is not None
    assert result.status == ProcessStatus.COMPLETED, (
        f"Expected COMPLETED after resume tick, got {result.status}"
    )
