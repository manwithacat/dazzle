"""Tests for #952 cycle 5 — dispatch retry + delivery audit log.

The cycle-2 dispatcher's `dispatch()` method always made one
provider.send() attempt. Cycle 5 adds:

- `dispatch_async()` — async variant with retry on transient failures
  (provider returns False)
- `RetryPolicy` — exponential backoff schedule, 3 attempts default
- `DeliveryRecord` — one row per delivery attempt, written to the
  dispatcher's `deliveries` deque so an audit consumer can see what
  happened to each message
- `DeliveryOutcome` — SENT / FAILED_TRANSIENT / FAILED_PERMANENT

These tests exercise the retry loop, the delivery log, and the
backoff math. They use a flaky stub provider (controllable from the
test) instead of a real SMTP server so the suite stays fast.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from dazzle.notifications import (
    DeliveryOutcome,
    NotificationDispatcher,
    RenderedNotification,
    RetryPolicy,
)


class _StubProvider:
    """Configurable provider for the retry tests.

    `outcomes` is a list of outcomes for successive calls:
    - True  → return True (sent)
    - False → return False (transient)
    - Exception instance → raise it (permanent)
    """

    def __init__(self, outcomes: list[Any]) -> None:
        self.outcomes = outcomes
        self.calls: list[RenderedNotification] = []

    def send(self, notification: RenderedNotification) -> bool:
        self.calls.append(notification)
        idx = len(self.calls) - 1
        outcome = self.outcomes[idx] if idx < len(self.outcomes) else self.outcomes[-1]
        if isinstance(outcome, Exception):
            raise outcome
        return bool(outcome)


def _spec(channels: list[str] | None = None) -> Any:
    return SimpleNamespace(
        name="welcome_email",
        title="Welcome",
        subject="Hi",
        message="Hello {{ name }}",
        template="",
        channels=[SimpleNamespace(value=c) for c in (channels or ["email"])],
        recipients=SimpleNamespace(kind="field", value="email"),
    )


# Speed up retry tests — base 0.001s gives 0/0.001/0.002 between attempts.
_FAST_POLICY = RetryPolicy(max_attempts=3, base_delay_seconds=0.001, max_delay_seconds=0.01)


# ---------------------------------------------------------------------------
# RetryPolicy maths
# ---------------------------------------------------------------------------


class TestRetryPolicy:
    def test_first_attempt_no_delay(self):
        policy = RetryPolicy(max_attempts=3, base_delay_seconds=1.0, max_delay_seconds=10.0)
        # Attempt 0 means "before the first send" — no delay.
        assert policy.delay_for_attempt(0) == 0.0

    def test_exponential_backoff(self):
        policy = RetryPolicy(max_attempts=5, base_delay_seconds=1.0, max_delay_seconds=100.0)
        # base * 2^(n-1)
        assert policy.delay_for_attempt(1) == 1.0
        assert policy.delay_for_attempt(2) == 2.0
        assert policy.delay_for_attempt(3) == 4.0
        assert policy.delay_for_attempt(4) == 8.0

    def test_caps_at_max_delay(self):
        policy = RetryPolicy(max_attempts=10, base_delay_seconds=1.0, max_delay_seconds=5.0)
        assert policy.delay_for_attempt(3) == 4.0  # under cap
        assert policy.delay_for_attempt(4) == 5.0  # at cap
        assert policy.delay_for_attempt(10) == 5.0  # capped


# ---------------------------------------------------------------------------
# dispatch_async — happy path
# ---------------------------------------------------------------------------


class TestDispatchAsyncSuccess:
    def test_sent_on_first_attempt_records_one_send(self):
        provider = _StubProvider([True])
        dispatcher = NotificationDispatcher(provider=provider, retry_policy=_FAST_POLICY)
        asyncio.run(dispatcher.dispatch_async(_spec(), {"name": "Ada", "email": "a@b.com"}))

        assert len(provider.calls) == 1
        assert len(dispatcher.deliveries) == 1
        record = dispatcher.deliveries[0]
        assert record.outcome == DeliveryOutcome.SENT
        assert record.attempts == 1
        assert record.notification_name == "welcome_email"
        assert record.channel == "email"
        assert record.recipient == "a@b.com"


# ---------------------------------------------------------------------------
# dispatch_async — transient retry
# ---------------------------------------------------------------------------


class TestDispatchAsyncTransientRetry:
    def test_transient_then_success_records_two_attempts(self):
        # Provider returns False once, then True — should retry once and succeed.
        provider = _StubProvider([False, True])
        dispatcher = NotificationDispatcher(provider=provider, retry_policy=_FAST_POLICY)
        asyncio.run(dispatcher.dispatch_async(_spec(), {"email": "a@b.com"}))

        assert len(provider.calls) == 2
        record = dispatcher.deliveries[0]
        assert record.outcome == DeliveryOutcome.SENT
        assert record.attempts == 2

    def test_all_transient_records_dead_letter(self):
        # Provider always returns False → exhaust attempts → FAILED_TRANSIENT.
        provider = _StubProvider([False])  # repeats False indefinitely
        dispatcher = NotificationDispatcher(provider=provider, retry_policy=_FAST_POLICY)
        asyncio.run(dispatcher.dispatch_async(_spec(), {"email": "a@b.com"}))

        assert len(provider.calls) == 3  # max_attempts=3
        record = dispatcher.deliveries[0]
        assert record.outcome == DeliveryOutcome.FAILED_TRANSIENT
        assert record.attempts == 3


# ---------------------------------------------------------------------------
# dispatch_async — permanent failure short-circuits
# ---------------------------------------------------------------------------


class TestDispatchAsyncPermanentFailure:
    def test_provider_raise_records_permanent_no_retry(self):
        # First call raises — should NOT retry, should record FAILED_PERMANENT.
        boom = RuntimeError("malformed address")
        provider = _StubProvider([boom, True])  # second outcome never reached
        dispatcher = NotificationDispatcher(provider=provider, retry_policy=_FAST_POLICY)
        asyncio.run(dispatcher.dispatch_async(_spec(), {"email": "a@b.com"}))

        assert len(provider.calls) == 1  # only one attempt
        record = dispatcher.deliveries[0]
        assert record.outcome == DeliveryOutcome.FAILED_PERMANENT
        assert "malformed address" in record.error_message
        assert record.attempts == 1


# ---------------------------------------------------------------------------
# dispatch_async — multi-channel independent retry
# ---------------------------------------------------------------------------


class TestDispatchAsyncMultiChannel:
    def test_one_channel_failure_does_not_block_other(self):
        # email transient-fails twice then succeeds; in_app always succeeds.
        # Since outcomes apply across the combined call sequence we'll
        # use a more deterministic approach: 3 outcomes total covering
        # both channels (email retries + in_app once).
        provider = _StubProvider([False, False, True, True])
        dispatcher = NotificationDispatcher(provider=provider, retry_policy=_FAST_POLICY)
        asyncio.run(
            dispatcher.dispatch_async(_spec(channels=["email", "in_app"]), {"email": "a@b.com"})
        )

        # 3 email attempts + 1 in_app attempt = 4 total
        assert len(provider.calls) == 4
        # Two delivery records, one per channel.
        assert len(dispatcher.deliveries) == 2
        outcomes_by_channel = {r.channel: r for r in dispatcher.deliveries}
        assert outcomes_by_channel["email"].outcome == DeliveryOutcome.SENT
        assert outcomes_by_channel["email"].attempts == 3
        assert outcomes_by_channel["in_app"].outcome == DeliveryOutcome.SENT
        assert outcomes_by_channel["in_app"].attempts == 1


# ---------------------------------------------------------------------------
# Sync dispatch path also records to the deque (cycle 5 polish)
# ---------------------------------------------------------------------------


class TestSyncDispatchAlsoRecords:
    def test_sync_dispatch_records_sent(self):
        provider = _StubProvider([True])
        dispatcher = NotificationDispatcher(provider=provider, retry_policy=_FAST_POLICY)
        dispatcher.dispatch(_spec(), {"email": "a@b.com"})
        record = dispatcher.deliveries[0]
        assert record.outcome == DeliveryOutcome.SENT
        assert record.attempts == 1

    def test_sync_dispatch_records_transient_no_retry(self):
        # Sync path doesn't retry — single False → FAILED_TRANSIENT recorded once.
        provider = _StubProvider([False])
        dispatcher = NotificationDispatcher(provider=provider, retry_policy=_FAST_POLICY)
        dispatcher.dispatch(_spec(), {"email": "a@b.com"})
        record = dispatcher.deliveries[0]
        assert record.outcome == DeliveryOutcome.FAILED_TRANSIENT
        assert record.attempts == 1


# ---------------------------------------------------------------------------
# Deque cap
# ---------------------------------------------------------------------------


def test_deliveries_deque_capped_at_512():
    """Memory footprint must stay bounded — older records fall off."""
    provider = _StubProvider([True])
    dispatcher = NotificationDispatcher(provider=provider, retry_policy=_FAST_POLICY)
    for _ in range(600):
        asyncio.run(dispatcher.dispatch_async(_spec(), {"email": "a@b.com"}))
    assert len(dispatcher.deliveries) == 512


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
