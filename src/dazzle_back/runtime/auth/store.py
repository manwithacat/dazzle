"""Authentication store (PostgreSQL) — user CRUD, sessions, and 2FA state."""

import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

try:
    import psycopg
    from psycopg.rows import dict_row

    PSYCOPG_AVAILABLE = True
except ImportError:
    psycopg = None  # type: ignore[assignment]
    dict_row = None  # type: ignore[assignment]
    PSYCOPG_AVAILABLE = False

from .crypto import hash_password, verify_password
from .models import AuthContext, SessionRecord, UserRecord

logger = logging.getLogger(__name__)


class UserStoreMixin:
    """User CRUD, password management, and password reset tokens."""

    # These methods are provided by AuthStore.__init__ via mixin composition.
    _execute: Any
    _execute_one: Any
    _execute_modify: Any

    def create_user(
        self,
        email: str,
        password: str,
        username: str | None = None,
        is_superuser: bool = False,
        roles: list[str] | None = None,
    ) -> UserRecord:
        """
        Create a new user.

        Args:
            email: User email
            password: Plain text password
            username: Optional username
            is_superuser: Is superuser flag
            roles: List of role names

        Returns:
            Created user record
        """
        import json

        user = UserRecord(
            email=email,
            password_hash=hash_password(password),
            username=username,
            is_superuser=is_superuser,
            roles=roles or [],
        )

        self._execute(
            """
            INSERT INTO users (id, email, password_hash, username, is_active,
                               is_superuser, roles, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                str(user.id),
                user.email,
                user.password_hash,
                user.username,
                user.is_active,
                user.is_superuser,
                json.dumps(user.roles),
                user.created_at.isoformat(),
                user.updated_at.isoformat(),
            ),
        )

        return user

    def _row_to_user(self, row: dict[str, Any]) -> UserRecord:
        """Convert a database row to UserRecord."""
        import json

        return UserRecord(
            id=UUID(row["id"]),
            email=row["email"],
            password_hash=row["password_hash"],
            username=row["username"],
            is_active=bool(row["is_active"]),
            is_superuser=bool(row["is_superuser"]),
            roles=json.loads(row["roles"]),
            totp_secret=row.get("totp_secret"),
            totp_enabled=bool(row.get("totp_enabled", False)),
            email_otp_enabled=bool(row.get("email_otp_enabled", False)),
            recovery_codes_generated=bool(row.get("recovery_codes_generated", False)),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def get_user_by_email(self, email: str) -> UserRecord | None:
        """Get user by email."""
        row = self._execute_one("SELECT * FROM users WHERE email = %s", (email,))
        return self._row_to_user(row) if row else None

    def get_user_by_id(self, user_id: UUID) -> UserRecord | None:
        """Get user by ID."""
        row = self._execute_one("SELECT * FROM users WHERE id = %s", (str(user_id),))
        return self._row_to_user(row) if row else None

    def authenticate(self, email: str, password: str) -> UserRecord | None:
        """
        Authenticate user by email and password.

        Returns user if credentials are valid, None otherwise.
        """
        user = self.get_user_by_email(email)

        if user and user.is_active and verify_password(password, user.password_hash):
            return user

        return None

    def update_password(self, user_id: UUID, new_password: str) -> bool:
        """Update user password."""
        rowcount = self._execute_modify(
            """
            UPDATE users
            SET password_hash = %s, updated_at = %s
            WHERE id = %s
            """,
            (hash_password(new_password), datetime.now(UTC).isoformat(), str(user_id)),
        )
        return bool(rowcount > 0)

    def create_password_reset_token(
        self,
        user_id: UUID,
        expires_in: timedelta | None = None,
    ) -> str:
        """Create a password reset token for the given user.

        Args:
            user_id: User to create reset token for.
            expires_in: Token lifetime (default 1 hour).

        Returns:
            The generated token string.
        """
        if expires_in is None:
            expires_in = timedelta(hours=1)

        token = secrets.token_urlsafe(32)
        now = datetime.now(UTC)
        expires_at = now + expires_in

        # Invalidate any existing unused tokens for this user
        self._execute_modify(
            "UPDATE password_reset_tokens SET used = TRUE WHERE user_id = %s AND used = FALSE",
            (str(user_id),),
        )

        self._execute_modify(
            """
            INSERT INTO password_reset_tokens (token, user_id, created_at, expires_at, used)
            VALUES (%s, %s, %s, %s, FALSE)
            """,
            (token, str(user_id), now.isoformat(), expires_at.isoformat()),
        )

        return token

    def validate_password_reset_token(self, token: str) -> UserRecord | None:
        """Validate a password reset token and return the associated user.

        Returns None if the token is invalid, expired, or already used.
        """
        rows = self._execute(
            "SELECT * FROM password_reset_tokens WHERE token = %s",
            (token,),
        )

        if not rows:
            return None

        row = rows[0]
        if row.get("used") is True:
            return None

        expires_at = datetime.fromisoformat(row["expires_at"])
        if datetime.now(UTC) > expires_at:
            return None

        user_id = UUID(row["user_id"])
        return self.get_user_by_id(user_id)

    def consume_password_reset_token(self, token: str) -> bool:
        """Mark a password reset token as used.

        Returns True if the token was successfully consumed.
        """
        rowcount = self._execute_modify(
            "UPDATE password_reset_tokens SET used = TRUE WHERE token = %s AND used = FALSE",
            (token,),
        )
        return bool(rowcount > 0)

    def list_users(
        self,
        active_only: bool = True,
        role: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[UserRecord]:
        """
        List users with optional filters.

        Args:
            active_only: Only return active users
            role: Filter by role (Python-side, checks JSON roles array)
            limit: Maximum users to return
            offset: Number of users to skip for pagination

        Returns:
            List of matching UserRecord objects
        """
        conditions: list[str] = []
        params: list[object] = []

        if active_only:
            conditions.append("is_active = TRUE")

        where_clause = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"SELECT * FROM users{where_clause} ORDER BY created_at DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        rows = self._execute(query, tuple(params))

        users = []
        for row in rows:
            user = self._row_to_user(row)
            if role and role not in user.roles:
                continue
            users.append(user)

        return users

    def update_user(
        self,
        user_id: UUID,
        username: str | None = None,
        roles: list[str] | None = None,
        is_active: bool | None = None,
        is_superuser: bool | None = None,
    ) -> UserRecord | None:
        """
        Update a user's properties.

        Args:
            user_id: User UUID
            username: New display name
            roles: New roles list (replaces existing)
            is_active: Set active status
            is_superuser: Set superuser status

        Returns:
            Updated UserRecord, or None if user not found or no updates provided
        """
        import json

        updates: list[str] = []
        params: list[object] = []

        if username is not None:
            updates.append("username = %s")
            params.append(username)

        if roles is not None:
            updates.append("roles = %s")
            params.append(json.dumps(roles))

        if is_active is not None:
            updates.append("is_active = %s")
            params.append(is_active)

        if is_superuser is not None:
            updates.append("is_superuser = %s")
            params.append(is_superuser)

        if not updates:
            return None

        updates.append("updated_at = %s")
        params.append(datetime.now(UTC).isoformat())
        params.append(str(user_id))

        query = f"UPDATE users SET {', '.join(updates)} WHERE id = %s"
        rowcount = self._execute_modify(query, tuple(params))

        if rowcount == 0:
            return None

        return self.get_user_by_id(user_id)


class TwoFactorMixin:
    """Two-factor authentication state management."""

    _execute: Any
    _execute_one: Any
    _execute_modify: Any
    get_user_by_id: Any

    def enable_totp(self, user_id: UUID, secret: str) -> None:
        """Enable TOTP for a user and store the encrypted secret.

        Args:
            user_id: User UUID
            secret: Base32-encoded TOTP secret
        """
        self._execute_modify(
            "UPDATE users SET totp_secret = %s, totp_enabled = TRUE, updated_at = %s WHERE id = %s",
            (secret, datetime.now(UTC).isoformat(), str(user_id)),
        )

    def disable_totp(self, user_id: UUID) -> None:
        """Disable TOTP for a user and clear the secret."""
        self._execute_modify(
            "UPDATE users SET totp_secret = NULL, totp_enabled = FALSE, updated_at = %s "
            "WHERE id = %s",
            (datetime.now(UTC).isoformat(), str(user_id)),
        )

    def enable_email_otp(self, user_id: UUID) -> None:
        """Enable email OTP for a user."""
        self._execute_modify(
            "UPDATE users SET email_otp_enabled = TRUE, updated_at = %s WHERE id = %s",
            (datetime.now(UTC).isoformat(), str(user_id)),
        )

    def disable_email_otp(self, user_id: UUID) -> None:
        """Disable email OTP for a user."""
        self._execute_modify(
            "UPDATE users SET email_otp_enabled = FALSE, updated_at = %s WHERE id = %s",
            (datetime.now(UTC).isoformat(), str(user_id)),
        )

    def set_recovery_codes_generated(self, user_id: UUID, generated: bool = True) -> None:
        """Mark whether recovery codes have been generated for a user."""
        self._execute_modify(
            "UPDATE users SET recovery_codes_generated = %s, updated_at = %s WHERE id = %s",
            (generated, datetime.now(UTC).isoformat(), str(user_id)),
        )

    def get_totp_secret(self, user_id: UUID) -> str | None:
        """Get the TOTP secret for a user.

        Args:
            user_id: User UUID

        Returns:
            Base32-encoded TOTP secret or None
        """
        row = self._execute_one("SELECT totp_secret FROM users WHERE id = %s", (str(user_id),))
        return row["totp_secret"] if row else None


class SessionStoreMixin:
    """Session lifecycle, validation, and cleanup."""

    # These methods are provided by AuthStore.__init__ via mixin composition.
    _execute: Any
    _execute_one: Any
    _execute_modify: Any

    # Cross-cutting method provided by UserStoreMixin via AuthStore.
    get_user_by_id: Any

    def create_session(
        self,
        user: UserRecord,
        expires_in: timedelta = timedelta(days=7),
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> SessionRecord:
        """
        Create a new session for a user.

        Args:
            user: User record
            expires_in: Session expiration time
            ip_address: Client IP address
            user_agent: Client user agent

        Returns:
            Created session record
        """
        session = SessionRecord(
            user_id=user.id,
            expires_at=datetime.now(UTC) + expires_in,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        self._execute(
            """
            INSERT INTO sessions (id, user_id, created_at, expires_at, ip_address, user_agent)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                session.id,
                str(session.user_id),
                session.created_at.isoformat(),
                session.expires_at.isoformat(),
                session.ip_address,
                session.user_agent,
            ),
        )

        return session

    def get_session(self, session_id: str) -> SessionRecord | None:
        """Get session by ID."""
        row = self._execute_one("SELECT * FROM sessions WHERE id = %s", (session_id,))

        if row:
            return SessionRecord(
                id=row["id"],
                user_id=UUID(row["user_id"]),
                created_at=datetime.fromisoformat(row["created_at"]),
                expires_at=datetime.fromisoformat(row["expires_at"]),
                ip_address=row["ip_address"],
                user_agent=row["user_agent"],
            )

        return None

    def validate_session(self, session_id: str) -> AuthContext:
        """
        Validate a session and return auth context.

        Returns AuthContext with is_authenticated=True if session is valid.
        """
        session = self.get_session(session_id)

        if not session:
            return AuthContext()

        # Check expiration
        if session.expires_at < datetime.now(UTC):
            self.delete_session(session_id)
            return AuthContext()

        # Get user
        user = self.get_user_by_id(session.user_id)

        if not user or not user.is_active:
            self.delete_session(session_id)
            return AuthContext()

        return AuthContext(
            user=user,
            session=session,
            is_authenticated=True,
            roles=user.roles,
        )

    def delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        rowcount = self._execute_modify("DELETE FROM sessions WHERE id = %s", (session_id,))
        return bool(rowcount > 0)

    def delete_user_sessions(self, user_id: UUID) -> int:
        """Delete all sessions for a user."""
        return int(self._execute_modify("DELETE FROM sessions WHERE user_id = %s", (str(user_id),)))

    def count_active_sessions(self, user_id: UUID) -> int:
        """
        Count active (non-expired) sessions for a user.

        Args:
            user_id: User UUID

        Returns:
            Number of active sessions
        """
        rows = self._execute(
            "SELECT COUNT(*) as count FROM sessions WHERE user_id = %s AND expires_at > %s",
            (str(user_id), datetime.now(UTC).isoformat()),
        )
        return int(rows[0]["count"]) if rows else 0

    def cleanup_expired_sessions(self) -> int:
        """Delete all expired sessions."""
        return int(
            self._execute_modify(
                "DELETE FROM sessions WHERE expires_at < %s",
                (datetime.now(UTC).isoformat(),),
            )
        )


