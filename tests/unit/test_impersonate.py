"""Tests for dazzle auth impersonate command (#695)."""

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

runner = CliRunner()


class TestParseTtl:
    def test_minutes(self):
        from dazzle.cli.auth import _parse_ttl

        assert _parse_ttl("5m") == 300

    def test_hours(self):
        from dazzle.cli.auth import _parse_ttl

        assert _parse_ttl("1h") == 3600

    def test_seconds(self):
        from dazzle.cli.auth import _parse_ttl

        assert _parse_ttl("30s") == 30

    def test_bare_number(self):
        from dazzle.cli.auth import _parse_ttl

        assert _parse_ttl("120") == 120


class TestImpersonateCommand:
    @patch("dazzle.cli.auth._get_auth_store")
    def test_cookie_mode_prints_session(self, mock_store_fn):
        mock_store = MagicMock()
        mock_user = MagicMock()
        mock_user.id = "user-uuid-1"
        mock_user.email = "teacher@school.uk"
        mock_session = MagicMock()
        mock_session.id = "session-token-abc"
        mock_store.get_user_by_email.return_value = mock_user
        mock_store.create_session.return_value = mock_session
        mock_store_fn.return_value = mock_store
        from dazzle.cli.auth import auth_app

        result = runner.invoke(auth_app, ["impersonate", "teacher@school.uk"])
        assert result.exit_code == 0
        assert "session-token-abc" in result.output

    @patch("dazzle.cli.auth._get_auth_store")
    def test_url_mode_prints_magic_link(self, mock_store_fn):
        mock_store = MagicMock()
        mock_user = MagicMock()
        mock_user.id = "user-uuid-1"
        mock_user.email = "teacher@school.uk"
        mock_store.get_user_by_email.return_value = mock_user
        mock_store._execute_modify = MagicMock()
        mock_store_fn.return_value = mock_store
        from dazzle.cli.auth import auth_app

        result = runner.invoke(auth_app, ["impersonate", "teacher@school.uk", "--url"])
        assert result.exit_code == 0
        assert "/_auth/magic/" in result.output

    @patch("dazzle.cli.auth._get_auth_store")
    def test_user_not_found(self, mock_store_fn):
        mock_store = MagicMock()
        mock_store.get_user_by_email.return_value = None
        mock_store_fn.return_value = mock_store
        from dazzle.cli.auth import auth_app

        result = runner.invoke(auth_app, ["impersonate", "nobody@example.com"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    @patch("dazzle.cli.auth._get_auth_store")
    def test_json_output(self, mock_store_fn):
        mock_store = MagicMock()
        mock_user = MagicMock()
        mock_user.id = "user-uuid-1"
        mock_user.email = "teacher@school.uk"
        mock_session = MagicMock()
        mock_session.id = "session-abc"
        mock_store.get_user_by_email.return_value = mock_user
        mock_store.create_session.return_value = mock_session
        mock_store_fn.return_value = mock_store
        from dazzle.cli.auth import auth_app

        result = runner.invoke(auth_app, ["impersonate", "teacher@school.uk", "--json"])
        assert result.exit_code == 0
        assert '"session_id"' in result.output
