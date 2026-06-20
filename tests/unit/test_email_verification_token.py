"""Tests for the email-verification token primitive (#1109).

Verifies the DB-backed contract: tokens are one-shot, TTL-gated, and
the ``validate`` call also flips ``email_verified=true`` on the user
record via ``store.mark_email_verified``.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from dazzle.http.runtime.auth.email_verification import (
    create_email_verification_token,
    validate_email_verification_token,
)


def _store_with_rows(rows: list[dict]) -> MagicMock:
    """Mock the duck-typed store: ``_execute`` returns rows, ``_execute_modify``
    is fire-and-forget for the INSERT/UPDATE side effects."""
    store = MagicMock()
    store._execute = MagicMock(return_value=rows)
    store._execute_modify = MagicMock(return_value=1)
    store.mark_email_verified = MagicMock(return_value=True)
    return store


def test_create_token_inserts_row_and_returns_unguessable_string() -> None:
    store = _store_with_rows([])
    token = create_email_verification_token(
        store, user_id="user-123", ttl_hours=24, created_by="signup"
    )
    assert isinstance(token, str)
    # `secrets.token_urlsafe(32)` produces at least 43 url-safe chars.
    assert len(token) >= 32
    # One INSERT call.
    store._execute_modify.assert_called_once()
    args, _kwargs = store._execute_modify.call_args
    assert "INSERT INTO email_verification_tokens" in args[0]


def test_validate_token_consumes_and_marks_verified() -> None:
    expires = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    store = _store_with_rows([{"user_id": "user-123", "expires_at": expires, "used_at": None}])
    user_id = validate_email_verification_token(store, "valid-token")
    assert user_id == "user-123"
    # The token row got marked used.
    assert any(
        "UPDATE email_verification_tokens SET used_at" in call.args[0]
        for call in store._execute_modify.call_args_list
    )
    # The user got flipped to verified.
    store.mark_email_verified.assert_called_once_with("user-123")


def test_validate_token_returns_none_for_unknown_token() -> None:
    store = _store_with_rows([])
    assert validate_email_verification_token(store, "unknown") is None
    store.mark_email_verified.assert_not_called()


def test_validate_token_returns_none_for_used_token() -> None:
    expires = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    store = _store_with_rows(
        [
            {
                "user_id": "user-123",
                "expires_at": expires,
                "used_at": "2026-05-16T00:00:00+00:00",  # already used
            }
        ]
    )
    assert validate_email_verification_token(store, "used-token") is None
    store.mark_email_verified.assert_not_called()


def test_validate_token_returns_none_for_expired_token() -> None:
    expires = (datetime.now(UTC) - timedelta(hours=1)).isoformat()  # past
    store = _store_with_rows([{"user_id": "user-123", "expires_at": expires, "used_at": None}])
    assert validate_email_verification_token(store, "expired-token") is None
    store.mark_email_verified.assert_not_called()


def test_validate_skips_mark_email_verified_if_store_lacks_method() -> None:
    """Forward-compat: stores without mark_email_verified still get the
    consume-the-token half (used_at) — no AttributeError."""
    expires = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    store = MagicMock()
    store._execute = MagicMock(
        return_value=[{"user_id": "user-123", "expires_at": expires, "used_at": None}]
    )
    store._execute_modify = MagicMock(return_value=1)
    # Explicitly remove the attribute so hasattr() returns False.
    del store.mark_email_verified
    user_id = validate_email_verification_token(store, "valid-token")
    assert user_id == "user-123"
