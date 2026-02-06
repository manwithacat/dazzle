"""
Unit tests for MCP user_management handlers.

Tests all 9 handler operations:
- list_users_handler
- create_user_handler
- get_user_handler
- update_user_handler
- reset_password_handler
- deactivate_user_handler
- list_sessions_handler
- revoke_session_handler
- get_auth_config_handler
"""

from __future__ import annotations

import importlib.util
import string
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _import_user_management():
    """Import user_management handlers directly to avoid MCP package init issues.

    The dazzle.mcp.__init__.py imports mcp.server which may not be installed
    in test environments. We need to import the handlers module directly.
    """
    # Create a mock state module to satisfy the relative import
    mock_state = MagicMock()
    mock_state.get_project_path = MagicMock(return_value=None)
    sys.modules["dazzle.mcp.server.handlers"] = MagicMock(pytest_plugins=[])
    sys.modules["dazzle.mcp.server.state"] = mock_state

    module_path = (
        Path(__file__).parent.parent.parent.parent
        / "src"
        / "dazzle"
        / "mcp"
        / "server"
        / "handlers"
        / "user_management.py"
    )
    spec = importlib.util.spec_from_file_location(
        "dazzle.mcp.server.handlers.user_management",
        module_path,
        submodule_search_locations=[],
    )
    module = importlib.util.module_from_spec(spec)

    # Set up the package structure for relative imports
    module.__package__ = "dazzle.mcp.server.handlers"
    sys.modules["dazzle.mcp.server.handlers.user_management"] = module

    spec.loader.exec_module(module)
    return module


# Import the module once at module load time
_um = _import_user_management()


@pytest.fixture
def temp_project(tmp_path):
    """Create a temporary project directory with auth database."""
    project_dir = tmp_path / "test_project"
    project_dir.mkdir()
    dazzle_dir = project_dir / ".dazzle"
    dazzle_dir.mkdir()
    return project_dir


@pytest.fixture
def auth_store(temp_project):
    """Create an AuthStore instance for testing."""
    from dazzle_back.runtime.auth import AuthStore

    db_path = temp_project / ".dazzle" / "auth.db"
    return AuthStore(db_path=db_path)


@pytest.fixture
def test_user(auth_store):
    """Create a test user in the auth store."""
    return auth_store.create_user(
        email="test@example.com",
        password="testpass123",
        username="testuser",
        is_superuser=False,
        roles=["user"],
    )


@pytest.fixture
def admin_user(auth_store):
    """Create an admin user in the auth store."""
    return auth_store.create_user(
        email="admin@example.com",
        password="adminpass123",
        username="adminuser",
        is_superuser=True,
        roles=["admin", "user"],
    )


class TestListUsersHandler:
    """Tests for list_users_handler."""

    @pytest.mark.asyncio
    async def test_list_users_returns_all(self, temp_project, test_user, admin_user):
        """Test that list_users returns all active users."""
        result = await _um.list_users_handler(project_path=str(temp_project))

        assert result["count"] == 2
        assert len(result["users"]) == 2
        emails = [u["email"] for u in result["users"]]
        assert "test@example.com" in emails
        assert "admin@example.com" in emails

    @pytest.mark.asyncio
    async def test_list_users_filters_by_role(self, temp_project, test_user, admin_user):
        """Test filtering users by role."""
        result = await _um.list_users_handler(role="admin", project_path=str(temp_project))

        assert result["count"] == 1
        assert result["users"][0]["email"] == "admin@example.com"
        assert result["filters"]["role"] == "admin"

    @pytest.mark.asyncio
    async def test_list_users_respects_active_only(self, temp_project, auth_store, test_user):
        """Test that active_only filter works."""
        # Deactivate user
        auth_store._execute_modify(
            "UPDATE users SET is_active = ? WHERE id = ?",
            (auth_store._bool_to_db(False), str(test_user.id)),
        )

        # With active_only=True (default)
        result = await _um.list_users_handler(project_path=str(temp_project))
        assert result["count"] == 0

        # With active_only=False
        result = await _um.list_users_handler(active_only=False, project_path=str(temp_project))
        assert result["count"] == 1

    @pytest.mark.asyncio
    async def test_list_users_pagination(self, temp_project, auth_store):
        """Test pagination with limit and offset."""
        # Create 5 users
        for i in range(5):
            auth_store.create_user(
                email=f"user{i}@example.com",
                password="pass123",
                username=f"user{i}",
            )

        # Test limit
        result = await _um.list_users_handler(limit=2, project_path=str(temp_project))
        assert result["count"] == 2
        assert result["filters"]["limit"] == 2

        # Test offset
        result = await _um.list_users_handler(limit=2, offset=2, project_path=str(temp_project))
        assert result["count"] == 2
        assert result["filters"]["offset"] == 2


