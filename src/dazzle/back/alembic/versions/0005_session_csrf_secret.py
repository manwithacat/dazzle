"""Add csrf_secret to sessions (declarative-CSRF Phase 1).

Phase 1 of the declarative-CSRF spec binds the CSRF token to the session: the
`SessionRecord` model carries a `csrf_secret`, and the `sessions` table needs a
matching column. The fresh-install path creates it via the runtime's
`CREATE TABLE IF NOT EXISTS sessions (...)` (auth store); this migration is the
canonical schema-change path (ADR-0017) for already-migrated trees.

Revision ID: 0005_session_csrf_secret
Revises: 0004_widen_alembic_version_num
Created: 2026-06-03
"""

from __future__ import annotations

import secrets

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision = "0005_session_csrf_secret"
down_revision = "0004_widen_alembic_version_num"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa_inspect(bind)
    if not insp.has_table(table):
        return False
    return any(c["name"] == column for c in insp.get_columns(table))


def upgrade() -> None:
    # Idempotent: framework migrations may re-run on a partially-migrated tree
    # (e.g. fresh installs where the runtime's `CREATE TABLE IF NOT EXISTS`
    # already added the column). Uses the dialect-agnostic inspector so this
    # runs identically on the PostgreSQL runtime and the SQLite test sandbox.
    if _has_column("sessions", "csrf_secret"):
        return
    op.add_column("sessions", sa.Column("csrf_secret", sa.Text(), nullable=True))
    # Backfill existing rows so sessions predating this column present a valid token.
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id FROM sessions")).fetchall()
    for (sid,) in rows:
        bind.execute(
            sa.text("UPDATE sessions SET csrf_secret = :s WHERE id = :id"),
            {"s": secrets.token_urlsafe(32), "id": sid},
        )


def downgrade() -> None:
    if _has_column("sessions", "csrf_secret"):
        op.drop_column("sessions", "csrf_secret")
