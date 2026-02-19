"""
Experience flow state management.

Manages step tracking, navigation history, and data accumulation
for multi-step experience flows. State is stored in signed cookies
to prevent tampering.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import time
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# 24-hour cookie expiry
_COOKIE_MAX_AGE = 86400


class ExperienceState(BaseModel):
    """State for an in-progress experience flow."""

    step: str
    completed: list[str] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)
    started_at: float = Field(default_factory=time.time)


def cookie_name(experience_name: str) -> str:
    """Return the cookie name for a given experience."""
    return f"dz-exp-{experience_name}"


def _get_signing_key() -> bytes:
    """Get the HMAC signing key from environment or fallback."""
    key = os.environ.get("DAZZLE_SECRET_KEY", "dazzle-dev-secret-key")
    return key.encode("utf-8")


def sign_state(state: ExperienceState) -> str:
    """Serialize and sign an ExperienceState for cookie storage.

    Returns:
        Base64-encoded payload (no padding) with HMAC-SHA256 signature appended.
    """
    payload = state.model_dump_json().encode("utf-8")
    b64_payload = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    sig = hmac.new(_get_signing_key(), payload, hashlib.sha256).hexdigest()
    return f"{b64_payload}.{sig}"


def verify_state(raw: str) -> ExperienceState | None:
    """Verify signature and deserialize an ExperienceState from a cookie.

    Returns:
        ExperienceState if valid, None if tampered or expired.
    """
    if not raw or "." not in raw:
        return None

    parts = raw.rsplit(".", 1)
    if len(parts) != 2:
        return None

    b64_payload, sig = parts
    # Re-add padding for base64 decode
    padded = b64_payload + "=" * (-len(b64_payload) % 4)
    try:
        payload = base64.urlsafe_b64decode(padded)
    except Exception:
        return None

    expected_sig = hmac.new(_get_signing_key(), payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected_sig):
        logger.warning("Experience state cookie signature mismatch (tamper detected)")
        return None

    try:
        state = ExperienceState.model_validate_json(payload)
    except Exception:
        return None

    # Check expiry
    if time.time() - state.started_at > _COOKIE_MAX_AGE:
        logger.debug("Experience state cookie expired")
        return None

    return state


def create_initial_state(start_step: str) -> ExperienceState:
    """Create a fresh experience state starting at the given step."""
    return ExperienceState(step=start_step)
