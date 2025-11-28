"""
Authentication runtime for DNR Backend.

Provides session-based authentication with cookie management.
"""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

# FastAPI is optional - import for type hints and runtime
try:
    from fastapi import Request as FastAPIRequest

    FASTAPI_AVAILABLE = True
except ImportError:
    FastAPIRequest = None  # type: ignore
    FASTAPI_AVAILABLE = False


# =============================================================================
# User Model
# =============================================================================


class UserRecord(BaseModel):
    """User record for authentication."""

    id: UUID = Field(default_factory=uuid4)
    email: str
    password_hash: str
    username: str | None = None
    is_active: bool = True
    is_superuser: bool = False
    roles: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        frozen = True


class SessionRecord(BaseModel):
    """Session record for authentication."""

    id: str = Field(default_factory=lambda: secrets.token_urlsafe(32))
    user_id: UUID
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime
    ip_address: str | None = None
    user_agent: str | None = None

    class Config:
        frozen = True


class AuthContext(BaseModel):
    """Current authentication context."""

    user: UserRecord | None = None
    session: SessionRecord | None = None
    is_authenticated: bool = False
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)

    @property
    def user_id(self) -> UUID | None:
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
# Auth Store (SQLite-based)
# =============================================================================


class AuthStore:
    """
    Authentication store using SQLite.

    Manages users and sessions in a separate auth database.
    """

    def __init__(self, db_path: str | Path | None = None):
        """
        Initialize the auth store.

        Args:
            db_path: Path to SQLite database (default: .dazzle/auth.db)
        """
        self.db_path = Path(db_path) if db_path else Path(".dazzle/auth.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Initialize database tables."""
        with self._get_connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    username TEXT,
                    is_active INTEGER DEFAULT 1,
                    is_superuser INTEGER DEFAULT 0,
                    roles TEXT DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id),
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    ip_address TEXT,
                    user_agent TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
                CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
                CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);
            """)
            conn.commit()

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

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO users (id, email, password_hash, username, is_active,
                                   is_superuser, roles, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(user.id),
                    user.email,
                    user.password_hash,
                    user.username,
                    1 if user.is_active else 0,
                    1 if user.is_superuser else 0,
                    json.dumps(user.roles),
                    user.created_at.isoformat(),
                    user.updated_at.isoformat(),
                ),
            )
            conn.commit()

        return user

    def get_user_by_email(self, email: str) -> UserRecord | None:
        """Get user by email."""
        import json

        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

            if row:
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

        return None

    def get_user_by_id(self, user_id: UUID) -> UserRecord | None:
        """Get user by ID."""
        import json

        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (str(user_id),)).fetchone()

            if row:
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

        return None

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
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                UPDATE users
                SET password_hash = ?, updated_at = ?
                WHERE id = ?
                """,
                (hash_password(new_password), datetime.utcnow().isoformat(), str(user_id)),
            )
            conn.commit()
            return cursor.rowcount > 0

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
            expires_at=datetime.utcnow() + expires_in,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO sessions (id, user_id, created_at, expires_at, ip_address, user_agent)
                VALUES (?, ?, ?, ?, ?, ?)
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
            conn.commit()

        return session

    def get_session(self, session_id: str) -> SessionRecord | None:
        """Get session by ID."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()

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
        if session.expires_at < datetime.utcnow():
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
        with self._get_connection() as conn:
            cursor = conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            conn.commit()
            return cursor.rowcount > 0

    def delete_user_sessions(self, user_id: UUID) -> int:
        """Delete all sessions for a user."""
        with self._get_connection() as conn:
            cursor = conn.execute("DELETE FROM sessions WHERE user_id = ?", (str(user_id),))
            conn.commit()
            return cursor.rowcount

    def cleanup_expired_sessions(self) -> int:
        """Delete all expired sessions."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM sessions WHERE expires_at < ?",
                (datetime.utcnow().isoformat(),),
            )
            conn.commit()
            return cursor.rowcount


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
        cookie_name: str = "dnr_session",
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
    cookie_name: str = "dnr_session",
    session_expires_days: int = 7,
):
    """
    Create authentication routes for FastAPI.

    Returns a router with login, logout, register, and me endpoints.
    """
    if not FASTAPI_AVAILABLE:
        raise RuntimeError("FastAPI is required for auth routes")

    from fastapi import APIRouter, HTTPException
    from fastapi.responses import JSONResponse

    router = APIRouter(prefix="/auth", tags=["Authentication"])

    # =========================================================================
    # Login
    # =========================================================================

    @router.post("/login")
    async def login(credentials: LoginRequest, request: FastAPIRequest):
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
    async def logout(request: FastAPIRequest):
        """
        Logout and delete session.
        """
        session_id = request.cookies.get(cookie_name)

        if session_id:
            auth_store.delete_session(session_id)

        response = JSONResponse(content={"message": "Logout successful"})
        response.delete_cookie(cookie_name)

        return response

    # =========================================================================
    # Register
    # =========================================================================

    @router.post("/register", status_code=201)
    async def register(data: RegisterRequest, request: FastAPIRequest):
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
    async def get_me(request: FastAPIRequest):
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
    async def change_password(data: ChangePasswordRequest, request: FastAPIRequest):
        """
        Change current user's password.
        """
        session_id = request.cookies.get(cookie_name)

        if not session_id:
            raise HTTPException(status_code=401, detail="Not authenticated")

        auth_context = auth_store.validate_session(session_id)

        if not auth_context.is_authenticated:
            raise HTTPException(status_code=401, detail="Session expired")

        # Verify current password
        if not verify_password(data.current_password, auth_context.user.password_hash):
            raise HTTPException(status_code=400, detail="Current password is incorrect")

        # Update password
        auth_store.update_password(auth_context.user.id, data.new_password)

        # Invalidate all other sessions
        auth_store.delete_user_sessions(auth_context.user.id)

        # Create new session
        session = auth_store.create_session(
            auth_context.user,
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

    return router


# =============================================================================
# Auth Dependencies (for protected routes)
# =============================================================================


def create_auth_dependency(
    auth_store: AuthStore,
    cookie_name: str = "dnr_session",
    require_roles: list[str] | None = None,
):
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


def create_optional_auth_dependency(
    auth_store: AuthStore,
    cookie_name: str = "dnr_session",
):
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
