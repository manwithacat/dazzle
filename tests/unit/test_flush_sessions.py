"""Tests for flush-sessions command (#695)."""

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

runner = CliRunner()


class TestDeleteAllSessions:
    def test_delete_all_sessions_returns_count(self):
        from dazzle_back.runtime.auth.store import SessionStoreMixin

        mixin = SessionStoreMixin.__new__(SessionStoreMixin)
        mixin._execute_modify = MagicMock(return_value=5)
        result = mixin.delete_all_sessions()
        assert result == 5
        sql = mixin._execute_modify.call_args[0][0]
        assert "DELETE FROM sessions" in sql
        assert "WHERE" not in sql


class TestFlushSessionsCommand:
    @patch("dazzle.cli.auth._get_auth_store")
    def test_flush_all_requires_yes(self, mock_store_fn):
        from dazzle.cli.auth import auth_app

        result = runner.invoke(auth_app, ["flush-sessions"], input="n\n")
        assert result.exit_code != 0

    @patch("dazzle.cli.auth._get_auth_store")
    def test_flush_all_with_yes(self, mock_store_fn):
        mock_store = MagicMock()
        mock_store.delete_all_sessions.return_value = 42
        mock_store_fn.return_value = mock_store
        from dazzle.cli.auth import auth_app

        result = runner.invoke(auth_app, ["flush-sessions", "--yes"])
        assert result.exit_code == 0
        assert "42" in result.output
        mock_store.delete_all_sessions.assert_called_once()

    @patch("dazzle.cli.auth._get_auth_store")
    def test_flush_expired(self, mock_store_fn):
        mock_store = MagicMock()
        mock_store.cleanup_expired_sessions.return_value = 10
        mock_store_fn.return_value = mock_store
        from dazzle.cli.auth import auth_app

        result = runner.invoke(auth_app, ["flush-sessions", "--expired"])
        assert result.exit_code == 0
        assert "10" in result.output

    @patch("dazzle.cli.auth._get_auth_store")
    def test_flush_user(self, mock_store_fn):
        mock_store = MagicMock()
        mock_user = MagicMock()
        mock_user.id = "user-uuid-123"
        mock_store.get_user_by_email.return_value = mock_user
        mock_store.delete_user_sessions.return_value = 3
        mock_store_fn.return_value = mock_store
        from dazzle.cli.auth import auth_app

        result = runner.invoke(auth_app, ["flush-sessions", "--user", "test@example.com"])
        assert result.exit_code == 0
        assert "3" in result.output

    @patch("dazzle.cli.auth._get_auth_store")
    def test_flush_json_output(self, mock_store_fn):
        mock_store = MagicMock()
        mock_store.delete_all_sessions.return_value = 5
        mock_store_fn.return_value = mock_store
        from dazzle.cli.auth import auth_app

        result = runner.invoke(auth_app, ["flush-sessions", "--yes", "--json"])
        assert result.exit_code == 0
        assert '"deleted"' in result.output
