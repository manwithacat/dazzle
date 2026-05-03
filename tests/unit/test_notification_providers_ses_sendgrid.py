"""Tests for #952 cycle 6 — SesProvider + SendgridProvider.

SES tests use moto (in-process AWS mock — `pip install dazzle-dsl[aws-test]`).
SendGrid tests use a tiny stub client because the sendgrid library is
optional, and live API calls would burn quota / cost real money. The
stub mimics the relevant surface (`send(mail) → response.status_code`)
so the provider's outcome classification (transient retry vs permanent
raise) is fully exercised without a network round-trip.

This pairs with the cycle-5 retry tests — together they verify that
provider returning False routes through dispatch_async's backoff and
that exceptions classify as permanent vs transient correctly.
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
    SendgridProvider,
    SesProvider,
)

# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


_FAST_POLICY = RetryPolicy(max_attempts=3, base_delay_seconds=0.001, max_delay_seconds=0.01)


def _email_notification(channel: str = "email") -> RenderedNotification:
    return RenderedNotification(
        notification_name="welcome_email",
        recipient="ada@example.com",
        channel=channel,
        subject="Welcome",
        body="Hello Ada",
    )


def _spec_with_channel(channel: str = "email") -> Any:
    return SimpleNamespace(
        name="welcome_email",
        title=None,
        subject="Hi {{ name }}",
        message="Hello {{ name }}",
        template="",
        channels=[SimpleNamespace(value=channel)],
        recipients=SimpleNamespace(kind="field", value="email"),
    )


# ---------------------------------------------------------------------------
# SesProvider — uses moto to mock the AWS API
# ---------------------------------------------------------------------------


class TestSesProvider:
    def test_skip_non_email_channels(self):
        """SES can't deliver in_app/sms/slack — those fall through cleanly."""
        provider = SesProvider(region="us-east-1", from_address="from@example.com")
        # No client needed — the channel guard returns True before the boto3 import.
        assert provider.send(_email_notification(channel="in_app")) is True

    def test_send_via_moto_succeeds(self):
        """End-to-end happy path against an in-process SES mock."""
        boto3 = pytest.importorskip("boto3")
        moto = pytest.importorskip("moto")
        with moto.mock_aws():  # type: ignore[attr-defined]
            client = boto3.client("ses", region_name="us-east-1")
            # SES requires the source identity to be verified before send.
            client.verify_email_identity(EmailAddress="from@example.com")
            provider = SesProvider(
                region="us-east-1",
                from_address="from@example.com",
                client=client,
            )
            assert provider.send(_email_notification()) is True

    def test_throttling_returns_false_for_retry(self):
        """Throttling errors must classify as transient so dispatch_async retries."""

        class Throttling(Exception):  # name matches the transient_names set
            pass

        class _ThrottlingClient:
            def __init__(self) -> None:
                self.calls = 0

            def send_raw_email(self, **_kwargs: Any) -> Any:
                self.calls += 1
                raise Throttling("Maximum sending rate exceeded")

        provider = SesProvider(
            region="us-east-1", from_address="from@example.com", client=_ThrottlingClient()
        )
        assert provider.send(_email_notification()) is False

    def test_message_rejected_raises_for_permanent(self):
        """MessageRejected (e.g. unverified identity) is permanent — must raise
        so the dispatcher records FAILED_PERMANENT."""

        class _RejectingClient:
            def send_raw_email(self, **_kwargs: Any) -> Any:
                raise RuntimeError("Email address is not verified")

        provider = SesProvider(
            region="us-east-1", from_address="from@example.com", client=_RejectingClient()
        )
        with pytest.raises(RuntimeError, match="not verified"):
            provider.send(_email_notification())

    def test_botocore_client_error_with_throttling_code_is_transient(self):
        """ClientError carries an `Error.Code` — `Throttling` should retry."""

        class _ClientErrorClient:
            def send_raw_email(self, **_kwargs: Any) -> Any:
                exc = Exception("client error")
                exc.response = {  # type: ignore[attr-defined]
                    "Error": {"Code": "Throttling", "Message": "Rate exceeded"}
                }
                raise exc

        provider = SesProvider(
            region="us-east-1", from_address="from@example.com", client=_ClientErrorClient()
        )
        assert provider.send(_email_notification()) is False

    def test_boto3_missing_raises_clear_error(self, monkeypatch):
        """Without boto3 installed, the provider gives a clear install hint
        rather than a confusing ImportError on `import boto3`."""
        # Force the import path: client=None, then break boto3.
        import builtins

        real_import = builtins.__import__

        def _fail(name: str, *a: Any, **kw: Any) -> Any:
            if name == "boto3":
                raise ImportError("no boto3 in this env")
            return real_import(name, *a, **kw)

        monkeypatch.setattr(builtins, "__import__", _fail)
        provider = SesProvider(region="us-east-1", from_address="x@y.com")
        with pytest.raises(RuntimeError, match=r"dazzle-dsl\[aws\]"):
            provider.send(_email_notification())


