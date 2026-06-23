"""Complete squashed framework baseline — all in-scope app-DB framework tables.

This is the SINGLE root migration for the Dazzle framework schema (Task 2 of
the framework-migration-baseline plan, ADR-0044).  It replaces the chain
0001–0018 with a single, idempotent baseline that calls the same DDL core as
``ensure_framework_schema`` in ``dazzle.http.runtime.framework_schema``.

**Design — shared DDL core (no copy):**
  ``upgrade()`` calls ``_ensure_framework_schema_ddl(cur)`` — the same
  no-commit, no-lock function that ``ensure_framework_schema`` delegates to.
  The baseline is therefore *provably identical* to the orchestrator by shared
  code, not by copied DDL.

**alembic_version widening (Task-0 carry-forward, was migration 0004):**
  ``ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(128)``
  is executed first so long revision ids fit.  This is migration-only
  (alembic_version is not a framework table) — it does NOT appear in the
  orchestrator.

**In-scope tables (all created by the shared DDL core):**
  _dazzle_params; users, sessions, memberships, organizations,
  membership_events, invitations, connections, connection_secret_events,
  scim_groups, scim_group_members, saml_consumed_assertions,
  password_reset_tokens, magic_links, email_verification_tokens,
  user_preferences, join_requests; process_runs, process_tasks;
  _dazzle_audit_log, _dazzle_atomic_audit, dazzle_files, refresh_tokens,
  devices, _grants, _grant_events, _dazzle_otp_codes, _dazzle_recovery_codes,
  _dazzle_event_inbox, _dazzle_event_outbox.

**Excluded (same exclusions as the orchestrator):**
  ops_database tables (separate DB); event-bus ``{prefix}events/offsets/dlq``
  (dynamic prefix); tenant registry ``public.tenants`` + per-tenant schemas.

Revision ID: 0019_process_runtime_tables
Revises:     (none — this is the chain root)
Created:     2026-06-23
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "0019_process_runtime_tables"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── alembic_version widening (Task-0 carry-forward, was 0004) ────────────
    # Widen version_num so long revision ids (e.g. 0019_process_runtime_tables)
    # fit.  This is migration-only — alembic_version is not a framework table
    # and does not appear in ensure_framework_schema.
    bind = op.get_bind()
    bind.execute(sa.text("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(128)"))

    # ── full framework schema via the shared DDL core ─────────────────────────
    # ``_ensure_framework_schema_ddl(cur)`` is the no-commit, no-lock DDL body
    # also called by ``ensure_framework_schema``.  Running it here keeps the
    # baseline provably identical to the orchestrator.
    #
    # Cursor access: ``op.get_bind()`` is a SQLAlchemy Connection whose
    # ``.connection`` attribute is the raw psycopg DBAPI connection.
    # ``.cursor()`` on that gives a psycopg cursor that accepts raw SQL
    # strings — exactly what the DDL core expects.
    from dazzle.http.runtime.framework_schema import _ensure_framework_schema_ddl

    raw_conn: Any = bind.connection
    cur = raw_conn.cursor()
    try:
        _ensure_framework_schema_ddl(cur)
    finally:
        cur.close()


def downgrade() -> None:
    # Chain root — downgrade is a deliberate no-op.  Dropping the entire
    # framework schema requires an out-of-band DBA operation; an automated
    # downgrade here would be data-destructive and is not safe to run
    # unattended.  This is the framework baseline root (0019); prior
    # per-migration roots 0001–0018 were squashed into this baseline.
    pass
