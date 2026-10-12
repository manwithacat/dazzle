"""Flense ship F (ADR-0057): drop the three framework tables whose runtime is gone.

* ``_dazzle_atomic_audit`` — strict atomic-flow audit (``atomic``, DD-004).
* ``_dazzle_ingest_fingerprint`` — ingest batch idempotency (``ingest``, DD-006).
* ``join_requests`` — verified-domain join approvals (domain-join, DD-009).

``ensure_framework_schema`` no longer creates them and no runtime path reads or
writes them. This revision shipped as a no-op pending the operator's sign-off
on dropping data from consumer databases; that sign-off was given on
2026-10-13 (flense plan §8, decision 1) before any release carried the
revision, so the drop lives here rather than in a second revision. A database
that was stamped at ``0022`` by a pre-release checkout keeps the three tables;
run the three ``DROP TABLE IF EXISTS`` statements below by hand.

``downgrade`` recreates the tables with the DDL the removed runtime used so a
rollback to ``0021`` is schema-complete; the dropped rows are not restored.

Revision ID: 0022_flense_park_tables
Revises:     0021_ingest_fingerprint
"""

from alembic import op

revision = "0022_flense_park_tables"
down_revision = "0021_ingest_fingerprint"
branch_labels = None
depends_on = None

_PARKED_TABLES = ("_dazzle_atomic_audit", "_dazzle_ingest_fingerprint", "join_requests")


def upgrade() -> None:
    for table in _PARKED_TABLES:
        op.execute(f"DROP TABLE IF EXISTS {table}")


def downgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS _dazzle_atomic_audit (
            id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            flow_name TEXT NOT NULL,
            user_id TEXT,
            user_email TEXT,
            user_roles TEXT,
            operation TEXT NOT NULL,
            entity_name TEXT NOT NULL,
            entity_id TEXT,
            decision TEXT NOT NULL,
            matched_policy TEXT
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS _dazzle_ingest_fingerprint (
            ingest_name TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (ingest_name, sha256)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS join_requests (
            id          TEXT PRIMARY KEY,
            tenant_id   TEXT NOT NULL,
            identity_id TEXT NOT NULL,
            email       TEXT NOT NULL,
            status      TEXT NOT NULL DEFAULT 'pending',
            created_at  TEXT NOT NULL,
            decided_at  TEXT,
            decided_by  TEXT
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_join_requests_tenant ON join_requests(tenant_id)")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_join_requests_pending "
        "ON join_requests(tenant_id, identity_id) WHERE status = 'pending'"
    )
