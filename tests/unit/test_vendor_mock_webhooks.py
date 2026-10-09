"""Tests for vendor mock webhook dispatcher."""

import hashlib
import hmac as hmac_mod
from typing import Any

import pytest

from dazzle.testing.vendor_mock.webhooks import (
    WEBHOOK_EVENTS,
    DeliveryAttempt,
    WebhookDispatcher,
    _deep_merge,
)

# ---------------------------------------------------------------------------
# Payload building tests
# ---------------------------------------------------------------------------


class TestPayloadBuilding:
    def test_build_stripe_payment_succeeded(self) -> None:
        dispatcher = WebhookDispatcher()
        payload = dispatcher.build_payload("stripe_payments", "payment_intent.succeeded")
        assert payload["type"] == "payment_intent.succeeded"
        assert payload["data"]["object"]["status"] == "succeeded"

    def test_build_with_overrides(self) -> None:
        dispatcher = WebhookDispatcher()
        payload = dispatcher.build_payload(
            "stripe_payments",
            "payment_intent.succeeded",
            overrides={"data": {"object": {"status": "processing"}}},
        )
        assert payload["data"]["object"]["status"] == "processing"
        assert payload["type"] == "payment_intent.succeeded"

    def test_build_with_entity_data(self) -> None:
        dispatcher = WebhookDispatcher()
        payload = dispatcher.build_payload(
            "stripe_payments",
            "payment_intent.succeeded",
            entity_data={"id": "pi_abc"},
        )
        assert payload["id"] == "pi_abc"

    def test_build_stripe_with_entity_data(self) -> None:
        dispatcher = WebhookDispatcher()
        payload = dispatcher.build_payload(
            "stripe_payments",
            "payment_intent.succeeded",
            entity_data={"id": "pi_abc"},
        )
        assert payload["data"]["object"]["id"] == "pi_abc"

    def test_build_unknown_event_raises(self) -> None:
        dispatcher = WebhookDispatcher()
        with pytest.raises(ValueError, match="Unknown webhook event"):
            dispatcher.build_payload("stripe_payments", "nonexistent_event")

    def test_build_unknown_vendor_raises(self) -> None:
        dispatcher = WebhookDispatcher()
        with pytest.raises(ValueError, match="Unknown webhook event"):
            dispatcher.build_payload("unknown_vendor", "some_event")

    def test_timestamps_populated(self) -> None:
        dispatcher = WebhookDispatcher()
        payload = dispatcher.build_payload("stripe_payments", "payment_intent.succeeded")
        assert payload["created"] != 0


# ---------------------------------------------------------------------------
# Signing tests
# ---------------------------------------------------------------------------


class TestWebhookSigning:
    def test_stripe_signing(self) -> None:
        dispatcher = WebhookDispatcher(signing_secret="whsec_test")
        payload = b'{"type": "payment_intent.succeeded"}'
        headers = dispatcher.sign_payload("stripe_payments", payload)
        assert "Stripe-Signature" in headers
        sig_header = headers["Stripe-Signature"]
        assert sig_header.startswith("t=")
        assert ",v1=" in sig_header

        # Verify the signature
        parts = dict(p.split("=", 1) for p in sig_header.split(","))
        timestamp = parts["t"]
        signed_payload = f"{timestamp}.".encode() + payload
        expected = hmac_mod.new(b"whsec_test", signed_payload, hashlib.sha256).hexdigest()
        assert parts["v1"] == expected

    def test_per_vendor_secrets(self) -> None:
        dispatcher = WebhookDispatcher(
            signing_secret="default",
            vendor_secrets={"stripe_payments": "whsec_vendor"},
        )
        payload = b'{"test": true}'

        headers = dispatcher.sign_payload("stripe_payments", payload)
        sig_header = headers["Stripe-Signature"]
        parts = dict(p.split("=", 1) for p in sig_header.split(","))
        signed_payload = f"{parts['t']}.".encode() + payload
        expected = hmac_mod.new(b"whsec_vendor", signed_payload, hashlib.sha256).hexdigest()
        assert parts["v1"] == expected

        headers = dispatcher.sign_payload("custom_vendor", payload)
        expected = hmac_mod.new(b"default", payload, hashlib.sha256).hexdigest()
        assert headers["X-Webhook-Signature"] == expected


# ---------------------------------------------------------------------------
# Delivery tracking tests
# ---------------------------------------------------------------------------


class TestDeliveryTracking:
    def test_delivery_log_initially_empty(self) -> None:
        dispatcher = WebhookDispatcher()
        assert dispatcher.delivery_count == 0
        assert dispatcher.last_delivery() is None
        assert dispatcher.deliveries == []

    def test_delivery_attempt_dataclass(self) -> None:
        attempt = DeliveryAttempt(
            vendor="stripe_payments",
            event_name="payment_intent.succeeded",
            target_url="http://localhost:8000/webhooks/stripe",
            payload={"type": "payment_intent.succeeded"},
            status_code=200,
        )
        assert attempt.vendor == "stripe_payments"
        assert attempt.status_code == 200
        assert attempt.error is None

    def test_clear_deliveries(self) -> None:
        dispatcher = WebhookDispatcher()
        # Manually add a delivery
        dispatcher._delivery_log.append(
            DeliveryAttempt(
                vendor="test",
                event_name="test",
                target_url="http://test",
                payload={},
            )
        )
        assert dispatcher.delivery_count == 1
        dispatcher.clear()
        assert dispatcher.delivery_count == 0

    def test_deliveries_returns_copy(self) -> None:
        dispatcher = WebhookDispatcher()
        dispatcher._delivery_log.append(
            DeliveryAttempt(
                vendor="test",
                event_name="test",
                target_url="http://test",
                payload={},
            )
        )
        deliveries = dispatcher.deliveries
        deliveries.clear()
        assert dispatcher.delivery_count == 1  # Original not affected


