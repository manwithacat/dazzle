"""Sync Postgres drop-in for ``ProcessStateStore`` (Phase-1 Task 3).

``PgProcessStateStore`` exposes **exactly** the same public methods as
``ProcessStateStore`` (the Redis store in ``process_state.py``), backed by the
``process_runs`` / ``process_tasks`` framework tables created by
``ensure_process_tables`` (Task 2).

Design choices
--------------
* **In-memory dicts** for process specs, schedule specs, and entity metadata —
  the adapter re-registers on every boot (same pattern as ``EventBus``), so no
  third table is needed for Phase 1.
* **Sync** ``psycopg.connect`` per method — mirrors the Redis client's sync
  surface.  The async ``PostgresProcessAdapter`` (Task 5) wraps calls in
  ``asyncio.to_thread``.
* JSON-serialised via ``model_dump(mode="json")`` + ``psycopg.types.json.Jsonb``
  on write; ``ProcessRun(**row)`` / ``ProcessTask(**row)`` rehydration on read.
* ``claim_due_runs`` / ``mark_run_done`` / ``mark_run_retry`` are built on the
  shared ``claim_due_work`` / ``complete_work`` / ``fail_work`` primitives from
  Task 1.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from dazzle.core.coordination.claim import queue_columns_ddl
from dazzle.core.ir.process import ProcessSpec, ScheduleSpec
from dazzle.core.process.adapter import (
    ProcessRun,
    ProcessStatus,
    ProcessTask,
    TaskStatus,
)

# ── process_runs claim SQL ─────────────────────────────────────────────────────
# ``claim_due_work`` uses column ``id`` as the PK, but ``process_runs`` has
# ``run_id``.  We inline a table-specific variant here using the same
# SKIP LOCKED + lease pattern (spec §4) but keyed on ``run_id``.

_DEAD_SWEEP_RUNS = """
UPDATE process_runs
SET status = 'dead'
WHERE status = 'claimed'
  AND lease_expires_at <= now()
  AND attempts >= %(max)s;
"""

_CLAIM_RUNS = """
WITH due AS (
    SELECT run_id FROM process_runs
    WHERE (status = 'pending' AND deliver_at <= now())
       OR (status = 'claimed' AND lease_expires_at <= now() AND attempts < %(max)s)
    ORDER BY deliver_at, run_id
    FOR UPDATE SKIP LOCKED
    LIMIT %(batch)s
)
UPDATE process_runs t
SET status = 'claimed',
    claimed_by        = %(worker)s,
    claimed_at        = now(),
    lease_expires_at  = now() + (%(lease)s || ' seconds')::interval,
    attempts          = t.attempts + 1
