"""Integration test for QA mode end-to-end flow (#768)."""

import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dazzle.cli.runtime_impl.dev_personas import provision_dev_personas
from dazzle_back.runtime.auth.magic_link_routes import create_magic_link_routes
from dazzle_back.runtime.qa_routes import create_qa_routes


@pytest.fixture
def mock_auth_store_with_real_token_flow():
    """Auth store where create_magic_link and validate_magic_link work
    with an in-memory token dictionary, so we can trace a real flow."""
    store = MagicMock()

    tokens = {}  # token -> user_id
    users = {}  # email -> user

    def create_user(email, password, username, is_superuser, roles):
        user = MagicMock()
        user.id = f"u-{email}"
        user.email = email
        users[email] = user
        return user

    def get_user_by_email(email):
        return users.get(email)

    def get_user_by_id(user_id):
        for u in users.values():
            if u.id == user_id:
                return u
        return None

    def create_magic_link(store_arg, *, user_id, ttl_seconds=300, created_by="cli"):
        token = f"token-{len(tokens)}"
        tokens[token] = user_id
        return token

    def validate_magic_link(store_arg, token):
        # One-time use: pop the token
        return tokens.pop(token, None)

    def create_session(user):
        session = MagicMock()
        session.id = f"session-{user.id}"
        return session

    store.create_user = MagicMock(side_effect=create_user)
    store.get_user_by_email = MagicMock(side_effect=get_user_by_email)
    store.get_user_by_id = MagicMock(side_effect=get_user_by_id)
    store.create_session = MagicMock(side_effect=create_session)

    # Patch the module-level functions so the routes call our fakes
    with (
        patch(
            "dazzle_back.runtime.auth.magic_link_routes.validate_magic_link",
            side_effect=validate_magic_link,
        ),
        patch(
            "dazzle_back.runtime.qa_routes.create_magic_link",
            side_effect=create_magic_link,
        ),
    ):
        yield store


@pytest.fixture
def qa_app(mock_auth_store_with_real_token_flow):
    app = FastAPI()
    app.state.auth_store = mock_auth_store_with_real_token_flow
    app.include_router(create_magic_link_routes())
    app.include_router(create_qa_routes())
    return app


@pytest.fixture
def client(qa_app):
    return TestClient(qa_app)


def _make_appspec(personas):
    spec = MagicMock()
    spec.personas = personas
    spec.stories = []
    return spec


def _make_persona(id, label):
    p = MagicMock()
    p.id = id
    p.label = label
    p.description = None
    return p


class TestQAModeEndToEnd:
    def test_full_flow_provision_generate_consume(
        self, client, mock_auth_store_with_real_token_flow
    ):
        """Full end-to-end: provision → generate magic link → consume → session cookie."""
        # 1. Provision personas
        appspec = _make_appspec([_make_persona("accountant", "Accountant")])
        provisioned = provision_dev_personas(appspec, mock_auth_store_with_real_token_flow)
        assert len(provisioned) == 1

        # 2. Generate magic link (requires env flags)
        with patch.dict(
            os.environ,
            {"DAZZLE_ENV": "development", "DAZZLE_QA_MODE": "1"},
            clear=False,
        ):
            resp = client.post(
                "/qa/magic-link",
                json={"persona_id": "accountant"},
            )
            assert resp.status_code == 200
            url = resp.json()["url"]
            assert url.startswith("/auth/magic/token-")

            # 3. Consume the magic link
            resp = client.get(url, follow_redirects=False)
            assert resp.status_code == 303
            assert resp.headers["location"] == "/"
            assert "dazzle_session" in resp.cookies
            session_val = resp.cookies["dazzle_session"].strip('"')
            assert session_val.startswith("session-u-accountant")

            # 4. Consuming again should fail (one-time use)
            resp2 = client.get(url, follow_redirects=False)
            assert resp2.status_code == 303
            assert "error=invalid_magic_link" in resp2.headers["location"]

    def test_qa_endpoint_returns_404_without_env_flags(
        self, client, mock_auth_store_with_real_token_flow
    ):
        """/qa/magic-link is a 404 without env flags, regardless of auth state."""
        # Provision a persona so the store would succeed if checked
        appspec = _make_appspec([_make_persona("admin", "Admin")])
        provision_dev_personas(appspec, mock_auth_store_with_real_token_flow)

        # Clear env flags — ensure both are unset/wrong
        with patch.dict(
            os.environ,
            {"DAZZLE_ENV": "production", "DAZZLE_QA_MODE": "0"},
            clear=False,
        ):
            resp = client.post(
                "/qa/magic-link",
                json={"persona_id": "admin"},
            )
            assert resp.status_code == 404

    def test_magic_link_consumer_works_without_qa_env_flags(
        self, client, mock_auth_store_with_real_token_flow
    ):
        """The consumer endpoint is production-safe — works without QA mode flags."""
        # Pre-seed a valid token via direct store manipulation
        store = mock_auth_store_with_real_token_flow
        appspec = _make_appspec([_make_persona("admin", "Admin")])
        provisioned = provision_dev_personas(appspec, store)
        user_id = provisioned[0].user_id

        # Inject a token directly (simulating a token created by some other path)
        with patch(
            "dazzle_back.runtime.auth.magic_link_routes.validate_magic_link",
            return_value=user_id,
        ):
            # No QA env flags set — consumer should still work
            resp = client.get(
                "/auth/magic/some_production_token",
                follow_redirects=False,
            )
            assert resp.status_code == 303
            assert resp.headers["location"] == "/"
            assert "dazzle_session" in resp.cookies
