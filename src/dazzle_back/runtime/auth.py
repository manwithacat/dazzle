"""
Authentication runtime for DNR Backend (PostgreSQL-only).

Provides session-based authentication with cookie management.
"""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

try:
    import psycopg
    from psycopg.rows import dict_row

    PSYCOPG_AVAILABLE = True
except ImportError:
    psycopg = None  # type: ignore[assignment]
    dict_row = None  # type: ignore[assignment]
    PSYCOPG_AVAILABLE = False

# FastAPI is optional - import for type hints and runtime
try:
    from fastapi import Request as FastAPIRequest

    FASTAPI_AVAILABLE = True
except ImportError:
    FastAPIRequest = None  # type: ignore
    FASTAPI_AVAILABLE = False

if TYPE_CHECKING:
    from fastapi import APIRouter

    from dazzle_back.runtime.jwt_auth import JWTService
    from dazzle_back.runtime.token_store import TokenStore


# =============================================================================
# User Model
# =============================================================================


class UserRecord(BaseModel):
    """User record for authentication."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    email: str
    password_hash: str
    username: str | None = None
    is_active: bool = True
    is_superuser: bool = False
    roles: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SessionRecord(BaseModel):
    """Session record for authentication."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: secrets.token_urlsafe(32))
    user_id: UUID
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime
    ip_address: str | None = None
    user_agent: str | None = None


class AuthContext(BaseModel):
    """Current authentication context."""

    user: UserRecord | None = None
    session: SessionRecord | None = None
    is_authenticated: bool = False
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)

    @property
    def user_id(self) -> UUID | None:
        """Get the authenticated user's ID, or None if not authenticated."""
        return self.user.id if self.user else None


# =============================================================================
# Password Hashing
# =============================================================================


def hash_password(password: str, salt: str | None = None) -> str:
    """Hash a password with salt."""
    if salt is None:
        salt = secrets.token_hex(16)

    # Use PBKDF2 with SHA-256
    key = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        100000,  # iterations
    )

    return f"{salt}${key.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its hash."""
    try:
        salt, _ = password_hash.split("$")
        return hash_password(password, salt) == password_hash
    except ValueError:
        return False


# =============================================================================
# Auth Store (PostgreSQL)
# =============================================================================


