"""Real-Postgres tests for ``PgProcessStateStore`` (Task 3, Phase 1).

Skipped unless ``TEST_DATABASE_URL`` or ``DATABASE_URL`` is set in the
environment.  Uses a transaction-per-test approach where possible; rows
that cannot be rolled back (e.g. those that require commits for FK
integrity) are inserted with unique IDs and deleted in teardown.

Run:
    DATABASE_URL=postgresql://localhost:5432/postgres \
        python -m pytest tests/unit/test_pg_state_store.py -v
"""

from __future__ import annotations

import os
import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest

pytestmark = pytest.mark.postgres

_PG = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")


@pytest.fixture(scope="module")
def store():
    """One store instance per module; tables ensured once."""
    if not _PG:
        pytest.skip("needs real Postgres (TEST_DATABASE_URL/DATABASE_URL)")
    from dazzle.core.process.pg_state import PgProcessStateStore

    return PgProcessStateStore(dsn=_PG)


def _run_id() -> str:
    return f"test-run-{uuid.uuid4().hex}"


def _task_id() -> str:
    return f"test-task-{uuid.uuid4().hex}"


def _make_run(**overrides):  # -> ProcessRun
    from dazzle.core.process.adapter import ProcessRun, ProcessStatus

    now = datetime.now(UTC)
    defaults = {
        "run_id": _run_id(),
        "process_name": "test_process",
        "process_version": "v1",
        "dsl_version": "0.1",
        "status": ProcessStatus.PENDING,
        "current_step": None,
        "inputs": {"order_id": str(uuid.uuid4()), "amount": 42.5},
        "context": {"step_a": {"result": "ok"}, "nested": {"x": [1, 2, 3]}},
        "outputs": None,
        "error": None,
        "idempotency_key": f"idem-{uuid.uuid4().hex}",
        "started_at": now,
        "updated_at": now,
        "completed_at": None,
    }
    defaults.update(overrides)
    return ProcessRun(**defaults)


def _make_task(run_id: str, **overrides):  # -> ProcessTask
    from dazzle.core.process.adapter import ProcessTask, TaskStatus

    now = datetime.now(UTC)
    defaults = {
        "task_id": _task_id(),
        "run_id": run_id,
        "step_name": "approve_step",
        "surface_name": "approval_surface",
        "entity_name": "Order",
        "entity_id": str(uuid.uuid4()),
        "assignee_id": "user-abc",
        "assignee_role": "manager",
        "status": TaskStatus.PENDING,
        "outcome": None,
        "outcome_data": None,
        "due_at": now + timedelta(hours=24),
        "escalated_at": None,
        "completed_at": None,
        "created_at": now,
    }
    defaults.update(overrides)
    return ProcessTask(**defaults)


# ── save_run / get_run round-trip ─────────────────────────────────────────────


@pytest.mark.skipif(not _PG, reason="needs real Postgres")
def test_save_run_get_run_round_trips_all_fields(store):
    """All ProcessRun fields survive a save → get cycle including jsonb dicts."""
    from dazzle.core.process.adapter import ProcessStatus

    run = _make_run(
        inputs={"key": "value", "number": 99},
        context={"step_a": {"done": True}, "step_b": {"rows": [1, 2, 3]}},
        outputs={"result": "success"},
        status=ProcessStatus.RUNNING,
        current_step="step_b",
        error=None,
    )
    store.save_run(run)

    try:
        loaded = store.get_run(run.run_id)
        assert loaded is not None
        assert loaded.run_id == run.run_id
        assert loaded.process_name == run.process_name
        assert loaded.process_version == run.process_version
        assert loaded.dsl_version == run.dsl_version
        assert loaded.status == run.status
        assert loaded.current_step == run.current_step
        assert loaded.inputs == run.inputs
        assert loaded.context == run.context
        assert loaded.outputs == run.outputs
        assert loaded.error == run.error
        assert loaded.idempotency_key == run.idempotency_key
        # Timestamps: compare to seconds precision (DB may truncate microseconds)
        assert abs((loaded.started_at - run.started_at).total_seconds()) < 1
        assert abs((loaded.updated_at - run.updated_at).total_seconds()) < 1
        assert loaded.completed_at is None
    finally:
        _delete_runs([run.run_id])


