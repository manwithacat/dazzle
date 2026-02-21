"""Tests for test runner persona credential fallback (#253)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from dazzle.testing.test_runner import DazzleClient


@pytest.fixture
def runner() -> DazzleClient:
    """Create a DazzleClient with mocked HTTP client."""
    r = DazzleClient.__new__(DazzleClient)
    r.api_url = "http://localhost:8000"
    r.ui_url = "http://localhost:3000"
    r.client = MagicMock()
    r.client.cookies = MagicMock()
    r._test_routes_available = False  # Skip __test__/authenticate
    r._auth_token = None
    return r


class TestLoginWithCredentials:
    """_login_with_credentials should use per-persona credentials."""

    def test_admin_uses_env_vars(self, runner: DazzleClient) -> None:
        resp = MagicMock(status_code=200)
        resp.json.return_value = {"token": "admin-tok"}
        runner.client.request = MagicMock(return_value=resp)

        with patch.dict(
            "os.environ", {"DAZZLE_TEST_EMAIL": "a@b.com", "DAZZLE_TEST_PASSWORD": "pw"}
        ):
            assert runner._login_with_credentials("admin") is True
        runner.client.request.assert_called_once()
        call_json = runner.client.request.call_args.kwargs.get("json")
        assert call_json["email"] == "a@b.com"

    def test_non_admin_ignores_env_vars(self, runner: DazzleClient, tmp_path: Path) -> None:
        creds = {"personas": {"customer": {"email": "cust@test", "password": "pw"}}}
        creds_path = tmp_path / ".dazzle" / "test_credentials.json"
        creds_path.parent.mkdir(parents=True)
        creds_path.write_text(json.dumps(creds))

        resp = MagicMock(status_code=200)
        resp.json.return_value = {"token": "cust-tok"}
        runner.client.request = MagicMock(return_value=resp)

        with (
            patch.dict(
                "os.environ", {"DAZZLE_TEST_EMAIL": "admin@b.com", "DAZZLE_TEST_PASSWORD": "admpw"}
            ),
            patch("dazzle.testing.test_runner.Path", return_value=creds_path),
        ):
            assert runner._login_with_credentials("customer") is True
        call_json = runner.client.request.call_args.kwargs.get("json")
        assert call_json["email"] == "cust@test"

    def test_persona_from_creds_file(self, runner: DazzleClient, tmp_path: Path) -> None:
        creds = {
            "personas": {
                "admin": {"email": "admin@test", "password": "apw"},
                "agent": {"email": "agent@test", "password": "agpw"},
            }
        }
        creds_path = tmp_path / ".dazzle" / "test_credentials.json"
        creds_path.parent.mkdir(parents=True)
        creds_path.write_text(json.dumps(creds))

        resp = MagicMock(status_code=200)
        resp.json.return_value = {"token": "agent-tok"}
        runner.client.request = MagicMock(return_value=resp)

        with (
            patch.dict("os.environ", {}, clear=True),
            patch("dazzle.testing.test_runner.Path", return_value=creds_path),
        ):
            assert runner._login_with_credentials("agent") is True
        call_json = runner.client.request.call_args.kwargs.get("json")
        assert call_json["email"] == "agent@test"
        assert call_json["password"] == "agpw"

    def test_missing_persona_returns_false(self, runner: DazzleClient, tmp_path: Path) -> None:
        creds = {"personas": {"admin": {"email": "a@t", "password": "p"}}}
        creds_path = tmp_path / ".dazzle" / "test_credentials.json"
        creds_path.parent.mkdir(parents=True)
        creds_path.write_text(json.dumps(creds))

        with (
            patch.dict("os.environ", {}, clear=True),
            patch("dazzle.testing.test_runner.Path", return_value=creds_path),
        ):
            assert runner._login_with_credentials("unknown_persona") is False

    def test_admin_falls_back_to_top_level(self, runner: DazzleClient, tmp_path: Path) -> None:
        creds = {"email": "top@test", "password": "tpw"}
        creds_path = tmp_path / ".dazzle" / "test_credentials.json"
        creds_path.parent.mkdir(parents=True)
        creds_path.write_text(json.dumps(creds))

        resp = MagicMock(status_code=200)
        resp.json.return_value = {"token": "tok"}
        runner.client.request = MagicMock(return_value=resp)

        with (
            patch.dict("os.environ", {}, clear=True),
            patch("dazzle.testing.test_runner.Path", return_value=creds_path),
        ):
            assert runner._login_with_credentials("admin") is True
        call_json = runner.client.request.call_args.kwargs.get("json")
        assert call_json["email"] == "top@test"

    def test_non_admin_no_top_level_fallback(self, runner: DazzleClient, tmp_path: Path) -> None:
        """Non-admin personas should NOT fall back to top-level credentials."""
        creds = {"email": "top@test", "password": "tpw", "personas": {}}
        creds_path = tmp_path / ".dazzle" / "test_credentials.json"
        creds_path.parent.mkdir(parents=True)
        creds_path.write_text(json.dumps(creds))

        with (
            patch.dict("os.environ", {}, clear=True),
            patch("dazzle.testing.test_runner.Path", return_value=creds_path),
        ):
            assert runner._login_with_credentials("customer") is False


class TestAuthenticatePassesPersona:
    """authenticate() should pass persona through to _login_with_credentials."""

    def test_authenticate_passes_persona_on_fallback(self, runner: DazzleClient) -> None:
        runner._test_routes_available = False
        with patch.object(runner, "_login_with_credentials", return_value=True) as mock_login:
            runner.authenticate("customer")
        mock_login.assert_called_once_with("customer")

    def test_authenticate_passes_admin_persona(self, runner: DazzleClient) -> None:
        runner._test_routes_available = False
        with patch.object(runner, "_login_with_credentials", return_value=True) as mock_login:
            runner.authenticate("admin")
        mock_login.assert_called_once_with("admin")
