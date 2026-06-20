"""join_requests table — verified-domain self-service join (#1424)."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision = "0018_join_requests"
down_revision = "0017_org_settings"
branch_labels = None
depends_on = None


def _has_table(table: str) -> bool:
    return sa_inspect(op.get_bind()).has_table(table)


def upgrade() -> None:
    if not _has_table("join_requests"):
        op.create_table(
            "join_requests",
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("tenant_id", sa.Text(), nullable=False),
            sa.Column("identity_id", sa.Text(), nullable=False),
            sa.Column("email", sa.Text(), nullable=False),
            sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.Column("decided_at", sa.Text(), nullable=True),
            sa.Column("decided_by", sa.Text(), nullable=True),
        )
        op.create_index("ix_join_requests_tenant", "join_requests", ["tenant_id"])
        # one non-terminal request per (tenant, identity)
        op.create_index(
            "uq_join_requests_pending",
            "join_requests",
            ["tenant_id", "identity_id"],
            unique=True,
            postgresql_where=sa.text("status = 'pending'"),
        )


def downgrade() -> None:
    if _has_table("join_requests"):
        op.drop_table("join_requests")