@pytest.mark.skipif(not _PG, reason="needs real Postgres")
def test_save_run_updates_on_conflict(store):
    """Second save_run with the same run_id updates status/context/outputs."""
    from dazzle.core.process.adapter import ProcessStatus

    run = _make_run(status=ProcessStatus.PENDING, outputs=None)
    store.save_run(run)

    try:
        run.status = ProcessStatus.COMPLETED
        run.outputs = {"final": "done"}
        run.context = {"step_a": {"done": True}}
        store.save_run(run)

        loaded = store.get_run(run.run_id)
        assert loaded is not None
        assert loaded.status == ProcessStatus.COMPLETED
        assert loaded.outputs == {"final": "done"}
        assert loaded.context == {"step_a": {"done": True}}
    finally:
        _delete_runs([run.run_id])


# ── list_runs filtering ───────────────────────────────────────────────────────


@pytest.mark.skipif(not _PG, reason="needs real Postgres")
def test_list_runs_filter_by_status(store):
    """list_runs(status=PENDING) returns only pending runs."""
    from dazzle.core.process.adapter import ProcessStatus

    pending = _make_run(status=ProcessStatus.PENDING)
    completed = _make_run(status=ProcessStatus.COMPLETED)
    store.save_run(pending)
    store.save_run(completed)

    try:
        results = store.list_runs(status=ProcessStatus.PENDING)
        result_ids = {r.run_id for r in results}
        assert pending.run_id in result_ids
        # The completed run should NOT appear in the pending filter.
        assert completed.run_id not in result_ids
    finally:
        _delete_runs([pending.run_id, completed.run_id])


@pytest.mark.skipif(not _PG, reason="needs real Postgres")
def test_list_runs_filter_by_process_name(store):
    """list_runs(process_name=X) returns only runs for that process."""

    run_a = _make_run(process_name="proc_alpha")
    run_b = _make_run(process_name="proc_beta")
    store.save_run(run_a)
    store.save_run(run_b)

    try:
        results = store.list_runs(process_name="proc_alpha")
        result_ids = {r.run_id for r in results}
        assert run_a.run_id in result_ids
        assert run_b.run_id not in result_ids
    finally:
        _delete_runs([run_a.run_id, run_b.run_id])


@pytest.mark.skipif(not _PG, reason="needs real Postgres")
def test_list_runs_limit_and_offset(store):
    """limit / offset are honoured."""
    from dazzle.core.process.adapter import ProcessStatus

    pname = f"proc_paginate_{uuid.uuid4().hex[:8]}"
    runs = [_make_run(process_name=pname, status=ProcessStatus.PENDING) for _ in range(5)]
    for r in runs:
        store.save_run(r)

    try:
        page1 = store.list_runs(process_name=pname, limit=2, offset=0)
        page2 = store.list_runs(process_name=pname, limit=2, offset=2)
        assert len(page1) == 2
        assert len(page2) == 2
        # Pages must be disjoint.
        assert not {r.run_id for r in page1} & {r.run_id for r in page2}
    finally:
        _delete_runs([r.run_id for r in runs])


# ── list_runs_by_version / count_active ──────────────────────────────────────


@pytest.mark.skipif(not _PG, reason="needs real Postgres")
def test_list_runs_by_version(store):
    from dazzle.core.process.adapter import ProcessStatus

    ver = f"v-{uuid.uuid4().hex[:6]}"
    run_v = _make_run(dsl_version=ver, status=ProcessStatus.PENDING)
    run_other = _make_run(dsl_version="other", status=ProcessStatus.PENDING)
    store.save_run(run_v)
    store.save_run(run_other)

    try:
        results = store.list_runs_by_version(ver)
        ids = {r.run_id for r in results}
        assert run_v.run_id in ids
        assert run_other.run_id not in ids
    finally:
        _delete_runs([run_v.run_id, run_other.run_id])


