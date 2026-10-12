"""Add _dazzle_ingest_fingerprint (ingest OBSERVATION content-hash, #1676).

Production skips boot-time ``ensure_framework_schema`` (Alembic owns schema).
DBs already stamped at 0020 therefore needed this incremental. The ``ingest``
construct was parked in flense ship F (DD-006); 0022 drops the table again and
the DDL is inlined here so the revision chain no longer imports the removed
runtime.

Revision ID: 0021_ingest_fingerprint
Revises:     0020_tenant_host_aliases
"""

from alembic import op

revision = "0021_ingest_fingerprint"
down_revision = "0020_tenant_host_aliases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS _dazzle_ingest_fingerprint (
            ingest_name TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (ingest_name, sha256)
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS _dazzle_ingest_fingerprint")