class TestCreateUserHandler:
    """Tests for create_user_handler."""

    @pytest.mark.asyncio
    async def test_create_user_success(self, temp_project):
        """Test successful user creation."""
        result = await _um.create_user_handler(
            email="new@example.com",
            name="New User",
            roles=["user"],
            project_path=str(temp_project),
        )

        assert result["success"] is True
        assert result["user"]["email"] == "new@example.com"
        assert result["user"]["username"] == "New User"
        assert "temporary_password" in result
        assert len(result["temporary_password"]) >= 16

    @pytest.mark.asyncio
    async def test_create_user_duplicate_email(self, temp_project, test_user):
        """Test that duplicate email returns error."""
        result = await _um.create_user_handler(
            email="test@example.com",  # Same as test_user
            project_path=str(temp_project),
        )

        assert result["success"] is False
        assert "already exists" in result["error"]
        assert "existing_user_id" in result

    @pytest.mark.asyncio
    async def test_create_user_with_roles(self, temp_project):
        """Test creating user with multiple roles."""
        result = await _um.create_user_handler(
            email="manager@example.com",
            roles=["manager", "user"],
            is_superuser=False,
            project_path=str(temp_project),
        )

        assert result["success"] is True
        assert result["user"]["roles"] == ["manager", "user"]

    @pytest.mark.asyncio
    async def test_create_superuser(self, temp_project):
        """Test creating a superuser."""
        result = await _um.create_user_handler(
            email="superadmin@example.com",
            is_superuser=True,
            project_path=str(temp_project),
        )

        assert result["success"] is True
        assert result["user"]["is_superuser"] is True


class TestGetUserHandler:
    """Tests for get_user_handler."""

    @pytest.mark.asyncio
    async def test_get_user_by_id(self, temp_project, test_user):
        """Test getting user by ID."""
        result = await _um.get_user_handler(
            user_id=str(test_user.id),
            project_path=str(temp_project),
        )

        assert result["found"] is True
        assert result["user"]["email"] == "test@example.com"
        assert "active_sessions" in result

    @pytest.mark.asyncio
    async def test_get_user_by_email(self, temp_project, test_user):
        """Test getting user by email."""
        result = await _um.get_user_handler(
            email="test@example.com",
            project_path=str(temp_project),
        )

        assert result["found"] is True
        assert result["user"]["id"] == str(test_user.id)

    @pytest.mark.asyncio
    async def test_get_user_not_found(self, temp_project):
        """Test getting non-existent user."""
        result = await _um.get_user_handler(
            email="nonexistent@example.com",
            project_path=str(temp_project),
        )

        assert result["found"] is False
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_get_user_requires_id_or_email(self, temp_project):
        """Test that handler requires either user_id or email."""
        result = await _um.get_user_handler(project_path=str(temp_project))

        assert "error" in result
        assert "Must provide either" in result["error"]


class TestUpdateUserHandler:
    """Tests for update_user_handler."""

    @pytest.mark.asyncio
    async def test_update_username(self, temp_project, test_user):
        """Test updating username."""
        result = await _um.update_user_handler(
            user_id=str(test_user.id),
            username="newname",
            project_path=str(temp_project),
        )

        assert result["success"] is True
        assert result["user"]["username"] == "newname"
        assert result["changes"]["username"] == "newname"

    @pytest.mark.asyncio
    async def test_update_roles(self, temp_project, test_user):
        """Test updating user roles."""
        result = await _um.update_user_handler(
            user_id=str(test_user.id),
            roles=["admin", "user"],
            project_path=str(temp_project),
        )

        assert result["success"] is True
        assert result["user"]["roles"] == ["admin", "user"]

    @pytest.mark.asyncio
    async def test_update_deactivate(self, temp_project, test_user):
        """Test deactivating user via update."""
        result = await _um.update_user_handler(
            user_id=str(test_user.id),
            is_active=False,
            project_path=str(temp_project),
        )

        assert result["success"] is True
        assert result["user"]["is_active"] is False

    @pytest.mark.asyncio
    async def test_update_user_not_found(self, temp_project):
        """Test updating non-existent user."""
        result = await _um.update_user_handler(
            user_id="00000000-0000-0000-0000-000000000000",
            username="whatever",
            project_path=str(temp_project),
        )

        assert result["success"] is False
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_update_no_changes(self, temp_project, test_user):
        """Test update with no changes provided."""
        result = await _um.update_user_handler(
            user_id=str(test_user.id),
            project_path=str(temp_project),
        )

        assert result["success"] is False
        assert "No updates provided" in result["error"]