@pytest.mark.skipif(not _PG, reason="needs real Postgres")
def test_count_active_runs_by_version(store):
    from dazzle.core.process.adapter import ProcessStatus

    ver = f"v-{uuid.uuid4().hex[:6]}"
    run_active = _make_run(dsl_version=ver, status=ProcessStatus.PENDING)
    run_done = _make_run(dsl_version=ver, status=ProcessStatus.COMPLETED)
    store.save_run(run_active)
    store.save_run(run_done)

    try:
        count = store.count_active_runs_by_version(ver)
        # At least 1 active run (there may be others if tests run concurrently).
        assert count >= 1
        # The completed run should not bump the count beyond 1 for this version.
        # Verify by getting all active and checking completed is not there.
        active_runs = store.list_runs_by_version(ver, status=ProcessStatus.PENDING)
        active_ids = {r.run_id for r in active_runs}
        assert run_active.run_id in active_ids
        assert run_done.run_id not in active_ids
    finally:
        _delete_runs([run_active.run_id, run_done.run_id])


# ── save_task / get_task round-trip ──────────────────────────────────────────


@pytest.mark.skipif(not _PG, reason="needs real Postgres")
def test_save_task_get_task_round_trips_all_fields(store):
    """All ProcessTask fields survive a save → get cycle."""
    from dazzle.core.process.adapter import ProcessStatus, TaskStatus

    run = _make_run(status=ProcessStatus.WAITING)
    store.save_run(run)

    task = _make_task(
        run_id=run.run_id,
        outcome_data={"notes": "looks good", "score": 9},
    )
    store.save_task(task)

    try:
        loaded = store.get_task(task.task_id)
        assert loaded is not None
        assert loaded.task_id == task.task_id
        assert loaded.run_id == task.run_id
        assert loaded.step_name == task.step_name
        assert loaded.surface_name == task.surface_name
        assert loaded.entity_name == task.entity_name
        assert loaded.entity_id == task.entity_id
        assert loaded.assignee_id == task.assignee_id
        assert loaded.assignee_role == task.assignee_role
        assert loaded.status == TaskStatus.PENDING
        assert loaded.outcome_data == {"notes": "looks good", "score": 9}
        assert abs((loaded.due_at - task.due_at).total_seconds()) < 1
    finally:
        _delete_tasks([task.task_id])
        _delete_runs([run.run_id])


@pytest.mark.skipif(not _PG, reason="needs real Postgres")
def test_list_tasks_filter_by_run_id(store):
    from dazzle.core.process.adapter import ProcessStatus

    run = _make_run(status=ProcessStatus.WAITING)
    store.save_run(run)

    task1 = _make_task(run_id=run.run_id)
    task2 = _make_task(run_id=run.run_id)
    other_run = _make_run(status=ProcessStatus.WAITING)
    store.save_run(other_run)
    task_other = _make_task(run_id=other_run.run_id)
    for t in [task1, task2, task_other]:
        store.save_task(t)

    try:
        tasks = store.list_tasks(run_id=run.run_id)
        ids = {t.task_id for t in tasks}
        assert task1.task_id in ids
        assert task2.task_id in ids
        assert task_other.task_id not in ids
    finally:
        _delete_tasks([task1.task_id, task2.task_id, task_other.task_id])
        _delete_runs([run.run_id, other_run.run_id])


# ── spec / schedule / entity_meta (in-memory) ────────────────────────────────


@pytest.mark.skipif(not _PG, reason="needs real Postgres")
def test_register_get_process_spec(store):
    from unittest.mock import MagicMock

    from dazzle.core.ir.process import ProcessSpec

    spec = MagicMock(spec=ProcessSpec)
    spec.name = f"proc_{uuid.uuid4().hex[:6]}"
    spec.steps = []
    store.register_process(spec)
    got = store.get_process_spec(spec.name)
    assert got is not None
    assert got["name"] == spec.name


@pytest.mark.skipif(not _PG, reason="needs real Postgres")
def test_register_get_schedule_spec(store):
    from unittest.mock import MagicMock

    from dazzle.core.ir.process import ScheduleSpec

    spec = MagicMock(spec=ScheduleSpec)
    spec.name = f"sched_{uuid.uuid4().hex[:6]}"
    spec.process_name = "my_proc"
    spec.cron = "0 * * * *"
    spec.interval_seconds = None
    store.register_schedule(spec)

    got = store.get_schedule_spec(spec.name)
    assert got is not None
    assert got["name"] == spec.name

    all_specs = store.list_schedule_specs()
    names = [s["name"] for s in all_specs]
    assert spec.name in names


