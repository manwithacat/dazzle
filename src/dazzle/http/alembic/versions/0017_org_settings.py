"""Add organizations.settings JSON column (verified-domain join, #1424)."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision = "0017_org_settings"
down_revision = "0016_saml_consumed_assertions"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    insp = sa_inspect(op.get_bind())
    return any(c["name"] == column for c in insp.get_columns(table))


def upgrade() -> None:
    if not _has_column("organizations", "settings"):
        op.add_column(
            "organizations",
            sa.Column("settings", sa.Text(), nullable=False, server_default="{}"),
        )


def downgrade() -> None:
    if _has_column("organizations", "settings"):
        op.drop_column("organizations", "settings")