class AuthStore(UserStoreMixin, SessionStoreMixin, TwoFactorMixin):
    """
    Authentication store using PostgreSQL.

    Manages users and sessions in a separate auth database.
    Combines UserStoreMixin (user CRUD, passwords) and
    SessionStoreMixin (session lifecycle, validation).
    """

    def __init__(
        self,
        database_url: str,
    ):
        """
        Initialize the auth store.

        Args:
            database_url: PostgreSQL connection URL
        """
        self._database_url = database_url
        # Normalize Heroku's postgres:// to postgresql://
        if self._database_url.startswith("postgres://"):
            self._database_url = self._database_url.replace("postgres://", "postgresql://", 1)

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
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    username TEXT,
                    is_active BOOLEAN DEFAULT TRUE,
                    is_superuser BOOLEAN DEFAULT FALSE,
                    roles TEXT DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            # Add 2FA columns if they don't exist (idempotent migration)
            for col, col_type, default in [
                ("totp_secret", "TEXT", None),
                ("totp_enabled", "BOOLEAN", "FALSE"),
                ("email_otp_enabled", "BOOLEAN", "FALSE"),
                ("recovery_codes_generated", "BOOLEAN", "FALSE"),
            ]:
                try:
                    default_clause = f" DEFAULT {default}" if default else ""
                    cursor.execute(
                        f"ALTER TABLE users ADD COLUMN IF NOT EXISTS "
                        f"{col} {col_type}{default_clause}"
                    )
                except Exception:
                    logger.debug("Column %s may already exist: %s", col, col_type)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id),
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    ip_address TEXT,
                    user_agent TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS password_reset_tokens (
                    token TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id),
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    used BOOLEAN DEFAULT FALSE
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id)")
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_reset_tokens_user ON password_reset_tokens(user_id)"
            )
            conn.commit()
        finally:
            conn.close()

    def _execute(self, query: str, params: tuple[object, ...] = ()) -> list[dict[str, Any]]:
        """Execute a query and return results as list of dicts."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(query, params)
            if cursor.description:
                return [dict(row) for row in cursor.fetchall()]
            conn.commit()
            return []
        finally:
            conn.close()

    def _execute_one(self, query: str, params: tuple[object, ...] = ()) -> dict[str, Any] | None:
        """Execute a query and return single result."""
        results = self._execute(query, params)
        return results[0] if results else None

    def _execute_modify(self, query: str, params: tuple[object, ...] = ()) -> int:
        """Execute a modification query and return rowcount."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rowcount: int = cursor.rowcount
            conn.commit()
            return rowcount
        finally:
            conn.close()
