"""Unit tests for SES integration: detector, adapter, and webhooks."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dazzle_back.channels.adapters.base import SendStatus
from dazzle_back.channels.detection import DetectionResult, ProviderStatus
from dazzle_back.channels.outbox import OutboxMessage
from dazzle_back.channels.ses_webhooks import (
    _handle_bounce,
    _handle_complaint,
    _handle_delivery,
    handle_sns_notification,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_detection_result(**overrides: Any) -> DetectionResult:
    """Build a DetectionResult for SES with sensible defaults."""
    defaults: dict[str, Any] = {
        "provider_name": "ses",
        "status": ProviderStatus.AVAILABLE,
        "connection_url": None,
        "api_url": "https://email.eu-west-1.amazonaws.com",
        "management_url": "https://console.aws.amazon.com/ses/",
        "detection_method": "explicit",
        "metadata": {
            "region": "eu-west-1",
            "from_address": "noreply@example.com",
        },
    }
    defaults.update(overrides)
    return DetectionResult(**defaults)


def _make_outbox_message(**overrides: Any) -> OutboxMessage:
    """Build an OutboxMessage with sensible email defaults."""
    defaults: dict[str, Any] = {
        "id": "msg-001",
        "channel_name": "notifications",
        "operation_name": "send_welcome",
        "message_type": "welcome_email",
        "payload": {
            "to": "user@example.com",
            "from": "noreply@example.com",
            "subject": "Welcome!",
            "body": "Hello, welcome aboard.",
            "html_body": "<p>Hello, welcome aboard.</p>",
        },
        "recipient": "user@example.com",
    }
    defaults.update(overrides)
    return OutboxMessage(**defaults)


@pytest.fixture
def ses_detection_result() -> DetectionResult:
    return _make_detection_result()


@pytest.fixture
def outbox_message() -> OutboxMessage:
    return _make_outbox_message()


# ---------------------------------------------------------------------------
# Mock helpers for AWS imports
# ---------------------------------------------------------------------------


def _fake_aws_config(
    region: str = "eu-west-1",
    access_key_id: str | None = "AKIATEST",
    secret_access_key: str | None = "secret",
) -> MagicMock:
    """Return a mock AWSConfig."""
    cfg = MagicMock()
    cfg.region = region
    cfg.access_key_id = access_key_id
    cfg.secret_access_key = secret_access_key
    cfg.to_boto3_kwargs.return_value = {
        "region_name": region,
        "aws_access_key_id": access_key_id,
        "aws_secret_access_key": secret_access_key,
    }
    return cfg


# ===================================================================
# SESDetector tests
# ===================================================================


class TestSESDetector:
    """Tests for SESDetector.detect()."""

    @pytest.mark.asyncio
    async def test_detect_returns_none_when_no_env_vars(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """detect() returns None when no SES-related env vars are set."""
        monkeypatch.delenv("DAZZLE_EMAIL_PROVIDER", raising=False)
        monkeypatch.delenv("AWS_SES_ENABLED", raising=False)
        monkeypatch.delenv("DAZZLE_SES_FROM_ADDRESS", raising=False)

        from dazzle_back.channels.providers.email import SESDetector

        detector = SESDetector()
        result = await detector.detect()
        assert result is None

    @pytest.mark.asyncio
    async def test_detect_explicit_provider_ses(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """detect() returns result when DAZZLE_EMAIL_PROVIDER=ses."""
        monkeypatch.setenv("DAZZLE_EMAIL_PROVIDER", "ses")
        monkeypatch.delenv("DAZZLE_SES_REGION", raising=False)
        monkeypatch.delenv("DAZZLE_SES_FROM_ADDRESS", raising=False)
        monkeypatch.delenv("DAZZLE_SES_CONFIGURATION_SET", raising=False)

        fake_cfg = _fake_aws_config()

        with (
            patch(
                "dazzle_back.channels.providers.email.get_env_var",
                side_effect=lambda name, default=None: {
                    "DAZZLE_EMAIL_PROVIDER": "ses",
                    "DAZZLE_SES_REGION": None,
                    "DAZZLE_SES_FROM_ADDRESS": default,
                    "DAZZLE_SES_CONFIGURATION_SET": None,
                }.get(name, default),
            ),
            patch(
                "dazzle_back.runtime.aws_config.get_aws_config",
                return_value=fake_cfg,
            ),
        ):
            from dazzle_back.channels.providers.email import SESDetector

            detector = SESDetector()
            result = await detector.detect()

        assert result is not None
        assert result.provider_name == "ses"
        assert result.status == ProviderStatus.AVAILABLE
        assert result.detection_method == "explicit"

    @pytest.mark.asyncio
    async def test_detect_aws_ses_enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """detect() returns result when AWS_SES_ENABLED=true."""
        fake_cfg = _fake_aws_config()

        with (
            patch(
                "dazzle_back.channels.providers.email.get_env_var",
                side_effect=lambda name, default=None: {
                    "DAZZLE_EMAIL_PROVIDER": None,
                    "AWS_SES_ENABLED": "true",
                    "DAZZLE_SES_REGION": None,
                    "DAZZLE_SES_FROM_ADDRESS": default,
                    "DAZZLE_SES_CONFIGURATION_SET": None,
                }.get(name, default),
            ),
            patch(
                "dazzle_back.runtime.aws_config.get_aws_config",
                return_value=fake_cfg,
            ),
        ):
            from dazzle_back.channels.providers.email import SESDetector

            detector = SESDetector()
            result = await detector.detect()

        assert result is not None
        assert result.provider_name == "ses"
        assert result.detection_method == "env"

    @pytest.mark.asyncio
    async def test_detect_from_address_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """detect() returns result when DAZZLE_SES_FROM_ADDRESS is set."""
        fake_cfg = _fake_aws_config()

        with (
            patch(
                "dazzle_back.channels.providers.email.get_env_var",
                side_effect=lambda name, default=None: {
                    "DAZZLE_EMAIL_PROVIDER": None,
                    "AWS_SES_ENABLED": "",
                    "DAZZLE_SES_FROM_ADDRESS": "hello@myapp.com",
                    "DAZZLE_SES_REGION": None,
                    "DAZZLE_SES_CONFIGURATION_SET": None,
                }.get(name, default),
            ),
            patch(
                "dazzle_back.runtime.aws_config.get_aws_config",
                return_value=fake_cfg,
            ),
        ):
            from dazzle_back.channels.providers.email import SESDetector

            detector = SESDetector()
            result = await detector.detect()

        assert result is not None
        assert result.metadata["from_address"] == "hello@myapp.com"
        assert result.detection_method == "env"

    @pytest.mark.asyncio
    async def test_metadata_includes_region_and_from_address(self) -> None:
        """Detection result metadata includes region and from_address."""
        fake_cfg = _fake_aws_config(region="ap-southeast-1")

        with (
            patch(
                "dazzle_back.channels.providers.email.get_env_var",
                side_effect=lambda name, default=None: {
                    "DAZZLE_EMAIL_PROVIDER": "ses",
                    "DAZZLE_SES_REGION": None,
                    "DAZZLE_SES_FROM_ADDRESS": "ops@myapp.com",
                    "DAZZLE_SES_CONFIGURATION_SET": None,
                }.get(name, default),
            ),
            patch(
                "dazzle_back.runtime.aws_config.get_aws_config",
                return_value=fake_cfg,
            ),
        ):
            from dazzle_back.channels.providers.email import SESDetector

            detector = SESDetector()
            result = await detector.detect()

        assert result is not None
        assert result.metadata["region"] == "ap-southeast-1"
        assert result.metadata["from_address"] == "ops@myapp.com"
        assert result.api_url == "https://email.ap-southeast-1.amazonaws.com"

    @pytest.mark.asyncio
    async def test_configuration_set_in_metadata(self) -> None:
        """DAZZLE_SES_CONFIGURATION_SET is included in metadata when set."""
        fake_cfg = _fake_aws_config()

        with (
            patch(
                "dazzle_back.channels.providers.email.get_env_var",
                side_effect=lambda name, default=None: {
                    "DAZZLE_EMAIL_PROVIDER": "ses",
                    "DAZZLE_SES_REGION": None,
                    "DAZZLE_SES_FROM_ADDRESS": default,
                    "DAZZLE_SES_CONFIGURATION_SET": "my-tracking-set",
                }.get(name, default),
            ),
            patch(
                "dazzle_back.runtime.aws_config.get_aws_config",
                return_value=fake_cfg,
            ),
        ):
            from dazzle_back.channels.providers.email import SESDetector

            detector = SESDetector()
            result = await detector.detect()

        assert result is not None
        assert result.metadata["configuration_set"] == "my-tracking-set"

    @pytest.mark.asyncio
    async def test_ses_region_overrides_default(self) -> None:
        """DAZZLE_SES_REGION overrides the default AWS region."""
        fake_cfg = _fake_aws_config(region="us-east-1")

        with (
            patch(
                "dazzle_back.channels.providers.email.get_env_var",
                side_effect=lambda name, default=None: {
                    "DAZZLE_EMAIL_PROVIDER": "ses",
                    "DAZZLE_SES_REGION": "eu-central-1",
                    "DAZZLE_SES_FROM_ADDRESS": default,
                    "DAZZLE_SES_CONFIGURATION_SET": None,
                }.get(name, default),
            ),
            patch(
                "dazzle_back.runtime.aws_config.get_aws_config",
                return_value=fake_cfg,
            ),
        ):
            from dazzle_back.channels.providers.email import SESDetector

            detector = SESDetector()
            result = await detector.detect()

        assert result is not None
        assert result.metadata["region"] == "eu-central-1"
        assert result.api_url == "https://email.eu-central-1.amazonaws.com"

    @pytest.mark.asyncio
    async def test_degraded_when_no_credentials(self) -> None:
        """Result is DEGRADED when AWS credentials are not configured."""
        fake_cfg = _fake_aws_config(access_key_id=None)

        with (
            patch(
                "dazzle_back.channels.providers.email.get_env_var",
                side_effect=lambda name, default=None: {
                    "DAZZLE_EMAIL_PROVIDER": "ses",
                    "DAZZLE_SES_REGION": None,
                    "DAZZLE_SES_FROM_ADDRESS": default,
                    "DAZZLE_SES_CONFIGURATION_SET": None,
                }.get(name, default),
            ),
            patch(
                "dazzle_back.runtime.aws_config.get_aws_config",
                return_value=fake_cfg,
            ),
        ):
            from dazzle_back.channels.providers.email import SESDetector

            detector = SESDetector()
            result = await detector.detect()

        assert result is not None
        assert result.status == ProviderStatus.DEGRADED
        assert result.error is not None
        assert "credentials" in result.error.lower()


# ===================================================================
# SESAdapter tests
# ===================================================================


class TestSESAdapter:
    """Tests for SESAdapter."""

    def test_constructor_parses_metadata(self, ses_detection_result: DetectionResult) -> None:
        """Constructor reads from_address, config_set, and region from metadata."""
        dr = _make_detection_result(
            metadata={
                "region": "ap-south-1",
                "from_address": "test@myapp.com",
                "configuration_set": "tracking-set",
            }
        )
        from dazzle_back.channels.adapters.email import SESAdapter

        adapter = SESAdapter(dr)

        assert adapter._from_address == "test@myapp.com"
        assert adapter._config_set == "tracking-set"
        assert adapter._ses_region == "ap-south-1"

    def test_constructor_defaults(self) -> None:
        """Constructor falls back to defaults when metadata is sparse."""
        dr = _make_detection_result(metadata={})
        from dazzle_back.channels.adapters.email import SESAdapter

        adapter = SESAdapter(dr)

        assert adapter._from_address == "noreply@example.com"
        assert adapter._config_set is None
        assert adapter._ses_region == "us-east-1"

    @pytest.mark.asyncio
    async def test_send_success(
        self, ses_detection_result: DetectionResult, outbox_message: OutboxMessage
    ) -> None:
        """send() returns SUCCESS with message_id on success."""
        mock_ses_client = AsyncMock()
        mock_ses_client.send_email = AsyncMock(return_value={"MessageId": "ses-msg-12345"})
        mock_ses_client.__aenter__ = AsyncMock(return_value=mock_ses_client)
        mock_ses_client.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.client.return_value = mock_ses_client

        with (
            patch(
                "dazzle_back.runtime.aws_config.get_aioboto3_session",
                return_value=mock_session,
            ),
            patch(
                "dazzle_back.runtime.aws_config.get_aws_config",
                return_value=_fake_aws_config(),
            ),
        ):
            from dazzle_back.channels.adapters.email import SESAdapter

            adapter = SESAdapter(ses_detection_result)
            result = await adapter.send(outbox_message)

        assert result.status == SendStatus.SUCCESS
        assert result.message_id == "ses-msg-12345"
        assert result.provider_response is not None
        assert result.provider_response["ses_message_id"] == "ses-msg-12345"
        assert result.latency_ms is not None
        assert result.latency_ms >= 0

        # Verify send_email was called with the right structure
        mock_ses_client.send_email.assert_awaited_once()
        call_kwargs = mock_ses_client.send_email.call_args.kwargs
        assert call_kwargs["FromEmailAddress"] == "noreply@example.com"
        assert call_kwargs["Destination"]["ToAddresses"] == ["user@example.com"]
        assert call_kwargs["Content"]["Simple"]["Subject"]["Data"] == "Welcome!"

    @pytest.mark.asyncio
    async def test_send_includes_cc_bcc_reply_to(
        self, ses_detection_result: DetectionResult
    ) -> None:
        """send() passes cc, bcc, and reply_to to SES when present."""
        msg = _make_outbox_message(
            payload={
                "to": "user@example.com",
                "from": "noreply@example.com",
                "subject": "Test",
                "body": "body",
                "cc": ["cc1@example.com"],
                "bcc": ["bcc1@example.com"],
                "reply_to": "support@example.com",
            }
        )

        mock_ses_client = AsyncMock()
        mock_ses_client.send_email = AsyncMock(return_value={"MessageId": "ses-cc-msg"})
        mock_ses_client.__aenter__ = AsyncMock(return_value=mock_ses_client)
        mock_ses_client.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.client.return_value = mock_ses_client

        with (
            patch(
                "dazzle_back.runtime.aws_config.get_aioboto3_session",
                return_value=mock_session,
            ),
            patch(
                "dazzle_back.runtime.aws_config.get_aws_config",
                return_value=_fake_aws_config(),
            ),
        ):
            from dazzle_back.channels.adapters.email import SESAdapter

            adapter = SESAdapter(ses_detection_result)
            result = await adapter.send(msg)

        assert result.status == SendStatus.SUCCESS
        call_kwargs = mock_ses_client.send_email.call_args.kwargs
        assert call_kwargs["Destination"]["CcAddresses"] == ["cc1@example.com"]
        assert call_kwargs["Destination"]["BccAddresses"] == ["bcc1@example.com"]
        assert call_kwargs["ReplyToAddresses"] == ["support@example.com"]

    @pytest.mark.asyncio
    async def test_send_includes_configuration_set(self, outbox_message: OutboxMessage) -> None:
        """send() passes ConfigurationSetName when adapter has one."""
        dr = _make_detection_result(
            metadata={
                "region": "eu-west-1",
                "from_address": "noreply@example.com",
                "configuration_set": "my-config-set",
            }
        )

        mock_ses_client = AsyncMock()
        mock_ses_client.send_email = AsyncMock(return_value={"MessageId": "ses-cs-msg"})
        mock_ses_client.__aenter__ = AsyncMock(return_value=mock_ses_client)
        mock_ses_client.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.client.return_value = mock_ses_client

        with (
            patch(
                "dazzle_back.runtime.aws_config.get_aioboto3_session",
                return_value=mock_session,
            ),
            patch(
                "dazzle_back.runtime.aws_config.get_aws_config",
                return_value=_fake_aws_config(),
            ),
        ):
            from dazzle_back.channels.adapters.email import SESAdapter

            adapter = SESAdapter(dr)
            result = await adapter.send(outbox_message)

        assert result.status == SendStatus.SUCCESS
        call_kwargs = mock_ses_client.send_email.call_args.kwargs
        assert call_kwargs["ConfigurationSetName"] == "my-config-set"

    @pytest.mark.asyncio
    async def test_send_returns_failed_on_error(
        self, ses_detection_result: DetectionResult, outbox_message: OutboxMessage
    ) -> None:
        """send() returns FAILED on generic SES error."""
        mock_ses_client = AsyncMock()
        mock_ses_client.send_email = AsyncMock(
            side_effect=Exception("MessageRejected: Email address not verified")
        )
        mock_ses_client.__aenter__ = AsyncMock(return_value=mock_ses_client)
        mock_ses_client.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.client.return_value = mock_ses_client

        with (
            patch(
                "dazzle_back.runtime.aws_config.get_aioboto3_session",
                return_value=mock_session,
            ),
            patch(
                "dazzle_back.runtime.aws_config.get_aws_config",
                return_value=_fake_aws_config(),
            ),
        ):
            from dazzle_back.channels.adapters.email import SESAdapter

            adapter = SESAdapter(ses_detection_result)
            result = await adapter.send(outbox_message)

        assert result.status == SendStatus.FAILED
        assert result.error is not None
        assert "MessageRejected" in result.error

    @pytest.mark.asyncio
    async def test_send_returns_rate_limited_on_throttling(
        self, ses_detection_result: DetectionResult, outbox_message: OutboxMessage
    ) -> None:
        """send() returns RATE_LIMITED on throttling error."""
        mock_ses_client = AsyncMock()
        mock_ses_client.send_email = AsyncMock(side_effect=Exception("Throttling: Rate exceeded"))
        mock_ses_client.__aenter__ = AsyncMock(return_value=mock_ses_client)
        mock_ses_client.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.client.return_value = mock_ses_client

        with (
            patch(
                "dazzle_back.runtime.aws_config.get_aioboto3_session",
                return_value=mock_session,
            ),
            patch(
                "dazzle_back.runtime.aws_config.get_aws_config",
                return_value=_fake_aws_config(),
            ),
        ):
            from dazzle_back.channels.adapters.email import SESAdapter

            adapter = SESAdapter(ses_detection_result)
            result = await adapter.send(outbox_message)

        assert result.status == SendStatus.RATE_LIMITED
        assert result.error is not None
        assert "Throttling" in result.error

    @pytest.mark.asyncio
    async def test_send_returns_rate_limited_on_too_many_requests(
        self, ses_detection_result: DetectionResult, outbox_message: OutboxMessage
    ) -> None:
        """send() returns RATE_LIMITED on TooManyRequests error."""
        mock_ses_client = AsyncMock()
        mock_ses_client.send_email = AsyncMock(side_effect=Exception("TooManyRequests: Slow down"))
        mock_ses_client.__aenter__ = AsyncMock(return_value=mock_ses_client)
        mock_ses_client.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.client.return_value = mock_ses_client

        with (
            patch(
                "dazzle_back.runtime.aws_config.get_aioboto3_session",
                return_value=mock_session,
            ),
            patch(
                "dazzle_back.runtime.aws_config.get_aws_config",
                return_value=_fake_aws_config(),
            ),
        ):
            from dazzle_back.channels.adapters.email import SESAdapter

            adapter = SESAdapter(ses_detection_result)
            result = await adapter.send(outbox_message)

        assert result.status == SendStatus.RATE_LIMITED

    @pytest.mark.asyncio
    async def test_health_check_returns_true(self, ses_detection_result: DetectionResult) -> None:
        """health_check() returns True when SES is reachable and sending enabled."""
        mock_ses_client = AsyncMock()
        mock_ses_client.get_account = AsyncMock(return_value={"SendingEnabled": True})
        mock_ses_client.__aenter__ = AsyncMock(return_value=mock_ses_client)
        mock_ses_client.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.client.return_value = mock_ses_client

        with (
            patch(
                "dazzle_back.runtime.aws_config.get_aioboto3_session",
                return_value=mock_session,
            ),
            patch(
                "dazzle_back.runtime.aws_config.get_aws_config",
                return_value=_fake_aws_config(),
            ),
        ):
            from dazzle_back.channels.adapters.email import SESAdapter

            adapter = SESAdapter(ses_detection_result)
            healthy = await adapter.health_check()

        assert healthy is True
        mock_ses_client.get_account.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_health_check_returns_false_on_error(
        self, ses_detection_result: DetectionResult
    ) -> None:
        """health_check() returns False when SES raises an exception."""
        mock_ses_client = AsyncMock()
        mock_ses_client.get_account = AsyncMock(side_effect=Exception("AccessDenied"))
        mock_ses_client.__aenter__ = AsyncMock(return_value=mock_ses_client)
        mock_ses_client.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.client.return_value = mock_ses_client

        with (
            patch(
                "dazzle_back.runtime.aws_config.get_aioboto3_session",
                return_value=mock_session,
            ),
            patch(
                "dazzle_back.runtime.aws_config.get_aws_config",
                return_value=_fake_aws_config(),
            ),
        ):
            from dazzle_back.channels.adapters.email import SESAdapter

            adapter = SESAdapter(ses_detection_result)
            healthy = await adapter.health_check()

        assert healthy is False

    @pytest.mark.asyncio
    async def test_health_check_sending_disabled(
        self, ses_detection_result: DetectionResult
    ) -> None:
        """health_check() returns False when SendingEnabled is False."""
        mock_ses_client = AsyncMock()
        mock_ses_client.get_account = AsyncMock(return_value={"SendingEnabled": False})
        mock_ses_client.__aenter__ = AsyncMock(return_value=mock_ses_client)
        mock_ses_client.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.client.return_value = mock_ses_client

        with (
            patch(
                "dazzle_back.runtime.aws_config.get_aioboto3_session",
                return_value=mock_session,
            ),
            patch(
                "dazzle_back.runtime.aws_config.get_aws_config",
                return_value=_fake_aws_config(),
            ),
        ):
            from dazzle_back.channels.adapters.email import SESAdapter

            adapter = SESAdapter(ses_detection_result)
            healthy = await adapter.health_check()

        assert healthy is False


# ===================================================================
# SES Webhooks tests (handle_sns_notification)
# ===================================================================


class TestSESWebhooks:
    """Tests for SES webhook / SNS notification handling."""

    @pytest.mark.asyncio
    async def test_subscription_confirmation_auto_confirms(self) -> None:
        """SubscriptionConfirmation messages trigger auto-confirm via urllib."""
        sns_message = {
            "Type": "SubscriptionConfirmation",
            "TopicArn": "arn:aws:sns:us-east-1:123456789:ses-bounces",
            "SubscribeURL": "https://sns.us-east-1.amazonaws.com/?Action=ConfirmSubscription&Token=abc",
        }
        body = json.dumps(sns_message).encode()

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
            result = await handle_sns_notification(body)

        assert result["event_type"] == "subscription_confirmation"
        assert result["confirmed"] is True
        mock_urlopen.assert_called_once()

    @pytest.mark.asyncio
    async def test_subscription_confirmation_failure(self) -> None:
        """SubscriptionConfirmation returns confirmed=False on HTTP error."""
        sns_message = {
            "Type": "SubscriptionConfirmation",
            "TopicArn": "arn:aws:sns:us-east-1:123456789:ses-bounces",
            "SubscribeURL": "https://sns.us-east-1.amazonaws.com/?Action=ConfirmSubscription&Token=abc",
        }
        body = json.dumps(sns_message).encode()

        with patch("urllib.request.urlopen", side_effect=Exception("Network error")):
            result = await handle_sns_notification(body)

        assert result["event_type"] == "subscription_confirmation"
        assert result["confirmed"] is False

    @pytest.mark.asyncio
    async def test_bounce_notification_parsed(self) -> None:
        """Bounce notification is parsed with correct fields."""
        ses_event = {
            "notificationType": "Bounce",
            "bounce": {
                "bounceType": "Permanent",
                "bounceSubType": "General",
                "bouncedRecipients": [
                    {"emailAddress": "bad@example.com"},
                    {"emailAddress": "invalid@example.com"},
                ],
                "timestamp": "2026-02-19T10:00:00.000Z",
            },
            "mail": {
                "messageId": "ses-msg-bounce-001",
            },
        }
        sns_message = {
            "Type": "Notification",
            "Message": json.dumps(ses_event),
        }
        body = json.dumps(sns_message).encode()

        result = await handle_sns_notification(body)

        assert result["event_type"] == "bounce"
        assert result["bounce_type"] == "Permanent"
        assert result["bounce_sub_type"] == "General"
        assert result["recipients"] == ["bad@example.com", "invalid@example.com"]
        assert result["message_id"] == "ses-msg-bounce-001"
        assert result["timestamp"] == "2026-02-19T10:00:00.000Z"

    @pytest.mark.asyncio
    async def test_complaint_notification_parsed(self) -> None:
        """Complaint notification is parsed with correct fields."""
        ses_event = {
            "notificationType": "Complaint",
            "complaint": {
                "complaintFeedbackType": "abuse",
                "complainedRecipients": [
                    {"emailAddress": "angry@example.com"},
                ],
                "timestamp": "2026-02-19T11:00:00.000Z",
            },
            "mail": {
                "messageId": "ses-msg-complaint-001",
            },
        }
        sns_message = {
            "Type": "Notification",
            "Message": json.dumps(ses_event),
        }
        body = json.dumps(sns_message).encode()

        result = await handle_sns_notification(body)

        assert result["event_type"] == "complaint"
        assert result["complaint_type"] == "abuse"
        assert result["recipients"] == ["angry@example.com"]
        assert result["message_id"] == "ses-msg-complaint-001"
        assert result["timestamp"] == "2026-02-19T11:00:00.000Z"

    @pytest.mark.asyncio
    async def test_delivery_notification_parsed(self) -> None:
        """Delivery notification is parsed with correct fields."""
        ses_event = {
            "notificationType": "Delivery",
            "delivery": {
                "recipients": ["success@example.com"],
                "timestamp": "2026-02-19T12:00:00.000Z",
                "processingTimeMillis": 450,
            },
            "mail": {
                "messageId": "ses-msg-delivery-001",
            },
        }
        sns_message = {
            "Type": "Notification",
            "Message": json.dumps(ses_event),
        }
        body = json.dumps(sns_message).encode()

        result = await handle_sns_notification(body)

        assert result["event_type"] == "delivery"
        assert result["recipients"] == ["success@example.com"]
        assert result["message_id"] == "ses-msg-delivery-001"
        assert result["timestamp"] == "2026-02-19T12:00:00.000Z"
        assert result["processing_time_ms"] == 450

    @pytest.mark.asyncio
    async def test_unknown_notification_type(self) -> None:
        """Unknown notification types are handled gracefully."""
        ses_event = {
            "notificationType": "NewFeatureEvent",
            "mail": {"messageId": "ses-msg-unknown-001"},
        }
        sns_message = {
            "Type": "Notification",
            "Message": json.dumps(ses_event),
        }
        body = json.dumps(sns_message).encode()

        result = await handle_sns_notification(body)

        assert result["event_type"] == "unknown"
        assert result["notification_type"] == "newfeatureevent"

    @pytest.mark.asyncio
    async def test_unknown_sns_message_type_ignored(self) -> None:
        """Non-Notification, non-SubscriptionConfirmation SNS messages are ignored."""
        sns_message = {
            "Type": "UnsubscribeConfirmation",
            "TopicArn": "arn:aws:sns:us-east-1:123456789:ses-bounces",
        }
        body = json.dumps(sns_message).encode()

        result = await handle_sns_notification(body)

        assert result["event_type"] == "ignored"
        assert result["message_type"] == "UnsubscribeConfirmation"

    @pytest.mark.asyncio
    async def test_malformed_ses_event_returns_parse_error(self) -> None:
        """Notification with unparseable Message returns parse_error."""
        sns_message = {
            "Type": "Notification",
            "Message": "this is not json",
        }
        body = json.dumps(sns_message).encode()

        result = await handle_sns_notification(body)

        assert result["event_type"] == "parse_error"
        assert "error" in result

    def test_handle_bounce_direct(self) -> None:
        """_handle_bounce returns expected structure."""
        ses_event = {
            "bounce": {
                "bounceType": "Transient",
                "bounceSubType": "MailboxFull",
                "bouncedRecipients": [{"emailAddress": "full@example.com"}],
                "timestamp": "2026-02-19T10:00:00Z",
            },
            "mail": {"messageId": "msg-123"},
        }
        result = _handle_bounce(ses_event)

        assert result["event_type"] == "bounce"
        assert result["bounce_type"] == "Transient"
        assert result["bounce_sub_type"] == "MailboxFull"
        assert result["recipients"] == ["full@example.com"]
        assert result["message_id"] == "msg-123"

    def test_handle_complaint_direct(self) -> None:
        """_handle_complaint returns expected structure."""
        ses_event = {
            "complaint": {
                "complaintFeedbackType": "not-spam",
                "complainedRecipients": [{"emailAddress": "user@example.com"}],
                "timestamp": "2026-02-19T11:00:00Z",
            },
            "mail": {"messageId": "msg-456"},
        }
        result = _handle_complaint(ses_event)

        assert result["event_type"] == "complaint"
        assert result["complaint_type"] == "not-spam"
        assert result["recipients"] == ["user@example.com"]

    def test_handle_delivery_direct(self) -> None:
        """_handle_delivery returns expected structure."""
        ses_event = {
            "delivery": {
                "recipients": ["ok@example.com", "ok2@example.com"],
                "timestamp": "2026-02-19T12:00:00Z",
                "processingTimeMillis": 200,
            },
            "mail": {"messageId": "msg-789"},
        }
        result = _handle_delivery(ses_event)

        assert result["event_type"] == "delivery"
        assert result["recipients"] == ["ok@example.com", "ok2@example.com"]
        assert result["processing_time_ms"] == 200

    @pytest.mark.asyncio
    async def test_subscription_confirmation_missing_url(self) -> None:
        """SubscriptionConfirmation with missing SubscribeURL returns confirmed=False."""
        sns_message = {
            "Type": "SubscriptionConfirmation",
            "TopicArn": "arn:aws:sns:us-east-1:123456789:ses-bounces",
            # No SubscribeURL
        }
        body = json.dumps(sns_message).encode()

        result = await handle_sns_notification(body)

        assert result["event_type"] == "subscription_confirmation"
        assert result["confirmed"] is False
