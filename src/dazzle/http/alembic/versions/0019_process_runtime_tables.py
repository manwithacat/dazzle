"""process_runs + process_tasks framework tables (Task 2, Phase 1 #pg-coordination).

Creates the durable process-runtime queue tables.  DDL mirrors
``ensure_process_tables()`` in ``dazzle.http.runtime.process_schema`` exactly,
so dev (boot DDL) and prod (this Alembic migration) always end up with the
same schema — the authstore-parity rule (ADR-0017).

Table naming note
-----------------
The #1454 ``ProcessRun`` IR entity is materialised by SQLAlchemy as a table
named ``"ProcessRun"`` (``entity.name``, mixed-case, singular).  The framework
runtime tables are ``process_runs`` / ``process_tasks`` (snake_case, plural) —
structurally distinct; no collision, no ``_dazzle_`` prefix required.

Revision ID: 0019_process_runtime_tables
Revises:     0018_join_requests
Created:     2026-06-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.dialects import postgresql

revision = "0019_process_runtime_tables"
down_revision = "0018_join_requests"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return sa_inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    # Idempotent: boot-DDL may have already created these tables via
    # ``ensure_process_tables()`` before this migration ever runs.
    # Guard each statement separately so a partial prior run is also safe.

    if not _has_table("process_runs"):
        op.create_table(
            "process_runs",
            # ── ProcessRun domain fields ───────────────────────────────
            sa.Column("run_id", sa.Text(), primary_key=True, nullable=False),
            sa.Column("process_name", sa.Text(), nullable=False),
            sa.Column("process_version", sa.Text(), nullable=False, server_default=sa.text("'v1'")),
            sa.Column("dsl_version", sa.Text(), nullable=False, server_default=sa.text("'0.1'")),
            sa.Column("current_step", sa.Text(), nullable=True),
            sa.Column(
                "inputs",
                postgresql.JSONB(),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
            sa.Column(
                "context",
                postgresql.JSONB(),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
            sa.Column("outputs", postgresql.JSONB(), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("idempotency_key", sa.Text(), nullable=True),
            sa.Column(
                "started_at",
                postgresql.TIMESTAMP(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column(
                "updated_at",
                postgresql.TIMESTAMP(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column("completed_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
            # ── queue columns (claim.queue_columns_ddl) ────────────────
            sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'pending'")),
            sa.Column(
                "deliver_at",
                postgresql.TIMESTAMP(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column("claimed_by", sa.Text(), nullable=True),
            sa.Column("claimed_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
            sa.Column("lease_expires_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
            sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column(
                "payload",
                postgresql.JSONB(),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
        )
        # Partial due-index — claim_due_work only scans pending/claimed rows.
        op.create_index(
            "ix_process_runs_due",
            "process_runs",
            ["deliver_at"],
            postgresql_where=sa.text("status IN ('pending', 'claimed')"),
        )

    if not _has_table("process_tasks"):
        op.create_table(
            "process_tasks",
            # ── ProcessTask domain fields ──────────────────────────────
            sa.Column("task_id", sa.Text(), primary_key=True, nullable=False),
            sa.Column(
                "run_id",
                sa.Text(),
                sa.ForeignKey("process_runs.run_id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("step_name", sa.Text(), nullable=False),
            sa.Column("surface_name", sa.Text(), nullable=False),
            sa.Column("entity_name", sa.Text(), nullable=False),
            sa.Column("entity_id", sa.Text(), nullable=False),
            sa.Column("assignee_id", sa.Text(), nullable=True),
            sa.Column("assignee_role", sa.Text(), nullable=True),
            sa.Column("outcome", sa.Text(), nullable=True),
            sa.Column("outcome_data", postgresql.JSONB(), nullable=True),
            sa.Column("due_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
            sa.Column("escalated_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
            sa.Column("completed_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                postgresql.TIMESTAMP(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            # ── queue columns (claim.queue_columns_ddl) ────────────────
            sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'pending'")),
            sa.Column(
                "deliver_at",
                postgresql.TIMESTAMP(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column("claimed_by", sa.Text(), nullable=True),
            sa.Column("claimed_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
            sa.Column("lease_expires_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
            sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column(
                "payload",
                postgresql.JSONB(),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
        )
        op.create_index(
            "ix_process_tasks_due",
            "process_tasks",
            ["deliver_at"],
            postgresql_where=sa.text("status IN ('pending', 'claimed')"),
        )


def downgrade() -> None:
    if _has_table("process_tasks"):
        op.drop_table("process_tasks")
    if _has_table("process_runs"):
        op.drop_table("process_runs")