# ---------------------------------------------------------------------------
# SendgridProvider — uses a stub client to avoid burning API quota
# ---------------------------------------------------------------------------


class _SendgridResponse:
    """Mimics the sendgrid library's response object."""

    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class _StubSendgridClient:
    """Replaces SendGridAPIClient — captures sends + returns canned status."""

    def __init__(self, responses: list[Any]) -> None:
        # responses can be int (status), Exception instance, or _SendgridResponse.
        self.responses = responses
        self.calls: list[Any] = []

    def send(self, mail: Any) -> Any:
        self.calls.append(mail)
        idx = len(self.calls) - 1
        outcome = self.responses[idx] if idx < len(self.responses) else self.responses[-1]
        if isinstance(outcome, Exception):
            raise outcome
        if isinstance(outcome, int):
            return _SendgridResponse(outcome)
        return outcome


class TestSendgridProvider:
    def test_skip_non_email_channels(self):
        provider = SendgridProvider(api_key="x", from_address="from@example.com")
        assert provider.send(_email_notification(channel="in_app")) is True

    def test_send_202_succeeds(self):
        """202 Accepted is the SendGrid happy-path response."""
        pytest.importorskip("sendgrid")  # need Mail helper for _build_mail_payload
        client = _StubSendgridClient([202])
        provider = SendgridProvider(api_key="key", from_address="from@example.com", client=client)
        assert provider.send(_email_notification()) is True
        assert len(client.calls) == 1

    def test_429_returns_false_for_retry(self):
        """Rate-limit response must classify as transient so dispatch_async retries."""
        pytest.importorskip("sendgrid")
        client = _StubSendgridClient([_SendgridResponse(429)])
        provider = SendgridProvider(api_key="key", from_address="from@example.com", client=client)
        assert provider.send(_email_notification()) is False

    def test_5xx_returns_false_for_retry(self):
        pytest.importorskip("sendgrid")
        client = _StubSendgridClient([_SendgridResponse(503)])
        provider = SendgridProvider(api_key="key", from_address="from@example.com", client=client)
        assert provider.send(_email_notification()) is False

    def test_4xx_other_than_429_raises_permanent(self):
        """401 unauthorized should not retry — re-raise so dispatch records permanent."""
        pytest.importorskip("sendgrid")

        class _Unauthorized(Exception):
            status_code = 401

        client = _StubSendgridClient([_Unauthorized("invalid api key")])
        provider = SendgridProvider(api_key="key", from_address="from@example.com", client=client)
        with pytest.raises(_Unauthorized):
            provider.send(_email_notification())

    def test_network_error_is_transient(self):
        pytest.importorskip("sendgrid")

        class ConnectionError(Exception):  # noqa: A001 — name matches network class
            pass

        client = _StubSendgridClient([ConnectionError("dns lookup failed")])
        provider = SendgridProvider(api_key="key", from_address="from@example.com", client=client)
        assert provider.send(_email_notification()) is False

    def test_missing_api_key_raises_clear_error(self):
        """No api_key → don't even build the client; error tells the operator
        to set it in dazzle.toml."""
        # Don't inject client — let the constructor path try to build one,
        # which checks api_key first.
        provider = SendgridProvider(api_key="", from_address="x@y.com")
        with pytest.raises(RuntimeError, match="api_key"):
            provider.send(_email_notification())

    def test_sendgrid_missing_raises_clear_error(self, monkeypatch):
        """Without sendgrid installed, the provider gives a clear install hint."""
        import builtins

        real_import = builtins.__import__

        def _fail(name: str, *a: Any, **kw: Any) -> Any:
            if name == "sendgrid":
                raise ImportError("no sendgrid in this env")
            return real_import(name, *a, **kw)

        monkeypatch.setattr(builtins, "__import__", _fail)
        provider = SendgridProvider(api_key="x", from_address="from@example.com")
        with pytest.raises(RuntimeError, match=r"dazzle-dsl\[sendgrid\]"):
            provider.send(_email_notification())


