"""Add memberships table + sessions.active_membership_id (auth Plan 1a).

The framework gains a ``memberships`` join (identity x org x roles) — the fenced
source of the RLS ``dazzle.tenant_id`` — plus a nullable
``sessions.active_membership_id`` pinning the session's active org.

The auth tables (``users`` / ``sessions``) live in the ``AuthStore._init_db``
raw-SQL subsystem and are **not** part of the Alembic-created chain (see
0005_session_csrf_secret, which only guarded-ALTERs ``sessions``). This migration
follows that same pattern: it is a guarded safety-net that mirrors what
``_init_db`` does idempotently, so the committed chain carries the change even
though ``_init_db`` is the primary creator. Guards (``_has_table`` /
``_has_column``) make it safe whether or not the auth tables exist yet.

``memberships`` deliberately carries **no DB foreign key** to ``users`` — the
auth tables are loosely coupled and ``users`` may not exist at migration time
(it is not in the Alembic chain). Referential integrity is enforced at the app
layer, and tenant excision (#1338, Phase E) deletes memberships explicitly in
order rather than relying on ``ON DELETE CASCADE``.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision = "0007_memberships"
down_revision = "0006_tenant_is_test"
branch_labels = None
depends_on = None


def _has_table(table: str) -> bool:
    return sa_inspect(op.get_bind()).has_table(table)


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa_inspect(bind)
    if not insp.has_table(table):
        return False
    return any(c["name"] == column for c in insp.get_columns(table))


def upgrade() -> None:
    if not _has_table("memberships"):
        op.create_table(
            "memberships",
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("tenant_id", sa.Text(), nullable=False),
            sa.Column("identity_id", sa.Text(), nullable=False),
            sa.Column("roles", sa.Text(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'active'")),
            sa.Column("invited_by", sa.Text(), nullable=True),
            sa.Column("joined_at", sa.Text(), nullable=False),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.Column("updated_at", sa.Text(), nullable=False),
            sa.UniqueConstraint("tenant_id", "identity_id", name="uq_memberships_tenant_identity"),
        )
        op.create_index("ix_memberships_identity_id", "memberships", ["identity_id"])
        op.create_index("ix_memberships_tenant_id", "memberships", ["tenant_id"])

    if _has_table("sessions") and not _has_column("sessions", "active_membership_id"):
        op.add_column(
            "sessions",
            sa.Column("active_membership_id", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    if _has_column("sessions", "active_membership_id"):
        op.drop_column("sessions", "active_membership_id")
    if _has_table("memberships"):
        op.drop_table("memberships")
