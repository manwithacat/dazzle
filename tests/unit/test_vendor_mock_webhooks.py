"""Tests for vendor mock webhook dispatcher."""

from __future__ import annotations

import base64
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
    def test_build_sumsub_applicant_reviewed(self) -> None:
        dispatcher = WebhookDispatcher()
        payload = dispatcher.build_payload("sumsub_kyc", "applicant_reviewed")
        assert payload["type"] == "applicant_reviewed"
        assert "reviewResult" in payload
        assert payload["reviewResult"]["reviewAnswer"] == "GREEN"

    def test_build_stripe_payment_succeeded(self) -> None:
        dispatcher = WebhookDispatcher()
        payload = dispatcher.build_payload("stripe_payments", "payment_intent.succeeded")
        assert payload["type"] == "payment_intent.succeeded"
        assert payload["data"]["object"]["status"] == "succeeded"

    def test_build_docuseal_submission_completed(self) -> None:
        dispatcher = WebhookDispatcher()
        payload = dispatcher.build_payload("docuseal_signatures", "submission.completed")
        assert payload["event_type"] == "submission.completed"
        assert payload["data"]["status"] == "completed"

    def test_build_xero_invoice_updated(self) -> None:
        dispatcher = WebhookDispatcher()
        payload = dispatcher.build_payload("xero_accounting", "invoice.updated")
        assert "events" in payload
        assert payload["events"][0]["eventCategory"] == "INVOICE"

    def test_build_with_overrides(self) -> None:
        dispatcher = WebhookDispatcher()
        payload = dispatcher.build_payload(
            "sumsub_kyc",
            "applicant_reviewed",
            overrides={"reviewResult": {"reviewAnswer": "RED", "rejectLabels": ["FRAUD"]}},
        )
        assert payload["reviewResult"]["reviewAnswer"] == "RED"
        assert payload["reviewResult"]["rejectLabels"] == ["FRAUD"]

    def test_build_with_entity_data(self) -> None:
        dispatcher = WebhookDispatcher()
        payload = dispatcher.build_payload(
            "sumsub_kyc",
            "applicant_reviewed",
            entity_data={"id": "app-123"},
        )
        assert payload["applicantId"] == "app-123"

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
            dispatcher.build_payload("sumsub_kyc", "nonexistent_event")

    def test_build_unknown_vendor_raises(self) -> None:
        dispatcher = WebhookDispatcher()
        with pytest.raises(ValueError, match="Unknown webhook event"):
            dispatcher.build_payload("unknown_vendor", "some_event")

    def test_timestamps_populated(self) -> None:
        dispatcher = WebhookDispatcher()
        payload = dispatcher.build_payload("sumsub_kyc", "applicant_reviewed")
        # createdAtMs should be populated (non-empty)
        assert payload["createdAtMs"] != ""


# ---------------------------------------------------------------------------
# Signing tests
# ---------------------------------------------------------------------------


class TestWebhookSigning:
    def test_sumsub_signing(self) -> None:
        dispatcher = WebhookDispatcher(signing_secret="test-secret")
        payload = b'{"type": "applicant_reviewed"}'
        headers = dispatcher.sign_payload("sumsub_kyc", payload)
        assert "X-Payload-Digest" in headers
        # Verify the HMAC
        expected = hmac_mod.new(b"test-secret", payload, hashlib.sha256).hexdigest()
        assert headers["X-Payload-Digest"] == expected

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

    def test_xero_signing(self) -> None:
        dispatcher = WebhookDispatcher(signing_secret="xero-key")
        payload = b'{"events": []}'
        headers = dispatcher.sign_payload("xero_accounting", payload)
        assert "x-xero-signature" in headers
        # Verify base64-encoded HMAC
        expected = hmac_mod.new(b"xero-key", payload, hashlib.sha256).digest()
        assert headers["x-xero-signature"] == base64.b64encode(expected).decode()

    def test_docuseal_generic_signing(self) -> None:
        dispatcher = WebhookDispatcher(signing_secret="ds-secret")
        payload = b'{"event_type": "submission.completed"}'
        headers = dispatcher.sign_payload("docuseal_signatures", payload)
        assert "X-Webhook-Signature" in headers

    def test_per_vendor_secrets(self) -> None:
        dispatcher = WebhookDispatcher(
            signing_secret="default",
            vendor_secrets={"sumsub_kyc": "sumsub-secret"},
        )
        payload = b'{"test": true}'

        # SumSub uses its specific secret
        headers = dispatcher.sign_payload("sumsub_kyc", payload)
        expected = hmac_mod.new(b"sumsub-secret", payload, hashlib.sha256).hexdigest()
        assert headers["X-Payload-Digest"] == expected

        # Other vendors use default
        headers = dispatcher.sign_payload("docuseal_signatures", payload)
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
            vendor="sumsub_kyc",
            event_name="applicant_reviewed",
            target_url="http://localhost:8000/webhooks/sumsub",
            payload={"type": "applicant_reviewed"},
            status_code=200,
        )
        assert attempt.vendor == "sumsub_kyc"
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
        assert any("sumsub_kyc/" in e for e in events)
        assert any("stripe_payments/" in e for e in events)

    def test_list_vendor_events(self) -> None:
        dispatcher = WebhookDispatcher()
        events = dispatcher.list_events(vendor="sumsub_kyc")
        assert all(e.startswith("sumsub_kyc/") for e in events)
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
        assert dispatcher._get_target_url("sumsub_kyc") == "http://localhost:8000/webhooks/sumsub"
        assert (
            dispatcher._get_target_url("stripe_payments") == "http://localhost:8000/webhooks/stripe"
        )

    def test_custom_paths(self) -> None:
        dispatcher = WebhookDispatcher(
            target_base_url="http://localhost:3000",
            webhook_paths={"sumsub_kyc": "/api/hooks/sumsub"},
        )
        assert dispatcher._get_target_url("sumsub_kyc") == "http://localhost:3000/api/hooks/sumsub"
        # Others still use defaults
        assert (
            dispatcher._get_target_url("stripe_payments") == "http://localhost:3000/webhooks/stripe"
        )

    def test_unknown_vendor_fallback(self) -> None:
        dispatcher = WebhookDispatcher(target_base_url="http://localhost:8000")
        assert (
            dispatcher._get_target_url("custom_vendor")
            == "http://localhost:8000/webhooks/custom_vendor"
        )

    def test_trailing_slash_stripped(self) -> None:
        dispatcher = WebhookDispatcher(target_base_url="http://localhost:8000/")
        assert dispatcher._get_target_url("sumsub_kyc") == "http://localhost:8000/webhooks/sumsub"


