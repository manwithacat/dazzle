"""
Tests for authentication runtime.

Tests user management, sessions, and auth endpoints.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from dazzle_dnr_back.runtime.auth import (
    AuthContext,
    AuthMiddleware,
    AuthStore,
    SessionRecord,
    UserRecord,
    create_auth_dependency,
    create_auth_routes,
    create_optional_auth_dependency,
    hash_password,
    verify_password,
)
from dazzle_dnr_back.runtime.auth_detection import (
    AuthConfig,
    detect_auth_requirements,
    find_user_entity,
    get_auth_field_mapping,
    has_auth_fields,
    should_enable_auth,
)

# =============================================================================
# Password Hashing Tests
# =============================================================================


class TestPasswordHashing:
    """Tests for password hashing functions."""

    def test_hash_password_creates_hash(self):
        """Test password hashing creates a hash."""
        password = "test_password_123"
        hashed = hash_password(password)

        assert hashed != password
        assert "$" in hashed  # salt$hash format
        assert len(hashed) > 50  # reasonable length

    def test_hash_password_with_salt(self):
        """Test password hashing with explicit salt."""
        password = "test_password"
        salt = "fixed_salt_value"

        hash1 = hash_password(password, salt)
        hash2 = hash_password(password, salt)

        assert hash1 == hash2
        assert hash1.startswith(f"{salt}$")

    def test_verify_password_correct(self):
        """Test verifying correct password."""
        password = "correct_password"
        hashed = hash_password(password)

        assert verify_password(password, hashed) is True

    def test_verify_password_incorrect(self):
        """Test verifying incorrect password."""
        password = "correct_password"
        hashed = hash_password(password)

        assert verify_password("wrong_password", hashed) is False

    def test_verify_password_invalid_hash(self):
        """Test verifying with invalid hash format."""
        assert verify_password("any", "invalid_hash_format") is False

    def test_different_passwords_different_hashes(self):
        """Test different passwords produce different hashes."""
        hash1 = hash_password("password1")
        hash2 = hash_password("password2")

        assert hash1 != hash2


# =============================================================================
# AuthStore Tests
# =============================================================================


class TestAuthStore:
    """Tests for AuthStore class."""

    @pytest.fixture
    def auth_store(self, tmp_path):
        """Create an auth store with temporary database."""
        db_path = tmp_path / "test_auth.db"
        return AuthStore(db_path)

    def test_create_user(self, auth_store):
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

    def test_create_superuser(self, auth_store):
        """Test creating a superuser."""
        user = auth_store.create_user(
            email="admin@example.com",
            password="admin_password",
            is_superuser=True,
            roles=["admin", "moderator"],
        )

        assert user.is_superuser is True
        assert user.roles == ["admin", "moderator"]

    def test_get_user_by_email(self, auth_store):
        """Test getting user by email."""
        auth_store.create_user(email="find@example.com", password="pass")

        user = auth_store.get_user_by_email("find@example.com")

        assert user is not None
        assert user.email == "find@example.com"

    def test_get_user_by_email_not_found(self, auth_store):
        """Test getting non-existent user by email."""
        user = auth_store.get_user_by_email("nonexistent@example.com")
        assert user is None

    def test_get_user_by_id(self, auth_store):
        """Test getting user by ID."""
        created = auth_store.create_user(email="byid@example.com", password="pass")

        user = auth_store.get_user_by_id(created.id)

        assert user is not None
        assert user.id == created.id

    def test_get_user_by_id_not_found(self, auth_store):
        """Test getting non-existent user by ID."""
        from uuid import uuid4

        user = auth_store.get_user_by_id(uuid4())
        assert user is None

    def test_authenticate_success(self, auth_store):
        """Test successful authentication."""
        auth_store.create_user(email="auth@example.com", password="correct_pass")

        user = auth_store.authenticate("auth@example.com", "correct_pass")

        assert user is not None
        assert user.email == "auth@example.com"

    def test_authenticate_wrong_password(self, auth_store):
        """Test authentication with wrong password."""
        auth_store.create_user(email="wrong@example.com", password="correct_pass")

        user = auth_store.authenticate("wrong@example.com", "wrong_pass")

        assert user is None

    def test_authenticate_nonexistent_user(self, auth_store):
        """Test authentication with non-existent user."""
        user = auth_store.authenticate("nonexistent@example.com", "any_pass")
        assert user is None

    def test_update_password(self, auth_store):
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


class TestSessions:
    """Tests for session management."""

    @pytest.fixture
    def auth_store(self, tmp_path):
        """Create an auth store with temporary database."""
        db_path = tmp_path / "test_sessions.db"
        return AuthStore(db_path)

    @pytest.fixture
    def test_user(self, auth_store):
        """Create a test user."""
        return auth_store.create_user(email="session@example.com", password="pass")

    def test_create_session(self, auth_store, test_user):
        """Test creating a session."""
        session = auth_store.create_session(test_user)

        assert isinstance(session, SessionRecord)
        assert session.user_id == test_user.id
        assert session.expires_at > datetime.now(UTC)
        assert len(session.id) > 20  # URL-safe token

    def test_create_session_with_metadata(self, auth_store, test_user):
        """Test creating session with IP and user agent."""
        session = auth_store.create_session(
            test_user,
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0",
        )

        assert session.ip_address == "192.168.1.1"
        assert session.user_agent == "Mozilla/5.0"

    def test_get_session(self, auth_store, test_user):
        """Test getting a session."""
        created = auth_store.create_session(test_user)

        session = auth_store.get_session(created.id)

        assert session is not None
        assert session.id == created.id

    def test_get_session_not_found(self, auth_store):
        """Test getting non-existent session."""
        session = auth_store.get_session("nonexistent_session_id")
        assert session is None

    def test_validate_session_success(self, auth_store, test_user):
        """Test validating a valid session."""
        session = auth_store.create_session(test_user)

        context = auth_store.validate_session(session.id)

        assert context.is_authenticated is True
        assert context.user is not None
        assert context.user.id == test_user.id
        assert context.session is not None

    def test_validate_session_expired(self, auth_store, test_user):
        """Test validating an expired session."""
        session = auth_store.create_session(
            test_user,
            expires_in=timedelta(seconds=-1),  # Already expired
        )

        context = auth_store.validate_session(session.id)

        assert context.is_authenticated is False
        assert context.user is None

    def test_validate_session_not_found(self, auth_store):
        """Test validating non-existent session."""
        context = auth_store.validate_session("nonexistent")

        assert context.is_authenticated is False
        assert context.user is None

    def test_delete_session(self, auth_store, test_user):
        """Test deleting a session."""
        session = auth_store.create_session(test_user)

        result = auth_store.delete_session(session.id)

        assert result is True
        # Verify session is deleted
        context = auth_store.validate_session(session.id)
        assert context.is_authenticated is False

    def test_delete_user_sessions(self, auth_store, test_user):
        """Test deleting all sessions for a user."""
        # Create multiple sessions
        auth_store.create_session(test_user)
        auth_store.create_session(test_user)
        auth_store.create_session(test_user)

        count = auth_store.delete_user_sessions(test_user.id)

        assert count == 3

    def test_cleanup_expired_sessions(self, auth_store, test_user):
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


# =============================================================================
# AuthContext Tests
# =============================================================================


class TestAuthContext:
    """Tests for AuthContext model."""

    def test_unauthenticated_context(self):
        """Test unauthenticated context."""
        context = AuthContext()

        assert context.is_authenticated is False
        assert context.user is None
        assert context.session is None
        assert context.user_id is None
        assert context.roles == []

    def test_authenticated_context(self):
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
# AuthMiddleware Tests
# =============================================================================


class TestAuthMiddleware:
    """Tests for AuthMiddleware class."""

    @pytest.fixture
    def auth_store(self, tmp_path):
        """Create an auth store."""
        return AuthStore(tmp_path / "middleware.db")

    @pytest.fixture
    def middleware(self, auth_store):
        """Create middleware instance."""
        return AuthMiddleware(auth_store)

    def test_is_excluded_path_health(self, middleware):
        """Test health endpoint is excluded."""
        assert middleware.is_excluded_path("/health") is True

    def test_is_excluded_path_docs(self, middleware):
        """Test docs endpoint is excluded."""
        assert middleware.is_excluded_path("/docs") is True
        assert middleware.is_excluded_path("/openapi.json") is True

    def test_is_excluded_path_auth(self, middleware):
        """Test auth endpoints are excluded."""
        assert middleware.is_excluded_path("/auth/login") is True
        assert middleware.is_excluded_path("/auth/register") is True

    def test_is_excluded_path_api(self, middleware):
        """Test API endpoints are not excluded."""
        assert middleware.is_excluded_path("/api/tasks") is False
        assert middleware.is_excluded_path("/users") is False

    def test_custom_exclude_paths(self, auth_store):
        """Test custom exclude paths."""
        middleware = AuthMiddleware(
            auth_store,
            exclude_paths=["/public", "/webhook"],
        )

        assert middleware.is_excluded_path("/public") is True
        assert middleware.is_excluded_path("/webhook") is True
        assert middleware.is_excluded_path("/private") is False


# =============================================================================
# Auth Routes Integration Tests
# =============================================================================


class TestAuthRoutes:
    """Integration tests for auth routes."""

    @pytest.fixture
    def app(self, tmp_path):
        """Create a FastAPI app with auth routes."""
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except ImportError:
            pytest.skip("FastAPI not installed")

        auth_store = AuthStore(tmp_path / "routes.db")
        app = FastAPI()
        router = create_auth_routes(auth_store)
        app.include_router(router)

        return app, TestClient(app), auth_store

    def test_register_success(self, app):
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
        assert "dnr_session" in response.cookies

    def test_register_duplicate_email(self, app):
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

    def test_register_missing_fields(self, app):
        """Test registration with missing fields."""
        _, client, _ = app

        response = client.post(
            "/auth/register",
            json={
                "email": "only@email.com",
            },
        )

        # FastAPI returns 422 for validation errors (missing required fields)
        assert response.status_code == 422

    def test_login_success(self, app):
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
        assert "dnr_session" in response.cookies

    def test_login_wrong_password(self, app):
        """Test login with wrong password."""
        _, client, auth_store = app

        auth_store.create_user(email="wrong@example.com", password="correct_pass")

        response = client.post(
            "/auth/login",
            json={
                "email": "wrong@example.com",
                "password": "wrong_pass",
            },
        )

        assert response.status_code == 401

    def test_login_nonexistent_user(self, app):
        """Test login with non-existent user."""
        _, client, _ = app

        response = client.post(
            "/auth/login",
            json={
                "email": "nonexistent@example.com",
                "password": "any_pass",
            },
        )

        assert response.status_code == 401

    def test_logout(self, app):
        """Test logout."""
        _, client, auth_store = app

        # First login
        auth_store.create_user(email="logout@example.com", password="pass")
        login_response = client.post(
            "/auth/login",
            json={
                "email": "logout@example.com",
                "password": "pass",
            },
        )

        # Then logout
        response = client.post(
            "/auth/logout",
            cookies=login_response.cookies,
        )

        assert response.status_code == 200

    def test_get_me_authenticated(self, app):
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

    def test_get_me_unauthenticated(self, app):
        """Test getting current user when not authenticated."""
        _, client, _ = app

        response = client.get("/auth/me")

        assert response.status_code == 401

    def test_change_password_success(self, app):
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

        # Verify new password works
        login_response = client.post(
            "/auth/login",
            json={
                "email": "change@example.com",
                "password": "new_pass",
            },
        )
        assert login_response.status_code == 200

    def test_change_password_wrong_current(self, app):
        """Test password change with wrong current password."""
        _, client, auth_store = app

        # Login
        auth_store.create_user(email="wrongcur@example.com", password="correct_pass")
        login_response = client.post(
            "/auth/login",
            json={
                "email": "wrongcur@example.com",
                "password": "correct_pass",
            },
        )

        # Try to change with wrong current password
        response = client.post(
            "/auth/change-password",
            json={
                "current_password": "wrong_pass",
                "new_password": "new_pass",
            },
            cookies=login_response.cookies,
        )

        assert response.status_code == 400


# =============================================================================
# Server Integration Tests
# =============================================================================


class TestServerAuthIntegration:
    """Tests for auth integration with DNRBackendApp."""

    @pytest.fixture
    def simple_spec(self):
        """Create a simple BackendSpec for testing."""
        from dazzle_dnr_back.specs import BackendSpec, EntitySpec, FieldSpec
        from dazzle_dnr_back.specs.entity import FieldType, ScalarType

        return BackendSpec(
            name="test_app",
            version="1.0.0",
            entities=[
                EntitySpec(
                    name="Task",
                    fields=[
                        FieldSpec(
                            name="id",
                            type=FieldType(kind="scalar", scalar_type=ScalarType.UUID),
                        ),
                        FieldSpec(
                            name="title",
                            type=FieldType(kind="scalar", scalar_type=ScalarType.STR),
                        ),
                    ],
                )
            ],
        )

    def test_build_without_auth(self, simple_spec, tmp_path):
        """Test building app without auth."""
        from dazzle_dnr_back.runtime.server import DNRBackendApp

        builder = DNRBackendApp(
            simple_spec,
            db_path=tmp_path / "noauth.db",
            enable_auth=False,
        )
        builder.build()  # Triggers auth setup

        assert builder.auth_enabled is False
        assert builder.auth_store is None

    def test_build_with_auth(self, simple_spec, tmp_path):
        """Test building app with auth enabled."""
        from dazzle_dnr_back.runtime.server import DNRBackendApp

        builder = DNRBackendApp(
            simple_spec,
            db_path=tmp_path / "auth.db",
            enable_auth=True,
            auth_db_path=tmp_path / "auth_users.db",
        )
        builder.build()  # Triggers auth setup

        assert builder.auth_enabled is True
        assert builder.auth_store is not None

    def test_auth_routes_available(self, simple_spec, tmp_path):
        """Test auth routes are available when auth is enabled."""
        try:
            from fastapi.testclient import TestClient
        except ImportError:
            pytest.skip("FastAPI not installed")

        from dazzle_dnr_back.runtime.server import DNRBackendApp

        builder = DNRBackendApp(
            simple_spec,
            db_path=tmp_path / "routes.db",
            enable_auth=True,
            auth_db_path=tmp_path / "routes_auth.db",
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

    def test_db_info_shows_auth(self, simple_spec, tmp_path):
        """Test db-info endpoint shows auth info."""
        try:
            from fastapi.testclient import TestClient
        except ImportError:
            pytest.skip("FastAPI not installed")

        from dazzle_dnr_back.runtime.server import DNRBackendApp

        builder = DNRBackendApp(
            simple_spec,
            db_path=tmp_path / "info.db",
            enable_auth=True,
            auth_db_path=tmp_path / "info_auth.db",
        )
        app = builder.build()
        client = TestClient(app)

        response = client.get("/db-info")
        data = response.json()

        assert data["auth_enabled"] is True
        assert data["auth_database_path"] is not None


# =============================================================================
# Auth Detection Tests
# =============================================================================


class TestUserEntityDetection:
    """Tests for automatic user entity detection."""

    @pytest.fixture
    def spec_with_user(self):
        """Create a spec with User entity."""
        from dazzle_dnr_back.specs import BackendSpec, EntitySpec, FieldSpec
        from dazzle_dnr_back.specs.entity import FieldType, ScalarType

        return BackendSpec(
            name="test_app",
            version="1.0.0",
            entities=[
                EntitySpec(
                    name="User",
                    fields=[
                        FieldSpec(
                            name="id",
                            type=FieldType(kind="scalar", scalar_type=ScalarType.UUID),
                        ),
                        FieldSpec(
                            name="email",
                            type=FieldType(kind="scalar", scalar_type=ScalarType.EMAIL),
                        ),
                        FieldSpec(
                            name="password",
                            type=FieldType(kind="scalar", scalar_type=ScalarType.STR),
                        ),
                        FieldSpec(
                            name="username",
                            type=FieldType(kind="scalar", scalar_type=ScalarType.STR),
                        ),
                    ],
                ),
                EntitySpec(
                    name="Task",
                    fields=[
                        FieldSpec(
                            name="id",
                            type=FieldType(kind="scalar", scalar_type=ScalarType.UUID),
                        ),
                        FieldSpec(
                            name="title",
                            type=FieldType(kind="scalar", scalar_type=ScalarType.STR),
                        ),
                    ],
                ),
            ],
        )

    @pytest.fixture
    def spec_without_user(self):
        """Create a spec without User entity."""
        from dazzle_dnr_back.specs import BackendSpec, EntitySpec, FieldSpec
        from dazzle_dnr_back.specs.entity import FieldType, ScalarType

        return BackendSpec(
            name="test_app",
            version="1.0.0",
            entities=[
                EntitySpec(
                    name="Task",
                    fields=[
                        FieldSpec(
                            name="id",
                            type=FieldType(kind="scalar", scalar_type=ScalarType.UUID),
                        ),
                        FieldSpec(
                            name="title",
                            type=FieldType(kind="scalar", scalar_type=ScalarType.STR),
                        ),
                    ],
                ),
            ],
        )

    @pytest.fixture
    def spec_with_account(self):
        """Create a spec with Account entity (alternative user entity name)."""
        from dazzle_dnr_back.specs import BackendSpec, EntitySpec, FieldSpec
        from dazzle_dnr_back.specs.entity import FieldType, ScalarType

        return BackendSpec(
            name="test_app",
            version="1.0.0",
            entities=[
                EntitySpec(
                    name="Account",
                    fields=[
                        FieldSpec(
                            name="id",
                            type=FieldType(kind="scalar", scalar_type=ScalarType.UUID),
                        ),
                        FieldSpec(
                            name="email_address",
                            type=FieldType(kind="scalar", scalar_type=ScalarType.EMAIL),
                        ),
                    ],
                ),
            ],
        )

    def test_find_user_entity(self, spec_with_user):
        """Test finding User entity."""
        entity = find_user_entity(spec_with_user)

        assert entity is not None
        assert entity.name == "User"

    def test_find_user_entity_not_found(self, spec_without_user):
        """Test no User entity found."""
        entity = find_user_entity(spec_without_user)

        assert entity is None

    def test_find_user_entity_account(self, spec_with_account):
        """Test finding Account entity as user."""
        entity = find_user_entity(spec_with_account)

        assert entity is not None
        assert entity.name == "Account"

    def test_has_auth_fields_with_email(self, spec_with_user):
        """Test detecting auth fields."""
        user_entity = spec_with_user.entities[0]

        assert has_auth_fields(user_entity) is True

    def test_has_auth_fields_without_email(self, spec_without_user):
        """Test entity without email field."""
        task_entity = spec_without_user.entities[0]

        assert has_auth_fields(task_entity) is False

    def test_get_auth_field_mapping(self, spec_with_user):
        """Test field mapping detection."""
        user_entity = spec_with_user.entities[0]
        mapping = get_auth_field_mapping(user_entity)

        assert mapping["email"] == "email"
        assert mapping["password"] == "password"
        assert mapping["username"] == "username"

    def test_get_auth_field_mapping_alternate_names(self, spec_with_account):
        """Test field mapping with alternate names."""
        account_entity = spec_with_account.entities[0]
        mapping = get_auth_field_mapping(account_entity)

        assert mapping["email"] == "email_address"
        assert mapping["password"] is None
        assert mapping["username"] is None


class TestAuthConfig:
    """Tests for AuthConfig."""

    @pytest.fixture
    def spec_with_user(self):
        """Create a spec with User entity."""
        from dazzle_dnr_back.specs import BackendSpec, EntitySpec, FieldSpec
        from dazzle_dnr_back.specs.entity import FieldType, ScalarType

        return BackendSpec(
            name="test_app",
            version="1.0.0",
            entities=[
                EntitySpec(
                    name="User",
                    fields=[
                        FieldSpec(
                            name="id",
                            type=FieldType(kind="scalar", scalar_type=ScalarType.UUID),
                        ),
                        FieldSpec(
                            name="email",
                            type=FieldType(kind="scalar", scalar_type=ScalarType.EMAIL),
                        ),
                    ],
                ),
            ],
        )

    @pytest.fixture
    def spec_without_user(self):
        """Create a spec without User entity."""
        from dazzle_dnr_back.specs import BackendSpec, EntitySpec, FieldSpec
        from dazzle_dnr_back.specs.entity import FieldType, ScalarType

        return BackendSpec(
            name="test_app",
            version="1.0.0",
            entities=[
                EntitySpec(
                    name="Task",
                    fields=[
                        FieldSpec(
                            name="id",
                            type=FieldType(kind="scalar", scalar_type=ScalarType.UUID),
                        ),
                    ],
                ),
            ],
        )

    def test_auth_config_from_spec_with_user(self, spec_with_user):
        """Test creating auth config from spec with user."""
        config = AuthConfig.from_spec(spec_with_user)

        assert config.enabled is True
        assert config.user_entity_name == "User"
        assert config.field_mapping["email"] == "email"

    def test_auth_config_from_spec_without_user(self, spec_without_user):
        """Test creating auth config from spec without user."""
        config = AuthConfig.from_spec(spec_without_user)

        assert config.enabled is False
        assert config.user_entity is None

    def test_detect_auth_requirements(self, spec_with_user):
        """Test detect_auth_requirements convenience function."""
        config = detect_auth_requirements(spec_with_user)

        assert config.enabled is True

    def test_should_enable_auth(self, spec_with_user, spec_without_user):
        """Test should_enable_auth convenience function."""
        assert should_enable_auth(spec_with_user) is True
        assert should_enable_auth(spec_without_user) is False


# =============================================================================
# Auth Dependency Tests
# =============================================================================


class TestAuthDependencies:
    """Tests for auth dependency injection."""

    @pytest.fixture
    def app_with_protected_routes(self, tmp_path):
        """Create an app with protected routes."""
        try:
            from fastapi import Depends, FastAPI
            from fastapi.testclient import TestClient
        except ImportError:
            pytest.skip("FastAPI not installed")

        auth_store = AuthStore(tmp_path / "deps.db")
        app = FastAPI()

        # Create auth routes
        auth_router = create_auth_routes(auth_store)
        app.include_router(auth_router)

        # Create auth dependency
        get_current_user = create_auth_dependency(auth_store)
        get_optional_user = create_optional_auth_dependency(auth_store)
        get_admin_user = create_auth_dependency(auth_store, require_roles=["admin"])

        @app.get("/protected")
        async def protected_route(
            auth: AuthContext = Depends(get_current_user),  # noqa: B008
        ):
            return {"email": auth.user.email}

        @app.get("/optional")
        async def optional_route(
            auth: AuthContext = Depends(get_optional_user),  # noqa: B008
        ):
            if auth.is_authenticated:
                return {"authenticated": True, "email": auth.user.email}
            return {"authenticated": False}

        @app.get("/admin-only")
        async def admin_route(
            auth: AuthContext = Depends(get_admin_user),  # noqa: B008
        ):
            return {"admin": True, "email": auth.user.email}

        return app, TestClient(app), auth_store

    def test_protected_route_unauthorized(self, app_with_protected_routes):
        """Test accessing protected route without auth."""
        _, client, _ = app_with_protected_routes

        response = client.get("/protected")

        assert response.status_code == 401

    def test_protected_route_authorized(self, app_with_protected_routes):
        """Test accessing protected route with auth."""
        _, client, auth_store = app_with_protected_routes

        # Create user and login
        auth_store.create_user(email="test@example.com", password="pass")
        login_response = client.post(
            "/auth/login",
            json={
                "email": "test@example.com",
                "password": "pass",
            },
        )

        # Access protected route
        response = client.get("/protected", cookies=login_response.cookies)

        assert response.status_code == 200
        assert response.json()["email"] == "test@example.com"

    def test_optional_route_unauthorized(self, app_with_protected_routes):
        """Test accessing optional route without auth."""
        _, client, _ = app_with_protected_routes

        response = client.get("/optional")

        assert response.status_code == 200
        assert response.json()["authenticated"] is False

    def test_optional_route_authorized(self, app_with_protected_routes):
        """Test accessing optional route with auth."""
        _, client, auth_store = app_with_protected_routes

        # Create user and login
        auth_store.create_user(email="opt@example.com", password="pass")
        login_response = client.post(
            "/auth/login",
            json={
                "email": "opt@example.com",
                "password": "pass",
            },
        )

        # Access optional route
        response = client.get("/optional", cookies=login_response.cookies)

        assert response.status_code == 200
        data = response.json()
        assert data["authenticated"] is True
        assert data["email"] == "opt@example.com"

    def test_admin_route_no_role(self, app_with_protected_routes):
        """Test accessing admin route without admin role."""
        _, client, auth_store = app_with_protected_routes

        # Create regular user and login
        auth_store.create_user(email="regular@example.com", password="pass")
        login_response = client.post(
            "/auth/login",
            json={
                "email": "regular@example.com",
                "password": "pass",
            },
        )

        # Access admin route
        response = client.get("/admin-only", cookies=login_response.cookies)

        assert response.status_code == 403
        assert "admin" in response.json()["detail"]

    def test_admin_route_with_role(self, app_with_protected_routes):
        """Test accessing admin route with admin role."""
        _, client, auth_store = app_with_protected_routes

        # Create admin user and login
        auth_store.create_user(
            email="admin@example.com",
            password="pass",
            roles=["admin"],
        )
        login_response = client.post(
            "/auth/login",
            json={
                "email": "admin@example.com",
                "password": "pass",
            },
        )

        # Access admin route
        response = client.get("/admin-only", cookies=login_response.cookies)

        assert response.status_code == 200
        assert response.json()["admin"] is True
