"""Mirror the SAML IdP-initiated replay cache table into the alembic chain (#1342).

Guarded safety-net mirroring ``AuthStore._init_db`` (the primary creator). ``saml_consumed_assertions``
records one-time consumption of an IdP-initiated assertion id (keyed by the IdP-generated Assertion
ID, expiring at its NotOnOrAfter) so a captured unsolicited Response can't be replayed. Idempotent:
a DB already bootstrapped by ``_init_db`` no-ops.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision = "0016_saml_consumed_assertions"
down_revision = "0015_users_email_ci_unique"
branch_labels = None
depends_on = None


def _has_table(table: str) -> bool:
    return sa_inspect(op.get_bind()).has_table(table)


def upgrade() -> None:
    if not _has_table("saml_consumed_assertions"):
        op.create_table(
            "saml_consumed_assertions",
            sa.Column("assertion_id", sa.Text(), primary_key=True),
            sa.Column("connection_id", sa.Text(), nullable=False),
            sa.Column("tenant_id", sa.Text(), nullable=True),
            sa.Column("expires_at", sa.Text(), nullable=False),
            sa.Column("created_at", sa.Text(), nullable=False),
        )


def downgrade() -> None:
    if _has_table("saml_consumed_assertions"):
        op.drop_table("saml_consumed_assertions")
