"""Password hashing, verification, and cookie security helpers."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Any


def hash_password(password: str, salt: str | None = None) -> str:
    """Hash a password with salt using PBKDF2-SHA256 (100k iterations)."""
    if salt is None:
        salt = secrets.token_hex(16)

    key = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        100000,  # iterations
    )

    return f"{salt}${key.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its hash (constant-time comparison)."""
    try:
        salt, _ = password_hash.split("$")
        return hmac.compare_digest(hash_password(password, salt), password_hash)
    except ValueError:
        return False


def cookie_secure(request: Any) -> bool:
    """Determine cookie Secure flag from request scheme.

    Returns True when the request arrived over HTTPS (directly or via
    a reverse proxy that sets X-Forwarded-Proto).  Starlette's
    ``request.url.scheme`` already honours the forwarded header when
    ``TrustedHostMiddleware`` is configured, so this is sufficient.
    """
    if hasattr(request, "url"):
        return str(getattr(request.url, "scheme", "http")) == "https"
    return False
