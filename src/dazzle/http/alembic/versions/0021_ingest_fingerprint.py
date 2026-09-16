"""Add _dazzle_ingest_fingerprint (ingest OBSERVATION content-hash, #1676).

Production skips boot-time ``ensure_framework_schema`` (Alembic owns schema).
DBs already stamped at 0020 therefore need this incremental. Fresh installs
also get the table from 0019's shared DDL core (IF NOT EXISTS).

Revision ID: 0021_ingest_fingerprint
Revises:     0020_tenant_host_aliases
"""

from alembic import op

from dazzle.http.alembic.cursor_ddl import apply_ensure_on_alembic_cursor
from dazzle.http.runtime.ingest_engine import ensure_ingest_fingerprint_table

revision = "0021_ingest_fingerprint"
down_revision = "0020_tenant_host_aliases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    apply_ensure_on_alembic_cursor(ensure_ingest_fingerprint_table)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS _dazzle_ingest_fingerprint")
