"""Mirror scim_groups + scim_group_members into the alembic chain, and add external_id to
memberships + scim_groups (#1342 schools SCIM/SAML gap foundation).

Guarded safety-net mirroring ``AuthStore._init_db`` (the primary creator), same pattern as
0007_memberships. ``scim_group_members`` deliberately carries NO FK to ``memberships`` (the
documented FK-coupling trap — an FK there blocks the memberships-table rebuild); it DOES keep
the FK to ``scim_groups`` (matches ``_init_db``). The new ``external_id`` columns let the SCIM
group→role + identity joins key on the IdP's stable id instead of mutable email/displayName.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision = "0013_scim_groups_and_external_ids"
down_revision = "0012_connection_grace_secret"
branch_labels = None
depends_on = None


def _has_table(table: str) -> bool:
    return sa_inspect(op.get_bind()).has_table(table)


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa_inspect(bind)
    if not insp.has_table(table):
        return False
    return any(c["name"] == column for c in insp.get_columns(table))


def upgrade() -> None:
    if not _has_table("scim_groups"):
        op.create_table(
            "scim_groups",
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("connection_id", sa.Text(), nullable=False),
            sa.Column("display_name", sa.Text(), nullable=False),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.Column("updated_at", sa.Text(), nullable=False),
            sa.UniqueConstraint("connection_id", "display_name"),
        )
        op.create_index("ix_scim_groups_conn", "scim_groups", ["connection_id"])
    if not _has_table("scim_group_members"):
        op.create_table(
            "scim_group_members",
            sa.Column(
                "group_id",
                sa.Text(),
                sa.ForeignKey("scim_groups.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("membership_id", sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint("group_id", "membership_id"),
        )
        op.create_index("ix_scim_group_members_member", "scim_group_members", ["membership_id"])
    if _has_table("memberships") and not _has_column("memberships", "external_id"):
        op.add_column("memberships", sa.Column("external_id", sa.Text(), nullable=True))
    if _has_table("scim_groups") and not _has_column("scim_groups", "external_id"):
        op.add_column("scim_groups", sa.Column("external_id", sa.Text(), nullable=True))


def downgrade() -> None:
    if _has_column("scim_groups", "external_id"):
        op.drop_column("scim_groups", "external_id")
    if _has_column("memberships", "external_id"):
        op.drop_column("memberships", "external_id")
    if _has_table("scim_group_members"):
        op.drop_table("scim_group_members")
    if _has_table("scim_groups"):
        op.drop_table("scim_groups")
