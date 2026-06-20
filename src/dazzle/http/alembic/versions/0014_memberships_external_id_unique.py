"""Partial unique index on memberships(tenant_id, external_id) — SCIM provisioning dedup
(#1342 gap 1).

Guarded safety-net mirroring ``AuthStore._init_db`` (the primary creator). One membership per
(org, IdP user GUID); partial so non-SCIM / pre-existing NULL external_ids are unconstrained.
Closes the concurrent double-POST race that lookup-first dedup alone can't (two provisions for
the same externalId arriving together → two rows). Idempotent: created with IF NOT EXISTS so a
DB already bootstrapped by ``_init_db`` is a no-op.
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import inspect as sa_inspect

revision = "0014_memberships_external_id_unique"
down_revision = "0013_scim_groups_and_external_ids"
branch_labels = None
depends_on = None


def _has_table(table: str) -> bool:
    return sa_inspect(op.get_bind()).has_table(table)


def upgrade() -> None:
    # Static DDL — no interpolation (the index/table/column names are literals here).
    if not _has_table("memberships"):
        return
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_memberships_tenant_external "
        "ON memberships(tenant_id, external_id) WHERE external_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_memberships_tenant_external")