# ---------------------------------------------------------------------------
# build_dispatcher_from_manifest — provider routing
# ---------------------------------------------------------------------------


class TestManifestRouting:
    def test_ses_provider_built_with_aws_region(self):
        from dazzle.core.manifest import NotificationsConfig
        from dazzle.notifications import build_dispatcher_from_manifest

        cfg = NotificationsConfig(
            provider="ses",
            from_address="ops@example.com",
            aws_region="eu-west-2",
        )
        dispatcher = build_dispatcher_from_manifest(cfg)
        assert isinstance(dispatcher.provider, SesProvider)
        assert dispatcher.provider.region == "eu-west-2"
        assert dispatcher.provider.from_address == "ops@example.com"

    def test_sendgrid_provider_built_with_api_key(self):
        from dazzle.core.manifest import NotificationsConfig
        from dazzle.notifications import build_dispatcher_from_manifest

        cfg = NotificationsConfig(
            provider="sendgrid",
            from_address="ops@example.com",
            api_key="SG.abc123",
        )
        dispatcher = build_dispatcher_from_manifest(cfg)
        assert isinstance(dispatcher.provider, SendgridProvider)
        assert dispatcher.provider.api_key == "SG.abc123"

    def test_sendgrid_without_api_key_falls_back_to_log(self, caplog):
        """No api_key → don't crash startup; warn + degrade to LogProvider."""
        from dazzle.core.manifest import NotificationsConfig
        from dazzle.notifications import LogProvider, build_dispatcher_from_manifest

        cfg = NotificationsConfig(provider="sendgrid", api_key="")
        with caplog.at_level("WARNING"):
            dispatcher = build_dispatcher_from_manifest(cfg)
        assert isinstance(dispatcher.provider, LogProvider)
        assert "api_key" in caplog.text


# ---------------------------------------------------------------------------
# End-to-end: SES provider + dispatch_async retry loop
# ---------------------------------------------------------------------------


class TestSesDispatchAsyncRetry:
    def test_throttling_then_success_records_two_attempts(self):
        """Wire the SES provider into the dispatcher and prove the retry loop
        kicks in when the provider returns False (transient)."""

        class Throttling(Exception):
            pass

        class _FlakyClient:
            def __init__(self) -> None:
                self.calls = 0

            def send_raw_email(self, **_kwargs: Any) -> Any:
                self.calls += 1
                if self.calls == 1:
                    raise Throttling("Throttled")
                # Second attempt succeeds — boto3 returns a dict; we don't read it.
                return {"MessageId": "abc"}

        provider = SesProvider(
            region="us-east-1", from_address="from@example.com", client=_FlakyClient()
        )
        dispatcher = NotificationDispatcher(provider=provider, retry_policy=_FAST_POLICY)
        asyncio.run(
            dispatcher.dispatch_async(
                _spec_with_channel(), {"name": "Ada", "email": "ada@example.com"}
            )
        )
        record = dispatcher.deliveries[0]
        assert record.outcome == DeliveryOutcome.SENT
        assert record.attempts == 2
