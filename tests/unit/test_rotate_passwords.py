"""Tests for dazzle auth rotate-passwords command (#695)."""

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

runner = CliRunner()


class TestRotatePasswordsCommand:
    @patch("dazzle.cli.auth._get_auth_store")
    def test_rotate_all_generate(self, mock_store_fn):
        mock_store = MagicMock()
        user1 = MagicMock()
        user1.id = "u1"
        user1.email = "a@test.com"
        user2 = MagicMock()
        user2.id = "u2"
        user2.email = "b@test.com"
        mock_store.list_users.return_value = [user1, user2]
        mock_store.update_password.return_value = True
        mock_store.delete_user_sessions.return_value = 1
        mock_store_fn.return_value = mock_store
        from dazzle.cli.auth import auth_app

        result = runner.invoke(auth_app, ["rotate-passwords", "--all", "--generate", "--yes"])
        assert result.exit_code == 0
        assert mock_store.update_password.call_count == 2
        assert mock_store.delete_user_sessions.call_count == 2

    @patch("dazzle.cli.auth._get_auth_store")
    def test_rotate_by_role(self, mock_store_fn):
        mock_store = MagicMock()
        user1 = MagicMock()
        user1.id = "u1"
        user1.email = "teacher@test.com"
        mock_store.list_users.return_value = [user1]
        mock_store.update_password.return_value = True
        mock_store.delete_user_sessions.return_value = 0
        mock_store_fn.return_value = mock_store
        from dazzle.cli.auth import auth_app

        result = runner.invoke(
            auth_app, ["rotate-passwords", "--role", "teacher", "--generate", "--yes"]
        )
        assert result.exit_code == 0
        mock_store.list_users.assert_called_once_with(role="teacher")

    @patch("dazzle.cli.auth._get_auth_store")
    def test_rotate_explicit_password(self, mock_store_fn):
        mock_store = MagicMock()
        user1 = MagicMock()
        user1.id = "u1"
        user1.email = "a@test.com"
        mock_store.list_users.return_value = [user1]
        mock_store.update_password.return_value = True
        mock_store.delete_user_sessions.return_value = 0
        mock_store_fn.return_value = mock_store
        from dazzle.cli.auth import auth_app

        result = runner.invoke(
            auth_app, ["rotate-passwords", "--all", "--password", "NewSecure123", "--yes"]
        )
        assert result.exit_code == 0
        mock_store.update_password.assert_called_once_with("u1", "NewSecure123")

    @patch("dazzle.cli.auth._get_auth_store")
    def test_requires_yes(self, mock_store_fn):
        from dazzle.cli.auth import auth_app

        result = runner.invoke(auth_app, ["rotate-passwords", "--all", "--generate"], input="n\n")
        assert result.exit_code != 0

    @patch("dazzle.cli.auth._get_auth_store")
    def test_requires_generate_or_password(self, mock_store_fn):
        from dazzle.cli.auth import auth_app

        result = runner.invoke(auth_app, ["rotate-passwords", "--all", "--yes"])
        assert result.exit_code == 1

    @patch("dazzle.cli.auth._get_auth_store")
    def test_requires_all_or_role(self, mock_store_fn):
        from dazzle.cli.auth import auth_app

        result = runner.invoke(auth_app, ["rotate-passwords", "--generate", "--yes"])
        assert result.exit_code == 1
