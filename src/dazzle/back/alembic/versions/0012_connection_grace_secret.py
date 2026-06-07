"""Add SCIM bearer grace window + rotation audit (#1342 — connection secret rotation).

Two nullable columns on ``connections`` (previous_encrypted_secret +
previous_secret_expires_at) hold the old SCIM bearer during an overlap window;
``connection_secret_events`` is the append-only rotation audit (no DB FK — auth
tables live outside the DSL metadata; the trail survives a connection delete).
Idempotent (guards on column/table presence); mirrors the _init_db dev path.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision = "0012_connection_grace_secret"
down_revision = "0011_connections"
branch_labels = None
depends_on = None


def _has_table(table: str) -> bool:
    return sa_inspect(op.get_bind()).has_table(table)


def _has_column(table: str, column: str) -> bool:
    insp = sa_inspect(op.get_bind())
    return _has_table(table) and any(c["name"] == column for c in insp.get_columns(table))


def upgrade() -> None:
    if _has_table("connections"):
        if not _has_column("connections", "previous_encrypted_secret"):
            op.add_column(
                "connections", sa.Column("previous_encrypted_secret", sa.Text(), nullable=True)
            )
        if not _has_column("connections", "previous_secret_expires_at"):
            op.add_column(
                "connections", sa.Column("previous_secret_expires_at", sa.Text(), nullable=True)
            )
    if not _has_table("connection_secret_events"):
        op.create_table(
            "connection_secret_events",
            sa.Column("seq", sa.BigInteger(), sa.Identity(always=False), unique=True),
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("connection_id", sa.Text(), nullable=False),
            sa.Column("tenant_id", sa.Text(), nullable=False),
            sa.Column("event", sa.Text(), nullable=False),
            sa.Column("actor", sa.Text(), nullable=True),
            sa.Column("detail", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("at", sa.Text(), nullable=False),
        )
        op.create_index(
            "ix_connection_secret_events_conn",
            "connection_secret_events",
            ["connection_id", "seq"],
        )


def downgrade() -> None:
    if _has_table("connection_secret_events"):
        op.drop_table("connection_secret_events")
    if _has_column("connections", "previous_secret_expires_at"):
        op.drop_column("connections", "previous_secret_expires_at")
    if _has_column("connections", "previous_encrypted_secret"):
        op.drop_column("connections", "previous_encrypted_secret")
