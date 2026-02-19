"""
TOTP (Time-based One-Time Password) implementation per RFC 6238.

Pure-Python implementation using HMAC-SHA1 — no external dependencies.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
import urllib.parse


def generate_totp_secret(length: int = 20) -> str:
    """Generate a random TOTP secret encoded as base32.

    Args:
        length: Number of random bytes (20 = 160 bits, recommended)

    Returns:
        Base32-encoded secret string
    """
    raw = secrets.token_bytes(length)
    return base64.b32encode(raw).decode("ascii")


def get_totp_uri(secret: str, email: str, issuer: str = "Dazzle") -> str:
    """Build an otpauth:// URI for QR code generation.

    Args:
        secret: Base32-encoded TOTP secret
        email: User's email address
        issuer: Application name displayed in authenticator apps

    Returns:
        otpauth:// URI string
    """
    label = urllib.parse.quote(f"{issuer}:{email}", safe=":")
    params = urllib.parse.urlencode(
        {"secret": secret, "issuer": issuer, "algorithm": "SHA1", "digits": "6", "period": "30"}
    )
    return f"otpauth://totp/{label}?{params}"


def _compute_hotp(secret: str, counter: int) -> str:
    """Compute HOTP value per RFC 4226.

    Args:
        secret: Base32-encoded secret
        counter: 8-byte counter value

    Returns:
        6-digit OTP string
    """
    # Decode secret
    key = base64.b32decode(secret.upper())

    # Pack counter as big-endian 8-byte integer
    msg = struct.pack(">Q", counter)

    # HMAC-SHA1
    digest = hmac.new(key, msg, hashlib.sha1).digest()

    # Dynamic truncation
    offset = digest[-1] & 0x0F
    truncated = struct.unpack(">I", digest[offset : offset + 4])[0]
    truncated &= 0x7FFFFFFF

    # Generate 6-digit code
    code = truncated % 1_000_000
    return f"{code:06d}"


def generate_totp(secret: str, time_step: int = 30, timestamp: float | None = None) -> str:
    """Generate the current TOTP code.

    Args:
        secret: Base32-encoded TOTP secret
        time_step: Time step in seconds (default 30)
        timestamp: Override current time (for testing)

    Returns:
        6-digit TOTP code
    """
    if timestamp is None:
        timestamp = time.time()
    counter = int(timestamp) // time_step
    return _compute_hotp(secret, counter)


def verify_totp(
    secret: str,
    code: str,
    *,
    window: int = 1,
    time_step: int = 30,
    timestamp: float | None = None,
) -> bool:
    """Verify a TOTP code against current time with drift window.

    Uses constant-time comparison to prevent timing attacks.

    Args:
        secret: Base32-encoded TOTP secret
        code: User-provided 6-digit code
        window: Number of time steps to check before/after current (default 1)
        time_step: Time step in seconds (default 30)
        timestamp: Override current time (for testing)

    Returns:
        True if code is valid for any step in the window
    """
    if timestamp is None:
        timestamp = time.time()

    current_counter = int(timestamp) // time_step

    for offset in range(-window, window + 1):
        expected = _compute_hotp(secret, current_counter + offset)
        if hmac.compare_digest(expected, code):
            return True

    return False
