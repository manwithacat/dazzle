"""Add invitations table (auth Plan 3a — org invitation tokens).

Email-addressed invitation tokens; the membership is created at accept time
(verified-email join). Idempotent (guards on table presence); mirrors
0009_membership_events. No DB FK (the auth tables live outside the DSL metadata;
joins enforced in the store).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision = "0010_invitations"
down_revision = "0009_membership_events"
branch_labels = None
depends_on = None


def _has_table(table: str) -> bool:
    return sa_inspect(op.get_bind()).has_table(table)


def upgrade() -> None:
    if not _has_table("invitations"):
        op.create_table(
            "invitations",
            sa.Column("token", sa.Text(), primary_key=True),
            sa.Column("org_id", sa.Text(), nullable=False),
            sa.Column("email", sa.Text(), nullable=False),
            sa.Column("roles", sa.Text(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("invited_by", sa.Text(), nullable=False),
            sa.Column("expires_at", sa.Text(), nullable=False),
            sa.Column("accepted_at", sa.Text(), nullable=True),
            sa.Column("created_at", sa.Text(), nullable=False),
        )
        op.create_index("ix_invitations_org", "invitations", ["org_id"])
        op.create_index("ix_invitations_email", "invitations", ["email"])


def downgrade() -> None:
    if _has_table("invitations"):
        op.drop_table("invitations")
