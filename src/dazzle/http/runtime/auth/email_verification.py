"""Email-verification tokens for password-signup flows (#1109).

DB-backed one-shot tokens that flip ``users.email_verified=true`` when
consumed. Mirrors the ``magic_link.py`` primitive deliberately — same
shape, same TTL semantics, same store interface — so the operational
contract is consistent across the framework's email-mediated auth
flows (magic-link login, magic-link signup, password reset, email
verification).

Tokens are opaque, unpredictable ``secrets.token_urlsafe(32)`` strings
stored alongside the issuing ``user_id`` and an ``expires_at`` field.
``validate_email_verification_token`` consumes them atomically: a
successful match clears the token + flips ``email_verified`` in a
single transaction so a captured token can't be replayed.
"""

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

EMAIL_VERIFICATION_TOKENS_DDL = """
CREATE TABLE IF NOT EXISTS email_verification_tokens (
    token TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    used_at TEXT,
    created_by TEXT
)
"""

# 24 hours — long enough for a user to find the email in spam and click
# through, short enough that a leaked token doesn't stay live forever.
DEFAULT_TOKEN_TTL_HOURS = 24


def create_email_verification_token(
    store: Any,
    *,
    user_id: str,
    ttl_hours: int = DEFAULT_TOKEN_TTL_HOURS,
    created_by: str = "signup",
) -> str:
    """Mint a new email-verification token for ``user_id``.

    Returns the opaque token string — callers compose the verification
    URL by embedding it in the path (``/auth/verify-email?token=…``).
    Multiple tokens per user are allowed; ``validate`` invalidates the
    consumed one but doesn't sweep others, so a resend cycle that
    produces three tokens has all three live until each expires or
    is used.
    """
    token = secrets.token_urlsafe(32)
    expires_at = (datetime.now(UTC) + timedelta(hours=ttl_hours)).isoformat()
    store._execute_modify(
        "INSERT INTO email_verification_tokens "
        "(token, user_id, expires_at, created_by) VALUES (%s, %s, %s, %s)",
        (token, str(user_id), expires_at, created_by),
    )
    return token


def validate_email_verification_token(store: Any, token: str) -> str | None:
    """Consume a verification token. Returns the ``user_id`` on success.

    Atomic: a single ``UPDATE`` flips ``used_at`` on the token AND
    ``email_verified=true`` on the user record. Returns ``None`` for any
    of: unknown token, expired token, already-used token, missing user.
    """
    rows = store._execute(
        "SELECT user_id, expires_at, used_at FROM email_verification_tokens WHERE token = %s",
        (token,),
    )
    if not rows:
        return None
    row = rows[0]
    if row["used_at"] is not None:
        return None
    expires_at = datetime.fromisoformat(row["expires_at"])
    if datetime.now(UTC) > expires_at:
        return None

    user_id = str(row["user_id"])
    now_iso = datetime.now(UTC).isoformat()
    store._execute_modify(
        "UPDATE email_verification_tokens SET used_at = %s WHERE token = %s",
        (now_iso, token),
    )
    # Flip the user's verified flag. Mark_email_verified updates the
    # users table; callers should never have to flip both — the token
    # primitive owns the lifecycle.
    if hasattr(store, "mark_email_verified"):
        store.mark_email_verified(user_id)
    return user_id
