"""
Recovery code generation and storage for two-factor authentication.

Recovery codes are one-time-use backup codes that allow users to
regain access when they lose their TOTP device.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime
from typing import Any
from uuid import UUID


def generate_recovery_codes(count: int = 8) -> list[str]:
    """Generate a set of recovery codes.

    Each code is 8 alphanumeric characters in XXXX-XXXX format.

    Args:
        count: Number of codes to generate (default 8)

    Returns:
        List of recovery code strings (e.g., ["A1B2-C3D4", ...])
    """
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # No I, O, 0, 1 for readability
    codes: list[str] = []
    for _ in range(count):
        part1 = "".join(secrets.choice(alphabet) for _ in range(4))
        part2 = "".join(secrets.choice(alphabet) for _ in range(4))
        codes.append(f"{part1}-{part2}")
    return codes


def _hash_code(code: str) -> str:
    """Hash a recovery code with SHA-256.

    Normalizes by stripping dashes and uppercasing before hashing.
    """
    normalized = code.replace("-", "").upper()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class RecoveryCodeStore:
    """Database-backed recovery code storage.

    Stores hashed codes in PostgreSQL. Each code can only be used once.
    """

    TABLE = "_dazzle_recovery_codes"

    def __init__(self, database_url: str):
        """Initialize recovery code store.

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
        """Create recovery codes table if it doesn't exist."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.TABLE} (
                    id SERIAL PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    code_hash TEXT NOT NULL,
                    used BOOLEAN DEFAULT FALSE,
                    used_at TEXT,
                    created_at TEXT NOT NULL
                )
            """)
            cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_recovery_user ON {self.TABLE}(user_id)")
            conn.commit()
        finally:
            conn.close()

    def store_codes(self, user_id: UUID, codes: list[str]) -> None:
        """Store a set of recovery codes for a user.

        Replaces any existing codes for the user.

        Args:
            user_id: User UUID
            codes: List of plaintext recovery codes
        """
        now = datetime.now(UTC).isoformat()

        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            # Delete existing codes for this user
            cursor.execute(
                f"DELETE FROM {self.TABLE} WHERE user_id = %s",
                (str(user_id),),
            )

            # Insert new codes
            for code in codes:
                cursor.execute(
                    f"INSERT INTO {self.TABLE} (user_id, code_hash, created_at) "
                    f"VALUES (%s, %s, %s)",
                    (str(user_id), _hash_code(code), now),
                )

            conn.commit()
        finally:
            conn.close()

    def verify_code(self, user_id: UUID, code: str) -> bool:
        """Verify and consume a recovery code.

        Uses constant-time comparison. Marks the code as used on success.

        Args:
            user_id: User UUID
            code: User-provided recovery code

        Returns:
            True if code is valid and unused
        """
        provided_hash = _hash_code(code)

        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            # Find all unused codes for this user
            cursor.execute(
                f"SELECT id, code_hash FROM {self.TABLE} WHERE user_id = %s AND used = FALSE",
                (str(user_id),),
            )
            rows = cursor.fetchall()

            for row in rows:
                if hmac.compare_digest(row["code_hash"], provided_hash):
                    # Mark as used
                    cursor.execute(
                        f"UPDATE {self.TABLE} SET used = TRUE, used_at = %s WHERE id = %s",
                        (datetime.now(UTC).isoformat(), row["id"]),
                    )
                    conn.commit()
                    return True

            return False
        finally:
            conn.close()

    def remaining_count(self, user_id: UUID) -> int:
        """Count unused recovery codes for a user.

        Args:
            user_id: User UUID

        Returns:
            Number of unused codes remaining
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                f"SELECT COUNT(*) as count FROM {self.TABLE} WHERE user_id = %s AND used = FALSE",
                (str(user_id),),
            )
            row = cursor.fetchone()
            return int(row["count"]) if row else 0
        finally:
            conn.close()
