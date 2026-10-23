"""Bring a production database to parity with the schema the orchestrator builds (#1850).

``0019`` is the squashed root and calls the *live* ``_ensure_framework_schema_ddl``,
so only a database created after an orchestrator change gets that change. Production
runs no boot-time DDL (#1462), so a database stamped at ``0019`` before these objects
were added to the orchestrator never received them. Diffing a database built by each
historical ``0019`` (2026-06-23 onwards) and upgraded to ``0027`` against a fresh
``upgrade head`` plus a development boot finds four gaps, all created here:

* ``_dazzle_usage_events`` and its indexes ``idx_usage_events_agg`` /
  ``idx_usage_events_ts`` (ADR-0050 Option A; orchestrator since 2026-07-01).
* ``dazzle_files.uploaded_by`` (#1551; since 2026-07-07).
* ``memberships.partition_root_id`` (#1463 groundwork; since 2026-06-23, after the
  first ``0019``).
* ``users_email_lower_key``, the case-insensitive email unique index (#1342). The
  orchestrator gained it with #1462; before that only ``AuthStore._init_db`` built
  it, which production skips. The auth store has trimmed and lowercased every email it
  writes since #1342, but rows written before that keep their original case, and login
  (which looks up the lowercased form) cannot find them. So the revision first rewrites
  those rows to ``LOWER(TRIM(email))``, then adds the index. Two rows that normalize to
  the same address are two separate accounts (passwords, memberships, owned records),
  which no migration can merge safely: the upgrade stops and names them, as the
  development path does.

The DDL is frozen here (not imported from the runtime) so this revision means the
same thing whatever the orchestrator later becomes. Every statement is idempotent;
on a fresh install ``0019`` already created the objects and this revision is a no-op.

From this revision on, every change to the orchestrator's DDL ships its own
incremental revision (ADR-0044, amended for #1850). The gate
``tests/unit/test_orchestrator_ddl_revision_gate.py`` compares a fingerprint of the
orchestrator's statements with ``ORCHESTRATOR_DDL_SHA256`` on the head revision; a
new revision carries the new fingerprint.

``downgrade`` is a no-op: these objects belong to the schema ``0019`` defines today,
and the runtime at ``0027`` already reads and writes them, so dropping them would
break that runtime rather than restore it.

Revision ID: 0028_runtime_schema_parity
Revises:     0027_two_factor_restore
"""

import sqlalchemy as sa
from alembic import op

revision = "0028_runtime_schema_parity"
down_revision = "0027_two_factor_restore"
branch_labels = None
depends_on = None

#: SHA-256 of the orchestrator's normalised DDL at this revision (see the gate above).
ORCHESTRATOR_DDL_SHA256 = "96a31723d2351623361009a4f84c5d28307046d08beadfedb6120a8d3d071a20"

_USAGE_EVENTS_DDL = (
    """
    CREATE TABLE IF NOT EXISTS _dazzle_usage_events (
        id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        tenant_id TEXT NOT NULL DEFAULT '',
        surface TEXT NOT NULL,
        kind TEXT NOT NULL,
        target TEXT NOT NULL,
        ts TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_usage_events_agg "
    "ON _dazzle_usage_events (tenant_id, surface, kind, target)",
    "CREATE INDEX IF NOT EXISTS idx_usage_events_ts ON _dazzle_usage_events (tenant_id, ts)",
)


def upgrade() -> None:
    for statement in _USAGE_EVENTS_DDL:
        op.execute(statement)
    op.execute("ALTER TABLE dazzle_files ADD COLUMN IF NOT EXISTS uploaded_by TEXT")
    op.execute("ALTER TABLE memberships ADD COLUMN IF NOT EXISTS partition_root_id TEXT")

    bind = op.get_bind()
    collisions = bind.execute(
        sa.text(
            "SELECT LOWER(TRIM(email)) AS k, COUNT(*) AS n FROM users "
            "GROUP BY LOWER(TRIM(email)) HAVING COUNT(*) > 1 ORDER BY 1 LIMIT 5"
        )
    ).fetchall()
    if collisions:
        examples = ", ".join(f"{k} (x{n})" for k, n in collisions)
        raise RuntimeError(
            "0028_runtime_schema_parity cannot normalize users.email (#1342): separate "
            f"accounts share an address once lowercased: {examples}. Merge or re-address "
            "the duplicate users (one identity per lowercased email), then re-run "
            "`dazzle db upgrade`."
        )
    # Rows written before #1342 kept their case and are invisible to login.
    op.execute("UPDATE users SET email = LOWER(TRIM(email)) WHERE email <> LOWER(TRIM(email))")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS users_email_lower_key ON users (LOWER(email))")


def downgrade() -> None:
    # Deliberate no-op — see the module docstring.
    pass
