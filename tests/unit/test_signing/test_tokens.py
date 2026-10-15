"""HMAC signing tokens: mint / verify / recovery verify (#1283).

Every way a token must fail verification is its own row in
``REJECTION_CASES``; each also proves ``InvalidTokenError`` is a
``SigningError`` so callers that catch the base class still refuse.
"""

from __future__ import annotations

import time
from collections.abc import Callable

import pytest

from dazzle.signing import (
    InvalidTokenError,
    SigningError,
    mint_token,
    token_hash,
    verify_token,
    verify_token_allow_expired,
)

T0 = 1_000_000.0


@pytest.fixture(autouse=True)
def _signing_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SIGNING_TOKEN_SECRET", "test-secret-not-for-prod")


def _tamper(token: str) -> str:
    return token[:-2] + ("bb" if token.endswith("aa") else "aa")


def _expired(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setattr(time, "time", lambda: T0)
    token = mint_token("rec-1", "alice@example.com", expires_hours=1)
    monkeypatch.setattr(time, "time", lambda: T0 + 3700)
    return token


def _other_secret(monkeypatch: pytest.MonkeyPatch) -> str:
    token = mint_token("rec-1", "alice@example.com")
    monkeypatch.setenv("SIGNING_TOKEN_SECRET", "different-secret")
    return token


REJECTION_CASES = [
    # (make token, verifier, message pattern)
    pytest.param(
        lambda mp: _tamper(mint_token("rec-1", "alice@example.com")),
        verify_token,
        "signature|decode|payload",
        id="tampered-signature",
    ),
    pytest.param(_expired, verify_token, "expired", id="expired"),
    pytest.param(lambda mp: "not-a-valid-token", verify_token, "decode failed", id="malformed"),
    pytest.param(
        _other_secret, verify_token, "Invalid token signature", id="secret-rotated-invalidates"
    ),
    # A colon in the email would corrupt the payload split; the route layer
    # must refuse such emails before mint, and verify refuses them here.
    pytest.param(
        lambda mp: mint_token("rec-1", "weird:email@example.com"),
        verify_token,
        "Malformed token payload",
        id="email-containing-colon",
    ),
    # Recovery acceptance (TR-53) must not weaken HMAC integrity checking.
    pytest.param(
        lambda mp: _tamper(mint_token("rec-1", "alice@example.com")),
        verify_token_allow_expired,
        "signature|decode|payload",
        id="recovery-verify-still-rejects-tampered",
    ),
]


@pytest.mark.parametrize(("make", "verify", "match"), REJECTION_CASES)
def test_verify_rejects(
    make: Callable[[pytest.MonkeyPatch], str],
    verify: Callable[[str], tuple[str, str]],
    match: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = make(monkeypatch)
    with pytest.raises(InvalidTokenError, match=match) as raised:
        verify(token)
    assert isinstance(raised.value, SigningError)


def test_mint_verify_roundtrip() -> None:
    assert verify_token(mint_token("rec-123", "alice@example.com")) == (
        "rec-123",
        "alice@example.com",
    )


def test_recovery_verify_accepts_expired_but_intact(monkeypatch: pytest.MonkeyPatch) -> None:
    """TR-53: an expired-but-HMAC-valid token verifies on the recovery path."""
    token = _expired(monkeypatch)
    assert verify_token_allow_expired(token) == ("rec-1", "alice@example.com")


def test_token_hash_is_stable_sha256_and_distinct_per_token() -> None:
    a = mint_token("rec-1", "x@example.com")
    b = mint_token("rec-2", "x@example.com")
    assert token_hash(a) == token_hash(a)
    assert len(token_hash(a)) == 64
    assert token_hash(a) != token_hash(b)


def test_mint_without_secret_names_the_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SIGNING_TOKEN_SECRET", raising=False)
    with pytest.raises(SigningError, match="SIGNING_TOKEN_SECRET"):
        mint_token("rec-1", "x@example.com")
