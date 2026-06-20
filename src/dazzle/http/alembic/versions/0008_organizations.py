"""Add organizations table (auth Plan 1c — framework Organization registry).

The framework gains an `organizations` join (the tenant root in shared-schema):
`organizations.id` is the `dazzle.tenant_id` discriminator a membership carries.
Idempotent: guards on table presence so the dev `_init_db` create path and this
migration are interchangeable. No DB FK from `memberships.tenant_id` (the auth
tables aren't in the Alembic-managed DSL metadata; the join is enforced in the
store, mirroring 0007's identity_id treatment).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision = "0008_organizations"
down_revision = "0007_memberships"
branch_labels = None
depends_on = None


def _has_table(table: str) -> bool:
    return sa_inspect(op.get_bind()).has_table(table)


def upgrade() -> None:
    if not _has_table("organizations"):
        op.create_table(
            "organizations",
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("slug", sa.Text(), nullable=False),
            sa.Column("name", sa.Text(), nullable=False),
            sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'active'")),
            sa.Column("is_test", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.Column("updated_at", sa.Text(), nullable=False),
            sa.UniqueConstraint("slug", name="uq_organizations_slug"),
        )


def downgrade() -> None:
    if _has_table("organizations"):
        op.drop_table("organizations")
