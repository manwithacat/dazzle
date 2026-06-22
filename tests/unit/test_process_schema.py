"""Task 2 — real-PG proof: process_runs / process_tasks DDL is idempotent.

Mirrors the marker idiom in tests/integration/test_current_tenant_scope_pg.py.
Skips unless DATABASE_URL / TEST_DATABASE_URL is set.

TDD: this file is written first (RED), then process_schema.py is implemented (GREEN).
"""

from __future__ import annotations

import os

import pytest

pytestmark = [pytest.mark.postgres]

_PG_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")

# ── helper ────────────────────────────────────────────────────────────────────


def _column_names(conn, table: str) -> set[str]:
    """Return the column names for *table* from information_schema."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = %s",
            (table,),
        )
        return {row[0] for row in cur.fetchall()}


def _drop_tables(conn, *tables: str) -> None:
    """Tear-down helper — drop scratch tables unconditionally."""
    with conn.cursor() as cur:
        for t in tables:
            # nosemgrep: python.lang.security.audit.formatted-sql-query.formatted-sql-query
            cur.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
    conn.commit()


# ── tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.skipif(not _PG_URL, reason="no TEST_DATABASE_URL / DATABASE_URL — needs real Postgres")
def test_ensure_process_tables_idempotent_and_columns() -> None:
    """ensure_process_tables is idempotent (double-call) and creates expected columns."""
    import psycopg

    from dazzle.http.runtime.process_schema import ensure_process_tables

    conn = psycopg.connect(_PG_URL)
    try:
        # First call — creates tables
        ensure_process_tables(conn)
        # Second call — must NOT raise (IF NOT EXISTS idempotence)
        ensure_process_tables(conn)

        # ── process_runs columns ──────────────────────────────────────────
        runs_cols = _column_names(conn, "process_runs")
        required_runs = {
            # ProcessRun domain fields
            "run_id",
            "process_name",
            "process_version",
            "dsl_version",
            "status",
            "current_step",
            "inputs",
            "context",
            "outputs",
            "error",
            "idempotency_key",
            "started_at",
            "updated_at",
            "completed_at",
            # queue columns (from claim.queue_columns_ddl)
            "deliver_at",
            "claimed_by",
            "claimed_at",
            "lease_expires_at",
            "attempts",
            "payload",
        }
        missing_runs = required_runs - runs_cols
        assert not missing_runs, f"process_runs missing columns: {missing_runs}"

        # ── process_tasks columns ─────────────────────────────────────────
        tasks_cols = _column_names(conn, "process_tasks")
        required_tasks = {
            # ProcessTask domain fields
            "task_id",
            "run_id",
            "step_name",
            "surface_name",
            "entity_name",
            "entity_id",
            "assignee_id",
            "assignee_role",
            "status",
            "outcome",
            "outcome_data",
            "due_at",
            "escalated_at",
            "completed_at",
            "created_at",
            # queue columns
            "deliver_at",
            "claimed_by",
            "claimed_at",
            "lease_expires_at",
            "attempts",
            "payload",
        }
        missing_tasks = required_tasks - tasks_cols
        assert not missing_tasks, f"process_tasks missing columns: {missing_tasks}"

    finally:
        # Self-cleaning teardown
        _drop_tables(conn, "process_tasks", "process_runs")
        conn.close()


@pytest.mark.skipif(not _PG_URL, reason="no TEST_DATABASE_URL / DATABASE_URL — needs real Postgres")
def test_process_runs_due_index_exists() -> None:
    """The partial due-index on process_runs (status IN pending/claimed) is created."""
    import psycopg

    from dazzle.http.runtime.process_schema import ensure_process_tables

    conn = psycopg.connect(_PG_URL)
    try:
        ensure_process_tables(conn)

        with conn.cursor() as cur:
            cur.execute(
                "SELECT indexname FROM pg_indexes "
                "WHERE schemaname = 'public' AND tablename = 'process_runs' "
                "AND indexname = 'ix_process_runs_due'",
            )
            row = cur.fetchone()
        assert row is not None, "ix_process_runs_due index not found on process_runs"

    finally:
        _drop_tables(conn, "process_tasks", "process_runs")
        conn.close()
