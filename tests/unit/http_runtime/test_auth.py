"""
Tests for authentication runtime.

Tests user management, sessions, and auth endpoints.
"""

import os
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest

from dazzle.http.runtime.auth import (
    AuthContext,
    AuthStore,
    SessionRecord,
    UserRecord,
    create_auth_dependency,
    create_auth_routes,
    create_optional_auth_dependency,
    hash_password,
    verify_password,
)
from dazzle.http.runtime.auth_detection import (
    AuthConfig,
    find_user_entity,
    get_auth_field_mapping,
    has_auth_fields,
)


@pytest.fixture(autouse=True)
def _clean_auth_tables() -> Any:
    """Clean auth tables before each test to ensure isolation."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        yield
        return
    from dazzle.http.runtime.pg_backend import PostgresBackend

    db = PostgresBackend(database_url)

    def _wipe(stmt: str) -> None:
        try:
            with db.connection() as conn:
                conn.execute(stmt)
        except Exception:
            pass  # table may not exist yet

    # FK-safe order: group members → groups → memberships → users (#1342). Each
    # runs independently so a not-yet-created table doesn't block the rest.
    _wipe("DELETE FROM memberships")
    _wipe("DELETE FROM sessions")
    _wipe("DELETE FROM password_reset_tokens")
    _wipe("DELETE FROM users")
    yield


# =============================================================================
# Password Hashing Tests
# =============================================================================


def test_hash_password_is_salted() -> None:
    hashed = hash_password("test_password_123")
    assert hashed != "test_password_123"
    assert "$" in hashed  # salt$hash format
    assert len(hashed) > 50
    assert hash_password("password1") != hash_password("password2")
    # An explicit salt makes the hash deterministic and leads the stored value.
    salted = hash_password("test_password", "fixed_salt_value")
    assert salted == hash_password("test_password", "fixed_salt_value")
    assert salted.startswith("fixed_salt_value$")


@pytest.mark.parametrize(
    ("candidate", "stored", "expected"),
    [
        pytest.param("correct_password", None, True, id="correct-password"),
        pytest.param("wrong_password", None, False, id="wrong-password-rejected"),
        pytest.param("any", "invalid_hash_format", False, id="malformed-hash-rejected"),
    ],
)
def test_verify_password(candidate: str, stored: str | None, expected: bool) -> None:
    """``stored=None`` means the real hash of ``correct_password``."""
    stored = stored if stored is not None else hash_password("correct_password")
    assert verify_password(candidate, stored) is expected


# =============================================================================
# AuthStore Tests
# =============================================================================


@pytest.mark.postgres
@pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set")
class TestAuthStore:
    """Tests for AuthStore class."""

    @pytest.fixture
    def auth_store(self) -> Any:
        """Create an auth store with PostgreSQL database."""
        return AuthStore(os.environ["DATABASE_URL"])

    def test_create_user(self, auth_store: Any) -> None:
        """Test creating a user."""
        user = auth_store.create_user(
            email="test@example.com",
            password="test_password",
            username="testuser",
        )

        assert isinstance(user, UserRecord)
        assert user.email == "test@example.com"
        assert user.username == "testuser"
        assert user.is_active is True
        assert user.is_superuser is False
        assert user.roles == []
        assert isinstance(user.id, UUID)

    def test_create_superuser(self, auth_store: Any) -> None:
        """Test creating a superuser."""
        user = auth_store.create_user(
            email="admin@example.com",
            password="admin_password",
            is_superuser=True,
            roles=["admin", "moderator"],
        )

        assert user.is_superuser is True
        assert user.roles == ["admin", "moderator"]

    @pytest.mark.parametrize(
        "lookup",
        [
            pytest.param(lambda s, u: s.get_user_by_email("find@example.com"), id="get-by-email"),
            pytest.param(lambda s, u: s.get_user_by_id(u.id), id="get-by-id"),
            pytest.param(
                lambda s, u: s.authenticate("find@example.com", "correct_pass"),
                id="authenticate-correct-password",
            ),
        ],
    )
    def test_lookup_hit_returns_the_user(self, auth_store: Any, lookup: Any) -> None:
        created = auth_store.create_user(email="find@example.com", password="correct_pass")
        user = lookup(auth_store, created)
        assert user is not None
        assert (user.id, user.email) == (created.id, "find@example.com")

    @pytest.mark.parametrize(
        "lookup",
        [
            pytest.param(
                lambda s: s.get_user_by_email("nonexistent@example.com"), id="get-by-unknown-email"
            ),
            pytest.param(lambda s: s.get_user_by_id(uuid4()), id="get-by-unknown-id"),
            pytest.param(
                lambda s: s.authenticate("find@example.com", "wrong_pass"),
                id="authenticate-wrong-password-rejected",
            ),
            pytest.param(
                lambda s: s.authenticate("nonexistent@example.com", "any_pass"),
                id="authenticate-unknown-user-rejected",
            ),
        ],
    )
    def test_lookup_miss_returns_none(self, auth_store: Any, lookup: Any) -> None:
        auth_store.create_user(email="find@example.com", password="correct_pass")
        assert lookup(auth_store) is None

    def test_email_normalized_on_create_and_lookup(self, auth_store: Any) -> None:
        """The store is the normalization chokepoint (#1342 M2): create_user stores the
        canonical (trimmed + lowercased) email, and get_user_by_email resolves any-case input
        to the same identity — so the invariant holds even if a caller forgets to lowercase."""
        created = auth_store.create_user(email="  Mixed.Case@Example.COM ", password="pass")
        assert created.email == "mixed.case@example.com"  # stored canonical-lowercase
        # any-case lookup finds the one identity
        assert auth_store.get_user_by_email("mixed.case@example.com").id == created.id
        assert auth_store.get_user_by_email("MIXED.CASE@EXAMPLE.COM").id == created.id
        assert auth_store.get_user_by_email(" Mixed.Case@Example.com ").id == created.id

    def test_email_ci_index_rejects_raw_mixed_case_insert(self, auth_store: Any) -> None:
        """The functional index is the structural backstop for raw-SQL paths that BYPASS the
        store's normalization (#1342). A mixed-case duplicate inserted directly must be rejected
        by users_email_lower_key — not the case-sensitive `email UNIQUE` (users_email_key),
        which a same-case dup would also trip (false confidence)."""
        from uuid import uuid4

        from dazzle.http.runtime.pg_backend import PostgresBackend

        auth_store.create_user(email="split@example.com", password="pass")
        db = PostgresBackend(os.environ["DATABASE_URL"])
        now = datetime.now(UTC).isoformat()
        with pytest.raises(Exception) as exc:  # noqa: PT011 — asserting on the index name below
            with db.connection() as conn:
                conn.execute(
                    "INSERT INTO users (id, email, password_hash, username, is_active, "
                    "is_superuser, roles, created_at, updated_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (str(uuid4()), "SPLIT@example.com", "x", None, True, False, "[]", now, now),
                )
        assert "users_email_lower_key" in str(exc.value).lower(), (
            f"expected the LOWER(email) unique index to fire, got: {exc.value!r}"
        )

    def test_email_ci_uniqueness_preflight_reports_collisions(self, auth_store: Any) -> None:
        """Pre-existing case-dup rows surface an actionable error (not an opaque
        duplicate-key), and the index creation is isolated so it can't tear down
        the rest of the schema (#1342 review)."""
        from uuid import uuid4

        from dazzle.http.runtime.pg_backend import PostgresBackend

        # Construction is I/O-free since the lazy-init refactor (#1504 follow-up
        # 336877dcf), so the base schema (the `users` table) is no longer created
        # at fixture-construction time — initialize it explicitly before seeding.
        auth_store.ensure_initialized()

        db = PostgresBackend(os.environ["DATABASE_URL"])
        now = datetime.now(UTC).isoformat()
        with db.connection() as conn:
            conn.execute("DROP INDEX IF EXISTS users_email_lower_key")
            for email in ("Dup@example.com", "dup@example.com"):
                conn.execute(
                    "INSERT INTO users (id, email, password_hash, username, is_active, "
                    "is_superuser, roles, created_at, updated_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (str(uuid4()), email, "x", None, True, False, "[]", now, now),
                )

        # Construction is now I/O-free (lazy init, #1504 follow-up 336877dcf):
        # the pre-flight runs at ensure_initialized() — triggered lazily on first
        # use and explicitly at server boot (fail-fast preserved) — not in
        # __init__. So build the store, then trigger init: that must raise clearly.
        store = AuthStore(os.environ["DATABASE_URL"])
        with pytest.raises(RuntimeError) as exc:
            store.ensure_initialized()
        assert "share an address once lowercased" in str(exc.value)
        assert "dup@example.com" in str(exc.value)

    def test_email_ci_uniqueness_normalizes_legacy_mixed_case(self, auth_store: Any) -> None:
        """A row written before #1342 kept its case, which login (lowercased lookup)
        cannot find; init rewrites it, as revision 0028 does in production."""
        from uuid import uuid4

        from dazzle.http.runtime.pg_backend import PostgresBackend

        auth_store.ensure_initialized()
        db = PostgresBackend(os.environ["DATABASE_URL"])
        now = datetime.now(UTC).isoformat()
        with db.connection() as conn:
            conn.execute("DROP INDEX IF EXISTS users_email_lower_key")
            conn.execute(
                "INSERT INTO users (id, email, password_hash, username, is_active, "
                "is_superuser, roles, created_at, updated_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (str(uuid4()), " Legacy@Example.com", "x", None, True, False, "[]", now, now),
            )

        AuthStore(os.environ["DATABASE_URL"]).ensure_initialized()
        assert auth_store.get_user_by_email("legacy@example.com") is not None

    def test_update_password(self, auth_store: Any) -> None:
        """Test updating user password."""
        user = auth_store.create_user(email="update@example.com", password="old_pass")

        result = auth_store.update_password(user.id, "new_pass")

        assert result is True
        # Verify new password works
        auth_user = auth_store.authenticate("update@example.com", "new_pass")
        assert auth_user is not None
        # Verify old password fails
        auth_user = auth_store.authenticate("update@example.com", "old_pass")
        assert auth_user is None


# =============================================================================
# Session Tests
# =============================================================================


def _deleted_session_id(store: Any, user: Any) -> str:
    session = store.create_session(user)
    assert store.delete_session(session.id) is True
    return session.id


@pytest.mark.postgres
@pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set")
class TestSessions:
    """Tests for session management."""

    @pytest.fixture
    def auth_store(self) -> Any:
        """Create an auth store with PostgreSQL database."""
        return AuthStore(os.environ["DATABASE_URL"])

    @pytest.fixture
    def test_user(self, auth_store: Any) -> Any:
        """Create a test user."""
        return auth_store.create_user(email="session@example.com", password="pass")

    def test_create_session(self, auth_store: Any, test_user: Any) -> None:
        """Test creating a session."""
        session = auth_store.create_session(test_user)

        assert isinstance(session, SessionRecord)
        assert session.user_id == test_user.id
        assert session.expires_at > datetime.now(UTC)
        assert len(session.id) > 20  # URL-safe token

    def test_create_session_with_metadata(self, auth_store: Any, test_user: Any) -> None:
        """Test creating session with IP and user agent."""
        session = auth_store.create_session(
            test_user,
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0",
        )

        assert session.ip_address == "192.168.1.1"
        assert session.user_agent == "Mozilla/5.0"

    def test_get_session(self, auth_store: Any, test_user: Any) -> None:
        """Test getting a session."""
        created = auth_store.create_session(test_user)

        session = auth_store.get_session(created.id)

        assert session is not None
        assert session.id == created.id

    def test_get_session_not_found(self, auth_store: Any) -> None:
        """Test getting non-existent session."""
        session = auth_store.get_session("nonexistent_session_id")
        assert session is None

    def test_validate_session_success(self, auth_store: Any, test_user: Any) -> None:
        """Test validating a valid session."""
        session = auth_store.create_session(test_user)

        context = auth_store.validate_session(session.id)

        assert context.is_authenticated is True
        assert context.user is not None
        assert context.user.id == test_user.id
        assert context.session is not None

    @pytest.mark.parametrize(
        "session_id",
        [
            pytest.param(
                lambda s, u: s.create_session(u, expires_in=timedelta(seconds=-1)).id,
                id="expired-session-rejected",
            ),
            pytest.param(lambda s, u: "nonexistent", id="unknown-session-rejected"),
            pytest.param(_deleted_session_id, id="deleted-session-rejected"),
        ],
    )
    def test_validate_session_rejects(
        self, auth_store: Any, test_user: Any, session_id: Any
    ) -> None:
        context = auth_store.validate_session(session_id(auth_store, test_user))
        assert (context.is_authenticated, context.user) == (False, None)

    def test_delete_user_sessions(self, auth_store: Any, test_user: Any) -> None:
        """Test deleting all sessions for a user."""
        # Create multiple sessions
        auth_store.create_session(test_user)
        auth_store.create_session(test_user)
        auth_store.create_session(test_user)

        count = auth_store.delete_user_sessions(test_user.id)

        assert count == 3

    def test_cleanup_expired_sessions(self, auth_store: Any, test_user: Any) -> None:
        """Test cleaning up expired sessions."""
        # Create expired session
        auth_store.create_session(test_user, expires_in=timedelta(seconds=-1))
        # Create valid session
        valid = auth_store.create_session(test_user, expires_in=timedelta(days=1))

        count = auth_store.cleanup_expired_sessions()

        assert count == 1
        # Valid session should still exist
        context = auth_store.validate_session(valid.id)
        assert context.is_authenticated is True

    def test_create_session_persists_csrf_secret(self, auth_store: Any, test_user: Any) -> None:
        """The csrf_secret survives a store round-trip (not a fresh default)."""
        session = auth_store.create_session(test_user)

        loaded = auth_store.get_session(session.id)

        assert loaded is not None
        # The round-trip: loaded secret must equal the persisted one, NOT a
        # freshly-minted default_factory value.
        assert loaded.csrf_secret == session.csrf_secret
        assert len(loaded.csrf_secret) >= 32

    def test_regenerate_session_csrf_changes_secret(self, auth_store: Any, test_user: Any) -> None:
        """Regenerating rotates the secret and persists the new value."""
        session = auth_store.create_session(test_user)

        new_secret = auth_store.regenerate_session_csrf(session.id)

        assert new_secret != session.csrf_secret
        assert auth_store.get_session(session.id).csrf_secret == new_secret

    def test_regenerate_session_csrf_raises_for_unknown_session(self, auth_store: Any) -> None:
        """Rotating a non-existent session surfaces loudly, not a silent secret."""
        with pytest.raises((LookupError, ValueError)):
            auth_store.regenerate_session_csrf("does-not-exist")

    def test_get_session_warns_on_null_csrf_secret(
        self, auth_store: Any, test_user: Any, caplog: Any
    ) -> None:
        """A NULL csrf_secret (migration backfill gap) is surfaced loudly."""
        import logging

        session = auth_store.create_session(test_user)
        auth_store._execute("UPDATE sessions SET csrf_secret = NULL WHERE id = %s", (session.id,))

        with caplog.at_level(logging.WARNING):
            loaded = auth_store.get_session(session.id)

        # Robust: still returns a usable record rather than crashing.
        assert loaded is not None
        assert isinstance(loaded.csrf_secret, str) and len(loaded.csrf_secret) >= 32
        # Loud: the anomaly was logged.
        assert any("csrf_secret" in r.message for r in caplog.records)


# =============================================================================
# AuthContext Tests
# =============================================================================


class TestAuthContext:
    """Tests for AuthContext model."""

    def test_unauthenticated_context(self) -> None:
        """Test unauthenticated context."""
        context = AuthContext()

        assert context.is_authenticated is False
        assert context.user is None
        assert context.session is None
        assert context.user_id is None
        assert context.roles == []

    def test_authenticated_context(self) -> None:
        """Test authenticated context."""
        user = UserRecord(
            email="test@example.com",
            password_hash="hash",
            roles=["admin"],
        )

        context = AuthContext(
            user=user,
            is_authenticated=True,
            roles=user.roles,
        )

        assert context.is_authenticated is True
        assert context.user_id == user.id
        assert context.roles == ["admin"]


# =============================================================================
# Auth Routes Integration Tests
# =============================================================================


@pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set")
class TestAuthRoutes:
    """Integration tests for auth routes."""

    @pytest.fixture
    def app(self) -> Any:
        """Create a FastAPI app with auth routes."""
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except ImportError:
            pytest.skip("FastAPI not installed")

        auth_store = AuthStore(os.environ["DATABASE_URL"])
        app = FastAPI()
        router = create_auth_routes(auth_store)
        app.include_router(router)

        return app, TestClient(app), auth_store

    def test_register_success(self, app: Any) -> None:
        """Test successful registration."""
        _, client, _ = app

        response = client.post(
            "/auth/register",
            json={
                "email": "new@example.com",
                "password": "password123",
                "username": "newuser",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["user"]["email"] == "new@example.com"
        assert data["user"]["username"] == "newuser"
        assert "dazzle_session" in response.cookies

    def test_register_duplicate_email(self, app: Any) -> None:
        """Test registration with duplicate email."""
        _, client, auth_store = app

        # Create existing user
        auth_store.create_user(email="existing@example.com", password="pass")

        response = client.post(
            "/auth/register",
            json={
                "email": "existing@example.com",
                "password": "password123",
            },
        )

        assert response.status_code == 400
        assert "already registered" in response.json()["detail"]

    @pytest.mark.parametrize(
        ("login_first", "path", "body", "status"),
        [
            # FastAPI returns 422 for validation errors (missing required fields).
            pytest.param(
                False,
                "/auth/register",
                {"email": "only@email.com"},
                422,
                id="register-missing-password-422",
            ),
            pytest.param(
                False,
                "/auth/login",
                {"email": "user@example.com", "password": "wrong_pass"},
                401,
                id="login-wrong-password-401",
            ),
            pytest.param(
                False,
                "/auth/login",
                {"email": "nonexistent@example.com", "password": "any_pass"},
                401,
                id="login-unknown-user-401",
            ),
            pytest.param(False, "/auth/me", None, 401, id="me-anonymous-401"),
            pytest.param(
                True,
                "/auth/change-password",
                {"current_password": "wrong_pass", "new_password": "new_pass"},
                400,
                id="change-password-wrong-current-400",
            ),
        ],
    )
    def test_route_refuses(
        self, app: Any, login_first: bool, path: str, body: Any, status: int
    ) -> None:
        _, client, auth_store = app
        auth_store.create_user(email="user@example.com", password="correct_pass")
        cookies = None
        if login_first:
            cookies = client.post(
                "/auth/login", json={"email": "user@example.com", "password": "correct_pass"}
            ).cookies

        if body is None:
            response = client.get(path, cookies=cookies)
        else:
            response = client.post(path, json=body, cookies=cookies)

        assert response.status_code == status

    def test_login_success(self, app: Any) -> None:
        """Test successful login."""
        _, client, auth_store = app

        auth_store.create_user(email="login@example.com", password="correct_pass")

        response = client.post(
            "/auth/login",
            json={
                "email": "login@example.com",
                "password": "correct_pass",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["user"]["email"] == "login@example.com"
        assert "dazzle_session" in response.cookies

    def test_logout_ends_the_session(self, app: Any) -> None:
        _, client, auth_store = app
        auth_store.create_user(email="logout@example.com", password="pass")
        login = client.post("/auth/login", json={"email": "logout@example.com", "password": "pass"})
        session_id = login.cookies["dazzle_session"]

        assert client.post("/auth/logout", cookies=login.cookies).status_code == 200
        assert auth_store.validate_session(session_id).is_authenticated is False

    @pytest.mark.parametrize(
        ("persona_routes", "roles", "redirect_url"),
        [
            pytest.param(None, [], "/app", id="default-app"),
            pytest.param(
                {"admin": "/app/workspaces/admin_dashboard"},
                ["admin"],
                "/app/workspaces/admin_dashboard",
                id="persona-route-for-role",
            ),
        ],
    )
    def test_login_redirect_url(
        self, persona_routes: Any, roles: list[str], redirect_url: str
    ) -> None:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        auth_store = AuthStore(os.environ["DATABASE_URL"])
        app = FastAPI()
        app.include_router(create_auth_routes(auth_store, persona_routes=persona_routes))
        client = TestClient(app)
        auth_store.create_user(email="redirect@example.com", password="pass", roles=roles)

        response = client.post(
            "/auth/login", json={"email": "redirect@example.com", "password": "pass"}
        )

        assert response.status_code == 200
        assert response.json()["redirect_url"] == redirect_url

    def test_get_me_authenticated(self, app: Any) -> None:
        """Test getting current user when authenticated."""
        _, client, auth_store = app

        # Login
        auth_store.create_user(email="me@example.com", password="pass")
        login_response = client.post(
            "/auth/login",
            json={
                "email": "me@example.com",
                "password": "pass",
            },
        )

        # Get me
        response = client.get("/auth/me", cookies=login_response.cookies)

        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "me@example.com"

    def test_change_password_success(self, app: Any) -> None:
        """Test successful password change."""
        _, client, auth_store = app

        # Login
        auth_store.create_user(email="change@example.com", password="old_pass")
        login_response = client.post(
            "/auth/login",
            json={
                "email": "change@example.com",
                "password": "old_pass",
            },
        )

        # Change password
        response = client.post(
            "/auth/change-password",
            json={
                "current_password": "old_pass",
                "new_password": "new_pass",
            },
            cookies=login_response.cookies,
        )

        assert response.status_code == 200

        new = {"email": "change@example.com", "password": "new_pass"}
        old = {"email": "change@example.com", "password": "old_pass"}
        assert client.post("/auth/login", json=new).status_code == 200
        assert client.post("/auth/login", json=old).status_code == 401


# =============================================================================
# Server Integration Tests
# =============================================================================


@pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set")
class TestServerAuthIntegration:
    """Tests for auth integration with DazzleBackendApp."""

    @pytest.fixture
    def simple_spec(self) -> Any:
        """Create a simple AppSpec for testing."""
        from dazzle.core.ir import AppSpec, DomainSpec
        from dazzle.core.ir import EntitySpec as IREntitySpec
        from dazzle.core.ir.fields import FieldModifier, FieldTypeKind
        from dazzle.core.ir.fields import FieldSpec as IRFieldSpec
        from dazzle.core.ir.fields import FieldType as IRFieldType

        return AppSpec(
            name="test_app",
            version="1.0.0",
            domain=DomainSpec(
                entities=[
                    IREntitySpec(
                        name="Task",
                        title="Task",
                        fields=[
                            IRFieldSpec(
                                name="id",
                                type=IRFieldType(kind=FieldTypeKind.UUID),
                                modifiers=[FieldModifier.PK],
                            ),
                            IRFieldSpec(
                                name="title",
                                type=IRFieldType(kind=FieldTypeKind.STR, max_length=200),
                            ),
                        ],
                    ),
                ]
            ),
        )

    def test_build_without_auth(self, simple_spec: Any, tmp_path: Any) -> None:
        """Test building app without auth."""
        from dazzle.http.runtime.server import DazzleBackendApp

        builder = DazzleBackendApp(
            simple_spec,
            enable_auth=False,
        )
        builder.build()  # Triggers auth setup

        assert builder.auth_enabled is False
        assert builder.auth_store is None

    @pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set")
    def test_build_with_auth(self, simple_spec: Any, tmp_path: Any) -> None:
        """Test building app with auth enabled."""
        from dazzle.http.runtime.server import DazzleBackendApp

        builder = DazzleBackendApp(
            simple_spec,
            database_url=os.environ["DATABASE_URL"],
            enable_auth=True,
        )
        builder.build()  # Triggers auth setup

        assert builder.auth_enabled is True
        assert builder.auth_store is not None

    @pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set")
    def test_auth_routes_available(self, simple_spec: Any, tmp_path: Any) -> None:
        """Test auth routes are available when auth is enabled."""
        try:
            from fastapi.testclient import TestClient
        except ImportError:
            pytest.skip("FastAPI not installed")

        from dazzle.http.runtime.server import DazzleBackendApp

        builder = DazzleBackendApp(
            simple_spec,
            database_url=os.environ["DATABASE_URL"],
            enable_auth=True,
        )
        app = builder.build()
        client = TestClient(app)

        # Check auth endpoints are available
        response = client.post(
            "/auth/login",
            json={
                "email": "test@test.com",
                "password": "test",
            },
        )
        # Should return 401 (invalid credentials), not 404
        assert response.status_code == 401

    @pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set")
    def test_db_info_shows_auth(self, simple_spec: Any, tmp_path: Any) -> None:
        """db-info is admin-only once auth is enabled."""
        try:
            from fastapi.testclient import TestClient
        except ImportError:
            pytest.skip("FastAPI not installed")

        from dazzle.http.runtime.server import DazzleBackendApp

        builder = DazzleBackendApp(
            simple_spec,
            database_url=os.environ["DATABASE_URL"],
            enable_auth=True,
        )
        app = builder.build()
        client = TestClient(app)

        # /db-info takes the app's auth posture: anonymous callers get 401.
        response = client.get("/db-info")
        assert response.status_code == 401


# =============================================================================
# Auth Detection Tests
# =============================================================================


def _backend(*entities: tuple[str, list[tuple[str, str]]]) -> Any:
    """A BackendSpec from ``(entity_name, [(field_name, scalar_type_name), ...])``."""
    from dazzle.http.specs import BackendSpec, EntitySpec, FieldSpec
    from dazzle.http.specs.entity import FieldType, ScalarType

    return BackendSpec(
        name="test_app",
        version="1.0.0",
        entities=[
            EntitySpec(
                name=name,
                fields=[
                    FieldSpec(
                        name=field,
                        type=FieldType(kind="scalar", scalar_type=ScalarType[scalar]),
                    )
                    for field, scalar in fields
                ],
            )
            for name, fields in entities
        ],
    )


_USER = (
    "User",
    [("id", "UUID"), ("email", "EMAIL"), ("password", "STR"), ("username", "STR")],
)
_TASK = ("Task", [("id", "UUID"), ("title", "STR")])
_ACCOUNT = ("Account", [("id", "UUID"), ("email_address", "EMAIL")])


@pytest.mark.parametrize(
    ("entities", "user_entity"),
    [
        pytest.param([_USER, _TASK], "User", id="user"),
        pytest.param([_ACCOUNT], "Account", id="account-alias"),
        pytest.param([_TASK], None, id="none"),
    ],
)
def test_find_user_entity_and_auth_config(entities: list, user_entity: str | None) -> None:
    spec = _backend(*entities)
    found = find_user_entity(spec)
    assert (found.name if found else None) == user_entity
    config = AuthConfig.from_spec(spec)
    assert config.enabled is (user_entity is not None)
    assert config.user_entity_name == user_entity
    if user_entity is None:
        assert config.user_entity is None


@pytest.mark.parametrize(
    ("entity", "has_auth", "mapping"),
    [
        pytest.param(
            _USER,
            True,
            {"email": "email", "password": "password", "username": "username"},
            id="user-conventional-names",
        ),
        pytest.param(
            _ACCOUNT,
            True,
            {"email": "email_address", "password": None, "username": None},
            id="account-alternate-email-name",
        ),
        pytest.param(
            _TASK,
            False,
            {"email": None, "password": None, "username": None},
            id="task-no-email",
        ),
    ],
)
def test_auth_field_detection(entity: tuple, has_auth: bool, mapping: dict) -> None:
    detected = _backend(entity).entities[0]
    assert has_auth_fields(detected) is has_auth
    assert get_auth_field_mapping(detected) == mapping


# =============================================================================
# Auth Dependency Tests
# =============================================================================


@pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set")
class TestAuthDependencies:
    """Required, optional and role-gated auth dependencies over real sessions."""

    @pytest.fixture
    def client_and_store(self) -> Any:
        from fastapi import Depends, FastAPI
        from fastapi.testclient import TestClient

        auth_store = AuthStore(os.environ["DATABASE_URL"])
        app = FastAPI()
        app.include_router(create_auth_routes(auth_store))

        get_current_user = create_auth_dependency(auth_store)
        get_optional_user = create_optional_auth_dependency(auth_store)
        get_admin_user = create_auth_dependency(auth_store, require_roles=["admin"])

        @app.get("/protected")
        async def protected_route(
            auth: AuthContext = Depends(get_current_user),  # noqa: B008
        ) -> Any:
            return {"email": auth.user.email}  # type: ignore[union-attr]

        @app.get("/optional")
        async def optional_route(
            auth: AuthContext = Depends(get_optional_user),  # noqa: B008
        ) -> Any:
            if auth.is_authenticated:
                return {"authenticated": True, "email": auth.user.email}  # type: ignore[union-attr]
            return {"authenticated": False}

        @app.get("/admin-only")
        async def admin_route(
            auth: AuthContext = Depends(get_admin_user),  # noqa: B008
        ) -> Any:
            return {"admin": True, "email": auth.user.email}  # type: ignore[union-attr]

        return TestClient(app), auth_store

    @pytest.mark.parametrize(
        ("roles", "path", "status", "body"),
        [
            pytest.param(None, "/protected", 401, None, id="required-anonymous-401"),
            pytest.param(
                [], "/protected", 200, {"email": "u@example.com"}, id="required-signed-in-200"
            ),
            pytest.param(
                None, "/optional", 200, {"authenticated": False}, id="optional-anonymous-200"
            ),
            pytest.param(
                [],
                "/optional",
                200,
                {"authenticated": True, "email": "u@example.com"},
                id="optional-signed-in-200",
            ),
            pytest.param(None, "/admin-only", 401, None, id="role-gated-anonymous-401"),
            pytest.param([], "/admin-only", 403, None, id="role-gated-without-role-403"),
            pytest.param(
                ["admin"],
                "/admin-only",
                200,
                {"admin": True, "email": "u@example.com"},
                id="role-gated-with-role-200",
            ),
        ],
    )
    def test_dependency_gate(
        self, client_and_store: Any, roles: list[str] | None, path: str, status: int, body: Any
    ) -> None:
        """``roles=None`` = anonymous; otherwise sign in a user holding ``roles``."""
        client, auth_store = client_and_store
        cookies = None
        if roles is not None:
            auth_store.create_user(email="u@example.com", password="pass", roles=roles)
            cookies = client.post(
                "/auth/login", json={"email": "u@example.com", "password": "pass"}
            ).cookies

        response = client.get(path, cookies=cookies)

        assert response.status_code == status
        if body is not None:
            assert response.json() == body
        if status == 403:
            assert "admin" in response.json()["detail"]
