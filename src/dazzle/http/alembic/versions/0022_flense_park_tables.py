"""Flense ship F (ADR-0057): the runtime that wrote three framework tables is gone.

* ``_dazzle_atomic_audit`` — strict atomic-flow audit (``atomic``, DD-004).
* ``_dazzle_ingest_fingerprint`` — ingest batch idempotency (``ingest``, DD-006).
* ``join_requests`` — verified-domain join approvals (domain-join, DD-009).

``ensure_framework_schema`` no longer creates them. This revision deliberately
does NOT drop them: dropping data in consumer databases needs the operator's
sign-off (see the Deferred Decisions above). When that sign-off exists, a later
revision drops the three tables; until then they sit unused and unreferenced.

Revision ID: 0022_flense_park_tables
Revises:     0021_ingest_fingerprint
"""

revision = "0022_flense_park_tables"
down_revision = "0021_ingest_fingerprint"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """No-op: the parked tables are left in place pending operator sign-off."""


def downgrade() -> None:
    """No-op (nothing was dropped)."""
