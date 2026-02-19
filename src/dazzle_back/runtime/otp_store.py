"""
OTP (One-Time Password) store for email verification codes.

Stores hashed OTP codes in PostgreSQL with expiry and attempt limiting.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class OTPRecord(BaseModel):
    """Record for a stored OTP code."""

    model_config = ConfigDict(frozen=True)

    user_id: UUID
    code_hash: str
    method: str  # "email_otp" or "totp_setup"
    created_at: datetime
    expires_at: datetime
    attempts: int = 0
    max_attempts: int = 3
    used: bool = False


def _hash_code(code: str) -> str:
    """Hash an OTP code with SHA-256."""
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _generate_code(length: int = 6) -> str:
    """Generate a numeric OTP code.

    Args:
        length: Number of digits (default 6)

    Returns:
        Numeric string of specified length
    """
    upper = 10**length
    code = secrets.randbelow(upper)
    return f"{code:0{length}d}"


class OTPStore:
    """Database-backed OTP code store.

    Stores hashed codes in PostgreSQL for verification.
    Supports rate limiting via attempt counting.
    """

    TABLE = "_dazzle_otp_codes"

    def __init__(self, database_url: str):
        """Initialize OTP store.

        Args:
            database_url: PostgreSQL connection URL
        """
        self._database_url = database_url
        if self._database_url.startswith("postgres://"):
            self._database_url = self._database_url.replace("postgres://", "postgresql://", 1)

    def _get_connection(self) -> Any:
        """Get a PostgreSQL connection."""
        import psycopg
        from psycopg.rows import dict_row

        return psycopg.connect(self._database_url, row_factory=dict_row)

    def init_db(self) -> None:
        """Create OTP codes table if it doesn't exist."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.TABLE} (
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
            """)
            cursor.execute(
                f"CREATE INDEX IF NOT EXISTS idx_otp_user_method ON {self.TABLE}(user_id, method)"
            )
            cursor.execute(
                f"CREATE INDEX IF NOT EXISTS idx_otp_expires ON {self.TABLE}(expires_at)"
            )
            conn.commit()
        finally:
            conn.close()

    def create_otp(
        self,
        user_id: UUID,
        method: str = "email_otp",
        ttl: int = 300,
        length: int = 6,
        max_attempts: int = 3,
    ) -> str:
        """Create a new OTP code for a user.

        Invalidates any existing unused OTPs for the same user+method.

        Args:
            user_id: User UUID
            method: OTP method identifier
            ttl: Time to live in seconds (default 300 = 5 minutes)
            length: Code length in digits (default 6)
            max_attempts: Maximum verification attempts (default 3)

        Returns:
            The plaintext OTP code (for sending to user)
        """
        code = _generate_code(length)
        code_hash = _hash_code(code)
        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=ttl)

        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            # Invalidate existing unused OTPs for this user+method
            cursor.execute(
                f"UPDATE {self.TABLE} SET used = TRUE "
                f"WHERE user_id = %s AND method = %s AND used = FALSE",
                (str(user_id), method),
            )

            # Insert new OTP
            cursor.execute(
                f"INSERT INTO {self.TABLE} "
                f"(user_id, code_hash, method, created_at, expires_at, max_attempts) "
                f"VALUES (%s, %s, %s, %s, %s, %s)",
                (
                    str(user_id),
                    code_hash,
                    method,
                    now.isoformat(),
                    expires_at.isoformat(),
                    max_attempts,
                ),
            )
            conn.commit()
        finally:
            conn.close()

        return code

    def verify_otp(self, user_id: UUID, code: str, method: str = "email_otp") -> bool:
        """Verify an OTP code.

        Finds the latest unexpired, un-used OTP for user+method.
        Increments attempts counter. Uses constant-time comparison.

        Args:
            user_id: User UUID
            code: User-provided code to verify
            method: OTP method identifier

        Returns:
            True if code is valid
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            # Find latest unexpired, unused OTP for this user+method
            cursor.execute(
                f"SELECT * FROM {self.TABLE} "
                f"WHERE user_id = %s AND method = %s AND used = FALSE "
                f"AND expires_at > %s "
                f"ORDER BY created_at DESC LIMIT 1",
                (str(user_id), method, datetime.now(UTC).isoformat()),
            )
            row = cursor.fetchone()

            if not row:
                return False

            record_id = row["id"]
            stored_hash = row["code_hash"]
            attempts = row["attempts"]
            max_attempts = row["max_attempts"]

            # Check attempt limit
            if attempts >= max_attempts:
                # Mark as used (exhausted)
                cursor.execute(
                    f"UPDATE {self.TABLE} SET used = TRUE WHERE id = %s",
                    (record_id,),
                )
                conn.commit()
                return False

            # Increment attempts
            cursor.execute(
                f"UPDATE {self.TABLE} SET attempts = attempts + 1 WHERE id = %s",
                (record_id,),
            )

            # Constant-time comparison
            provided_hash = _hash_code(code)
            if hmac.compare_digest(stored_hash, provided_hash):
                # Mark as used
                cursor.execute(
                    f"UPDATE {self.TABLE} SET used = TRUE WHERE id = %s",
                    (record_id,),
                )
                conn.commit()
                return True

            conn.commit()
            return False

        finally:
            conn.close()

    def cleanup_expired(self) -> int:
        """Delete expired OTP records.

        Returns:
            Number of records deleted
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                f"DELETE FROM {self.TABLE} WHERE expires_at < %s",
                (datetime.now(UTC).isoformat(),),
            )
            count: int = cursor.rowcount
            conn.commit()
            return count
        finally:
            conn.close()
