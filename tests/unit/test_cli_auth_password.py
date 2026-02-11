"""Tests for --password flag on create-user and reset-password CLI commands."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

runner = CliRunner()


def _make_fake_user(email: str = "bob@example.com") -> MagicMock:
    fake_user = MagicMock()
    fake_user.id = "00000000-0000-0000-0000-000000000001"
    fake_user.email = email
    fake_user.username = None
    fake_user.is_active = True
    fake_user.is_superuser = False
    fake_user.roles = []
    fake_user.password_hash = "salt$hash"
    fake_user.created_at.isoformat.return_value = "2026-01-01T00:00:00"
    fake_user.updated_at.isoformat.return_value = "2026-01-01T00:00:00"
    return fake_user


@pytest.fixture()
def create_store():
    """Mock store for create-user tests — no existing user."""
    store = MagicMock()
    fake_user = _make_fake_user()
    store.get_user_by_email.return_value = None
    store.create_user.return_value = fake_user
    return store


@pytest.fixture()
def reset_store():
    """Mock store for reset-password tests — user exists."""
    store = MagicMock()
    fake_user = _make_fake_user()
    store.get_user_by_email.return_value = fake_user
    store.update_password.return_value = True
    store.delete_user_sessions.return_value = 2
    return store


@pytest.fixture()
def app():
    from dazzle.cli.auth import auth_app

    return auth_app


# ── create-user --password ───────────────────────────────────────────


class TestCreateUserExplicitPassword:
    def test_explicit_password_sets_value(self, app, create_store):
        with patch("dazzle.cli.auth._get_auth_store", return_value=create_store):
            result = runner.invoke(
                app, ["create-user", "bob@example.com", "--password", "MySecurePass123"]
            )
        assert result.exit_code == 0
        assert "User created" in result.output
        assert "set to provided value" in result.output
        create_store.create_user.assert_called_once()
        call_kwargs = create_store.create_user.call_args[1]
        assert call_kwargs["password"] == "MySecurePass123"

    def test_explicit_password_json_omits_temporary(self, app, create_store):
        with patch("dazzle.cli.auth._get_auth_store", return_value=create_store):
            result = runner.invoke(
                app,
                ["create-user", "bob@example.com", "--password", "MySecurePass123", "--json"],
            )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["email"] == "bob@example.com"
        assert "temporary_password" not in data

    def test_generated_password_json_includes_temporary(self, app, create_store):
        with patch("dazzle.cli.auth._get_auth_store", return_value=create_store):
            result = runner.invoke(app, ["create-user", "bob@example.com", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "temporary_password" in data

    def test_short_password_rejected(self, app, create_store):
        with patch("dazzle.cli.auth._get_auth_store", return_value=create_store):
            result = runner.invoke(app, ["create-user", "bob@example.com", "--password", "short"])
        assert result.exit_code == 1
        assert "at least 8 characters" in result.output
        create_store.create_user.assert_not_called()

    def test_password_exactly_min_length_accepted(self, app, create_store):
        with patch("dazzle.cli.auth._get_auth_store", return_value=create_store):
            result = runner.invoke(
                app, ["create-user", "bob@example.com", "--password", "12345678"]
            )
        assert result.exit_code == 0
        create_store.create_user.assert_called_once()


# ── reset-password --password ────────────────────────────────────────


class TestResetPasswordExplicitPassword:
    def test_explicit_password_sets_value(self, app, reset_store):
        with patch("dazzle.cli.auth._get_auth_store", return_value=reset_store):
            result = runner.invoke(
                app, ["reset-password", "bob@example.com", "--password", "NewSecurePass1"]
            )
        assert result.exit_code == 0
        assert "Password reset" in result.output
        assert "set to provided value" in result.output
        reset_store.update_password.assert_called_once()
        call_args = reset_store.update_password.call_args[0]
        assert call_args[1] == "NewSecurePass1"

    def test_explicit_password_json_omits_temporary(self, app, reset_store):
        with patch("dazzle.cli.auth._get_auth_store", return_value=reset_store):
            result = runner.invoke(
                app,
                ["reset-password", "bob@example.com", "--password", "NewSecurePass1", "--json"],
            )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["email"] == "bob@example.com"
        assert "temporary_password" not in data

    def test_generated_password_json_includes_temporary(self, app, reset_store):
        with patch("dazzle.cli.auth._get_auth_store", return_value=reset_store):
            result = runner.invoke(app, ["reset-password", "bob@example.com", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "temporary_password" in data

    def test_short_password_rejected(self, app, reset_store):
        with patch("dazzle.cli.auth._get_auth_store", return_value=reset_store):
            result = runner.invoke(
                app, ["reset-password", "bob@example.com", "--password", "short"]
            )
        assert result.exit_code == 1
        assert "at least 8 characters" in result.output
        reset_store.update_password.assert_not_called()
