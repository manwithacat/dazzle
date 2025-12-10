"""
Test mode routes for DNR container runtime.

Provides endpoints for testing: reset, seed, snapshot, and test authentication.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from .auth import AUTH_SESSIONS, AUTH_USERS, clear_auth_data, get_auth_stats, hash_password
from .data_store import data_store


def register_test_routes(
    app: FastAPI,
    auth_enabled: bool = False,
) -> None:
    """
    Register test mode routes on the FastAPI app.

    Args:
        app: FastAPI application instance
        auth_enabled: Whether auth is enabled (affects snapshot output)
    """

    @app.post("/__test__/reset")
    async def test_reset() -> dict[str, bool]:
        """Reset all data."""
        data_store.clear()
        if auth_enabled:
            clear_auth_data()
        return {"reset": True}

    @app.post("/__test__/seed")
    async def test_seed(request: Request) -> dict[str, bool]:
        """Seed data."""
        data = await request.json()
        for entity_name, items in data.items():
            collection = data_store.get_collection(entity_name)
            for item in items:
                if "id" not in item:
                    item["id"] = str(uuid.uuid4())
                collection[item["id"]] = item
        return {"seeded": True}

    @app.get("/__test__/snapshot")
    async def test_snapshot() -> dict[str, Any]:
        """Get database snapshot."""
        snapshot = data_store.snapshot()
        if auth_enabled:
            # Include user count (not full data for security)
            snapshot["__auth__"] = get_auth_stats()
        return snapshot

    if auth_enabled:
        _register_auth_test_routes(app)
    else:
        _register_mock_auth_route(app)


def _register_auth_test_routes(app: FastAPI) -> None:
    """Register test routes for auth-enabled mode."""

    @app.post("/__test__/create_user")
    async def test_create_user(request: Request) -> dict[str, Any]:
        """Create a test user with optional persona."""
        data = await request.json()

        email = data.get("email")
        password = data.get("password")
        display_name = data.get("display_name")
        persona = data.get("persona")

        if not email or not password:
            raise HTTPException(status_code=400, detail="email and password required")

        if email in AUTH_USERS:
            # Return existing user (idempotent)
            user = AUTH_USERS[email]
            return {
                "id": user["id"],
                "email": user["email"],
                "display_name": user.get("display_name"),
                "persona": user.get("persona"),
                "created": False,
            }

        user_id = str(uuid.uuid4())
        user = {
            "id": user_id,
            "email": email,
            "password_hash": hash_password(password),
            "display_name": display_name or email.split("@")[0],
            "persona": persona,
            "is_active": True,
            "created_at": datetime.now(UTC).isoformat(),
        }
        AUTH_USERS[email] = user

        return {
            "id": user_id,
            "email": email,
            "display_name": user["display_name"],
            "persona": persona,
            "created": True,
        }

    @app.post("/__test__/authenticate")
    async def test_authenticate(request: Request) -> JSONResponse:
        """Authenticate for testing (creates session without password check)."""
        data = await request.json()
        email = data.get("email") or data.get("username")
        role = data.get("role")

        # Find or create user
        if email not in AUTH_USERS:
            user_id = str(uuid.uuid4())
            user = {
                "id": user_id,
                "email": email,
                "password_hash": hash_password("test_password"),
                "display_name": email.split("@")[0] if email else f"test_{role or 'user'}",
                "persona": role,
                "is_active": True,
                "created_at": datetime.now(UTC).isoformat(),
            }
            AUTH_USERS[email] = user
        else:
            user = AUTH_USERS[email]

        # Create session
        session_token = secrets.token_urlsafe(32)
        session = {
            "user_id": user["id"],
            "token": session_token,
            "expires_at": (datetime.now(UTC) + timedelta(days=7)).isoformat(),
        }
        AUTH_SESSIONS[session_token] = session

        response = JSONResponse(
            {
                "user": {
                    "id": user["id"],
                    "email": user.get("email"),
                    "display_name": user.get("display_name"),
                    "persona": user.get("persona"),
                },
                "session_token": session_token,
            }
        )
        response.set_cookie(
            "dnr_session",
            session_token,
            httponly=True,
            samesite="lax",
            max_age=7 * 24 * 60 * 60,
        )
        return response


def _register_mock_auth_route(app: FastAPI) -> None:
    """Register mock authenticate endpoint when auth is disabled."""

    @app.post("/__test__/authenticate")
    async def test_authenticate_mock(request: Request) -> dict[str, Any]:
        """Mock authentication for testing (no real auth system)."""
        data = await request.json()
        username = data.get("username") or data.get("email")
        role = data.get("role")

        # Return a mock response
        user_id = str(uuid.uuid4())
        username = username or f"test_{role or 'user'}"
        role = role or "user"
        session_token = str(uuid.uuid4())

        return {
            "user_id": user_id,
            "username": username,
            "role": role,
            "session_token": session_token,
        }
