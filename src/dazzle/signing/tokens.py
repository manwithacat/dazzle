"""HMAC-SHA256 signing tokens for native document signing (#1283).

A signing token is a self-contained, URL-safe credential that lets an
unauthenticated signer open the signing page from a one-shot email link.
Tokens carry the target record id, signer email, and an expiry timestamp.
They are integrity-protected by an HMAC-SHA256 signature keyed on
``SIGNING_TOKEN_SECRET``.

Lifted from cyfuture's working implementation
(`services/signing_service.py`) and generalised: ``letter_id`` →
``record_id``, ``SECRET_KEY`` → ``SIGNING_TOKEN_SECRET``.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time

DEFAULT_EXPIRY_HOURS = 72
TOKEN_SECRET_ENV_VAR = "SIGNING_TOKEN_SECRET"


class SigningError(Exception):
    """Raised when a signing operation fails (config, crypto, IO)."""


class InvalidTokenError(SigningError):
    """Raised when a signing token is malformed, tampered, or expired."""


def _get_secret() -> str:
    secret = os.environ.get(TOKEN_SECRET_ENV_VAR, "")
    if not secret:
        raise SigningError(f"{TOKEN_SECRET_ENV_VAR} not configured")
    return secret


def mint_token(
    record_id: str,
    email: str,
    expires_hours: int = DEFAULT_EXPIRY_HOURS,
) -> str:
    """Mint a time-limited HMAC-SHA256 signing token.

    The token encodes ``record_id``, ``email``, and an absolute expiry
    timestamp (seconds since epoch). The whole payload is HMAC-signed
    with ``SIGNING_TOKEN_SECRET``, then base64-url-encoded.

    Returns a URL-safe string suitable for embedding in an email link.
    """
    secret = _get_secret()
    expires = int(time.time()) + (expires_hours * 3600)
    payload = f"{record_id}:{email}:{expires}"
    sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{payload}:{sig}".encode()).decode()


def _verify_token_signature(token: str) -> tuple[str, str, int]:
    """Validate decode + shape + HMAC and return ``(record_id, email, expires)``.

    Shared by :func:`verify_token` (which additionally enforces expiry)
    and :func:`verify_token_allow_expired` (which deliberately doesn't).
    """
    secret = _get_secret()
    try:
        decoded = base64.urlsafe_b64decode(token.encode()).decode()
    except Exception as exc:
        raise InvalidTokenError(f"Token decode failed: {exc}") from exc

    parts = decoded.rsplit(":", 1)
    if len(parts) != 2:
        raise InvalidTokenError("Malformed token")
    payload, received_sig = parts

    expected_sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(received_sig, expected_sig):
        raise InvalidTokenError("Invalid token signature")

    payload_parts = payload.split(":")
    if len(payload_parts) != 3:
        raise InvalidTokenError("Malformed token payload")
    record_id, email, expires_str = payload_parts

    try:
        expires = int(expires_str)
    except ValueError as exc:
        raise InvalidTokenError("Malformed token expiry") from exc

    return record_id, email, expires


def verify_token(token: str) -> tuple[str, str]:
    """Verify a signing token and return ``(record_id, email)``.

    Raises ``InvalidTokenError`` if the token is malformed, the HMAC
    fails verification, or the expiry has passed.
    """
    record_id, email, expires = _verify_token_signature(token)
    if time.time() > expires:
        raise InvalidTokenError("Token has expired")
    return record_id, email


def verify_token_allow_expired(token: str) -> tuple[str, str]:
    """Verify a token's integrity but accept an expired timestamp.

    For the expired-link recovery flow ONLY: a valid-but-expired HMAC
    proves the bearer once held a legitimate link for this
    ``(record, email)`` pair, which is sufficient to *request* a fresh
    link be delivered to that same email — and nothing more. Callers
    must never grant signing-page access or hand a fresh token to the
    bearer on this basis; the new link goes out through the app's own
    delivery channel to the original recipient.

    Raises ``InvalidTokenError`` for malformed or tampered tokens.
    """
    record_id, email, _expires = _verify_token_signature(token)
    return record_id, email


def token_hash(token: str) -> str:
    """SHA-256 hash of a token, hex-encoded. For audit-trail storage."""
    return hashlib.sha256(token.encode()).hexdigest()