@pytest.mark.skipif(not _PG, reason="needs real Postgres")
def test_set_schedule_last_run(store):
    name = f"sched_{uuid.uuid4().hex[:6]}"
    ts = datetime.now(UTC)
    store.set_schedule_last_run(name, ts)
    # Verify stored (internal dict).
    assert store._schedule_last_run.get(name) == ts


@pytest.mark.skipif(not _PG, reason="needs real Postgres")
def test_entity_meta_round_trip(store):
    meta = {"pk": "id", "fields": ["name", "status"], "slug": "order"}
    store.save_entity_meta("Order", meta)
    got = store.get_entity_meta("Order")
    assert got == meta
    assert store.get_entity_meta("NonExistent") is None


# ── claim_due_runs — exclusivity ──────────────────────────────────────────────


@pytest.mark.skipif(not _PG, reason="needs real Postgres")
def test_claim_due_runs_returns_pending_run(store):
    """claim_due_runs picks up a pending run and returns it as a ProcessRun."""
    from dazzle.core.process.adapter import ProcessStatus

    run = _make_run(status=ProcessStatus.PENDING)
    store.save_run(run)

    try:
        claimed = store.claim_due_runs(worker="worker-A", lease_seconds=30, batch=5)
        claimed_ids = {r.run_id for r in claimed}
        assert run.run_id in claimed_ids
    finally:
        _delete_runs([run.run_id])


@pytest.mark.skipif(not _PG, reason="needs real Postgres")
def test_claim_due_runs_exclusivity(store):
    """A run claimed by worker-A is NOT returned to worker-B in a second claim."""
    from dazzle.core.process.adapter import ProcessStatus

    run = _make_run(status=ProcessStatus.PENDING)
    store.save_run(run)

    try:
        # First claim — worker A picks it up.
        claimed_a = store.claim_due_runs(worker="worker-A", lease_seconds=60, batch=10)
        claimed_a_ids = {r.run_id for r in claimed_a}
        assert run.run_id in claimed_a_ids

        # Second claim — worker B must NOT receive the same run.
        claimed_b = store.claim_due_runs(worker="worker-B", lease_seconds=60, batch=10)
        claimed_b_ids = {r.run_id for r in claimed_b}
        assert run.run_id not in claimed_b_ids
    finally:
        _delete_runs([run.run_id])


@pytest.mark.skipif(not _PG, reason="needs real Postgres")
def test_claim_due_runs_expired_lease_is_reclaimed(store):
    """A run whose lease has expired is reclaimable by a second worker."""
    from dazzle.core.process.adapter import ProcessStatus

    run = _make_run(status=ProcessStatus.PENDING)
    store.save_run(run)

    try:
        # Claim with a 1-second lease.
        claimed_a = store.claim_due_runs(worker="worker-A", lease_seconds=1, batch=10)
        assert run.run_id in {r.run_id for r in claimed_a}

        # Wait for the lease to expire.
        time.sleep(1.5)

        # Worker B should now be able to reclaim the same run.
        claimed_b = store.claim_due_runs(worker="worker-B", lease_seconds=30, batch=10)
        assert run.run_id in {r.run_id for r in claimed_b}
    finally:
        _delete_runs([run.run_id])


# ── mark_run_done / mark_run_retry ───────────────────────────────────────────


@pytest.mark.skipif(not _PG, reason="needs real Postgres")
def test_mark_run_done_sets_completed(store):
    """mark_run_done transitions the run to completed and it's no longer claimable."""
    from dazzle.core.process.adapter import ProcessStatus

    run = _make_run(status=ProcessStatus.PENDING)
    store.save_run(run)

    try:
        store.claim_due_runs(worker="worker-X", lease_seconds=60, batch=5)
        store.mark_run_done(run.run_id)

        loaded = store.get_run(run.run_id)
        assert loaded is not None
        assert loaded.status == ProcessStatus.COMPLETED

        # Should not be claimable again.
        claimed = store.claim_due_runs(worker="worker-Y", lease_seconds=60, batch=10)
        assert run.run_id not in {r.run_id for r in claimed}
    finally:
        _delete_runs([run.run_id])


