"""
Tests for signup role assignment (issue #268).

Verifies that:
1. create_auth_routes passes default_signup_roles to create_user on register.
2. The register response includes redirect_url resolved from persona_routes.
3. No roles assigned when default_signup_roles is not provided.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock
from uuid import uuid4

import fastapi
from starlette.testclient import TestClient

from dazzle_back.runtime.auth import (
    SessionRecord,
    UserRecord,
    create_auth_routes,
)


def _make_auth_store(
    existing_user: UserRecord | None = None,
    created_user: UserRecord | None = None,
) -> MagicMock:
    """Create a mock AuthStore."""
    store = MagicMock()
    store.get_user_by_email.return_value = existing_user

    if created_user is None:
        created_user = UserRecord(
            id=uuid4(),
            email="new@example.com",
            password_hash="hashed",
            username="newuser",
            roles=[],
        )
    store.create_user.return_value = created_user

    session = SessionRecord(
        user_id=created_user.id,
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    store.create_session.return_value = session

    return store


class TestSignupRoleAssignment:
    def test_register_assigns_default_roles(self) -> None:
        """New signups get default_signup_roles assigned."""
        created = UserRecord(
            id=uuid4(),
            email="new@example.com",
            password_hash="h",
            username="newuser",
            roles=["customer"],
        )
        store = _make_auth_store(created_user=created)

        router = create_auth_routes(
            store,
            default_signup_roles=["customer"],
        )
        app = fastapi.FastAPI()
        app.include_router(router)
        client = TestClient(app)

        response = client.post(
            "/auth/register",
            json={"email": "new@example.com", "password": "pass123", "username": "newuser"},
        )

        assert response.status_code == 201
        # Verify create_user was called with roles
        store.create_user.assert_called_once_with(
            email="new@example.com",
            password="pass123",
            username="newuser",
            roles=["customer"],
        )
        data = response.json()
        assert data["user"]["roles"] == ["customer"]

    def test_register_no_default_roles(self) -> None:
        """Without default_signup_roles, no roles are passed to create_user."""
        store = _make_auth_store()

        router = create_auth_routes(store)
        app = fastapi.FastAPI()
        app.include_router(router)
        client = TestClient(app)

        response = client.post(
            "/auth/register",
            json={"email": "new@example.com", "password": "pass123"},
        )

        assert response.status_code == 201
        store.create_user.assert_called_once_with(
            email="new@example.com",
            password="pass123",
            username=None,
            roles=None,
        )

    def test_register_includes_redirect_url(self) -> None:
        """Register response includes redirect_url from persona_routes."""
        created = UserRecord(
            id=uuid4(),
            email="new@example.com",
            password_hash="h",
            username="newuser",
            roles=["customer"],
        )
        store = _make_auth_store(created_user=created)

        router = create_auth_routes(
            store,
            persona_routes={"customer": "/app/workspaces/customer_dashboard"},
            default_signup_roles=["customer"],
        )
        app = fastapi.FastAPI()
        app.include_router(router)
        client = TestClient(app)

        response = client.post(
            "/auth/register",
            json={"email": "new@example.com", "password": "pass123", "username": "newuser"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["redirect_url"] == "/app/workspaces/customer_dashboard"

    def test_register_redirect_url_default_when_no_persona_routes(self) -> None:
        """Without persona_routes, redirect_url defaults to /app."""
        created = UserRecord(
            id=uuid4(),
            email="new@example.com",
            password_hash="h",
            username="newuser",
            roles=["customer"],
        )
        store = _make_auth_store(created_user=created)

        router = create_auth_routes(
            store,
            default_signup_roles=["customer"],
        )
        app = fastapi.FastAPI()
        app.include_router(router)
        client = TestClient(app)

        response = client.post(
            "/auth/register",
            json={"email": "new@example.com", "password": "pass123", "username": "newuser"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["redirect_url"] == "/app"

    def test_register_multiple_default_roles(self) -> None:
        """Multiple default roles are all assigned on signup."""
        created = UserRecord(
            id=uuid4(),
            email="new@example.com",
            password_hash="h",
            roles=["customer", "viewer"],
        )
        store = _make_auth_store(created_user=created)

        router = create_auth_routes(
            store,
            default_signup_roles=["customer", "viewer"],
        )
        app = fastapi.FastAPI()
        app.include_router(router)
        client = TestClient(app)

        response = client.post(
            "/auth/register",
            json={"email": "new@example.com", "password": "pass123"},
        )

        assert response.status_code == 201
        store.create_user.assert_called_once_with(
            email="new@example.com",
            password="pass123",
            username=None,
            roles=["customer", "viewer"],
        )
