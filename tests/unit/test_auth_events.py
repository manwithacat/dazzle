"""Tests for auth lifecycle event emission.

Verifies that successful registration, login, password change, and 2FA
verification emit the correct events via the EventFramework bus.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from dazzle_back.events.envelope import EventEnvelope
from dazzle_back.runtime.auth.events import (
    AUTH_USER_LOGGED_IN,
    AUTH_USER_PASSWORD_CHANGED,
    AUTH_USER_REGISTERED,
    _publish,
    emit_user_logged_in,
    emit_user_password_changed,
    emit_user_registered,
)
from dazzle_back.runtime.auth.models import UserRecord

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def user() -> UserRecord:
    """A minimal UserRecord for testing."""
    return UserRecord(
        id=uuid4(),
        email="alice@example.com",
        password_hash="hashed",
        username="Alice",
        roles=["customer"],
    )


@pytest.fixture
def mock_bus() -> AsyncMock:
    """An AsyncMock standing in for EventBus.publish."""
    return AsyncMock()


@pytest.fixture
def mock_framework(mock_bus: AsyncMock) -> MagicMock:
    """A MagicMock EventFramework whose get_bus().publish is async."""
    fw = MagicMock()
    bus = MagicMock()
    bus.publish = mock_bus
    fw.get_bus.return_value = bus
    return fw


# ---------------------------------------------------------------------------
# Unit tests for individual emit helpers
# ---------------------------------------------------------------------------


class TestEmitUserRegistered:
    @pytest.mark.asyncio
    async def test_creates_correct_envelope(
        self, user: UserRecord, mock_framework: MagicMock, mock_bus: AsyncMock
    ) -> None:
        with patch("dazzle_back.runtime.auth.events._event_framework", mock_framework):
            await emit_user_registered(user, session_id="sess_abc")

        mock_bus.assert_awaited_once()
        topic, envelope = mock_bus.await_args.args
        assert topic == "auth.user"
        assert envelope.event_type == AUTH_USER_REGISTERED
        assert envelope.key == str(user.id)
        assert envelope.payload["user_id"] == str(user.id)
        assert envelope.payload["email"] == "alice@example.com"
        assert envelope.payload["username"] == "Alice"
        assert envelope.payload["roles"] == ["customer"]
        assert "timestamp" in envelope.payload
        assert envelope.headers["session_id"] == "sess_abc"
        assert envelope.producer == "dazzle-auth"

    @pytest.mark.asyncio
    async def test_without_session_id(
        self, user: UserRecord, mock_framework: MagicMock, mock_bus: AsyncMock
    ) -> None:
        with patch("dazzle_back.runtime.auth.events._event_framework", mock_framework):
            await emit_user_registered(user)

        envelope = mock_bus.await_args.args[1]
        assert "session_id" not in envelope.headers


class TestEmitUserLoggedIn:
    @pytest.mark.asyncio
    async def test_creates_correct_envelope(
        self, user: UserRecord, mock_framework: MagicMock, mock_bus: AsyncMock
    ) -> None:
        with patch("dazzle_back.runtime.auth.events._event_framework", mock_framework):
            await emit_user_logged_in(user, session_id="sess_xyz", method="password")

        mock_bus.assert_awaited_once()
        topic, envelope = mock_bus.await_args.args
        assert topic == "auth.user"
        assert envelope.event_type == AUTH_USER_LOGGED_IN
        assert envelope.key == str(user.id)
        assert envelope.payload["user_id"] == str(user.id)
        assert envelope.payload["email"] == "alice@example.com"
        assert envelope.payload["session_id"] == "sess_xyz"
        assert envelope.payload["method"] == "password"
        assert "timestamp" in envelope.payload

    @pytest.mark.asyncio
    async def test_2fa_method(
        self, user: UserRecord, mock_framework: MagicMock, mock_bus: AsyncMock
    ) -> None:
        with patch("dazzle_back.runtime.auth.events._event_framework", mock_framework):
            await emit_user_logged_in(user, session_id="s", method="2fa")

        envelope = mock_bus.await_args.args[1]
        assert envelope.payload["method"] == "2fa"

    @pytest.mark.asyncio
    async def test_default_method_is_password(
        self, user: UserRecord, mock_framework: MagicMock, mock_bus: AsyncMock
    ) -> None:
        with patch("dazzle_back.runtime.auth.events._event_framework", mock_framework):
            await emit_user_logged_in(user)

        envelope = mock_bus.await_args.args[1]
        assert envelope.payload["method"] == "password"


class TestEmitUserPasswordChanged:
    @pytest.mark.asyncio
    async def test_creates_correct_envelope(
        self, user: UserRecord, mock_framework: MagicMock, mock_bus: AsyncMock
    ) -> None:
        with patch("dazzle_back.runtime.auth.events._event_framework", mock_framework):
            await emit_user_password_changed(user)

        mock_bus.assert_awaited_once()
        topic, envelope = mock_bus.await_args.args
        assert topic == "auth.user"
        assert envelope.event_type == AUTH_USER_PASSWORD_CHANGED
        assert envelope.key == str(user.id)
        assert envelope.payload["user_id"] == str(user.id)
        assert "timestamp" in envelope.payload
        # Password changed should NOT include email for security
        assert "email" not in envelope.payload


# ---------------------------------------------------------------------------
# Tests for _publish resilience
# ---------------------------------------------------------------------------


class TestPublishResilience:
    @pytest.mark.asyncio
    async def test_swallows_framework_not_initialized(self) -> None:
        """_publish should not raise when framework is not initialized."""
        with patch("dazzle_back.runtime.auth.events._event_framework", None):
            # Should not raise
            envelope = EventEnvelope.create(
                event_type="auth.user.registered",
                key="test",
                payload={},
            )
            await _publish(envelope)

    @pytest.mark.asyncio
    async def test_swallows_bus_publish_error(self, mock_framework: MagicMock) -> None:
        """_publish should not raise when bus.publish fails."""
        mock_framework.get_bus().publish = AsyncMock(side_effect=ConnectionError("redis down"))

        with patch("dazzle_back.runtime.auth.events._event_framework", mock_framework):
            envelope = EventEnvelope.create(
                event_type="auth.user.registered",
                key="test",
                payload={},
            )
            await _publish(envelope)

    @pytest.mark.asyncio
    async def test_skips_when_bus_is_none(self) -> None:
        """_publish should skip gracefully when bus is None."""
        fw = MagicMock()
        fw.get_bus.return_value = None

        with patch("dazzle_back.runtime.auth.events._event_framework", fw):
            envelope = EventEnvelope.create(
                event_type="auth.user.registered",
                key="test",
                payload={},
            )
            await _publish(envelope)


# ---------------------------------------------------------------------------
# Envelope shape tests
# ---------------------------------------------------------------------------


class TestEnvelopeShape:
    @pytest.mark.asyncio
    async def test_envelope_topic_derivation(
        self, user: UserRecord, mock_framework: MagicMock, mock_bus: AsyncMock
    ) -> None:
        """Event type 'auth.user.registered' should derive topic 'auth.user'."""
        with patch("dazzle_back.runtime.auth.events._event_framework", mock_framework):
            await emit_user_registered(user)

        envelope: EventEnvelope = mock_bus.await_args.args[1]
        assert envelope.topic == "auth.user"
        assert envelope.action == "registered"

    @pytest.mark.asyncio
    async def test_envelope_is_serializable(
        self, user: UserRecord, mock_framework: MagicMock, mock_bus: AsyncMock
    ) -> None:
        """All emitted envelopes should be JSON-serializable."""
        with patch("dazzle_back.runtime.auth.events._event_framework", mock_framework):
            await emit_user_registered(user)
            await emit_user_logged_in(user, session_id="s1")
            await emit_user_password_changed(user)

        for call in mock_bus.await_args_list:
            envelope: EventEnvelope = call.args[1]
            # Should not raise
            d = envelope.to_dict()
            assert isinstance(d, dict)
            json_str = envelope.to_json()
            assert isinstance(json_str, str)
            # Round-trip
            restored = EventEnvelope.from_json(json_str)
            assert restored.event_type == envelope.event_type
