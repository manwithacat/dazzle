"""Tests for magic link token lifecycle (#695)."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from dazzle_back.runtime.auth.magic_link import create_magic_link, validate_magic_link


class TestCreateMagicLink:
    def test_returns_url_safe_token(self):
        mock_store = MagicMock()
        token = create_magic_link(mock_store, user_id="user-1", ttl_seconds=300, created_by="cli")
        assert len(token) > 20
        assert all(c.isalnum() or c in "-_" for c in token)

    def test_stores_token_in_db(self):
        mock_store = MagicMock()
        create_magic_link(mock_store, user_id="user-1", ttl_seconds=300, created_by="test")
        mock_store._execute_modify.assert_called_once()
        sql = mock_store._execute_modify.call_args[0][0]
        assert "INSERT INTO magic_links" in sql


class TestValidateMagicLink:
    def test_valid_token_returns_user_id(self):
        mock_store = MagicMock()
        future = (datetime.now(UTC) + timedelta(minutes=5)).isoformat()
        mock_store._execute.return_value = [
            {"user_id": "user-1", "expires_at": future, "used_at": None}
        ]
        result = validate_magic_link(mock_store, "some-token")
        assert result == "user-1"

    def test_expired_token_returns_none(self):
        mock_store = MagicMock()
        past = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
        mock_store._execute.return_value = [
            {"user_id": "user-1", "expires_at": past, "used_at": None}
        ]
        assert validate_magic_link(mock_store, "expired-token") is None

    def test_used_token_returns_none(self):
        mock_store = MagicMock()
        future = (datetime.now(UTC) + timedelta(minutes=5)).isoformat()
        mock_store._execute.return_value = [
            {"user_id": "user-1", "expires_at": future, "used_at": "2026-03-26T12:00:00"}
        ]
        assert validate_magic_link(mock_store, "used-token") is None

    def test_unknown_token_returns_none(self):
        mock_store = MagicMock()
        mock_store._execute.return_value = []
        assert validate_magic_link(mock_store, "unknown") is None

    def test_marks_token_as_used(self):
        mock_store = MagicMock()
        future = (datetime.now(UTC) + timedelta(minutes=5)).isoformat()
        mock_store._execute.return_value = [
            {"user_id": "user-1", "expires_at": future, "used_at": None}
        ]
        validate_magic_link(mock_store, "some-token")
        mock_store._execute_modify.assert_called_once()
        sql = mock_store._execute_modify.call_args[0][0]
        assert "UPDATE magic_links" in sql
        assert "used_at" in sql
