"""TOTP (RFC 6238) — pure Python, HMAC-SHA1, 6 digits, 30-second steps (DD-014).

Restored from ``229226a88:src/dazzle/http/runtime/totp.py``. ``match_totp_step``
replaces the old boolean ``verify_totp``: it returns the time step the code matched
so the store can refuse a code whose step was already accepted (no replay inside the
drift window).
"""

import base64
import hashlib
import hmac
import secrets
import struct
import time
import urllib.parse

TIME_STEP_SECONDS = 30


def generate_totp_secret(length: int = 20) -> str:
    """A random base32 TOTP secret (20 bytes = 160 bits, as RFC 4226 recommends)."""
    return base64.b32encode(secrets.token_bytes(length)).decode("ascii")


def get_totp_uri(secret: str, email: str, issuer: str = "Dazzle") -> str:
    """The ``otpauth://totp/...`` URI an authenticator app reads from the QR code."""
    label = urllib.parse.quote(f"{issuer}:{email}", safe=":")
    params = urllib.parse.urlencode(
        {"secret": secret, "issuer": issuer, "algorithm": "SHA1", "digits": "6", "period": "30"}
    )
    return f"otpauth://totp/{label}?{params}"


def _hotp(secret: str, counter: int) -> str:
    """RFC 4226 HOTP value for ``counter``."""
    key = base64.b32decode(secret.upper())
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    truncated = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return f"{truncated % 1_000_000:06d}"


def totp_step(timestamp: float | None = None) -> int:
    """The RFC 6238 time step for ``timestamp`` (now by default)."""
    return int(time.time() if timestamp is None else timestamp) // TIME_STEP_SECONDS


def generate_totp(secret: str, timestamp: float | None = None) -> str:
    """The 6-digit code for ``timestamp`` (now by default)."""
    return _hotp(secret, totp_step(timestamp))


def match_totp_step(
    secret: str, code: str, *, window: int = 1, timestamp: float | None = None
) -> int | None:
    """The time step ``code`` is valid for, within ``window`` steps of drift; else None.

    Every candidate step is compared in constant time.
    """
    if not (len(code) == 6 and code.isascii() and code.isdigit()):
        return None
    current = totp_step(timestamp)
    matched: int | None = None
    for step in range(current - window, current + window + 1):
        if hmac.compare_digest(_hotp(secret, step), code) and matched is None:
            matched = step
    return matched
