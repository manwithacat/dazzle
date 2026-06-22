"""Framework process-runtime tables — boot-time DDL (Task 2, Phase 1).

Creates ``process_runs`` and ``process_tasks`` using ``CREATE TABLE IF NOT
EXISTS`` (idempotent) wrapped in ``pg_advisory_xact_lock`` so concurrent
boot workers (e.g. multiple uvicorn processes) don't race on the catalog.

Table naming — no collision with #1454 app entity
-------------------------------------------------
The #1454 ``ProcessRun`` IR entity is injected into the APP schema by the
linker when an ``llm_intent`` step is present.  SQLAlchemy materialises it
as ``sa.Table(entity.name, metadata, ...)`` — i.e. table name ``"ProcessRun"``
(mixed-case, singular, un-prefixed).

The framework runtime tables are:
  * ``process_runs``   — plural, snake_case, no camel, no ``_dazzle_`` prefix needed
  * ``process_tasks``  — ditto

These do NOT collide with the #1454 app-facing ``ProcessRun`` IR entity: that
entity tables as ``sa.Table(entity.name)`` = the quoted, case-sensitive
identifier ``"ProcessRun"``, whereas these framework tables are the lowercase
plural ``process_runs`` / ``process_tasks``. ``"ProcessRun" != process_runs`` in
Postgres, so no ``_dazzle_`` prefix is required.

Advisory lock
-------------
Lock key ``0x70726F63`` (= ``"proc"`` in hex, 1886285155 decimal) is reserved
for this DDL.  It does not overlap with ``AUTH_DDL_LOCK_KEY = 0x647A646C``
(auth store) or any other Dazzle framework lock.

Queue columns
-------------
Included via ``dazzle.core.coordination.claim.queue_columns_ddl(table)``  so
``claim_due_work`` always sees the exact column set it expects (single source
of truth).

Dual-write
----------
This boot path (``ensure_process_tables``) is the dev path.  The companion
Alembic migration (``src/dazzle/http/alembic/versions/0019_process_runtime_tables.py``)
mirrors this DDL for production deploys, following the authstore-parity rule
(ADR-0017).
"""

from __future__ import annotations

import logging

from dazzle.core.coordination.claim import queue_columns_ddl

logger = logging.getLogger(__name__)

# Advisory lock key for process DDL boot concurrency.
# "proc" = 0x70726F63 = 1886285155 — does not collide with auth (0x647A646C).
_PROCESS_DDL_LOCK_KEY = 0x70726F63


def ensure_process_tables(conn) -> None:  # conn: psycopg.Connection
    """Create ``process_runs`` and ``process_tasks`` if they don't exist.

    Idempotent — safe to call on every boot worker simultaneously.  The
    ``pg_advisory_xact_lock`` serialises concurrent callers at the Postgres
    level; ``IF NOT EXISTS`` makes each statement a no-op if already present.

    The connection is committed inside this function (same pattern as
    ``AuthStore._init_db``).
    """
    # queue_columns_ddl(table) returns the shared column fragment.
    # The ``table`` arg is passed for API symmetry; the index is created
    # separately below (outside the column fragment, matching claim.py's
    # in-code comment).
    runs_queue_cols = queue_columns_ddl("process_runs")
    tasks_queue_cols = queue_columns_ddl("process_tasks")

    with conn.cursor() as cur:
        # Serialise concurrent boot workers.
        cur.execute("SELECT pg_advisory_xact_lock(%s)", (_PROCESS_DDL_LOCK_KEY,))

        # ── process_runs ──────────────────────────────────────────────────
        # Columns: ProcessRun fields (adapter.py:51-69) + queue columns.
        # Dict fields (inputs, context, outputs) → jsonb.
        # Timestamps → timestamptz.
        # NOTE: ``status`` comes from queue_columns_ddl (the ProcessRun status
        # IS the queue status — "pending"/"claimed"/"done"/"dead" map to
        # ProcessStatus values).  Do not declare it again here.
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS process_runs (
                run_id              text        NOT NULL PRIMARY KEY,
                process_name        text        NOT NULL,
                process_version     text        NOT NULL DEFAULT 'v1',
                dsl_version         text        NOT NULL DEFAULT '0.1',
                current_step        text,
                inputs              jsonb       NOT NULL DEFAULT '{{}}'::jsonb,
                context             jsonb       NOT NULL DEFAULT '{{}}'::jsonb,
                outputs             jsonb,
                error               text,
                idempotency_key     text,
                started_at          timestamptz NOT NULL DEFAULT now(),
                updated_at          timestamptz NOT NULL DEFAULT now(),
                completed_at        timestamptz,
                {runs_queue_cols}
            )
        """)

        # Partial index: claim_due_work only scans pending/claimed rows.
        cur.execute("""
            CREATE INDEX IF NOT EXISTS ix_process_runs_due
            ON process_runs (deliver_at)
            WHERE status IN ('pending', 'claimed')
        """)

        # ── process_tasks ─────────────────────────────────────────────────
        # Columns: ProcessTask fields (adapter.py:72-91) + queue columns.
        # ``due_at`` is the task deadline; ``deliver_at`` (from the queue
        # column set) is used by claim_due_work for timeout/escalation.
        # NOTE: ``status`` comes from queue_columns_ddl — do not declare twice.
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS process_tasks (
                task_id             text        NOT NULL PRIMARY KEY,
                run_id              text        NOT NULL
                    REFERENCES process_runs (run_id) ON DELETE CASCADE,
                step_name           text        NOT NULL,
                surface_name        text        NOT NULL,
                entity_name         text        NOT NULL,
                entity_id           text        NOT NULL,
                assignee_id         text,
                assignee_role       text,
                outcome             text,
                outcome_data        jsonb,
                due_at              timestamptz NOT NULL,
                escalated_at        timestamptz,
                completed_at        timestamptz,
                created_at          timestamptz NOT NULL DEFAULT now(),
                {tasks_queue_cols}
            )
        """)

        # Partial index for task claim_due_work (escalation/timeout dispatch).
        cur.execute("""
            CREATE INDEX IF NOT EXISTS ix_process_tasks_due
            ON process_tasks (deliver_at)
            WHERE status IN ('pending', 'claimed')
        """)

    conn.commit()
    logger.debug("process_runs + process_tasks ensured")
