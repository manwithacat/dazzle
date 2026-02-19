"""
Webhook dispatcher for vendor mock servers.

Simulates vendor-initiated webhook calls to a running Dazzle app. Supports
vendor-appropriate HMAC signing (SumSub, Stripe, DocuSeal, Xero), automatic
triggering from scenario steps, and delivery tracking.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Vendor webhook event registry
# ---------------------------------------------------------------------------

# Maps vendor → { event_name → default_payload_template }
WEBHOOK_EVENTS: dict[str, dict[str, dict[str, Any]]] = {
    "sumsub_kyc": {
        "applicant_reviewed": {
            "type": "applicant_reviewed",
            "applicantId": "",
            "inspectionId": "",
            "correlationId": "",
            "reviewResult": {
                "reviewAnswer": "GREEN",
                "moderationComment": "",
                "rejectLabels": [],
            },
            "reviewStatus": "completed",
            "createdAtMs": "",
        },
        "applicant_created": {
            "type": "applicant_created",
            "applicantId": "",
            "inspectionId": "",
            "correlationId": "",
            "createdAtMs": "",
        },
        "applicant_pending": {
            "type": "applicant_pending",
            "applicantId": "",
            "inspectionId": "",
            "reviewStatus": "pending",
            "createdAtMs": "",
        },
    },
    "stripe_payments": {
        "payment_intent.succeeded": {
            "id": "",
            "object": "event",
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": "",
                    "object": "payment_intent",
                    "amount": 0,
                    "currency": "gbp",
                    "status": "succeeded",
                },
            },
            "created": 0,
        },
        "payment_intent.payment_failed": {
            "id": "",
            "object": "event",
            "type": "payment_intent.payment_failed",
            "data": {
                "object": {
                    "id": "",
                    "object": "payment_intent",
                    "amount": 0,
                    "currency": "gbp",
                    "status": "requires_payment_method",
                    "last_payment_error": {
                        "code": "card_declined",
                        "message": "Your card was declined.",
                    },
                },
            },
            "created": 0,
        },
        "charge.refunded": {
            "id": "",
            "object": "event",
            "type": "charge.refunded",
            "data": {
                "object": {
                    "id": "",
                    "object": "charge",
                    "amount_refunded": 0,
                    "refunded": True,
                },
            },
            "created": 0,
        },
    },
    "docuseal_signatures": {
        "submission.completed": {
            "event_type": "submission.completed",
            "timestamp": "",
            "data": {
                "id": 0,
                "status": "completed",
                "completed_at": "",
                "submitters": [],
            },
        },
        "submission.created": {
            "event_type": "submission.created",
            "timestamp": "",
            "data": {
                "id": 0,
                "status": "pending",
                "submitters": [],
            },
        },
    },
    "xero_accounting": {
        "invoice.updated": {
            "events": [
                {
                    "resourceUrl": "",
                    "resourceId": "",
                    "eventDateUtc": "",
                    "eventType": "UPDATE",
                    "eventCategory": "INVOICE",
                    "tenantId": "",
                    "tenantType": "ORGANISATION",
                },
            ],
            "firstEventSequence": 1,
            "lastEventSequence": 1,
            "entropy": "",
        },
    },
}

# Signing schemes per vendor
SIGNING_SCHEMES: dict[str, str] = {
    "sumsub_kyc": "sumsub_hmac",
    "stripe_payments": "stripe_hmac",
    "docuseal_signatures": "hmac_sha256",
    "xero_accounting": "xero_hmac",
}

# Default webhook URL patterns
DEFAULT_WEBHOOK_PATHS: dict[str, str] = {
    "sumsub_kyc": "/webhooks/sumsub",
    "stripe_payments": "/webhooks/stripe",
    "docuseal_signatures": "/webhooks/docuseal",
    "xero_accounting": "/webhooks/xero",
}


@dataclass
class DeliveryAttempt:
    """Record of a webhook delivery attempt."""

    vendor: str
    event_name: str
    target_url: str
    payload: dict[str, Any]
    status_code: int | None = None
    response_body: str | None = None
    error: str | None = None
    timestamp: float = field(default_factory=time.time)
    elapsed_ms: float = 0.0


class WebhookDispatcher:
    """Fires and tracks webhook deliveries from vendor mocks.

    Args:
        target_base_url: Base URL of the Dazzle app (e.g. "http://localhost:8000").
        signing_secret: Secret key for HMAC signing (used for all vendors unless
            per-vendor secrets are provided).
        vendor_secrets: Per-vendor signing secrets, keyed by pack_name.
        webhook_paths: Per-vendor webhook URL paths, overriding defaults.
    """

    def __init__(
        self,
        target_base_url: str = "http://localhost:8000",
        *,
        signing_secret: str = "test-webhook-secret",
        vendor_secrets: dict[str, str] | None = None,
        webhook_paths: dict[str, str] | None = None,
    ) -> None:
        self._base_url = target_base_url.rstrip("/")
        self._default_secret = signing_secret
        self._vendor_secrets = vendor_secrets or {}
        self._paths = {**DEFAULT_WEBHOOK_PATHS, **(webhook_paths or {})}
        self._delivery_log: list[DeliveryAttempt] = []

    @property
    def deliveries(self) -> list[DeliveryAttempt]:
        """All delivery attempts."""
        return list(self._delivery_log)

    @property
    def delivery_count(self) -> int:
        """Number of delivery attempts."""
        return len(self._delivery_log)

    def last_delivery(self) -> DeliveryAttempt | None:
        """The most recent delivery attempt."""
        return self._delivery_log[-1] if self._delivery_log else None

    def clear(self) -> None:
        """Clear delivery log."""
        self._delivery_log.clear()

    def _get_secret(self, vendor: str) -> str:
        """Get the signing secret for a vendor."""
        return self._vendor_secrets.get(vendor, self._default_secret)

    def _get_target_url(self, vendor: str) -> str:
        """Get the full webhook target URL for a vendor."""
        path = self._paths.get(vendor, f"/webhooks/{vendor}")
        return f"{self._base_url}{path}"

    def build_payload(
        self,
        vendor: str,
        event_name: str,
        *,
        overrides: dict[str, Any] | None = None,
        entity_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build a webhook payload from the event template.

        Args:
            vendor: API pack name.
            event_name: Event name from the registry.
            overrides: Field overrides to merge into the payload.
            entity_data: Entity data to populate ID fields.

        Returns:
            Complete webhook payload dict.

        Raises:
            ValueError: If the event is not found.
        """
        vendor_events = WEBHOOK_EVENTS.get(vendor, {})
        template = vendor_events.get(event_name)
        if template is None:
            raise ValueError(
                f"Unknown webhook event '{event_name}' for vendor '{vendor}'. "
                f"Available: {list(vendor_events.keys())}"
            )

        payload = _deep_merge(template, {})  # Deep copy
        now_ms = str(int(time.time() * 1000))

        # Populate timestamp fields
        _set_nested(payload, "createdAtMs", now_ms)
        _set_nested(payload, "created", int(time.time()))
        _set_nested(payload, "timestamp", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

        # Populate IDs from entity data
        if entity_data:
            _set_nested(payload, "applicantId", entity_data.get("id", ""))
            _set_nested(payload, "id", entity_data.get("id", ""))
            if "data" in payload and isinstance(payload["data"], dict):
                if "object" in payload["data"] and isinstance(payload["data"]["object"], dict):
                    _set_nested(payload["data"]["object"], "id", entity_data.get("id", ""))
                if "id" in payload["data"]:
                    payload["data"]["id"] = entity_data.get("id", 0)

        # Apply overrides
        if overrides:
            payload = _deep_merge(payload, overrides)

        return payload

    def sign_payload(self, vendor: str, payload_bytes: bytes) -> dict[str, str]:
        """Generate signing headers for a webhook payload.

        Args:
            vendor: API pack name.
            payload_bytes: The JSON-encoded payload bytes.

        Returns:
            Dict of headers to include with the webhook request.
        """
        secret = self._get_secret(vendor)
        scheme = SIGNING_SCHEMES.get(vendor, "hmac_sha256")

        if scheme == "sumsub_hmac":
            hex_sig = hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()
            return {"X-Payload-Digest": hex_sig}

        elif scheme == "stripe_hmac":
            timestamp = str(int(time.time()))
            signed_payload = f"{timestamp}.".encode() + payload_bytes
            sig = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
            return {"Stripe-Signature": f"t={timestamp},v1={sig}"}

        elif scheme == "xero_hmac":
            raw_sig = hmac.new(secret.encode(), payload_bytes, hashlib.sha256).digest()
            return {"x-xero-signature": base64.b64encode(raw_sig).decode()}

        else:
            # Generic HMAC-SHA256
            hex_sig = hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()
            return {"X-Webhook-Signature": hex_sig}

    async def fire(
        self,
        vendor: str,
        event_name: str,
        *,
        overrides: dict[str, Any] | None = None,
        entity_data: dict[str, Any] | None = None,
        delay_ms: int = 0,
        target_url: str | None = None,
    ) -> DeliveryAttempt:
        """Fire a webhook to the target Dazzle app.

        Args:
            vendor: API pack name.
            event_name: Event name from the registry.
            overrides: Payload field overrides.
            entity_data: Entity data for ID population.
            delay_ms: Delay before sending (simulates async vendor processing).
            target_url: Override the target URL.

        Returns:
            DeliveryAttempt with status and response details.
        """
        if delay_ms > 0:
            await asyncio.sleep(delay_ms / 1000.0)

        payload = self.build_payload(
            vendor, event_name, overrides=overrides, entity_data=entity_data
        )
        payload_bytes = json.dumps(payload).encode()
        headers = {
            "Content-Type": "application/json",
            **self.sign_payload(vendor, payload_bytes),
        }

        url = target_url or self._get_target_url(vendor)

        attempt = DeliveryAttempt(
            vendor=vendor,
            event_name=event_name,
            target_url=url,
            payload=payload,
        )

        start = time.monotonic()
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, content=payload_bytes, headers=headers, timeout=10.0)
            attempt.status_code = resp.status_code
            attempt.response_body = resp.text[:1000]
        except Exception as e:
            attempt.error = str(e)
            logger.warning("Webhook delivery failed for %s/%s: %s", vendor, event_name, e)

        attempt.elapsed_ms = (time.monotonic() - start) * 1000
        self._delivery_log.append(attempt)
        return attempt

    def fire_sync(
        self,
        vendor: str,
        event_name: str,
        *,
        overrides: dict[str, Any] | None = None,
        entity_data: dict[str, Any] | None = None,
        target_url: str | None = None,
    ) -> DeliveryAttempt:
        """Synchronous webhook delivery (for use with TestClient).

        Uses httpx synchronous client instead of async. Suitable for tests
        where the target is a TestClient-hosted app.

        Args:
            vendor: API pack name.
            event_name: Event name.
            overrides: Payload overrides.
            entity_data: Entity data for IDs.
            target_url: Override URL (required for TestClient usage).

        Returns:
            DeliveryAttempt with results.
        """
        payload = self.build_payload(
            vendor, event_name, overrides=overrides, entity_data=entity_data
        )
        payload_bytes = json.dumps(payload).encode()
        headers = {
            "Content-Type": "application/json",
            **self.sign_payload(vendor, payload_bytes),
        }

        url = target_url or self._get_target_url(vendor)
        attempt = DeliveryAttempt(
            vendor=vendor,
            event_name=event_name,
            target_url=url,
            payload=payload,
        )

        start = time.monotonic()
        try:
            with httpx.Client() as client:
                resp = client.post(url, content=payload_bytes, headers=headers, timeout=10.0)
            attempt.status_code = resp.status_code
            attempt.response_body = resp.text[:1000]
        except Exception as e:
            attempt.error = str(e)

        attempt.elapsed_ms = (time.monotonic() - start) * 1000
        self._delivery_log.append(attempt)
        return attempt

    def list_events(self, vendor: str | None = None) -> list[str]:
        """List available webhook event names.

        Args:
            vendor: Filter by vendor, or None for all.

        Returns:
            List of "vendor/event_name" strings.
        """
        results: list[str] = []
        for v, events in WEBHOOK_EVENTS.items():
            if vendor and v != vendor:
                continue
            for event_name in sorted(events.keys()):
                results.append(f"{v}/{event_name}")
        return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _deep_merge(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    """Deep merge overrides into a copy of base."""
    result: dict[str, Any] = {}
    for key, value in base.items():
        if key in overrides:
            if isinstance(value, dict) and isinstance(overrides[key], dict):
                result[key] = _deep_merge(value, overrides[key])
            else:
                result[key] = overrides[key]
        else:
            if isinstance(value, dict):
                result[key] = _deep_merge(value, {})
            elif isinstance(value, list):
                result[key] = list(value)
            else:
                result[key] = value
    # Add keys from overrides not in base
    for key, value in overrides.items():
        if key not in base:
            result[key] = value
    return result


def _set_nested(d: dict[str, Any], key: str, value: Any) -> None:
    """Set a value only if the key exists and has an empty-ish default."""
    if key in d and (d[key] == "" or d[key] == 0):
        d[key] = value
