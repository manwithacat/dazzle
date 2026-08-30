"""Add tenant_host_aliases (ADR-0055 PR4 composing custom-domain aliases).

Production skips boot-time ``ensure_framework_schema`` (Alembic owns schema).
DBs already stamped at 0019 therefore need this incremental. Fresh installs
also get the table from 0019's shared DDL core (IF NOT EXISTS).

Revision ID: 0020_tenant_host_aliases
Revises:     0019_process_runtime_tables
"""

from __future__ import annotations

from typing import Any

from alembic import op

from dazzle.http.runtime.tenant.aliases import ensure_tenant_host_aliases_table

revision = "0020_tenant_host_aliases"
down_revision = "0019_process_runtime_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    raw_conn: Any = bind.connection
    cur = raw_conn.cursor()
    try:
        ensure_tenant_host_aliases_table(cur)
    finally:
        cur.close()


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS tenant_host_aliases")
