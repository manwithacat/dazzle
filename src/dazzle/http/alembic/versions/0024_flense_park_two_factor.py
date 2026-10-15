"""Flense ship AG (ADR-0057): drop the two-factor tables whose runtime is gone.

* ``_dazzle_otp_codes`` — hashed email one-time codes for the 2FA challenge.
* ``_dazzle_recovery_codes`` — hashed single-use 2FA recovery codes.

Two-factor authentication is parked in
``docs/decisions/DD-014-two-factor-authentication.md``. ``ensure_framework_schema``
no longer creates these tables and no runtime path reads or writes them. No consumer
enrolled a user in 2FA (no checkout links to ``/2fa/*``), so on a consumer database the
tables are empty. Operator sign-off for the drop: 2026-10-15 (flense plan §9.4,
decision 3).

The four 2FA columns on ``users`` (``totp_secret``, ``totp_enabled``,
``email_otp_enabled``, ``recovery_codes_generated``) stay: ``users`` is a kept table and
dropping columns from it is a separate operator decision.

``downgrade`` recreates the tables with the DDL the removed runtime used so a rollback to
``0023`` is schema-complete; the dropped rows are not restored.

Revision ID: 0024_flense_park_two_factor
Revises:     0023_flense_park_enterprise_auth
"""

from alembic import op

revision = "0024_flense_park_two_factor"
down_revision = "0023_flense_park_enterprise_auth"
branch_labels = None
depends_on = None

# The DDL the removed runtime used (otp_store.ensure_otp_tables and
# recovery_codes.ensure_recovery_code_tables at 229226a88), replayed by downgrade.
_RESTORE_DDL = (
    """
    CREATE TABLE IF NOT EXISTS _dazzle_otp_codes (
        id SERIAL PRIMARY KEY,
        user_id TEXT NOT NULL,
        code_hash TEXT NOT NULL,
        method TEXT NOT NULL,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        attempts INTEGER DEFAULT 0,
        max_attempts INTEGER DEFAULT 3,
        used BOOLEAN DEFAULT FALSE
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_otp_user_method ON _dazzle_otp_codes(user_id, method)",
    "CREATE INDEX IF NOT EXISTS idx_otp_expires ON _dazzle_otp_codes(expires_at)",
    """
    CREATE TABLE IF NOT EXISTS _dazzle_recovery_codes (
        id SERIAL PRIMARY KEY,
        user_id TEXT NOT NULL,
        code_hash TEXT NOT NULL,
        used BOOLEAN DEFAULT FALSE,
        used_at TEXT,
        created_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_recovery_user ON _dazzle_recovery_codes(user_id)",
)


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS _dazzle_otp_codes, _dazzle_recovery_codes")


def downgrade() -> None:
    for ddl in _RESTORE_DDL:
        op.execute(ddl)
