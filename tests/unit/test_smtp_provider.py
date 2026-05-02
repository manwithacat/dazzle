"""Tests for `SmtpProvider` (#952 cycle 3).

Uses `unittest.mock` to stub `smtplib.SMTP` — no real network. Pins:

  * email channel sends real `EmailMessage` via `send_message`
  * non-email channels (in_app/sms/slack) skip cleanly without
    invoking smtplib
  * 5xx response → raises so dispatcher records permanent failure
  * 4xx / disconnect / timeout → returns False (transient, retryable)
  * TLS upgrade + login flow happens when configured
  * HTML body emits multipart with text/plain alternative
"""

from __future__ import annotations

import logging
import smtplib
from unittest.mock import MagicMock, patch

import pytest

from dazzle.notifications import RenderedNotification, SmtpProvider


def _email(
    *,
    channel: str = "email",
    recipient: str = "alice@example.com",
    subject: str = "Hello",
    body: str = "Plain body",
) -> RenderedNotification:
    return RenderedNotification(
        notification_name="welcome",
        recipient=recipient,
        channel=channel,
        subject=subject,
        body=body,
    )


@pytest.fixture()
def smtp_mock():
    """Patch `smtplib.SMTP` with a context-manager-friendly MagicMock."""
    with patch("smtplib.SMTP") as smtp_cls:
        instance = MagicMock()
        smtp_cls.return_value.__enter__.return_value = instance
        smtp_cls.return_value.__exit__.return_value = False
        yield smtp_cls, instance


class TestEmailChannel:
    """`SmtpProvider.send` for the email channel — happy path + variants."""

    def test_sends_message_via_smtp(self, smtp_mock):
        smtp_cls, smtp_inst = smtp_mock
        provider = SmtpProvider(
            host="smtp.example.com",
            port=587,
            username="user",
            password="secret",
            from_address="noreply@example.com",
        )

        result = provider.send(_email())

        assert result is True
        smtp_cls.assert_called_once_with("smtp.example.com", 587, timeout=30)
        smtp_inst.starttls.assert_called_once()
        smtp_inst.login.assert_called_once_with("user", "secret")
        smtp_inst.send_message.assert_called_once()

        msg = smtp_inst.send_message.call_args[0][0]
        assert msg["From"] == "noreply@example.com"
        assert msg["To"] == "alice@example.com"
        assert msg["Subject"] == "Hello"

    def test_skips_login_when_credentials_absent(self, smtp_mock):
        """Anonymous SMTP relays (in-cluster postfix etc) — no creds."""
        smtp_cls, smtp_inst = smtp_mock
        provider = SmtpProvider(host="smtp.local", from_address="no@reply.com")

        provider.send(_email())

        smtp_inst.login.assert_not_called()
        smtp_inst.send_message.assert_called_once()

    def test_skips_starttls_when_disabled(self, smtp_mock):
        smtp_cls, smtp_inst = smtp_mock
        provider = SmtpProvider(host="smtp.local", use_tls=False)

        provider.send(_email())

        smtp_inst.starttls.assert_not_called()
        smtp_inst.send_message.assert_called_once()

    def test_default_from_when_address_missing(self, smtp_mock):
        """Empty `from_address` should still send — falls back to a
        placeholder rather than producing a malformed envelope."""
        smtp_cls, smtp_inst = smtp_mock
        provider = SmtpProvider(host="smtp.local")

        provider.send(_email())

        msg = smtp_inst.send_message.call_args[0][0]
        assert msg["From"] == "noreply@localhost"