# ---------------------------------------------------------------------------
# Event listing tests
# ---------------------------------------------------------------------------


class TestEventListing:
    def test_list_all_events(self) -> None:
        dispatcher = WebhookDispatcher()
        events = dispatcher.list_events()
        assert len(events) > 0
        assert any("stripe_payments/" in e for e in events)
        assert all("sumsub_kyc/" not in e for e in events)

    def test_list_vendor_events(self) -> None:
        dispatcher = WebhookDispatcher()
        events = dispatcher.list_events(vendor="stripe_payments")
        assert all(e.startswith("stripe_payments/") for e in events)
        assert len(events) >= 3

    def test_list_unknown_vendor(self) -> None:
        dispatcher = WebhookDispatcher()
        events = dispatcher.list_events(vendor="nonexistent")
        assert events == []


# ---------------------------------------------------------------------------
# Target URL tests
# ---------------------------------------------------------------------------


class TestTargetUrls:
    def test_default_urls(self) -> None:
        dispatcher = WebhookDispatcher(target_base_url="http://localhost:8000")
        assert (
            dispatcher._get_target_url("stripe_payments") == "http://localhost:8000/webhooks/stripe"
        )

    def test_custom_paths(self) -> None:
        dispatcher = WebhookDispatcher(
            target_base_url="http://localhost:3000",
            webhook_paths={"stripe_payments": "/api/hooks/stripe"},
        )
        assert (
            dispatcher._get_target_url("stripe_payments")
            == "http://localhost:3000/api/hooks/stripe"
        )

    def test_unknown_vendor_fallback(self) -> None:
        dispatcher = WebhookDispatcher(target_base_url="http://localhost:8000")
        assert (
            dispatcher._get_target_url("custom_vendor")
            == "http://localhost:8000/webhooks/custom_vendor"
        )

    def test_trailing_slash_stripped(self) -> None:
        dispatcher = WebhookDispatcher(target_base_url="http://localhost:8000/")
        assert (
            dispatcher._get_target_url("stripe_payments") == "http://localhost:8000/webhooks/stripe"
        )


# ---------------------------------------------------------------------------
# Sync delivery tests (with connection error — no server running)
# ---------------------------------------------------------------------------


class TestSyncDelivery:
    def test_sync_delivery_connection_error(self) -> None:
        """fire_sync records connection errors gracefully."""
        dispatcher = WebhookDispatcher(target_base_url="http://127.0.0.1:19999")
        attempt = dispatcher.fire_sync("stripe_payments", "payment_intent.succeeded")
        assert attempt.status_code is None
        assert attempt.error is not None
        assert dispatcher.delivery_count == 1
        assert dispatcher.last_delivery() is attempt

    def test_sync_delivery_tracks_payload(self) -> None:
        dispatcher = WebhookDispatcher(target_base_url="http://127.0.0.1:19999")
        attempt = dispatcher.fire_sync(
            "stripe_payments",
            "payment_intent.succeeded",
            overrides={"data": {"object": {"status": "processing"}}},
        )
        assert attempt.payload["data"]["object"]["status"] == "processing"
        assert attempt.vendor == "stripe_payments"
        assert attempt.event_name == "payment_intent.succeeded"


# ---------------------------------------------------------------------------
# Deep merge helper tests
# ---------------------------------------------------------------------------


class TestDeepMerge:
    @pytest.mark.parametrize(
        "base,override,expected",
        [
            ({"a": 1, "b": 2}, {"b": 3, "c": 4}, {"a": 1, "b": 3, "c": 4}),
            ({"a": {"x": 1, "y": 2}}, {"a": {"y": 3, "z": 4}}, {"a": {"x": 1, "y": 3, "z": 4}}),
            ({"a": [1, 2]}, {"a": [3, 4, 5]}, {"a": [3, 4, 5]}),
        ],
        ids=[
            "test_simple_merge",
            "test_nested_merge",
            "test_list_replaced",
        ],
    )
    def test_merge_outputs(self, base: dict, override: dict, expected: dict) -> None:
        assert _deep_merge(base, override) == expected

    def test_deep_copy(self) -> None:
        """Merge returns a new dict, doesn't mutate inputs."""
        base: dict[str, Any] = {"a": {"x": 1}}
        override: dict[str, Any] = {"a": {"y": 2}}
        result = _deep_merge(base, override)
        result["a"]["x"] = 999
        assert base["a"]["x"] == 1  # Unchanged


# ---------------------------------------------------------------------------
# Webhook event registry completeness
# ---------------------------------------------------------------------------


class TestWebhookRegistry:
    def test_all_vendors_have_events(self) -> None:
        assert set(WEBHOOK_EVENTS.keys()) == {"stripe_payments"}

    def test_stripe_events(self) -> None:
        events = set(WEBHOOK_EVENTS["stripe_payments"].keys())
        assert "payment_intent.succeeded" in events
        assert "payment_intent.payment_failed" in events
        assert "charge.refunded" in events
