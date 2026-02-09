"""
Refresh token storage and management (PostgreSQL-only).

Provides secure storage for refresh tokens with revocation support.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from dazzle_back.runtime.auth import UserRecord


# =============================================================================
# Token Models
# =============================================================================


class RefreshTokenRecord(BaseModel):
    """
    Refresh token record stored in the database.
    """

    model_config = ConfigDict(frozen=True)

    token_hash: str = Field(description="SHA-256 hash of the refresh token")
    user_id: UUID = Field(description="User ID")
    device_id: str | None = Field(default=None, description="Device identifier")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime = Field(description="Token expiration time")
    last_used_at: datetime | None = Field(default=None, description="Last usage time")
    revoked_at: datetime | None = Field(default=None, description="Revocation time")
    ip_address: str | None = Field(default=None, description="Client IP address")
    user_agent: str | None = Field(default=None, description="Client user agent")

    @property
    def is_expired(self) -> bool:
        """Check if token is expired."""
        return datetime.now(UTC) > self.expires_at

    @property
    def is_revoked(self) -> bool:
        """Check if token has been revoked."""
        return self.revoked_at is not None


# =============================================================================
# Token Store
# =============================================================================


class TokenStore:
    """
    Secure refresh token storage using PostgreSQL.

    Features:
    - Token hashing (tokens are never stored in plain text)
    - Automatic cleanup of expired tokens
    - Support for token revocation
    - Token rotation on refresh
    """

    def __init__(
        self,
        database_url: str,
        token_lifetime_days: int = 7,
        db_path: str | Path | None = None,  # Deprecated, ignored. Kept for backward compat.
    ):
        """
        Initialize the token store.

        Args:
            database_url: PostgreSQL connection URL
            token_lifetime_days: Refresh token lifetime in days
            db_path: Deprecated, ignored. Kept for backward compatibility.
        """
        self._database_url = database_url
        # Normalize Heroku's postgres:// to postgresql://
        if self._database_url.startswith("postgres://"):
            self._database_url = self._database_url.replace("postgres://", "postgresql://", 1)

        self.token_lifetime_days = token_lifetime_days
        self._init_db()

    def _get_connection(self) -> psycopg.Connection[dict[str, Any]]:
        """Get a PostgreSQL database connection."""
        return psycopg.connect(self._database_url, row_factory=dict_row)

    def _init_db(self) -> None:
        """Initialize database tables."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS refresh_tokens (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    device_id TEXT,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    last_used_at TEXT,
                    revoked_at TEXT,
                    ip_address TEXT,
                    user_agent TEXT
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user_id
                    ON refresh_tokens(user_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_refresh_tokens_expires
                    ON refresh_tokens(expires_at)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_refresh_tokens_device
                    ON refresh_tokens(user_id, device_id)
            """)
            conn.commit()
        finally:
            conn.close()

    def _hash_token(self, token: str) -> str:
        """Hash a token for storage."""
        import hashlib

        return hashlib.sha256(token.encode()).hexdigest()

    # =========================================================================
    # Token Operations
    # =========================================================================

    def create_token(
        self,
        user: UserRecord,
        device_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> str:
        """
        Create a new refresh token.

        Args:
            user: User record
            device_id: Device identifier (for device-specific tokens)
            ip_address: Client IP address
            user_agent: Client user agent

        Returns:
            Plain text refresh token (only returned once)
        """
        # Generate token
        token = secrets.token_urlsafe(32)
        token_hash = self._hash_token(token)

        now = datetime.now(UTC)
        expires_at = now + timedelta(days=self.token_lifetime_days)

        conn = self._get_connection()
        try:
            with conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO refresh_tokens
                        (token_hash, user_id, device_id, created_at, expires_at,
                         ip_address, user_agent)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        token_hash,
                        str(user.id),
                        device_id,
                        now.isoformat(),
                        expires_at.isoformat(),
                        ip_address,
                        user_agent,
                    ),
                )
        finally:
            conn.close()

        return token

    def validate_token(self, token: str) -> RefreshTokenRecord | None:
        """
        Validate a refresh token.

        Args:
            token: Plain text refresh token

        Returns:
            Token record if valid, None otherwise
        """
        token_hash = self._hash_token(token)

        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM refresh_tokens WHERE token_hash = %s",
                (token_hash,),
            )
            row = cursor.fetchone()

            if not row:
                return None

            record = RefreshTokenRecord(
                token_hash=row["token_hash"],
                user_id=UUID(row["user_id"]),
                device_id=row["device_id"],
                created_at=datetime.fromisoformat(row["created_at"]),
                expires_at=datetime.fromisoformat(row["expires_at"]),
                last_used_at=(
                    datetime.fromisoformat(row["last_used_at"]) if row["last_used_at"] else None
                ),
                revoked_at=(
                    datetime.fromisoformat(row["revoked_at"]) if row["revoked_at"] else None
                ),
                ip_address=row["ip_address"],
                user_agent=row["user_agent"],
            )

            # Check if expired or revoked
            if record.is_expired or record.is_revoked:
                return None

            return record
        finally:
            conn.close()

    def use_token(self, token: str) -> bool:
        """
        Mark a token as used.

        Updates last_used_at timestamp.

        Args:
            token: Plain text refresh token

        Returns:
            True if token was updated
        """
        token_hash = self._hash_token(token)
        now = datetime.now(UTC)

        conn = self._get_connection()
        try:
            with conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE refresh_tokens
                    SET last_used_at = %s
                    WHERE token_hash = %s AND revoked_at IS NULL
                    """,
                    (now.isoformat(), token_hash),
                )
                return bool(cursor.rowcount > 0)
        finally:
            conn.close()

    def rotate_token(
        self,
        old_token: str,
        user: UserRecord,
        device_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> str | None:
        """
        Rotate a refresh token.

        Revokes the old token and creates a new one.
        This provides protection against token theft.

        Args:
            old_token: Current refresh token
            user: User record
            device_id: Device identifier
            ip_address: Client IP address
            user_agent: Client user agent

        Returns:
            New refresh token, or None if old token is invalid
        """
        # Validate old token first
        record = self.validate_token(old_token)
        if not record:
            return None

        # Revoke old token
        self.revoke_token(old_token)

        # Create new token
        return self.create_token(
            user,
            device_id=device_id or record.device_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    def revoke_token(self, token: str) -> bool:
        """
        Revoke a refresh token.

        Args:
            token: Plain text refresh token

        Returns:
            True if token was revoked
        """
        token_hash = self._hash_token(token)
        now = datetime.now(UTC)

        conn = self._get_connection()
        try:
            with conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE refresh_tokens
                    SET revoked_at = %s
                    WHERE token_hash = %s AND revoked_at IS NULL
                    """,
                    (now.isoformat(), token_hash),
                )
                return bool(cursor.rowcount > 0)
        finally:
            conn.close()

    def revoke_user_tokens(self, user_id: UUID, except_token: str | None = None) -> int:
        """
        Revoke all tokens for a user.

        Args:
            user_id: User ID
            except_token: Token to keep (for logout from other devices)

        Returns:
            Number of tokens revoked
        """
        now = datetime.now(UTC)
        except_hash = self._hash_token(except_token) if except_token else None

        conn = self._get_connection()
        try:
            with conn:
                cursor = conn.cursor()
                if except_hash:
                    cursor.execute(
                        """
                        UPDATE refresh_tokens
                        SET revoked_at = %s
                        WHERE user_id = %s AND token_hash != %s AND revoked_at IS NULL
                        """,
                        (now.isoformat(), str(user_id), except_hash),
                    )
                else:
                    cursor.execute(
                        """
                        UPDATE refresh_tokens
                        SET revoked_at = %s
                        WHERE user_id = %s AND revoked_at IS NULL
                        """,
                        (now.isoformat(), str(user_id)),
                    )
                return int(cursor.rowcount)
        finally:
            conn.close()

    def revoke_device_tokens(self, user_id: UUID, device_id: str) -> int:
        """
        Revoke all tokens for a specific device.

        Args:
            user_id: User ID
            device_id: Device identifier

        Returns:
            Number of tokens revoked
        """
        now = datetime.now(UTC)

        conn = self._get_connection()
        try:
            with conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE refresh_tokens
                    SET revoked_at = %s
                    WHERE user_id = %s AND device_id = %s AND revoked_at IS NULL
                    """,
                    (now.isoformat(), str(user_id), device_id),
                )
                return int(cursor.rowcount)
        finally:
            conn.close()

    def get_user_tokens(self, user_id: UUID) -> list[RefreshTokenRecord]:
        """
        Get all active tokens for a user.

        Args:
            user_id: User ID

        Returns:
            List of active token records
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM refresh_tokens
                WHERE user_id = %s AND revoked_at IS NULL AND expires_at > %s
                ORDER BY created_at DESC
                """,
                (str(user_id), datetime.now(UTC).isoformat()),
            )
            rows = cursor.fetchall()

            return [
                RefreshTokenRecord(
                    token_hash=row["token_hash"],
                    user_id=UUID(row["user_id"]),
                    device_id=row["device_id"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                    expires_at=datetime.fromisoformat(row["expires_at"]),
                    last_used_at=(
                        datetime.fromisoformat(row["last_used_at"]) if row["last_used_at"] else None
                    ),
                    revoked_at=None,
                    ip_address=row["ip_address"],
                    user_agent=row["user_agent"],
                )
                for row in rows
            ]
        finally:
            conn.close()

    def cleanup_expired(self) -> int:
        """
        Remove expired and revoked tokens.

        Returns:
            Number of tokens removed
        """
        cutoff = datetime.now(UTC) - timedelta(days=1)  # Keep revoked for 1 day for audit

        conn = self._get_connection()
        try:
            with conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    DELETE FROM refresh_tokens
                    WHERE expires_at < %s OR (revoked_at IS NOT NULL AND revoked_at < %s)
                    """,
                    (datetime.now(UTC).isoformat(), cutoff.isoformat()),
                )
                return int(cursor.rowcount)
        finally:
            conn.close()