class AuthStore:
    """
    Authentication store using PostgreSQL.

    Manages users and sessions in a separate auth database.
    """

    def __init__(
        self,
        database_url: str,
        db_path: str | Path | None = None,  # Deprecated, ignored. Kept for backward compat.
    ):
        """
        Initialize the auth store.

        Args:
            database_url: PostgreSQL connection URL
            db_path: Deprecated, ignored. Kept for backward compatibility.
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

    # =========================================================================
    # User Operations
    # =========================================================================

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
        return rowcount > 0

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
        return rowcount > 0

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
        return rows[0]["count"] if rows else 0

    # =========================================================================
    # Session Operations
    # =========================================================================

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
        return rowcount > 0

    def delete_user_sessions(self, user_id: UUID) -> int:
        """Delete all sessions for a user."""
        return self._execute_modify("DELETE FROM sessions WHERE user_id = %s", (str(user_id),))

    def cleanup_expired_sessions(self) -> int:
        """Delete all expired sessions."""
        return self._execute_modify(
            "DELETE FROM sessions WHERE expires_at < %s",
            (datetime.now(UTC).isoformat(),),
        )


# =============================================================================
# Auth Middleware
# =============================================================================


class AuthMiddleware:
    """
    Authentication middleware for FastAPI.

    Validates session cookies and sets auth context on request.
    """

    def __init__(
        self,
        auth_store: AuthStore,
        cookie_name: str = "dazzle_session",
        exclude_paths: list[str] | None = None,
    ):
        """
        Initialize the auth middleware.

        Args:
            auth_store: Auth store instance
            cookie_name: Session cookie name
            exclude_paths: Paths to exclude from auth
        """
        self.auth_store = auth_store
        self.cookie_name = cookie_name
        self.exclude_paths = exclude_paths or [
            "/health",
            "/docs",
            "/openapi.json",
            "/redoc",
            "/auth/login",
            "/auth/register",
            "/auth/forgot-password",
            "/auth/reset-password",
        ]

    def get_auth_context(self, request: FastAPIRequest) -> AuthContext:
        """
        Get auth context from request.

        Reads session cookie and validates session.
        """
        session_id = request.cookies.get(self.cookie_name)

        if not session_id:
            return AuthContext()

        return self.auth_store.validate_session(session_id)

    def is_excluded_path(self, path: str) -> bool:
        """Check if path is excluded from auth."""
        for excluded in self.exclude_paths:
            if path.startswith(excluded):
                return True
        return False


# =============================================================================
# Auth Router Factory
# =============================================================================


class LoginRequest(BaseModel):
    """Login request body."""

    email: str
    password: str


class RegisterRequest(BaseModel):
    """Registration request body."""

    email: str
    password: str
    username: str | None = None


class ChangePasswordRequest(BaseModel):
    """Change password request body."""

    current_password: str
    new_password: str


def create_auth_routes(
    auth_store: AuthStore,
    cookie_name: str = "dazzle_session",
    session_expires_days: int = 7,
) -> APIRouter:
    """
    Create authentication routes for FastAPI.

    Returns a router with login, logout, register, and me endpoints.
    """
    if not FASTAPI_AVAILABLE:
        raise RuntimeError("FastAPI is required for auth routes")

    from fastapi import APIRouter, HTTPException
    from fastapi.responses import JSONResponse
    from starlette.responses import Response

    router = APIRouter(prefix="/auth", tags=["Authentication"])

    # =========================================================================
    # Login
    # =========================================================================

    @router.post("/login")
    async def login(credentials: LoginRequest, request: FastAPIRequest) -> JSONResponse:
        """
        Login with email and password.

        Returns session cookie on success.
        """
        user = auth_store.authenticate(credentials.email, credentials.password)

        if not user:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        # Create session
        session = auth_store.create_session(
            user,
            expires_in=timedelta(days=session_expires_days),
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )

        # Return response with cookie
        response = JSONResponse(
            content={
                "user": {
                    "id": str(user.id),
                    "email": user.email,
                    "username": user.username,
                    "roles": user.roles,
                },
                "message": "Login successful",
            }
        )

        response.set_cookie(
            key=cookie_name,
            value=session.id,
            httponly=True,
            secure=False,  # Set to True in production with HTTPS
            samesite="lax",
            max_age=session_expires_days * 24 * 60 * 60,
        )

        return response

    # =========================================================================
    # Logout
    # =========================================================================

    @router.post("/logout")
    async def logout(request: FastAPIRequest) -> Response:
        """
        Logout and delete session.

        HTML form submissions (no JSON accept header) are redirected to /login.
        API callers receive a JSON response.
        """
        from fastapi.responses import RedirectResponse

        session_id = request.cookies.get(cookie_name)

        if session_id:
            auth_store.delete_session(session_id)

        # Detect HTML form submission (browser) vs API call
        accept = request.headers.get("accept", "")
        is_browser = "text/html" in accept and "application/json" not in accept

        response: Response
        if is_browser:
            response = RedirectResponse(url="/login", status_code=303)
        else:
            response = JSONResponse(content={"message": "Logout successful"})
        response.delete_cookie(cookie_name)

        return response

    # =========================================================================
    # Register
    # =========================================================================

    @router.post("/register", status_code=201)
    async def register(data: RegisterRequest, request: FastAPIRequest) -> JSONResponse:
        """
        Register a new user.
        """
        # Check if user exists
        if auth_store.get_user_by_email(data.email):
            raise HTTPException(status_code=400, detail="Email already registered")

        # Create user
        try:
            user = auth_store.create_user(
                email=data.email,
                password=data.password,
                username=data.username,
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

        # Auto-login after registration
        session = auth_store.create_session(
            user,
            expires_in=timedelta(days=session_expires_days),
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )

        response = JSONResponse(
            content={
                "user": {
                    "id": str(user.id),
                    "email": user.email,
                    "username": user.username,
                    "roles": user.roles,
                },
                "message": "Registration successful",
            },
            status_code=201,
        )

        response.set_cookie(
            key=cookie_name,
            value=session.id,
            httponly=True,
            secure=False,
            samesite="lax",
            max_age=session_expires_days * 24 * 60 * 60,
        )

        return response

    # =========================================================================
    # Get Current User
    # =========================================================================

    @router.get("/me")
    async def get_me(request: FastAPIRequest) -> dict[str, Any]:
        """
        Get current authenticated user.
        """
        session_id = request.cookies.get(cookie_name)

        if not session_id:
            raise HTTPException(status_code=401, detail="Not authenticated")

        auth_context = auth_store.validate_session(session_id)

        if not auth_context.is_authenticated:
            raise HTTPException(status_code=401, detail="Session expired")

        user = auth_context.user
        if user is None:
            raise HTTPException(status_code=401, detail="User not found")

        return {
            "id": str(user.id),
            "email": user.email,
            "username": user.username,
            "roles": user.roles,
            "is_superuser": user.is_superuser,
        }

    # =========================================================================
    # Change Password
    # =========================================================================

    @router.post("/change-password")
    async def change_password(data: ChangePasswordRequest, request: FastAPIRequest) -> JSONResponse:
        """
        Change current user's password.
        """
        session_id = request.cookies.get(cookie_name)

        if not session_id:
            raise HTTPException(status_code=401, detail="Not authenticated")

        auth_context = auth_store.validate_session(session_id)

        if not auth_context.is_authenticated:
            raise HTTPException(status_code=401, detail="Session expired")

        user = auth_context.user
        if user is None:
            raise HTTPException(status_code=401, detail="User not found")

        # Verify current password
        if not verify_password(data.current_password, user.password_hash):
            raise HTTPException(status_code=400, detail="Current password is incorrect")

        # Update password
        auth_store.update_password(user.id, data.new_password)

        # Invalidate all other sessions
        auth_store.delete_user_sessions(user.id)

        # Create new session
        session = auth_store.create_session(
            user,
            expires_in=timedelta(days=session_expires_days),
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )

        response = JSONResponse(content={"message": "Password changed successfully"})

        response.set_cookie(
            key=cookie_name,
            value=session.id,
            httponly=True,
            secure=False,
            samesite="lax",
            max_age=session_expires_days * 24 * 60 * 60,
        )

        return response

    # =========================================================================
    # Forgot Password (request reset)
    # =========================================================================

    @router.post("/forgot-password")
    async def forgot_password(data: ForgotPasswordRequest) -> JSONResponse:
        """
        Request a password reset.

        Always returns 200 to avoid user enumeration. If the email exists,
        a reset token is created and logged (email delivery is integration-dependent).
        """
        import logging

        logger = logging.getLogger("dazzle.auth")

        user = auth_store.get_user_by_email(data.email)

        if user and user.is_active:
            token = auth_store.create_password_reset_token(user.id)
            # Log the reset link — actual email delivery requires an integration
            logger.info(
                "Password reset requested for %s — token: %s "
                "(deliver via /auth/reset-password?token=%s)",
                data.email,
                token,
                token,
            )

        # Always return success to prevent user enumeration
        return JSONResponse(
            content={
                "message": (
                    "If an account with that email exists, a password reset link has been sent."
                )
            }
        )

    # =========================================================================
    # Reset Password (consume token + set new password)
    # =========================================================================

    @router.post("/reset-password")
    async def reset_password(data: ResetPasswordRequest, request: FastAPIRequest) -> JSONResponse:
        """
        Reset password using a valid reset token.

        Validates the token, updates the password, invalidates existing sessions,
        and auto-logs the user in.
        """
        user = auth_store.validate_password_reset_token(data.token)

        if not user:
            raise HTTPException(status_code=400, detail="Invalid or expired reset token")

        # Update password and consume token
        auth_store.update_password(user.id, data.new_password)
        auth_store.consume_password_reset_token(data.token)

        # Invalidate all existing sessions
        auth_store.delete_user_sessions(user.id)

        # Auto-login with new session
        session = auth_store.create_session(
            user,
            expires_in=timedelta(days=session_expires_days),
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )

        response = JSONResponse(content={"message": "Password reset successful"})

        response.set_cookie(
            key=cookie_name,
            value=session.id,
            httponly=True,
            secure=False,
            samesite="lax",
            max_age=session_expires_days * 24 * 60 * 60,
        )

        return response

    return router


class ForgotPasswordRequest(BaseModel):
    """Forgot password request body."""

    email: str


class ResetPasswordRequest(BaseModel):
    """Reset password request body."""

    token: str
    new_password: str


# =============================================================================
# JWT Token Routes (for mobile clients)
# =============================================================================


class TokenRequest(BaseModel):
    """Token request body (OAuth2 compatible)."""

    username: str  # email
    password: str
    grant_type: str = "password"


class RefreshTokenRequest(BaseModel):
    """Refresh token request body."""

    refresh_token: str


class TokenRevokeRequest(BaseModel):
    """Token revocation request body."""

    refresh_token: str


def create_jwt_auth_routes(
    auth_store: AuthStore,
    jwt_service: JWTService,
    token_store: TokenStore,
) -> APIRouter:
    """
    Create JWT authentication routes for mobile clients.

    Returns a router with OAuth2-compatible token endpoints.

    Args:
        auth_store: Auth store for user lookup
        jwt_service: JWT service for token creation
        token_store: Token store for refresh tokens
    """
    if not FASTAPI_AVAILABLE:
        raise RuntimeError("FastAPI is required for auth routes")

    from fastapi import APIRouter, HTTPException
    from fastapi.security import OAuth2PasswordRequestForm

    from dazzle_back.runtime.jwt_auth import TokenResponse

    router = APIRouter(prefix="/auth", tags=["Authentication"])

    # =========================================================================
    # Token (Login)
    # =========================================================================

    @router.post("/token", response_model=TokenResponse)
    async def login_for_token(
        form_data: OAuth2PasswordRequestForm | None = None,
        credentials: TokenRequest | None = None,
        request: FastAPIRequest | None = None,
    ) -> TokenResponse:
        """
        OAuth2 compatible token endpoint.

        Accepts either OAuth2 form data or JSON body.
        Returns access_token and refresh_token.
        """
        # Extract credentials from either form or JSON
        if form_data:
            email = form_data.username
            password = form_data.password
        elif credentials:
            email = credentials.username
            password = credentials.password
        else:
            raise HTTPException(status_code=400, detail="Missing credentials")

        # Authenticate user
        user = auth_store.authenticate(email, password)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        # Create tokens
        token_pair = jwt_service.create_token_pair(user)

        # Store refresh token
        token_store.create_token(
            user,
            ip_address=request.client.host if request and request.client else None,
            user_agent=request.headers.get("user-agent") if request else None,
        )

        return TokenResponse(
            access_token=token_pair.access_token,
            refresh_token=token_pair.refresh_token,
            token_type=token_pair.token_type,
            expires_in=token_pair.expires_in,
        )

    # =========================================================================
    # Token Refresh
    # =========================================================================

    @router.post("/token/refresh", response_model=TokenResponse)
    async def refresh_access_token(
        data: RefreshTokenRequest,
        request: FastAPIRequest | None = None,
    ) -> TokenResponse:
        """
        Exchange refresh token for new token pair.

        Implements token rotation: old refresh token is invalidated.
        """
        # Validate refresh token
        token_record = token_store.validate_token(data.refresh_token)
        if not token_record:
            raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

        # Get user
        user = auth_store.get_user_by_id(token_record.user_id)
        if not user or not user.is_active:
            token_store.revoke_token(data.refresh_token)
            raise HTTPException(status_code=401, detail="User not found or inactive")

        # Rotate token
        new_refresh_token = token_store.rotate_token(
            data.refresh_token,
            user,
            ip_address=request.client.host if request and request.client else None,
            user_agent=request.headers.get("user-agent") if request else None,
        )

        if not new_refresh_token:
            raise HTTPException(status_code=401, detail="Token rotation failed")

        # Create new access token
        access_token, _ = jwt_service.create_access_token(
            user_id=user.id,
            email=user.email,
            roles=user.roles,
        )

        return TokenResponse(
            access_token=access_token,
            refresh_token=new_refresh_token,
            token_type="Bearer",  # nosec B106 - OAuth2 token type, not a password
            expires_in=jwt_service.config.access_token_expire_minutes * 60,
        )

    # =========================================================================
    # Token Revoke (Logout)
    # =========================================================================

    @router.post("/token/revoke")
    async def revoke_token(data: TokenRevokeRequest) -> dict[str, str]:
        """
        Revoke a refresh token (logout from device).
        """
        revoked = token_store.revoke_token(data.refresh_token)
        if not revoked:
            # Don't reveal if token existed
            pass
        return {"status": "revoked"}

    # =========================================================================
    # Current User (JWT)
    # =========================================================================

    @router.get("/me/jwt")
    async def get_me_jwt(request: FastAPIRequest) -> dict[str, Any]:
        """
        Get current user from JWT token.

        Requires Authorization: Bearer <token> header.
        """
        from dazzle_back.runtime.jwt_middleware import JWTMiddleware

        # Create temporary middleware to validate
        middleware = JWTMiddleware(jwt_service, exclude_paths=[])
        context = middleware.get_auth_context(request)

        if not context.is_authenticated:
            raise HTTPException(
                status_code=401,
                detail=context.error or "Not authenticated",
            )

        if context.claims is None:
            raise HTTPException(status_code=401, detail="No claims found")

        # Get full user from store
        user = auth_store.get_user_by_id(context.claims.user_id)
        if not user:
            raise HTTPException(status_code=401, detail="User not found")

        return {
            "id": str(user.id),
            "email": user.email,
            "username": user.username,
            "roles": user.roles,
            "is_superuser": user.is_superuser,
        }

    # =========================================================================
    # Active Sessions/Devices
    # =========================================================================

    @router.get("/sessions")
    async def list_sessions(request: FastAPIRequest) -> dict[str, Any]:
        """
        List active refresh tokens/sessions for current user.

        Requires JWT authentication.
        """
        from dazzle_back.runtime.jwt_middleware import JWTMiddleware

        middleware = JWTMiddleware(jwt_service, exclude_paths=[])
        context = middleware.get_auth_context(request)

        if not context.is_authenticated:
            raise HTTPException(status_code=401, detail="Not authenticated")

        if context.claims is None:
            raise HTTPException(status_code=401, detail="No claims found")

        tokens = token_store.get_user_tokens(context.claims.user_id)

        return {
            "sessions": [
                {
                    "device_id": t.device_id,
                    "created_at": t.created_at.isoformat(),
                    "last_used_at": t.last_used_at.isoformat() if t.last_used_at else None,
                    "ip_address": t.ip_address,
                    "user_agent": t.user_agent,
                }
                for t in tokens
            ],
            "count": len(tokens),
        }

    @router.delete("/sessions")
    async def revoke_all_sessions(request: FastAPIRequest) -> dict[str, int]:
        """
        Revoke all refresh tokens except current (logout from all devices).
        """
        from dazzle_back.runtime.jwt_middleware import JWTMiddleware

        middleware = JWTMiddleware(jwt_service, exclude_paths=[])
        context = middleware.get_auth_context(request)

        if not context.is_authenticated:
            raise HTTPException(status_code=401, detail="Not authenticated")

        if context.claims is None:
            raise HTTPException(status_code=401, detail="No claims found")

        # Get current refresh token from request body if provided
        # Otherwise revoke all
        count = token_store.revoke_user_tokens(context.claims.user_id)

        return {"revoked_count": count}

    return router


# =============================================================================
# Auth Dependencies (for protected routes)
# =============================================================================


def create_auth_dependency(
    auth_store: AuthStore,
    cookie_name: str = "dazzle_session",
    require_roles: list[str] | None = None,
) -> Callable[[FastAPIRequest], Awaitable[AuthContext]]:
    """
    Create a FastAPI dependency for authentication.

    Use as a dependency in route functions to require authentication.

    Args:
        auth_store: Auth store instance
        cookie_name: Session cookie name
        require_roles: Required roles (if any)

    Returns:
        Dependency function

    Example:
        ```python
        get_current_user = create_auth_dependency(auth_store)

        @app.get("/protected")
        async def protected_route(user: AuthContext = Depends(get_current_user)):
            return {"user": user.user.email}
        ```
    """
    if not FASTAPI_AVAILABLE:
        raise RuntimeError("FastAPI is required for auth dependencies")

    from fastapi import HTTPException

    async def get_current_user(request: FastAPIRequest) -> AuthContext:
        """Get current authenticated user."""
        session_id = request.cookies.get(cookie_name)

        if not session_id:
            raise HTTPException(status_code=401, detail="Not authenticated")

        auth_context = auth_store.validate_session(session_id)

        if not auth_context.is_authenticated:
            raise HTTPException(status_code=401, detail="Session expired")

        # Check roles if required
        if require_roles:
            user_roles = set(auth_context.roles)
            required = set(require_roles)

            if not required.intersection(user_roles):
                raise HTTPException(
                    status_code=403,
                    detail=f"Required roles: {require_roles}",
                )

        return auth_context

    return get_current_user


def create_deny_dependency(
    auth_store: AuthStore,
    cookie_name: str = "dazzle_session",
    deny_roles: list[str] | None = None,
) -> Callable[[FastAPIRequest], Awaitable[AuthContext]]:
    """
    Create a FastAPI dependency that denies access for specific roles.

    Returns 403 if the authenticated user has any of the denied roles.

    Args:
        auth_store: Auth store instance
        cookie_name: Session cookie name
        deny_roles: Roles to deny (if user has any, returns 403)

    Returns:
        Dependency function
    """
    if not FASTAPI_AVAILABLE:
        raise RuntimeError("FastAPI is required for auth dependencies")

    from fastapi import HTTPException

    async def check_deny_roles(request: FastAPIRequest) -> AuthContext:
        """Reject users with denied roles."""
        session_id = request.cookies.get(cookie_name)

        if not session_id:
            return AuthContext()

        auth_context = auth_store.validate_session(session_id)

        if not auth_context.is_authenticated:
            return auth_context

        # Check deny roles
        if deny_roles:
            user_roles = set(auth_context.roles)
            denied = set(deny_roles)
            if user_roles.intersection(denied):
                raise HTTPException(
                    status_code=403,
                    detail=f"Access denied for roles: {list(user_roles & denied)}",
                )

        return auth_context

    return check_deny_roles


def create_optional_auth_dependency(
    auth_store: AuthStore,
    cookie_name: str = "dazzle_session",
) -> Callable[[FastAPIRequest], Awaitable[AuthContext]]:
    """
    Create a FastAPI dependency for optional authentication.

    Returns AuthContext even if not authenticated (is_authenticated=False).

    Args:
        auth_store: Auth store instance
        cookie_name: Session cookie name

    Returns:
        Dependency function
    """
    if not FASTAPI_AVAILABLE:
        raise RuntimeError("FastAPI is required for auth dependencies")

    async def get_optional_user(request: FastAPIRequest) -> AuthContext:
        """Get current user if authenticated, or empty context."""
        session_id = request.cookies.get(cookie_name)

        if not session_id:
            return AuthContext()

        return auth_store.validate_session(session_id)

    return get_optional_user
