"""Add is_test to public.tenants (ephemeral test-tenant lifecycle, #1339 slice 0).

The tenant registry record gains a queryable `is_test` boolean so the
test-tenant containment check and the excision reaper can filter on it (a
column, not a forgeable slug prefix). Fresh installs get the column via the
registry's `CREATE TABLE IF NOT EXISTS` (and a convergent boot-time
`ALTER ... IF NOT EXISTS`); this migration is the canonical schema-change path
(ADR-0017) for already-migrated trees. Idempotent + dialect-agnostic, mirroring
0005: guards on existence so it is safe to re-run and no-ops where the registry
table is absent (non-tenant projects, SQLite structural sandbox).

Revision ID: 0006_tenant_is_test
Revises: 0005_session_csrf_secret
Created: 2026-06-04
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision = "0006_tenant_is_test"
down_revision = "0005_session_csrf_secret"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa_inspect(bind)
    if not insp.has_table(table):
        return False
    return any(c["name"] == column for c in insp.get_columns(table))


def upgrade() -> None:
    # No-op when the registry table is absent (non-tenant project, or the SQLite
    # structural sandbox) or the column already exists (fresh installs create it
    # in `CREATE TABLE`, and the registry's boot-time ALTER may have run first).
    if not sa_inspect(op.get_bind()).has_table("tenants"):
        return
    if _has_column("tenants", "is_test"):
        return
    # NOT NULL + server_default false back-fills existing rows in one statement.
    op.add_column(
        "tenants",
        sa.Column("is_test", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    if _has_column("tenants", "is_test"):
        op.drop_column("tenants", "is_test")
