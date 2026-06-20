"""Widen alembic_version.version_num to VARCHAR(128).

Alembic's `DefaultImpl.version_table_impl()` defines `alembic_version.
version_num` as `String(32)`. Dazzle's revision-naming convention
encourages descriptive human-readable IDs (e.g.
`0003_subtype_kind_function`, `0004_widen_alembic_version_num`) — most
already brush against the 32-char ceiling, and any ID ≥33 chars
silently fails mid-upgrade: the DDL runs, then the trailing
`UPDATE alembic_version SET version_num=...` fails with a string-
truncation error, leaving the schema-vs-version-state divergent.

Postgres VARCHAR widening is a no-rewrite metadata-only change at the
catalogue level, so this is safe and fast even on tables with rows.

Revision ID: 0004_widen_alembic_version_num
Revises: 0003_subtype_kind_function
Created: 2026-05-27
"""

from __future__ import annotations

from alembic import op

revision = "0004_widen_alembic_version_num"
down_revision = "0003_subtype_kind_function"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(128)")


def downgrade() -> None:
    # Narrowing back to 32 would truncate any current revision id ≥33 chars,
    # bricking the chain. Refuse to downgrade rather than silently lose data.
    raise RuntimeError(
        "Cannot downgrade 0004_widen_alembic_version_num: narrowing "
        "version_num to VARCHAR(32) would truncate any in-flight revision id "
        ">=33 chars. If you genuinely need to revert, ensure the current "
        "head revision id fits in 32 chars first, then ALTER manually."
    )
