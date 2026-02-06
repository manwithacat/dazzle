"""Tests for dazzle.cli.auth CLI commands."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from dazzle_back.runtime.auth import AuthStore

runner = CliRunner()


@pytest.fixture()
def auth_store(tmp_path):
    """Create a real SQLite AuthStore in a temp directory."""
    db_path = tmp_path / "auth.db"
    return AuthStore(db_path=db_path)


@pytest.fixture()
def _patch_store(auth_store):
    """Patch _get_auth_store to return the test store."""
    with patch("dazzle.cli.auth._get_auth_store", return_value=auth_store):
        yield


@pytest.fixture()
def app():
    """Get the auth typer app."""
    from dazzle.cli.auth import auth_app

    return auth_app


@pytest.fixture()
def seeded_store(auth_store):
    """AuthStore with a pre-created user."""
    auth_store.create_user(
        email="alice@example.com",
        password="testpass123",
        username="Alice",
        roles=["admin"],
    )
    return auth_store


# =============================================================================
# create-user
# =============================================================================


@pytest.mark.usefixtures("_patch_store")
class TestCreateUser:
    def test_create_user_success(self, app, auth_store):
        result = runner.invoke(app, ["create-user", "bob@example.com", "--name", "Bob"])
        assert result.exit_code == 0
        assert "User created" in result.output
        assert "bob@example.com" in result.output

        user = auth_store.get_user_by_email("bob@example.com")
        assert user is not None
        assert user.username == "Bob"

    def test_create_user_with_roles(self, app, auth_store):
        result = runner.invoke(app, ["create-user", "bob@example.com", "--roles", "admin,manager"])
        assert result.exit_code == 0

        user = auth_store.get_user_by_email("bob@example.com")
        assert user is not None
        assert set(user.roles) == {"admin", "manager"}

    def test_create_user_duplicate(self, app, seeded_store):
        result = runner.invoke(app, ["create-user", "alice@example.com"])
        assert result.exit_code == 1
        assert "already exists" in result.output

    def test_create_user_json(self, app, auth_store):
        result = runner.invoke(app, ["create-user", "bob@example.com", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["email"] == "bob@example.com"
        assert "temporary_password" in data

    def test_create_user_superuser(self, app, auth_store):
        result = runner.invoke(app, ["create-user", "admin@example.com", "--superuser"])
        assert result.exit_code == 0

        user = auth_store.get_user_by_email("admin@example.com")
        assert user is not None
        assert user.is_superuser is True


# =============================================================================
# list-users
# =============================================================================


@pytest.mark.usefixtures("_patch_store")
class TestListUsers:
    def test_list_users_empty(self, app):
        result = runner.invoke(app, ["list-users"])
        assert result.exit_code == 0
        assert "No users found" in result.output

    def test_list_users_with_data(self, app, seeded_store):
        result = runner.invoke(app, ["list-users"])
        assert result.exit_code == 0
        assert "alice@example.com" in result.output

    def test_list_users_json(self, app, seeded_store):
        result = runner.invoke(app, ["list-users", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["email"] == "alice@example.com"

    def test_list_users_role_filter(self, app, seeded_store):
        # Add a non-admin user
        seeded_store.create_user(email="bob@example.com", password="pass", roles=["viewer"])

        result = runner.invoke(app, ["list-users", "--role", "admin", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["email"] == "alice@example.com"

    def test_list_users_include_inactive(self, app, seeded_store):
        user = seeded_store.get_user_by_email("alice@example.com")
        seeded_store.update_user(user_id=user.id, is_active=False)

        result = runner.invoke(app, ["list-users", "--json"])
        data = json.loads(result.output)
        assert len(data) == 0

        result = runner.invoke(app, ["list-users", "--include-inactive", "--json"])
        data = json.loads(result.output)
        assert len(data) == 1


# =============================================================================
# get-user
# =============================================================================


@pytest.mark.usefixtures("_patch_store")
class TestGetUser:
    def test_get_user_by_email(self, app, seeded_store):
        result = runner.invoke(app, ["get-user", "alice@example.com"])
        assert result.exit_code == 0
        assert "alice@example.com" in result.output
        assert "Alice" in result.output

    def test_get_user_by_uuid(self, app, seeded_store):
        user = seeded_store.get_user_by_email("alice@example.com")
        result = runner.invoke(app, ["get-user", str(user.id)])
        assert result.exit_code == 0
        assert "alice@example.com" in result.output

    def test_get_user_not_found(self, app, seeded_store):
        result = runner.invoke(app, ["get-user", "nobody@example.com"])
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_get_user_json(self, app, seeded_store):
        result = runner.invoke(app, ["get-user", "alice@example.com", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["email"] == "alice@example.com"
        assert "active_sessions" in data


# =============================================================================
# update-user
# =============================================================================


@pytest.mark.usefixtures("_patch_store")
class TestUpdateUser:
    def test_update_name(self, app, seeded_store):
        result = runner.invoke(app, ["update-user", "alice@example.com", "--name", "Alice B"])
        assert result.exit_code == 0
        assert "User updated" in result.output

        user = seeded_store.get_user_by_email("alice@example.com")
        assert user.username == "Alice B"

    def test_update_roles(self, app, seeded_store):
        result = runner.invoke(
            app, ["update-user", "alice@example.com", "--roles", "admin,manager"]
        )
        assert result.exit_code == 0

        user = seeded_store.get_user_by_email("alice@example.com")
        assert set(user.roles) == {"admin", "manager"}

    def test_update_not_found(self, app, seeded_store):
        result = runner.invoke(app, ["update-user", "nobody@example.com", "--name", "X"])
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_update_no_changes(self, app, seeded_store):
        result = runner.invoke(app, ["update-user", "alice@example.com"])
        assert result.exit_code == 1
        assert "No updates" in result.output

    def test_update_json(self, app, seeded_store):
        result = runner.invoke(
            app, ["update-user", "alice@example.com", "--name", "Alice Updated", "--json"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["username"] == "Alice Updated"


# =============================================================================
# reset-password
# =============================================================================


@pytest.mark.usefixtures("_patch_store")
class TestResetPassword:
    def test_reset_password(self, app, seeded_store):
        result = runner.invoke(app, ["reset-password", "alice@example.com"])
        assert result.exit_code == 0
        assert "Password reset" in result.output
        assert "New temporary password" in result.output

    def test_reset_password_not_found(self, app, seeded_store):
        result = runner.invoke(app, ["reset-password", "nobody@example.com"])
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_reset_password_json(self, app, seeded_store):
        result = runner.invoke(app, ["reset-password", "alice@example.com", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "temporary_password" in data
        assert data["email"] == "alice@example.com"


# =============================================================================
# deactivate
# =============================================================================


@pytest.mark.usefixtures("_patch_store")
class TestDeactivate:
    def test_deactivate_with_yes(self, app, seeded_store):
        result = runner.invoke(app, ["deactivate", "alice@example.com", "--yes"])
        assert result.exit_code == 0
        assert "deactivated" in result.output

        user = seeded_store.get_user_by_email("alice@example.com")
        assert user.is_active is False

    def test_deactivate_already_inactive(self, app, seeded_store):
        user = seeded_store.get_user_by_email("alice@example.com")
        seeded_store.update_user(user_id=user.id, is_active=False)

        result = runner.invoke(app, ["deactivate", "alice@example.com", "--yes"])
        assert result.exit_code == 1
        assert "already deactivated" in result.output

    def test_deactivate_not_found(self, app, seeded_store):
        result = runner.invoke(app, ["deactivate", "nobody@example.com", "--yes"])
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_deactivate_json(self, app, seeded_store):
        result = runner.invoke(app, ["deactivate", "alice@example.com", "--yes", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["deactivated"] is True


# =============================================================================
# list-sessions
# =============================================================================


@pytest.mark.usefixtures("_patch_store")
class TestListSessions:
    def test_list_sessions_empty(self, app, auth_store):
        result = runner.invoke(app, ["list-sessions"])
        assert result.exit_code == 0
        assert "No sessions found" in result.output

    def test_list_sessions_with_data(self, app, seeded_store):
        user = seeded_store.get_user_by_email("alice@example.com")
        seeded_store.create_session(user)

        result = runner.invoke(app, ["list-sessions"])
        assert result.exit_code == 0
        assert "1 session(s) shown" in result.output

    def test_list_sessions_json(self, app, seeded_store):
        user = seeded_store.get_user_by_email("alice@example.com")
        seeded_store.create_session(user)

        result = runner.invoke(app, ["list-sessions", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1

    def test_list_sessions_user_filter(self, app, seeded_store):
        result = runner.invoke(app, ["list-sessions", "--user", "alice@example.com", "--json"])
        assert result.exit_code == 0

    def test_list_sessions_user_not_found(self, app, seeded_store):
        result = runner.invoke(app, ["list-sessions", "--user", "nobody@example.com"])
        assert result.exit_code == 1
        assert "not found" in result.output


# =============================================================================
# cleanup-sessions
# =============================================================================


@pytest.mark.usefixtures("_patch_store")
class TestCleanupSessions:
    def test_cleanup_sessions(self, app, auth_store):
        result = runner.invoke(app, ["cleanup-sessions"])
        assert result.exit_code == 0
        assert "Removed" in result.output

    def test_cleanup_sessions_json(self, app, auth_store):
        result = runner.invoke(app, ["cleanup-sessions", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "removed" in data


# =============================================================================
# config
# =============================================================================


@pytest.mark.usefixtures("_patch_store")
class TestConfig:
    def test_config(self, app, auth_store):
        result = runner.invoke(app, ["config"])
        assert result.exit_code == 0
        assert "sqlite" in result.output
        assert "Total users" in result.output

    def test_config_json(self, app, auth_store):
        result = runner.invoke(app, ["config", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["database_type"] == "sqlite"
        assert "total_users" in data
        assert "active_users" in data
        assert "active_sessions" in data

    def test_config_with_users(self, app, seeded_store):
        result = runner.invoke(app, ["config", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["total_users"] == 1
        assert data["active_users"] == 1
        assert "admin" in data["roles_in_use"]
