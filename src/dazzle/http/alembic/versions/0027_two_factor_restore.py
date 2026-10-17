"""Restore two-factor sign-in storage and record the second factor on the session (DD-014).

* ``_dazzle_otp_codes`` and ``_dazzle_recovery_codes`` — re-created as dropped by
  ``0024_flense_park_two_factor``.
* ``_dazzle_2fa_challenges`` — new: the pending sign-in challenge (a hashed, short-lived,
  single-use token that is not a session) and the per-session attempt counters.
* ``users.totp_last_step`` — new: the last accepted TOTP time step (no code replay).
* ``sessions.mfa_method``, ``mfa_verified_at``, ``mfa_reference`` — new: the second
  factor the session completed (#1805).

DD-014 moved to FORCED on 2026-10-17 (consumer cyfuture: HMRC ``Gov-Client-Multi-Factor``).
The table DDL is ``dazzle.http.runtime.auth.store_two_factor.TWO_FACTOR_DDL``, which the
auth store's boot DDL also runs, so the two paths cannot drift.

Data: a TOTP secret a pre-DD-014 runtime stored in plaintext is encrypted here with
``DAZZLE_CONNECTION_SECRET`` (the migration fails, naming the variable, if such rows exist
and the key is not set). ``recovery_codes_generated`` is reset for users whose codes
``0024`` dropped, so the settings page offers fresh ones.

Revision ID: 0027_two_factor_restore
Revises:     0026_enterprise_auth_oidc_scim
"""

import sqlalchemy as sa
from alembic import op

from dazzle.http.runtime.auth.connection_crypto import encrypt_secret
from dazzle.http.runtime.auth.store import SESSION_MFA_COLUMNS
from dazzle.http.runtime.auth.store_two_factor import TWO_FACTOR_DDL, is_plaintext_totp_secret

revision = "0027_two_factor_restore"
down_revision = "0026_enterprise_auth_oidc_scim"
branch_labels = None
depends_on = None

_TABLES = ("_dazzle_2fa_challenges", "_dazzle_recovery_codes", "_dazzle_otp_codes")


def upgrade() -> None:
    for statement in TWO_FACTOR_DDL:
        op.execute(statement)
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS totp_last_step BIGINT")
    for column in SESSION_MFA_COLUMNS:
        op.execute(f"ALTER TABLE sessions ADD COLUMN IF NOT EXISTS {column} TEXT")

    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, totp_secret FROM users WHERE totp_secret IS NOT NULL")
    ).fetchall()
    for user_id, secret in rows:
        if is_plaintext_totp_secret(secret):
            bind.execute(
                sa.text("UPDATE users SET totp_secret = :enc WHERE id = :id"),
                {"enc": encrypt_secret(secret), "id": user_id},
            )
    op.execute(
        "UPDATE users SET recovery_codes_generated = FALSE "
        "WHERE recovery_codes_generated = TRUE AND NOT EXISTS ("
        "SELECT 1 FROM _dazzle_recovery_codes r WHERE r.user_id = users.id AND r.used = FALSE)"
    )


def downgrade() -> None:
    for column in SESSION_MFA_COLUMNS:
        op.execute(f"ALTER TABLE sessions DROP COLUMN IF EXISTS {column}")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS totp_last_step")
    op.execute(f"DROP TABLE IF EXISTS {', '.join(_TABLES)}")
