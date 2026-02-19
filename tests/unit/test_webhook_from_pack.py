"""Tests for webhook event loading from pack TOML files."""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import MagicMock

from dazzle.api_kb.loader import WebhookEventSpec, _load_pack_from_toml


def _write_toml(tmp_path: Path, content: str) -> Path:
    """Write a TOML file and return its path."""
    vendor_dir = tmp_path / "testvendor"
    vendor_dir.mkdir(parents=True, exist_ok=True)
    toml_path = vendor_dir / "test_pack.toml"
    toml_path.write_text(content)
    return toml_path


def test_webhook_events_loaded_from_toml(tmp_path: Path) -> None:
    """Webhook events are parsed from pack TOML."""
    toml_path = _write_toml(
        tmp_path,
        textwrap.dedent("""\
            [pack]
            name = "test_pack"
            provider = "Test"
            category = "testing"
            version = "1.0"

            [webhooks.item_created]
            description = "Item was created"
            signing = "hmac-sha256"
            signing_header = "X-Webhook-Signature"
            webhook_path = "/webhooks/test"

            [webhooks.item_created.payload]
            type = "item_created"
            item_id = ""
        """),
    )

    pack = _load_pack_from_toml(toml_path)

    assert len(pack.webhooks) == 1
    wh = pack.webhooks[0]
    assert wh.name == "item_created"
    assert wh.description == "Item was created"
    assert wh.signing == "hmac-sha256"
    assert wh.signing_header == "X-Webhook-Signature"
    assert wh.webhook_path == "/webhooks/test"
    assert wh.payload == {"type": "item_created", "item_id": ""}


def test_webhook_without_payload(tmp_path: Path) -> None:
    """Webhook events without payload templates are loaded."""
    toml_path = _write_toml(
        tmp_path,
        textwrap.dedent("""\
            [pack]
            name = "test_pack"
            provider = "Test"
            category = "testing"
            version = "1.0"

            [webhooks.simple_event]
            description = "Simple event"
        """),
    )

    pack = _load_pack_from_toml(toml_path)

    assert len(pack.webhooks) == 1
    wh = pack.webhooks[0]
    assert wh.name == "simple_event"
    assert wh.payload == {}


def test_webhook_string_shorthand(tmp_path: Path) -> None:
    """Webhook events can be specified as simple strings."""
    toml_path = _write_toml(
        tmp_path,
        textwrap.dedent("""\
            [pack]
            name = "test_pack"
            provider = "Test"
            category = "testing"
            version = "1.0"

            [webhooks]
            simple = "A simple event"
        """),
    )

    pack = _load_pack_from_toml(toml_path)

    assert len(pack.webhooks) == 1
    assert pack.webhooks[0].name == "simple"
    assert pack.webhooks[0].description == "A simple event"


def test_sumsub_pack_has_webhook_payloads() -> None:
    """SumSub pack TOML has webhook payload templates."""
    from dazzle.api_kb.loader import load_pack, set_project_root

    set_project_root(None)
    pack = load_pack("sumsub_kyc")
    assert pack is not None

    webhook_names = {wh.name for wh in pack.webhooks}
    assert "applicant_reviewed" in webhook_names
    assert "applicant_created" in webhook_names
    assert "applicant_pending" in webhook_names

    # Check payload on applicant_reviewed
    reviewed = next(wh for wh in pack.webhooks if wh.name == "applicant_reviewed")
    assert reviewed.payload.get("type") == "applicant_reviewed"
    assert reviewed.signing == "sumsub-hmac"
    assert reviewed.signing_header == "X-Payload-Digest"
    # Clean up
    set_project_root(None)


def test_load_events_from_packs() -> None:
    """load_events_from_packs extracts payload templates."""
    from dazzle.testing.vendor_mock.webhooks import load_events_from_packs

    # Create a mock pack with webhooks
    pack = MagicMock()
    pack.name = "test_vendor"
    pack.webhooks = [
        WebhookEventSpec(
            name="event_a",
            payload={"type": "event_a", "id": ""},
        ),
        WebhookEventSpec(
            name="event_b",
            payload={},  # Empty payload — should not be included
        ),
    ]

    events = load_events_from_packs([pack])

    assert "test_vendor" in events
    assert "event_a" in events["test_vendor"]
    assert events["test_vendor"]["event_a"] == {"type": "event_a", "id": ""}
    # event_b has no payload, should not be in events
    assert "event_b" not in events["test_vendor"]


def test_load_signing_from_packs() -> None:
    """load_signing_from_packs extracts signing config."""
    from dazzle.testing.vendor_mock.webhooks import load_signing_from_packs

    pack = MagicMock()
    pack.name = "test_vendor"
    pack.webhooks = [
        WebhookEventSpec(
            name="event_a",
            signing="stripe-v1",
            signing_header="Stripe-Signature",
        ),
    ]

    signing = load_signing_from_packs([pack])

    assert "test_vendor" in signing
    assert signing["test_vendor"] == ("stripe-v1", "Stripe-Signature")


def test_dispatcher_uses_pack_events() -> None:
    """WebhookDispatcher uses pack-sourced events when available."""
    from dazzle.testing.vendor_mock.webhooks import WebhookDispatcher

    pack = MagicMock()
    pack.name = "custom_vendor"
    pack.webhooks = [
        WebhookEventSpec(
            name="custom_event",
            signing="hmac-sha256",
            signing_header="X-Webhook-Signature",
            webhook_path="/webhooks/custom",
            payload={"event": "custom_event", "data": "test"},
        ),
    ]

    dispatcher = WebhookDispatcher(packs=[pack])
    events = dispatcher.list_events("custom_vendor")

    assert "custom_vendor/custom_event" in events
