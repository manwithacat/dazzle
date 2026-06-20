"""Drop orphan _dazzle_migrations table

Drops the `_dazzle_migrations` table that was abandoned when `MigrationHistory`
was retired in commit `adb3e0ca` (shipped via #1195). The table has had no
writer since that change, but pre-existing deployments still carry it — on
CyFuture staging it had grown to ~52K rows before manual cleanup. This
migration collapses the three divergent states (untouched legacy rows,
manually trimmed, fresh deploys with no table) into one truth.

Idempotent — uses `DROP TABLE IF EXISTS`. Downgrade is intentionally a no-op:
the table has no writer in the current codebase, so re-creating it empty would
mislead future investigators. Closes #1208.

Revision ID: 0002_drop_dazzle_migrations
Revises: 0001_framework_baseline
Created: 2026-05-23
"""

from __future__ import annotations

from alembic import op

revision = "0002_drop_dazzle_migrations"
down_revision = "0001_framework_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS _dazzle_migrations")


def downgrade() -> None:
    # Intentional no-op: the table has no writer in the current codebase
    # (retired in #1195). Re-creating it empty on downgrade would mislead
    # future investigators into thinking it's an active ledger.
    pass
