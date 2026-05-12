"""Framework baseline — create _dazzle_params

Creates the framework's `_dazzle_params` table that the runtime expects to
exist when `DAZZLE_ENV=production` (see ADR-0017 + commit 97ac3f65). DDL
matches `ensure_dazzle_params_table()` in `dazzle_back/runtime/migrations.py`
exactly so dev (which still calls `CREATE TABLE IF NOT EXISTS`) and
production (which runs this migration) end up with the same schema.

Revision ID: 0001_framework_baseline
Revises:
Created: 2026-04-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_framework_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "_dazzle_params",
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("scope_id", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("value_json", postgresql.JSONB(), nullable=False),
        sa.Column("updated_by", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("key", "scope", "scope_id", name="_dazzle_params_pkey"),
    )


def downgrade() -> None:
    op.drop_table("_dazzle_params")