@pytest.mark.skipif(not _PG, reason="needs real Postgres")
def test_mark_run_retry_persists_error(store):
    """mark_run_retry writes the error and returns retry/dead."""
    from dazzle.core.process.adapter import ProcessStatus

    run = _make_run(status=ProcessStatus.PENDING)
    store.save_run(run)

    try:
        store.claim_due_runs(worker="worker-X", lease_seconds=60, batch=5)
        outcome = store.mark_run_retry(run.run_id, "something went wrong")
        assert outcome in ("retry", "dead")

        loaded = store.get_run(run.run_id)
        assert loaded is not None
        assert loaded.error == "something went wrong"
    finally:
        _delete_runs([run.run_id])


# ── crash-loop dead-letter via shared primitive ───────────────────────────────


@pytest.mark.skipif(not _PG, reason="needs real Postgres")
def test_claim_due_runs_crash_loop_dead_letters_via_shared_primitive(store):
    """A process_run that crash-loops past max_attempts ends status='dead'.

    Proves that process_runs gets the full dead-letter sweep from the shared
    claim_due_work primitive (not a hand-rolled inline variant that might omit it).
    Simulates repeated crash: claim with a short lease, let it expire without
    calling mark_run_done/mark_run_retry.  After max_attempts expiries the
    next claim sweep must set status='dead'.
    """
    from dazzle.core.process.adapter import ProcessStatus

    max_attempts = 2
    run = _make_run(status=ProcessStatus.PENDING)
    store.save_run(run)

    try:
        for crash_n in range(1, max_attempts + 1):
            claimed = store.claim_due_runs(
                worker="crasher",
                lease_seconds=1,
                batch=5,
                max_attempts=max_attempts,
            )
            claimed_ids = {r.run_id for r in claimed}
            assert run.run_id in claimed_ids, (
                f"Crash {crash_n}: expected run {run.run_id} to be claimable, got {claimed_ids}"
            )
            # Simulate crash — do NOT call mark_run_done or mark_run_retry.
            time.sleep(1.2)  # let the 1-second lease expire

        # The dead-letter sweep fires on the next claim call.
        after = store.claim_due_runs(
            worker="sweeper",
            lease_seconds=30,
            batch=5,
            max_attempts=max_attempts,
        )
        assert run.run_id not in {r.run_id for r in after}, (
            f"Over-limit run must not be claimed after {max_attempts} crashes"
        )

        # Verify the row reached status='dead' in the DB (shared sweep, not inline).
        import psycopg

        with psycopg.connect(_PG) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT status, attempts FROM process_runs WHERE run_id=%s",
                (run.run_id,),
            )
            row = cur.fetchone()
        assert row is not None
        status, attempts = row
        assert status == "dead", (
            f"Expected status='dead' after {max_attempts} crash-loops on process_runs, "
            f"got {status!r} (attempts={attempts})"
        )
        assert attempts >= max_attempts, f"Expected attempts >= {max_attempts}, got {attempts}"
    finally:
        _delete_runs([run.run_id])


# ── helpers ───────────────────────────────────────────────────────────────────


def _delete_runs(run_ids: list[str]) -> None:
    """Remove test rows from process_runs (teardown helper)."""
    if not run_ids or not _PG:
        return
    import psycopg

    with psycopg.connect(_PG) as conn, conn.cursor() as cur:
        cur.execute(
            "DELETE FROM process_runs WHERE run_id = ANY(%s)",
            (run_ids,),
        )
        conn.commit()


def _delete_tasks(task_ids: list[str]) -> None:
    """Remove test rows from process_tasks (teardown helper)."""
    if not task_ids or not _PG:
        return
    import psycopg

    with psycopg.connect(_PG) as conn, conn.cursor() as cur:
        cur.execute(
            "DELETE FROM process_tasks WHERE task_id = ANY(%s)",
            (task_ids,),
        )
        conn.commit()
