"""
Authentication handlers for DNR container runtime.

Provides user registration, login, logout, and session management.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# Auth data stores (simple in-memory)
AUTH_USERS: dict[str, dict[str, Any]] = {}
AUTH_SESSIONS: dict[str, dict[str, Any]] = {}


class LoginRequest(BaseModel):
    """Login request body."""

    email: str
    password: str


class RegisterRequest(BaseModel):
    """Registration request body."""

    email: str
    password: str
    display_name: str | None = None


def hash_password(password: str, salt: str | None = None) -> str:
    """Simple password hashing using hashlib."""
    if salt is None:
        salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000)
    return f"{salt}${key.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    """Verify password against hash."""
    try:
        salt, _ = password_hash.split("$")
        return hash_password(password, salt) == password_hash
    except ValueError:
        return False


def clear_auth_data() -> None:
    """Clear all auth data (for testing)."""
    AUTH_USERS.clear()
    AUTH_SESSIONS.clear()


def get_auth_stats() -> dict[str, int]:
    """Get auth statistics."""
    return {
        "user_count": len(AUTH_USERS),
        "session_count": len(AUTH_SESSIONS),
    }


def register_auth_routes(app: FastAPI) -> None:
    """Register authentication routes on the FastAPI app."""

    @app.post("/auth/register", tags=["Authentication"], summary="Register new user")
    async def auth_register(data: RegisterRequest) -> JSONResponse:
        """Register a new user."""
        if data.email in AUTH_USERS:
            raise HTTPException(status_code=400, detail="Email already registered")

        user_id = str(uuid.uuid4())
        user = {
            "id": user_id,
            "email": data.email,
            "password_hash": hash_password(data.password),
            "display_name": data.display_name or data.email.split("@")[0],
            "is_active": True,
            "created_at": datetime.now(UTC).isoformat(),
        }
        AUTH_USERS[data.email] = user

        # Create session
        session_token = secrets.token_urlsafe(32)
        session = {
            "user_id": user_id,
            "token": session_token,
            "expires_at": (datetime.now(UTC) + timedelta(days=7)).isoformat(),
        }
        AUTH_SESSIONS[session_token] = session

        response = JSONResponse(
            {
                "user": {
                    "id": user_id,
                    "email": data.email,
                    "display_name": user["display_name"],
                },
                "message": "Registration successful",
            },
            status_code=201,
        )
        response.set_cookie(
            "dnr_session",
            session_token,
            httponly=True,
            samesite="lax",
            max_age=7 * 24 * 60 * 60,
        )
        return response

    @app.post("/auth/login", tags=["Authentication"], summary="Login")
    async def auth_login(data: LoginRequest) -> JSONResponse:
        """Login with email and password."""
        user = AUTH_USERS.get(data.email)
        if not user or not verify_password(data.password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid credentials")

        if not user.get("is_active", True):
            raise HTTPException(status_code=401, detail="Account is disabled")

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
                    "email": user["email"],
                    "display_name": user.get("display_name"),
                },
                "message": "Login successful",
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

    @app.post("/auth/logout", tags=["Authentication"], summary="Logout")
    async def auth_logout(request: Request) -> JSONResponse:
        """Logout and invalidate session."""
        session_token = request.cookies.get("dnr_session")
        if session_token and session_token in AUTH_SESSIONS:
            del AUTH_SESSIONS[session_token]

        response = JSONResponse({"message": "Logout successful"})
        response.delete_cookie("dnr_session")
        return response

    @app.get("/auth/me", tags=["Authentication"], summary="Get current user")
    async def auth_me(request: Request) -> dict[str, Any]:
        """Get current user."""
        session_token = request.cookies.get("dnr_session")
        if not session_token or session_token not in AUTH_SESSIONS:
            raise HTTPException(status_code=401, detail="Not authenticated")

        session = AUTH_SESSIONS[session_token]
        # Check expiry
        if datetime.fromisoformat(session["expires_at"]) < datetime.now(UTC):
            del AUTH_SESSIONS[session_token]
            raise HTTPException(status_code=401, detail="Session expired")

        # Find user
        user = None
        for u in AUTH_USERS.values():
            if u["id"] == session["user_id"]:
                user = u
                break

        if not user:
            raise HTTPException(status_code=401, detail="User not found")

        return {
            "id": user["id"],
            "email": user["email"],
            "display_name": user.get("display_name"),
            "is_authenticated": True,
        }
