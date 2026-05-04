"""Tests for dazzle auth impersonate command (#695)."""

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

runner = CliRunner()


class TestParseTtl:
    @pytest.mark.parametrize(
        ("ttl_str", "expected_seconds"),
        [
            ("5m", 300),
            ("1h", 3600),
            ("30s", 30),
            ("120", 120),
        ],
        ids=["test_minutes", "test_hours", "test_seconds", "test_bare_number"],
    )
    def test_parse_ttl(self, ttl_str: str, expected_seconds: int) -> None:
        """_parse_ttl converts time strings to seconds."""
        from dazzle.cli.auth import _parse_ttl

        assert _parse_ttl(ttl_str) == expected_seconds


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