FROM due
WHERE t.run_id = due.run_id
RETURNING t.run_id;
"""


def _claim_due_runs_sql(
    conn,
    *,
    worker: str,
    lease_seconds: int,
    batch: int = 1,
    max_attempts: int = 5,
) -> list[str]:
    """Claim up to *batch* due process_runs rows; return their run_ids."""
    params = {"batch": batch, "worker": worker, "lease": lease_seconds, "max": max_attempts}
    with conn.cursor() as cur:
        cur.execute(_DEAD_SWEEP_RUNS, params)
        cur.execute(_CLAIM_RUNS, params)
        rows = cur.fetchall()
    conn.commit()
    return [str(r[0]) for r in rows]


logger = logging.getLogger(__name__)

_ACTIVE_STATUSES = {
    ProcessStatus.PENDING,
    ProcessStatus.RUNNING,
    ProcessStatus.WAITING,
    ProcessStatus.SUSPENDED,
    ProcessStatus.DRAINING,
    ProcessStatus.COMPENSATING,
}

# ── helpers ───────────────────────────────────────────────────────────────────


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _serialize_step(step: Any) -> dict[str, Any]:
    """Serialise a ``ProcessStepSpec`` to a plain dict (mirrors Redis store)."""
    data: dict[str, Any] = {
        "name": step.name,
        "kind": step.kind.value if hasattr(step.kind, "value") else str(step.kind),
        "service": getattr(step, "service", None),
        "surface": getattr(step, "surface", None),
        "channel": getattr(step, "channel", None),
        "timeout_seconds": getattr(step, "timeout_seconds", None),
    }
    retry_cfg = getattr(step, "retry", None)
    if retry_cfg is not None:
        backoff_attr = getattr(retry_cfg, "backoff", None)
        if backoff_attr is None:
            backoff_str = "exponential"
        elif hasattr(backoff_attr, "value"):
            backoff_str = backoff_attr.value
        else:
            backoff_str = str(backoff_attr)
        data["retry"] = {
            "max_attempts": getattr(retry_cfg, "max_attempts", 3),
            "initial_interval_seconds": getattr(retry_cfg, "initial_interval_seconds", 1),
            "backoff": backoff_str,
            "backoff_coefficient": getattr(retry_cfg, "backoff_coefficient", 2.0),
            "max_interval_seconds": getattr(retry_cfg, "max_interval_seconds", 60),
        }
    if getattr(step, "query_entity", None):
        data["query_entity"] = step.query_entity
        data["query_filter"] = getattr(step, "query_filter", None)
        data["query_limit"] = getattr(step, "query_limit", 1000)
    if getattr(step, "foreach_source", None):
        data["foreach_source"] = step.foreach_source
        data["foreach_steps"] = [_serialize_step(s) for s in getattr(step, "foreach_steps", [])]
    return data


def _row_to_run(row: dict[str, Any]) -> ProcessRun:
    """Rehydrate a ``ProcessRun`` from a psycopg row dict."""
    # psycopg returns timestamptz as timezone-aware datetimes already.
    # status in the DB is the ProcessStatus string value OR an internal queue
    # value ('claimed'/'done'/'dead') set by the claim primitive.
    status_val = row.get("status", "pending")
    # Map internal queue states → ProcessStatus values.
    _queue_map = {"claimed": "running", "done": "completed", "dead": "failed"}
    status_val = _queue_map.get(status_val, status_val)

    def _dt(v: Any) -> datetime | None:
        if v is None:
            return None
        if isinstance(v, datetime):
            return v
        return datetime.fromisoformat(str(v))

    return ProcessRun(
        run_id=row["run_id"],
        process_name=row["process_name"],
        process_version=row.get("process_version", "v1"),
        dsl_version=row.get("dsl_version", "0.1"),
        status=ProcessStatus(status_val),
        current_step=row.get("current_step"),
        inputs=row.get("inputs") or {},
        context=row.get("context") or {},
        outputs=row.get("outputs"),
        error=row.get("error"),
        idempotency_key=row.get("idempotency_key"),
        started_at=_dt(row["started_at"]) or _utcnow(),
        updated_at=_dt(row["updated_at"]) or _utcnow(),
        completed_at=_dt(row.get("completed_at")),
    )


def _row_to_task(row: dict[str, Any]) -> ProcessTask:
    """Rehydrate a ``ProcessTask`` from a psycopg row dict."""
    status_val = row.get("status", "pending")
    _queue_map = {"done": "completed", "dead": "cancelled"}
    status_val = _queue_map.get(status_val, status_val)

    def _dt(v: Any) -> datetime | None:
        if v is None:
            return None
        if isinstance(v, datetime):
            return v
        return datetime.fromisoformat(str(v))

    return ProcessTask(
        task_id=row["task_id"],
        run_id=row["run_id"],
        step_name=row["step_name"],
        surface_name=row.get("surface_name", ""),
        entity_name=row.get("entity_name", ""),
        entity_id=row.get("entity_id", ""),
        assignee_id=row.get("assignee_id"),
        assignee_role=row.get("assignee_role"),
        status=TaskStatus(status_val),
        outcome=row.get("outcome"),
        outcome_data=row.get("outcome_data"),
        due_at=_dt(row["due_at"]) or _utcnow(),
        escalated_at=_dt(row.get("escalated_at")),
        completed_at=_dt(row.get("completed_at")),
        created_at=_dt(row.get("created_at")) or _utcnow(),
    )


# ── store ─────────────────────────────────────────────────────────────────────


class PgProcessStateStore:
    """Sync Postgres drop-in for ``ProcessStateStore``.

    Constructor::

        store = PgProcessStateStore(dsn="postgresql://localhost:5432/mydb")

    All public methods mirror ``ProcessStateStore`` exactly.  The three extra
    methods (``claim_due_runs``, ``mark_run_done``, ``mark_run_retry``) are
    built on the Task-1 lease primitive and are consumed by Task-5's async
    adapter.

    In-memory storage
    -----------------
    Process specs, schedule specs, schedule last-run timestamps, and entity
    metadata are held in in-memory dicts.  The adapter re-registers on every
    boot (same pattern as ``EventBus``), so no third table is needed for
    Phase 1.
    """

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        # In-memory stores (re-populated on adapter boot, as EventBus does).
        self._process_specs: dict[str, dict[str, Any]] = {}
        self._schedule_specs: dict[str, dict[str, Any]] = {}
        self._schedule_last_run: dict[str, datetime] = {}
        self._entity_meta: dict[str, dict[str, Any]] = {}
        self._tables_ensured = False

    def _ensure(self) -> None:
        """Create ``process_runs`` / ``process_tasks`` on first use.

        Inlines the same DDL as ``ensure_process_tables`` (Task 2 /
        ``dazzle.http.runtime.process_schema``) so that ``dazzle.core`` never
        imports ``dazzle.http`` — the import-linter layer contract forbids that
        edge.  Both paths share ``queue_columns_ddl`` (``dazzle.core.coordination``
        — a core→core import, allowed) as the single source of truth for the
        queue column set.

        The http-layer boot path (``ensure_process_tables``) and this core-layer
        path are intentional dual-write: each is idempotent (``IF NOT EXISTS``),
        so whichever runs first wins and the other is a no-op.
        """
        if self._tables_ensured:
            return
        runs_q = queue_columns_ddl("process_runs")
        tasks_q = queue_columns_ddl("process_tasks")
        _PROCESS_DDL_LOCK_KEY = 0x70726F63  # "proc" — same key as http path
        with psycopg.connect(self._dsn) as conn, conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(%s)", (_PROCESS_DDL_LOCK_KEY,))
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS process_runs (
                    run_id          text        NOT NULL PRIMARY KEY,
                    process_name    text        NOT NULL,
                    process_version text        NOT NULL DEFAULT 'v1',
                    dsl_version     text        NOT NULL DEFAULT '0.1',
                    current_step    text,
                    inputs          jsonb       NOT NULL DEFAULT '{{}}'::jsonb,
                    context         jsonb       NOT NULL DEFAULT '{{}}'::jsonb,
                    outputs         jsonb,
                    error           text,
                    idempotency_key text,
                    started_at      timestamptz NOT NULL DEFAULT now(),
                    updated_at      timestamptz NOT NULL DEFAULT now(),
                    completed_at    timestamptz,
                    {runs_q}
                )
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS ix_process_runs_due
                ON process_runs (deliver_at)
                WHERE status IN ('pending', 'claimed')
            """)
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS process_tasks (
                    task_id         text        NOT NULL PRIMARY KEY,
                    run_id          text        NOT NULL
                        REFERENCES process_runs (run_id) ON DELETE CASCADE,
                    step_name       text        NOT NULL,
                    surface_name    text        NOT NULL,
                    entity_name     text        NOT NULL,
                    entity_id       text        NOT NULL,
                    assignee_id     text,
                    assignee_role   text,
                    outcome         text,
                    outcome_data    jsonb,
                    due_at          timestamptz NOT NULL,
                    escalated_at    timestamptz,
                    completed_at    timestamptz,
                    created_at      timestamptz NOT NULL DEFAULT now(),
                    {tasks_q}
                )
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS ix_process_tasks_due
                ON process_tasks (deliver_at)
                WHERE status IN ('pending', 'claimed')
            """)
            conn.commit()
        self._tables_ensured = True

    def _connect(self) -> psycopg.Connection:
        """Open a new sync psycopg connection."""
        self._ensure()
        return psycopg.connect(self._dsn)

    # ── Process Specifications (in-memory) ───────────────────────────────────

    def register_process(self, spec: ProcessSpec) -> None:
        """Register a process specification (in-memory)."""
        data = {
            "name": spec.name,
            "version": getattr(spec, "version", "1.0"),
            "steps": [_serialize_step(s) for s in spec.steps],
        }
        self._process_specs[spec.name] = data
        logger.debug("Registered process spec: %s", spec.name)

    def get_process_spec(self, name: str) -> dict[str, Any] | None:
        """Get a process specification by name."""
        return self._process_specs.get(name)

    # ── Schedule Specifications (in-memory) ──────────────────────────────────

    def register_schedule(self, spec: ScheduleSpec) -> None:
        """Register a schedule specification (in-memory)."""
        data = {
            "name": spec.name,
            "process_name": getattr(spec, "process_name", spec.name),
            "cron": getattr(spec, "cron", None),
            "interval_seconds": getattr(spec, "interval_seconds", None),
        }
        self._schedule_specs[spec.name] = data
        logger.debug("Registered schedule spec: %s", spec.name)

    def get_schedule_spec(self, name: str) -> dict[str, Any] | None:
        """Get a schedule specification by name."""
        return self._schedule_specs.get(name)

    def list_schedule_specs(self) -> list[dict[str, Any]]:
        """List all registered schedule specs."""
        return list(self._schedule_specs.values())

    def set_schedule_last_run(self, name: str, timestamp: datetime) -> None:
        """Record the last run time for a schedule (in-memory)."""
        self._schedule_last_run[name] = timestamp

    # ── Process Runs ─────────────────────────────────────────────────────────

    def save_run(self, run: ProcessRun) -> None:
        """Upsert a process run to ``process_runs``."""
        d = run.model_dump(mode="json")
        # Map ProcessStatus values to the queue status column.
        # The queue col is 'status' — we store the ProcessStatus string directly.
        # claim_due_work matches on 'pending'/'claimed'; mark_run_done sets 'done'.
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO process_runs
                    (run_id, process_name, process_version, dsl_version, status,
                     current_step, inputs, context, outputs, error, idempotency_key,
                     started_at, updated_at, completed_at, deliver_at)
                VALUES
                    (%(run_id)s, %(process_name)s, %(process_version)s, %(dsl_version)s,
                     %(status)s, %(current_step)s, %(inputs)s, %(context)s, %(outputs)s,
                     %(error)s, %(idempotency_key)s, %(started_at)s, %(updated_at)s,
                     %(completed_at)s, now())
                ON CONFLICT (run_id) DO UPDATE SET
                    status        = EXCLUDED.status,
                    current_step  = EXCLUDED.current_step,
                    context       = EXCLUDED.context,
                    outputs       = EXCLUDED.outputs,
                    error         = EXCLUDED.error,
                    updated_at    = EXCLUDED.updated_at,
                    completed_at  = EXCLUDED.completed_at
                """,
                {
                    **d,
                    "inputs": Jsonb(d["inputs"] or {}),
                    "context": Jsonb(d["context"] or {}),
                    "outputs": Jsonb(d["outputs"]) if d["outputs"] is not None else None,
                },
            )
            conn.commit()
        logger.debug("Saved run %s status=%s", run.run_id, run.status)

    def get_run(self, run_id: str) -> ProcessRun | None:
        """Load a process run by ID."""
        with self._connect() as conn, conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
            cur.execute(
                "SELECT * FROM process_runs WHERE run_id = %s",
                (run_id,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return _row_to_run(dict(row))

    def list_runs(
        self,
        process_name: str | None = None,
        status: ProcessStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ProcessRun]:
        """List process runs with optional process_name / status filters."""
        clauses: list[str] = []
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if process_name:
            clauses.append("process_name = %(process_name)s")
            params["process_name"] = process_name
        if status:
            clauses.append("status = %(status)s")
            params["status"] = status.value
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = f"""
            SELECT * FROM process_runs
            {where}
            ORDER BY started_at DESC
            LIMIT %(limit)s OFFSET %(offset)s
        """
        with self._connect() as conn, conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        return [_row_to_run(dict(r)) for r in rows]

    def list_runs_by_version(
        self,
        dsl_version: str,
        status: ProcessStatus | None = None,
        limit: int = 100,
    ) -> list[ProcessRun]:
        """List runs for a specific DSL version."""
        clauses = ["dsl_version = %(dsl_version)s"]
        params: dict[str, Any] = {"dsl_version": dsl_version, "limit": limit}
        if status:
            clauses.append("status = %(status)s")
            params["status"] = status.value
        sql = f"""
            SELECT * FROM process_runs
            WHERE {" AND ".join(clauses)}
            ORDER BY started_at DESC
            LIMIT %(limit)s
        """
        with self._connect() as conn, conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        return [_row_to_run(dict(r)) for r in rows]

    def count_active_runs_by_version(self, dsl_version: str) -> int:
        """Count active (non-terminal) runs for a DSL version."""
        active_values = tuple(s.value for s in _ACTIVE_STATUSES)
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM process_runs WHERE dsl_version = %s AND status = ANY(%s)",
                (dsl_version, list(active_values)),
            )
            row = cur.fetchone()
        return int(row[0]) if row else 0

    # ── Human Tasks ──────────────────────────────────────────────────────────

    def save_task(self, task: ProcessTask) -> None:
        """Upsert a human task to ``process_tasks``."""
        d = task.model_dump(mode="json")
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO process_tasks
                    (task_id, run_id, step_name, surface_name, entity_name, entity_id,
                     assignee_id, assignee_role, status, outcome, outcome_data,
                     due_at, escalated_at, completed_at, created_at, deliver_at)
                VALUES
                    (%(task_id)s, %(run_id)s, %(step_name)s, %(surface_name)s,
                     %(entity_name)s, %(entity_id)s, %(assignee_id)s, %(assignee_role)s,
                     %(status)s, %(outcome)s, %(outcome_data)s,
                     %(due_at)s, %(escalated_at)s, %(completed_at)s, %(created_at)s, now())
                ON CONFLICT (task_id) DO UPDATE SET
                    status       = EXCLUDED.status,
                    assignee_id  = EXCLUDED.assignee_id,
                    outcome      = EXCLUDED.outcome,
                    outcome_data = EXCLUDED.outcome_data,
                    completed_at = EXCLUDED.completed_at,
                    escalated_at = EXCLUDED.escalated_at
                """,
                {
                    **d,
                    "outcome_data": Jsonb(d["outcome_data"]) if d.get("outcome_data") else None,
                },
            )
            conn.commit()
        logger.debug("Saved task %s status=%s", task.task_id, task.status)

    def get_task(self, task_id: str) -> ProcessTask | None:
        """Load a human task by ID."""
        with self._connect() as conn, conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
            cur.execute(
                "SELECT * FROM process_tasks WHERE task_id = %s",
                (task_id,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return _row_to_task(dict(row))

    def list_tasks(
        self,
        run_id: str | None = None,
        assignee_id: str | None = None,
        status: TaskStatus | None = None,
        limit: int = 100,
    ) -> list[ProcessTask]:
        """List human tasks with optional filters."""
        clauses: list[str] = []
        params: dict[str, Any] = {"limit": limit}
        if run_id:
            clauses.append("run_id = %(run_id)s")
            params["run_id"] = run_id
        if assignee_id:
            clauses.append("assignee_id = %(assignee_id)s")
            params["assignee_id"] = assignee_id
        if status:
            clauses.append("status = %(status)s")
            params["status"] = status.value
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = f"""
            SELECT * FROM process_tasks
            {where}
            ORDER BY created_at DESC
            LIMIT %(limit)s
        """
        with self._connect() as conn, conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        return [_row_to_task(dict(r)) for r in rows]

    # ── Entity Metadata (in-memory) ──────────────────────────────────────────

    def save_entity_meta(self, entity_name: str, meta: dict[str, Any]) -> None:
        """Store entity metadata (in-memory)."""
        self._entity_meta[entity_name] = meta

    def get_entity_meta(self, entity_name: str) -> dict[str, Any] | None:
        """Get entity metadata by name."""
        return self._entity_meta.get(entity_name)

    # ── Claim / Done / Retry (new — Task 1 primitive) ────────────────────────

    def claim_due_runs(
        self,
        worker: str,
        lease_seconds: int,
        batch: int = 1,
    ) -> list[ProcessRun]:
        """Claim up to *batch* due process runs and return them.

        Uses the Task-1 ``claim_due_work`` primitive (FOR UPDATE SKIP LOCKED)
        so concurrent workers never double-claim the same run.  The claimed run
        IDs are then loaded and returned as ``ProcessRun`` objects.

        The caller is responsible for calling ``mark_run_done`` /
        ``mark_run_retry`` once execution completes/fails.
        """
        with self._connect() as conn:
            run_ids = _claim_due_runs_sql(
                conn,
                worker=worker,
                lease_seconds=lease_seconds,
                batch=batch,
            )
        if not run_ids:
            return []
        runs = []
        for run_id in run_ids:
            run = self.get_run(run_id)
            if run is not None:
                runs.append(run)
        return runs

    def mark_run_done(self, run_id: str) -> None:
        """Mark a claimed run as successfully completed.

        Sets queue ``status='done'`` AND ``ProcessRun.status='completed'``
        so ``get_run`` / ``list_runs`` reflect the terminal state immediately.
        """
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE process_runs SET status='completed', completed_at=now() WHERE run_id=%s",
                (run_id,),
            )
            conn.commit()

    def mark_run_retry(self, run_id: str, error: str, max_attempts: int = 5) -> str:
        """Mark a claimed run as failed, scheduling a retry or dead-lettering.

        Returns ``"retry"`` or ``"dead"``.  Persists the error into the
        ``error`` column so ``get_run`` can surface it.
        """

        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT attempts FROM process_runs WHERE run_id=%s",
                (run_id,),
            )
            row = cur.fetchone()
            attempts = row[0] if row else 0
            if attempts >= max_attempts:
                cur.execute(
                    "UPDATE process_runs SET status='dead', error=%s WHERE run_id=%s",
                    (error, run_id),
                )
                outcome = "dead"
            else:
                cur.execute(
                    "UPDATE process_runs SET status='pending', error=%s, "
                    "deliver_at = now() + interval '30 seconds' WHERE run_id=%s",
                    (error, run_id),
                )
                outcome = "retry"
            conn.commit()
        return outcome
