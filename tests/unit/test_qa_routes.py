"""Tests for POST /qa/magic-link — dev-gated magic link generator."""

import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dazzle_back.runtime.qa_routes import create_qa_routes


@pytest.fixture
def mock_auth_store():
    store = MagicMock()
    return store


@pytest.fixture
def app_with_qa_routes(mock_auth_store):
    app = FastAPI()
    app.state.auth_store = mock_auth_store
    router = create_qa_routes()
    app.include_router(router)
    return app


@pytest.fixture
def client(app_with_qa_routes):
    return TestClient(app_with_qa_routes)


class TestQAMagicLinkGenerator:
    def test_returns_404_when_dazzle_env_not_development(self, client):
        """Without DAZZLE_ENV=development, endpoint returns 404."""
        with patch.dict(
            os.environ,
            {"DAZZLE_ENV": "production", "DAZZLE_QA_MODE": "1"},
            clear=False,
        ):
            resp = client.post(
                "/qa/magic-link",
                json={"persona_id": "admin"},
            )
        assert resp.status_code == 404

    def test_returns_404_when_qa_mode_not_set(self, client):
        """Without DAZZLE_QA_MODE=1, endpoint returns 404."""
        with patch.dict(
            os.environ,
            {"DAZZLE_ENV": "development", "DAZZLE_QA_MODE": "0"},
            clear=False,
        ):
            resp = client.post(
                "/qa/magic-link",
                json={"persona_id": "admin"},
            )
        assert resp.status_code == 404

    def test_returns_404_when_persona_not_found(self, client, mock_auth_store):
        """Unknown persona_id → 404."""
        mock_auth_store.get_user_by_email = MagicMock(return_value=None)
        with patch.dict(
            os.environ,
            {"DAZZLE_ENV": "development", "DAZZLE_QA_MODE": "1"},
            clear=False,
        ):
            resp = client.post(
                "/qa/magic-link",
                json={"persona_id": "nonexistent"},
            )
        assert resp.status_code == 404

    def test_valid_persona_returns_magic_link_url(self, client, mock_auth_store):
        """Valid persona → {url: /auth/magic/<token>}."""
        user = MagicMock()
        user.id = "user-abc-123"
        mock_auth_store.get_user_by_email = MagicMock(return_value=user)
        with patch.dict(
            os.environ,
            {"DAZZLE_ENV": "development", "DAZZLE_QA_MODE": "1"},
            clear=False,
        ):
            with patch(
                "dazzle_back.runtime.qa_routes.create_magic_link",
                return_value="dev_token_xyz",
            ):
                resp = client.post(
                    "/qa/magic-link",
                    json={"persona_id": "admin"},
                )
        assert resp.status_code == 200
        data = resp.json()
        assert data["url"] == "/auth/magic/dev_token_xyz"

    def test_lookup_uses_dev_email_format(self, client, mock_auth_store):
        """The persona is looked up by {persona_id}@example.test email."""
        user = MagicMock()
        user.id = "user-abc-123"
        mock_auth_store.get_user_by_email = MagicMock(return_value=user)
        with patch.dict(
            os.environ,
            {"DAZZLE_ENV": "development", "DAZZLE_QA_MODE": "1"},
            clear=False,
        ):
            with patch(
                "dazzle_back.runtime.qa_routes.create_magic_link",
                return_value="tok",
            ):
                client.post("/qa/magic-link", json={"persona_id": "accountant"})
        mock_auth_store.get_user_by_email.assert_called_once_with("accountant@example.test")

    def test_create_magic_link_called_with_store_and_user_id(self, client, mock_auth_store):
        """create_magic_link must be called with the auth_store as first arg and user_id kwarg."""
        user = MagicMock()
        user.id = "user-xyz"
        mock_auth_store.get_user_by_email = MagicMock(return_value=user)
        with patch.dict(
            os.environ,
            {"DAZZLE_ENV": "development", "DAZZLE_QA_MODE": "1"},
            clear=False,
        ):
            with patch(
                "dazzle_back.runtime.qa_routes.create_magic_link",
                return_value="tok",
            ) as mock_cml:
                client.post("/qa/magic-link", json={"persona_id": "admin"})
                # First positional arg must be the store
                args, kwargs = mock_cml.call_args
                assert args[0] is mock_auth_store
                assert kwargs["user_id"] == "user-xyz"
                assert kwargs["ttl_seconds"] == 60
                assert kwargs["created_by"] == "qa_panel"
