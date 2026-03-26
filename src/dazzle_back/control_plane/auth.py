"""
Control Plane Authentication.

Supports:
- HTTP Basic Auth
- Bearer token
- Session cookies (after login)
- Dev mode (no auth if password not configured)
"""

import asyncio
import hmac
import logging
import os
import secrets
import time
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials, HTTPBearer

logger = logging.getLogger(__name__)

# Configuration from environment
CONTROL_PLANE_USERNAME = os.environ.get("CONTROL_PLANE_USERNAME", "admin")
CONTROL_PLANE_PASSWORD = os.environ.get("CONTROL_PLANE_PASSWORD", "")
CONTROL_PLANE_TOKEN = os.environ.get("CONTROL_PLANE_TOKEN", "")

# Session management (simple in-memory, ephemeral)
_sessions: dict[str, float] = {}  # token -> expiry timestamp
_sessions_lock: asyncio.Lock = asyncio.Lock()
SESSION_DURATION = 86400  # 24 hours


@dataclass
class AuthContext:
    """Authentication context for a request."""

    authenticated: bool = False
    username: str = ""
    method: str = ""  # "basic", "bearer", "session", "dev"


async def create_session() -> str:
    """Create a new session token."""
    token = secrets.token_urlsafe(32)
    async with _sessions_lock:
        _sessions[token] = time.time() + SESSION_DURATION
    return token


async def validate_session(token: str) -> bool:
    """Validate a session token."""
    async with _sessions_lock:
        expiry = _sessions.get(token)
        if not expiry:
            return False
        if time.time() > expiry:
            del _sessions[token]
            return False
    return True


async def invalidate_session(token: str) -> None:
    """Invalidate a session token."""
    async with _sessions_lock:
        _sessions.pop(token, None)


# Security schemes
_basic = HTTPBasic(auto_error=False)
_bearer = HTTPBearer(auto_error=False)


async def get_auth_context(
    request: Request,
    basic_creds: HTTPBasicCredentials | None = Depends(_basic),
) -> AuthContext:
    """
    Get authentication context for a request.

    Checks in order:
    1. Session cookie
    2. Bearer token
    3. HTTP Basic Auth
    4. Dev mode (if password not configured)
    """
    # 1. Check session cookie
    session_token = request.cookies.get("control_session")
    if session_token and await validate_session(session_token):
        return AuthContext(
            authenticated=True,
            username=CONTROL_PLANE_USERNAME,
            method="session",
        )

    # 2. Check Bearer token
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        if CONTROL_PLANE_TOKEN and hmac.compare_digest(token, CONTROL_PLANE_TOKEN):
            return AuthContext(
                authenticated=True,
                username="api",
                method="bearer",
            )

    # 3. Check HTTP Basic Auth
    if basic_creds:
        username_valid = hmac.compare_digest(basic_creds.username, CONTROL_PLANE_USERNAME)
        password_valid = (
            hmac.compare_digest(basic_creds.password, CONTROL_PLANE_PASSWORD)
            if CONTROL_PLANE_PASSWORD
            else True
        )
        if username_valid and password_valid:
            return AuthContext(
                authenticated=True,
                username=basic_creds.username,
                method="basic",
            )

    # 4. Dev mode - allow access if no password configured
    if not CONTROL_PLANE_PASSWORD:
        logger.debug("Control plane running in dev mode (no auth)")
        return AuthContext(
            authenticated=True,
            username="dev",
            method="dev",
        )

    # Not authenticated
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
        headers={"WWW-Authenticate": "Basic"},
    )


def is_auth_required() -> bool:
    """Check if authentication is required (password is configured)."""
    return bool(CONTROL_PLANE_PASSWORD)