# ---------------------------------------------------------------------------
# Sync delivery tests (with connection error — no server running)
# ---------------------------------------------------------------------------


class TestSyncDelivery:
    def test_sync_delivery_connection_error(self) -> None:
        """fire_sync records connection errors gracefully."""
        dispatcher = WebhookDispatcher(target_base_url="http://127.0.0.1:19999")
        attempt = dispatcher.fire_sync("sumsub_kyc", "applicant_reviewed")
        assert attempt.status_code is None
        assert attempt.error is not None
        assert dispatcher.delivery_count == 1
        assert dispatcher.last_delivery() is attempt

    def test_sync_delivery_tracks_payload(self) -> None:
        dispatcher = WebhookDispatcher(target_base_url="http://127.0.0.1:19999")
        attempt = dispatcher.fire_sync(
            "sumsub_kyc",
            "applicant_reviewed",
            overrides={"reviewResult": {"reviewAnswer": "RED"}},
        )
        assert attempt.payload["reviewResult"]["reviewAnswer"] == "RED"
        assert attempt.vendor == "sumsub_kyc"
        assert attempt.event_name == "applicant_reviewed"


# ---------------------------------------------------------------------------
# Deep merge helper tests
# ---------------------------------------------------------------------------


class TestDeepMerge:
    def test_simple_merge(self) -> None:
        result = _deep_merge({"a": 1, "b": 2}, {"b": 3, "c": 4})
        assert result == {"a": 1, "b": 3, "c": 4}

    def test_nested_merge(self) -> None:
        result = _deep_merge(
            {"a": {"x": 1, "y": 2}},
            {"a": {"y": 3, "z": 4}},
        )
        assert result == {"a": {"x": 1, "y": 3, "z": 4}}

    def test_list_replaced(self) -> None:
        result = _deep_merge({"a": [1, 2]}, {"a": [3, 4, 5]})
        assert result == {"a": [3, 4, 5]}

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
        expected_vendors = {
            "sumsub_kyc",
            "stripe_payments",
            "docuseal_signatures",
            "xero_accounting",
        }
        assert expected_vendors.issubset(set(WEBHOOK_EVENTS.keys()))

    def test_sumsub_events(self) -> None:
        events = set(WEBHOOK_EVENTS["sumsub_kyc"].keys())
        assert "applicant_reviewed" in events
        assert "applicant_created" in events

    def test_stripe_events(self) -> None:
        events = set(WEBHOOK_EVENTS["stripe_payments"].keys())
        assert "payment_intent.succeeded" in events
        assert "payment_intent.payment_failed" in events
        assert "charge.refunded" in events

    def test_docuseal_events(self) -> None:
        events = set(WEBHOOK_EVENTS["docuseal_signatures"].keys())
        assert "submission.completed" in events

    def test_xero_events(self) -> None:
        events = set(WEBHOOK_EVENTS["xero_accounting"].keys())
        assert "invoice.updated" in events
