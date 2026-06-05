"""Signed QA-auth tokens (RLS Phase E.2, #1339).

A token is ``<email>:<run_id>:<issued_ts>.<hmac_hex>`` — an HMAC-SHA256 over the
payload keyed by ``QA_AUTH_SECRET``. The signature IS the credential (ADR-0033
NA_SIGNATURE); the ~60s window bounds replay. Constant-time verify; no logging
of the secret or token.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass

DEFAULT_MAX_AGE_SECONDS = 60


class QaTokenError(ValueError):
    """A QA token failed verification (bad signature, expiry, or shape)."""


@dataclass(frozen=True)
class QaTokenClaims:
    email: str
    run_id: str
    issued_at: float


def _payload(email: str, run_id: str, issued_ts: float) -> str:
    # `:` separates fields; the signature binds the exact string, so re-parsing
    # the signed payload is safe.
    return f"{email}:{run_id}:{issued_ts}"


def _sign(payload: str, secret: str) -> str:
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def sign_qa_token(email: str, run_id: str, *, secret: str, now: float) -> str:
    """Sign ``email:run_id:now`` → ``payload.signature``. ``now`` is the issue
    time (``time.time()`` at the caller; passed in for deterministic tests)."""
    payload = _payload(email, run_id, now)
    return f"{payload}.{_sign(payload, secret)}"


def verify_qa_token(
    token: str, *, secret: str, now: float, max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS
) -> QaTokenClaims:
    """Verify signature + replay window; return claims or raise ``QaTokenError``."""
    payload, sep, sig = token.rpartition(".")
    if not sep:
        raise QaTokenError("malformed token (no signature)")
    expected = _sign(payload, secret)
    if not hmac.compare_digest(sig, expected):
        raise QaTokenError("bad signature")
    parts = payload.split(":")
    if len(parts) != 3:
        raise QaTokenError("malformed payload")
    email, run_id, issued_raw = parts
    try:
        issued_at = float(issued_raw)
    except ValueError as exc:
        raise QaTokenError("malformed timestamp") from exc
    # Reject both stale (replay) and far-future (clock-skew/forgery) tokens.
    if abs(now - issued_at) > max_age_seconds:
        raise QaTokenError("token expired or outside the replay window")
    return QaTokenClaims(email=email, run_id=run_id, issued_at=issued_at)
