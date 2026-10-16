"""Restore the enterprise-auth tables for OIDC sign-in and SCIM provisioning (DD-013, EA-1).

* ``connections`` — per-org OIDC / SCIM / routing-only ``domain`` connections.
* ``connection_secret_events`` — the connection secret-rotation audit trail.
* ``scim_groups`` and ``scim_group_members`` — SCIM 2.0 groups and their members.

DD-013 moved to FORCED on 2026-10-16 (``consumer: platform (core requirement)``); the work
plan is ``docs/plans/2026-10-16-enterprise-auth-restore.md``. The DDL is
``dazzle.http.runtime.auth.store_enterprise.ENTERPRISE_AUTH_DDL`` — the same statements the
``downgrade`` of ``0023_flense_park_enterprise_auth`` recreates, minus the fifth table that
revision dropped, which stays out of scope. The auth store's boot DDL runs the same tuple,
so the two paths cannot drift. All statements are ``IF NOT EXISTS`` (on a fresh install
``0019``'s shared DDL core creates the tables and ``0023`` drops them before this runs).

Revision ID: 0026_enterprise_auth_oidc_scim
Revises:     0025_flense_park_event_transport
"""

from alembic import op

from dazzle.http.runtime.auth.store_enterprise import ENTERPRISE_AUTH_DDL

revision = "0026_enterprise_auth_oidc_scim"
down_revision = "0025_flense_park_event_transport"
branch_labels = None
depends_on = None

# Child before parent: scim_group_members references scim_groups.
_ENTERPRISE_TABLES = (
    "scim_group_members",
    "scim_groups",
    "connection_secret_events",
    "connections",
)


def upgrade() -> None:
    for statement in ENTERPRISE_AUTH_DDL:
        op.execute(statement)


def downgrade() -> None:
    op.execute(f"DROP TABLE IF EXISTS {', '.join(_ENTERPRISE_TABLES)}")
