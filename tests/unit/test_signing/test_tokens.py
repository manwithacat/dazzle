"""Unit tests for dazzle.signing.tokens — HMAC token mint/verify (#1283)."""

from __future__ import annotations

import time

import pytest

from dazzle.signing import (
    InvalidTokenError,
    SigningError,
    mint_token,
    token_hash,
    verify_token,
    verify_token_allow_expired,
)


@pytest.fixture(autouse=True)
def _signing_secret(monkeypatch):
    monkeypatch.setenv("SIGNING_TOKEN_SECRET", "test-secret-not-for-prod")


def test_mint_verify_roundtrip():
    token = mint_token("rec-123", "alice@example.com")
    record_id, email = verify_token(token)
    assert record_id == "rec-123"
    assert email == "alice@example.com"


def test_token_hash_is_deterministic():
    token = mint_token("rec-1", "x@example.com")
    assert token_hash(token) == token_hash(token)
    assert len(token_hash(token)) == 64  # sha256 hex


def test_token_hash_differs_per_token():
    a = mint_token("rec-1", "x@example.com")
    b = mint_token("rec-2", "x@example.com")
    assert token_hash(a) != token_hash(b)


def test_tampered_signature_rejects():
    token = mint_token("rec-1", "alice@example.com")
    tampered = token[:-2] + ("aa" if not token.endswith("aa") else "bb")
    with pytest.raises(InvalidTokenError, match="signature|decode|payload"):
        verify_token(tampered)


def test_expired_token_rejects(monkeypatch):
    monkeypatch.setattr(time, "time", lambda: 1_000_000.0)
    token = mint_token("rec-1", "alice@example.com", expires_hours=1)
    monkeypatch.setattr(time, "time", lambda: 1_000_000.0 + 3700)
    with pytest.raises(InvalidTokenError, match="expired"):
        verify_token(token)


def test_malformed_token_rejects():
    with pytest.raises(InvalidTokenError):
        verify_token("not-a-valid-token")


def test_allow_expired_accepts_expired_but_valid(monkeypatch):
    """TR-53: an expired-but-HMAC-valid token verifies for recovery."""
    monkeypatch.setattr(time, "time", lambda: 1_000_000.0)
    token = mint_token("rec-1", "alice@example.com", expires_hours=1)
    monkeypatch.setattr(time, "time", lambda: 1_000_000.0 + 3700)
    # The strict path rejects it...
    with pytest.raises(InvalidTokenError, match="expired"):
        verify_token(token)
    # ...the recovery path accepts it (integrity intact).
    record_id, email = verify_token_allow_expired(token)
    assert record_id == "rec-1"
    assert email == "alice@example.com"


def test_allow_expired_still_rejects_tampered():
    """Recovery acceptance must not weaken HMAC integrity checking."""
    token = mint_token("rec-1", "alice@example.com")
    tampered = token[:-2] + ("aa" if not token.endswith("aa") else "bb")
    with pytest.raises(InvalidTokenError):
        verify_token_allow_expired(tampered)


def test_missing_secret_raises_signing_error(monkeypatch):
    monkeypatch.delenv("SIGNING_TOKEN_SECRET", raising=False)
    with pytest.raises(SigningError, match="SIGNING_TOKEN_SECRET"):
        mint_token("rec-1", "x@example.com")


def test_invalid_token_error_is_signing_error():
    assert issubclass(InvalidTokenError, SigningError)


def test_secret_change_invalidates_token(monkeypatch):
    token = mint_token("rec-1", "alice@example.com")
    monkeypatch.setenv("SIGNING_TOKEN_SECRET", "different-secret")
    with pytest.raises(InvalidTokenError):
        verify_token(token)


def test_email_with_colons_rejects():
    """Email containing a colon would corrupt the payload split."""
    token = mint_token("rec-1", "weird:email@example.com")
    # Current implementation splits payload on ":" so this fails verify.
    # The signing-routes layer (phase 3) is responsible for rejecting
    # emails that contain ":" before mint — capturing that invariant
    # here so it's an explicit, tested behaviour rather than a silent
    # corruption.
    with pytest.raises(InvalidTokenError):
        verify_token(token)