class TestNonEmailChannels:
    """SmtpProvider can't deliver in_app/sms/slack — those paths must
    not invoke smtplib (avoids confusing 'sending email to @username'
    log lines for projects with mixed-channel specs)."""

    def test_in_app_channel_skipped(self, smtp_mock, caplog):
        smtp_cls, _ = smtp_mock
        provider = SmtpProvider(host="smtp.local")

        with caplog.at_level(logging.INFO, logger="dazzle.notifications"):
            result = provider.send(_email(channel="in_app", recipient="alice"))

        assert result is True
        smtp_cls.assert_not_called()
        assert "skipping non-email channel" in caplog.text

    def test_empty_recipient_skipped(self, smtp_mock, caplog):
        smtp_cls, _ = smtp_mock
        provider = SmtpProvider(host="smtp.local")

        with caplog.at_level(logging.WARNING, logger="dazzle.notifications"):
            result = provider.send(_email(recipient=""))

        assert result is True
        smtp_cls.assert_not_called()
        assert "no recipient" in caplog.text


class TestFailureSemantics:
    """Match the NotificationProvider protocol's transient/permanent split."""

    def test_disconnect_returns_false(self, smtp_mock, caplog):
        _, smtp_inst = smtp_mock
        smtp_inst.send_message.side_effect = smtplib.SMTPServerDisconnected("conn lost")
        provider = SmtpProvider(host="smtp.local")

        with caplog.at_level(logging.WARNING, logger="dazzle.notifications"):
            result = provider.send(_email())

        assert result is False
        assert "transient error" in caplog.text

    def test_timeout_returns_false(self, smtp_mock):
        _, smtp_inst = smtp_mock
        smtp_inst.send_message.side_effect = TimeoutError("smtp slow")
        provider = SmtpProvider(host="smtp.local")

        assert provider.send(_email()) is False

    def test_connection_refused_returns_false(self, smtp_mock):
        _, smtp_inst = smtp_mock
        smtp_inst.send_message.side_effect = OSError("connection refused")
        provider = SmtpProvider(host="smtp.local")

        assert provider.send(_email()) is False

    def test_4xx_response_returns_false(self, smtp_mock):
        """4xx is a soft-fail per RFC 5321 — try again later."""
        _, smtp_inst = smtp_mock
        smtp_inst.send_message.side_effect = smtplib.SMTPResponseException(
            451, b"temporary local problem"
        )
        provider = SmtpProvider(host="smtp.local")

        assert provider.send(_email()) is False

    def test_5xx_response_raises(self, smtp_mock):
        """5xx is permanent — re-raise so dispatcher logs the audit
        entry and stops retrying."""
        _, smtp_inst = smtp_mock
        smtp_inst.send_message.side_effect = smtplib.SMTPResponseException(
            550, b"mailbox unavailable"
        )
        provider = SmtpProvider(host="smtp.local")

        with pytest.raises(smtplib.SMTPResponseException) as exc_info:
            provider.send(_email())
        assert exc_info.value.smtp_code == 550


class TestHtmlBody:
    """HTML bodies emit multipart with text/plain alternative."""

    def test_html_body_creates_multipart(self, smtp_mock):
        _, smtp_inst = smtp_mock
        provider = SmtpProvider(host="smtp.local")

        provider.send(_email(body="<p>Hello <b>Alice</b></p>"))

        msg = smtp_inst.send_message.call_args[0][0]
        # `EmailMessage.is_multipart()` flips to True when an HTML
        # alternative is added.
        assert msg.is_multipart()
        # Plain-text part is the stripped HTML
        plain_part = next(p for p in msg.walk() if p.get_content_type() == "text/plain")
        assert "Hello Alice" in plain_part.get_content()
        # HTML part preserved
        html_part = next(p for p in msg.walk() if p.get_content_type() == "text/html")
        assert "<b>Alice</b>" in html_part.get_content()

    def test_plain_body_stays_single_part(self, smtp_mock):
        _, smtp_inst = smtp_mock
        provider = SmtpProvider(host="smtp.local")

        provider.send(_email(body="Just plain text"))

        msg = smtp_inst.send_message.call_args[0][0]
        assert not msg.is_multipart()
        assert msg.get_content_type() == "text/plain"
