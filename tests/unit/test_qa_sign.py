"""HMAC QA token signer (RLS Phase E.2)."""

import pytest

from dazzle.http.runtime.auth.qa_sign import (
    QaTokenError,
    sign_qa_token,
    verify_qa_token,
)

_SECRET = "test-secret"


def test_round_trip() -> None:
    tok = sign_qa_token("a@qa.test", "run1", secret=_SECRET, now=1000.0)
    claims = verify_qa_token(tok, secret=_SECRET, now=1010.0)
    assert claims.email == "a@qa.test"
    assert claims.run_id == "run1"


def test_expired_token_rejected() -> None:
    tok = sign_qa_token("a@qa.test", "run1", secret=_SECRET, now=1000.0)
    with pytest.raises(QaTokenError, match="expired"):
        verify_qa_token(tok, secret=_SECRET, now=1000.0 + 61)


def test_future_token_rejected() -> None:
    tok = sign_qa_token("a@qa.test", "run1", secret=_SECRET, now=2000.0)
    with pytest.raises(QaTokenError):
        verify_qa_token(tok, secret=_SECRET, now=2000.0 - 61)


def test_tampered_signature_rejected() -> None:
    tok = sign_qa_token("a@qa.test", "run1", secret=_SECRET, now=1000.0)
    body, _, _sig = tok.rpartition(".")
    forged = body + ".deadbeef"
    with pytest.raises(QaTokenError, match="signature"):
        verify_qa_token(forged, secret=_SECRET, now=1010.0)


def test_wrong_secret_rejected() -> None:
    tok = sign_qa_token("a@qa.test", "run1", secret=_SECRET, now=1000.0)
    with pytest.raises(QaTokenError, match="signature"):
        verify_qa_token(tok, secret="other-secret", now=1010.0)


def test_tampered_payload_rejected() -> None:
    tok = sign_qa_token("a@qa.test", "run1", secret=_SECRET, now=1000.0)
    _body, _, sig = tok.rpartition(".")
    forged = "evil@qa.test:run1:1000.0." + sig
    with pytest.raises(QaTokenError):
        verify_qa_token(forged, secret=_SECRET, now=1010.0)


def test_colon_in_claims_does_not_reparse() -> None:
    """An email containing ':' makes the payload split into >3 parts → rejected,
    so a forged payload can't re-parse into different valid claims."""
    tok = sign_qa_token("a:b", "c", secret=_SECRET, now=1000.0)
    with pytest.raises(QaTokenError, match="malformed payload"):
        verify_qa_token(tok, secret=_SECRET, now=1010.0)
