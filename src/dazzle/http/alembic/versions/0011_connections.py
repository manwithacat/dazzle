"""Add connections table (auth Plan 4a — per-org enterprise auth connections).

Org-fenced OIDC/SAML/SCIM connection config; secret material lives in
``encrypted_secret`` (AES-GCM, never plaintext). Idempotent (guards on table
presence); mirrors 0010. No DB FK (auth tables live outside the DSL metadata;
the join to organizations is enforced in the store).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision = "0011_connections"
down_revision = "0010_invitations"
branch_labels = None
depends_on = None


def _has_table(table: str) -> bool:
    return sa_inspect(op.get_bind()).has_table(table)


def upgrade() -> None:
    if not _has_table("connections"):
        op.create_table(
            "connections",
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("tenant_id", sa.Text(), nullable=False),
            sa.Column("type", sa.Text(), nullable=False),
            sa.Column("provider", sa.Text(), nullable=False, server_default=sa.text("'native'")),
            sa.Column("domains", sa.Text(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column(
                "verified_domains", sa.Text(), nullable=False, server_default=sa.text("'[]'")
            ),
            sa.Column("config", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("encrypted_secret", sa.Text(), nullable=True),
            sa.Column("group_mapping", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'active'")),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.Column("updated_at", sa.Text(), nullable=False),
        )
        op.create_index("ix_connections_tenant", "connections", ["tenant_id"])


def downgrade() -> None:
    if _has_table("connections"):
        op.drop_table("connections")