class TestResetPasswordHandler:
    """Tests for reset_password_handler."""

    @pytest.mark.asyncio
    async def test_reset_password_generates_new(self, temp_project, test_user):
        """Test that reset_password generates a new password."""
        result = await _um.reset_password_handler(
            user_id=str(test_user.id),
            project_path=str(temp_project),
        )

        assert result["success"] is True
        assert "temporary_password" in result
        assert len(result["temporary_password"]) >= 16
        assert result["email"] == "test@example.com"

    @pytest.mark.asyncio
    async def test_reset_password_revokes_sessions(self, temp_project, test_user, auth_store):
        """Test that reset_password revokes all sessions."""
        # Create sessions for the user
        auth_store.create_session(test_user)
        auth_store.create_session(test_user)

        result = await _um.reset_password_handler(
            user_id=str(test_user.id),
            project_path=str(temp_project),
        )

        assert result["success"] is True
        assert result["sessions_revoked"] == 2

    @pytest.mark.asyncio
    async def test_reset_password_user_not_found(self, temp_project):
        """Test reset_password for non-existent user."""
        result = await _um.reset_password_handler(
            user_id="00000000-0000-0000-0000-000000000000",
            project_path=str(temp_project),
        )

        assert result["success"] is False
        assert "not found" in result["error"]


class TestDeactivateUserHandler:
    """Tests for deactivate_user_handler."""

    @pytest.mark.asyncio
    async def test_deactivate_user(self, temp_project, test_user, auth_store):
        """Test deactivating an active user."""
        # Create a session first
        auth_store.create_session(test_user)

        result = await _um.deactivate_user_handler(
            user_id=str(test_user.id),
            project_path=str(temp_project),
        )

        assert result["success"] is True
        assert result["email"] == "test@example.com"
        assert result["sessions_revoked"] == 1

        # Verify user is actually deactivated
        user = auth_store.get_user_by_id(test_user.id)
        assert user.is_active is False

    @pytest.mark.asyncio
    async def test_deactivate_already_inactive(self, temp_project, test_user, auth_store):
        """Test deactivating an already inactive user."""
        # Deactivate first
        auth_store._execute_modify(
            "UPDATE users SET is_active = ? WHERE id = ?",
            (auth_store._bool_to_db(False), str(test_user.id)),
        )

        result = await _um.deactivate_user_handler(
            user_id=str(test_user.id),
            project_path=str(temp_project),
        )

        assert result["success"] is False
        assert "already deactivated" in result["error"]

    @pytest.mark.asyncio
    async def test_deactivate_user_not_found(self, temp_project):
        """Test deactivating non-existent user."""
        result = await _um.deactivate_user_handler(
            user_id="00000000-0000-0000-0000-000000000000",
            project_path=str(temp_project),
        )

        assert result["success"] is False
        assert "not found" in result["error"]


class TestListSessionsHandler:
    """Tests for list_sessions_handler."""

    @pytest.mark.asyncio
    async def test_list_sessions(self, temp_project, test_user, auth_store):
        """Test listing all sessions."""
        # Create sessions
        auth_store.create_session(test_user)
        auth_store.create_session(test_user)

        result = await _um.list_sessions_handler(project_path=str(temp_project))

        assert result["count"] == 2
        assert len(result["sessions"]) == 2

    @pytest.mark.asyncio
    async def test_list_sessions_by_user(self, temp_project, test_user, admin_user, auth_store):
        """Test listing sessions for a specific user."""
        auth_store.create_session(test_user)
        auth_store.create_session(admin_user)

        result = await _um.list_sessions_handler(
            user_id=str(test_user.id),
            project_path=str(temp_project),
        )

        assert result["count"] == 1
        assert result["sessions"][0]["user_id"] == str(test_user.id)

    @pytest.mark.asyncio
    async def test_list_sessions_active_only(self, temp_project, test_user, auth_store):
        """Test that active_only filters expired sessions."""
        # Create an active session
        auth_store.create_session(test_user)

        # Note: By default sessions are created with 7-day expiry,
        # so they're all active. Testing this properly would require
        # manipulating time or directly inserting expired sessions.

        result = await _um.list_sessions_handler(
            active_only=True,
            project_path=str(temp_project),
        )

        assert result["count"] == 1


