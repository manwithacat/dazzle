"""Magic link tokens for one-time authentication.

Reusable primitive for CLI impersonation, passwordless email login,
and API-driven session creation.
"""

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

MAGIC_LINKS_DDL = """
CREATE TABLE IF NOT EXISTS magic_links (
    token TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    used_at TEXT,
    created_by TEXT
)
"""


def create_magic_link(
    store: Any,
    *,
    user_id: str,
    ttl_seconds: int = 300,
    created_by: str = "cli",
) -> str:
    token = secrets.token_urlsafe(32)
    expires_at = (datetime.now(UTC) + timedelta(seconds=ttl_seconds)).isoformat()
    store._execute_modify(
        "INSERT INTO magic_links (token, user_id, expires_at, created_by) VALUES (%s, %s, %s, %s)",
        (token, str(user_id), expires_at, created_by),
    )
    return token


def validate_magic_link(store: Any, token: str) -> str | None:
    rows = store._execute(
        "SELECT user_id, expires_at, used_at FROM magic_links WHERE token = %s",
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
    store._execute_modify(
        "UPDATE magic_links SET used_at = %s WHERE token = %s",
        (datetime.now(UTC).isoformat(), token),
    )
    return str(row["user_id"])