class TestRevokeSessionHandler:
    """Tests for revoke_session_handler."""

    @pytest.mark.asyncio
    async def test_revoke_session(self, temp_project, test_user, auth_store):
        """Test revoking a specific session."""
        session = auth_store.create_session(test_user)

        result = await _um.revoke_session_handler(
            session_id=session.id,
            project_path=str(temp_project),
        )

        assert result["success"] is True
        assert result["session_id"] == session.id
        assert result["user_id"] == str(test_user.id)

        # Verify session is actually deleted
        deleted_session = auth_store.get_session(session.id)
        assert deleted_session is None

    @pytest.mark.asyncio
    async def test_revoke_session_not_found(self, temp_project):
        """Test revoking non-existent session."""
        result = await _um.revoke_session_handler(
            session_id="nonexistent-session-id",
            project_path=str(temp_project),
        )

        assert result["success"] is False
        assert "not found" in result["error"]


class TestGetAuthConfigHandler:
    """Tests for get_auth_config_handler."""

    @pytest.mark.asyncio
    async def test_get_config_sqlite(self, temp_project, test_user, admin_user, auth_store):
        """Test getting auth config for SQLite backend."""
        # Create a session
        auth_store.create_session(test_user)

        result = await _um.get_auth_config_handler(project_path=str(temp_project))

        assert result["database_type"] == "sqlite"
        assert result["total_users"] == 2
        assert result["active_users"] == 2
        assert result["active_sessions"] == 1
        assert "admin" in result["roles_in_use"]
        assert "user" in result["roles_in_use"]

    @pytest.mark.asyncio
    async def test_get_config_postgres(self, temp_project):
        """Test getting auth config for PostgreSQL backend."""
        # Mock the environment to simulate PostgreSQL
        with patch.dict("os.environ", {"DATABASE_URL": "postgresql://localhost/test"}):
            with patch("dazzle_back.runtime.auth.AuthStore._init_db"):
                with patch("dazzle_back.runtime.auth.AuthStore._execute") as mock_execute:
                    # Mock the queries that get_auth_config_handler makes
                    mock_execute.side_effect = [
                        [{"count": 10}],  # user count
                        [{"count": 8}],  # active user count
                        [{"count": 5}],  # session count
                        [{"roles": '["admin"]'}, {"roles": '["user"]'}],  # roles
                    ]

                    result = await _um.get_auth_config_handler(project_path=str(temp_project))

        assert result["database_type"] == "postgresql"
        assert result["total_users"] == 10
        assert result["active_users"] == 8
        assert result["active_sessions"] == 5


class TestHelperFunctions:
    """Tests for helper functions in user_management module."""

    def test_generate_temp_password_length(self):
        """Test that temp password has correct length."""
        password = _um._generate_temp_password(16)
        assert len(password) == 16

        password = _um._generate_temp_password(24)
        assert len(password) == 24

    def test_generate_temp_password_characters(self):
        """Test that temp password uses expected character set."""
        password = _um._generate_temp_password(100)
        allowed = set(string.ascii_letters + string.digits)
        assert all(c in allowed for c in password)

    def test_user_to_dict(self):
        """Test user record to dict conversion."""
        from dazzle_back.runtime.auth import UserRecord

        user = UserRecord(
            email="test@example.com",
            password_hash="hash123",
            username="testuser",
            roles=["admin"],
        )

        result = _um._user_to_dict(user)

        assert result["email"] == "test@example.com"
        assert result["username"] == "testuser"
        assert result["roles"] == ["admin"]
        assert "password_hash" not in result

    def test_user_to_dict_with_hash(self):
        """Test user record to dict with password hash included."""
        from dazzle_back.runtime.auth import UserRecord

        user = UserRecord(
            email="test@example.com",
            password_hash="hash123",
        )

        result = _um._user_to_dict(user, include_hash=True)

        assert "password_hash" in result
        assert result["password_hash"] == "hash123"
