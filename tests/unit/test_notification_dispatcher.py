"""Tests for the cycle-2 notification dispatcher (#952).

Cycle 1 added the email-shaped DSL and linker propagation. Cycle 2
(this test module) covers:

  * `[notifications]` block parsing on `dazzle.toml`.
  * `LogProvider` writes a structured log line per send.
  * `NotificationDispatcher` renders subject/body/template against the
    payload, falls back from `template:` to `message:` when the
    template isn't registered, and dispatches one entry per channel.
  * `build_dispatcher_from_manifest` constructs from `NotificationsConfig`.
  * Recipient resolution: `field(<name>)` is supported in cycle 2.

Cycle 3+ (real SMTP, trigger wiring, retry) is deferred and tracked
separately on #952.
"""

from __future__ import annotations

import logging

import pytest

from dazzle.core.ir.notifications import (
    NotificationChannel,
    NotificationRecipient,
    NotificationSpec,
    NotificationTrigger,
)
from dazzle.notifications import (
    LogProvider,
    NotificationDispatcher,
    RenderedNotification,
    build_dispatcher_from_manifest,
)


def _spec(
    *,
    name: str = "welcome_email",
    channels: list[NotificationChannel] | None = None,
    subject: str = "",
    message: str = "",
    template: str = "",
    recipient_kind: str = "",
    recipient_value: str = "",
) -> NotificationSpec:
    """Build a NotificationSpec for tests."""
    return NotificationSpec(
        name=name,
        trigger=NotificationTrigger(entity="User", event="created"),
        channels=channels or [NotificationChannel.EMAIL],
        subject=subject,
        message=message,
        template=template,
        recipients=NotificationRecipient(kind=recipient_kind, value=recipient_value),
    )


class TestLogProvider:
    def test_send_returns_true(self):
        provider = LogProvider()
        rendered = RenderedNotification(
            notification_name="x",
            recipient="alice@example.com",
            channel="email",
            subject="Hi",
            body="Hello",
        )
        assert provider.send(rendered) is True

    def test_send_logs_structured_line(self, caplog):
        provider = LogProvider()
        rendered = RenderedNotification(
            notification_name="welcome",
            recipient="alice@example.com",
            channel="email",
            subject="Welcome!",
            body="Hi Alice",
        )
        with caplog.at_level(logging.INFO, logger="dazzle.notifications"):
            provider.send(rendered)
        assert "notification.send" in caplog.text
        assert "welcome" in caplog.text
        assert "alice@example.com" in caplog.text


class TestRenderingPrecedence:
    """`template:` wins over `message:` when both are registered."""

    def test_template_wins_when_registered(self):
        dispatcher = NotificationDispatcher(
            templates={"emails/welcome.html": "Hello {{ name }} from template"}
        )
        spec = _spec(
            template="emails/welcome.html",
            message="fallback message",
            recipient_kind="field",
            recipient_value="email",
        )
        rendered = dispatcher.dispatch(spec, {"name": "Alice", "email": "alice@example.com"})
        assert rendered[0].body == "Hello Alice from template"

    def test_message_used_when_template_unregistered(self, caplog):
        """Spec sets `template:` but no source registered → fall back
        to `message:` AND log a warning so the misconfig surfaces."""
        dispatcher = NotificationDispatcher(templates={})  # empty
        spec = _spec(
            template="emails/missing.html",
            message="Inline body for {{ name }}",
            recipient_kind="field",
            recipient_value="email",
        )
        with caplog.at_level(logging.WARNING, logger="dazzle.notifications"):
            rendered = dispatcher.dispatch(spec, {"name": "Alice", "email": "alice@example.com"})
        assert rendered[0].body == "Inline body for Alice"
        assert "emails/missing.html" in caplog.text

    def test_message_used_when_no_template(self):
        dispatcher = NotificationDispatcher()
        spec = _spec(
            message="Welcome {{ name }}!",
            recipient_kind="field",
            recipient_value="email",
        )
        rendered = dispatcher.dispatch(spec, {"name": "Alice", "email": "alice@example.com"})
        assert rendered[0].body == "Welcome Alice!"


class TestSubjectRendering:
    def test_subject_renders_jinja_double_brace(self):
        dispatcher = NotificationDispatcher()
        spec = _spec(
            subject="Welcome {{ name }}",
            message="ignored",
            recipient_kind="field",
            recipient_value="email",
        )
        rendered = dispatcher.dispatch(spec, {"name": "Alice", "email": "alice@example.com"})
        assert rendered[0].subject == "Welcome Alice"

    def test_subject_missing_placeholder_keeps_token(self):
        """Missing payload keys land as `{name}` in the output rather
        than crashing — better to ship a clearly-broken email than
        nothing."""
        dispatcher = NotificationDispatcher()
        spec = _spec(
            subject="Welcome {{ missing }}",
            message="x",
            recipient_kind="field",
            recipient_value="email",
        )
        rendered = dispatcher.dispatch(spec, {"email": "alice@example.com"})
        # `_SafeDict` returns the raw `{missing}` token rather than crashing.
        assert "{missing}" in rendered[0].subject


class TestChannelDispatch:
    def test_one_render_per_channel(self):
        dispatcher = NotificationDispatcher()
        spec = _spec(
            channels=[NotificationChannel.EMAIL, NotificationChannel.IN_APP],
            subject="hi",
            message="hello",
            recipient_kind="field",
            recipient_value="email",
        )
        rendered = dispatcher.dispatch(spec, {"email": "a@b.com"})
        assert [r.channel for r in rendered] == ["email", "in_app"]

    def test_provider_failure_doesnt_abort_other_channels(self, caplog):
        """If the provider raises on one channel, the dispatcher must
        still send the remaining channels — partial-fail rather than
        all-or-nothing."""
        send_calls: list[str] = []

        class FlakyProvider:
            def send(self, notif):
                send_calls.append(notif.channel)
                if notif.channel == "email":
                    raise RuntimeError("smtp connection refused")
                return True

        dispatcher = NotificationDispatcher(provider=FlakyProvider())
        spec = _spec(
            channels=[NotificationChannel.EMAIL, NotificationChannel.IN_APP],
            message="hi",
            recipient_kind="field",
            recipient_value="email",
        )
        with caplog.at_level(logging.ERROR, logger="dazzle.notifications"):
            rendered = dispatcher.dispatch(spec, {"email": "a@b.com"})
        # Both channels were attempted
        assert send_calls == ["email", "in_app"]
        # Both rendered objects are returned even though `email` raised
        assert [r.channel for r in rendered] == ["email", "in_app"]
        # The exception was logged
        assert "smtp connection refused" in caplog.text


class TestRecipientResolution:
    def test_field_recipient_pulled_from_payload(self):
        dispatcher = NotificationDispatcher()
        spec = _spec(
            message="hi",
            recipient_kind="field",
            recipient_value="email",
        )
        rendered = dispatcher.dispatch(spec, {"email": "alice@example.com"})
        assert rendered[0].recipient == "alice@example.com"

    def test_explicit_recipient_overrides_field(self):
        dispatcher = NotificationDispatcher()
        spec = _spec(
            message="hi",
            recipient_kind="field",
            recipient_value="email",
        )
        rendered = dispatcher.dispatch(
            spec, {"email": "alice@example.com"}, recipient="override@example.com"
        )
        assert rendered[0].recipient == "override@example.com"

    def test_role_recipient_unsupported_in_cycle_2(self, caplog):
        """`role(...)` recipient kinds are deferred to cycle 4 (trigger
        pipeline). For now the dispatcher returns empty + logs."""
        dispatcher = NotificationDispatcher()
        spec = _spec(
            message="hi",
            recipient_kind="role",
            recipient_value="admin",
        )
        with caplog.at_level(logging.DEBUG, logger="dazzle.notifications"):
            rendered = dispatcher.dispatch(spec, {})
        assert rendered[0].recipient == ""

    def test_field_missing_from_payload_returns_empty(self):
        dispatcher = NotificationDispatcher()
        spec = _spec(
            message="hi",
            recipient_kind="field",
            recipient_value="email",
        )
        rendered = dispatcher.dispatch(spec, {})
        assert rendered[0].recipient == ""


class TestManifestNotificationsConfig:
    def test_defaults(self):
        from dazzle.core.manifest import NotificationsConfig

        cfg = NotificationsConfig()
        assert cfg.provider == "log"
        assert cfg.from_address == ""
        assert cfg.smtp_port == 587

    def test_log_provider_default(self, tmp_path):
        from dazzle.core.manifest import load_manifest

        toml = tmp_path / "dazzle.toml"
        toml.write_text(
            """
[project]
name = "test"
version = "0.1.0"

[modules]
paths = ["./dsl"]
"""
        )
        manifest = load_manifest(toml)
        assert manifest.notifications.provider == "log"

    def test_smtp_block_parses(self, tmp_path):
        from dazzle.core.manifest import load_manifest

        toml = tmp_path / "dazzle.toml"
        toml.write_text(
            """
[project]
name = "test"
version = "0.1.0"

[modules]
paths = ["./dsl"]

[notifications]
provider = "smtp"
from = "noreply@example.com"

[notifications.smtp]
host = "smtp.example.com"
port = 465
username = "user"
password = "secret"
"""
        )
        manifest = load_manifest(toml)
        assert manifest.notifications.provider == "smtp"
        assert manifest.notifications.from_address == "noreply@example.com"
        assert manifest.notifications.smtp_host == "smtp.example.com"
        assert manifest.notifications.smtp_port == 465
        assert manifest.notifications.smtp_username == "user"
        assert manifest.notifications.smtp_password == "secret"

    def test_invalid_provider_raises(self, tmp_path):
        from dazzle.core.manifest import load_manifest

        toml = tmp_path / "dazzle.toml"
        toml.write_text(
            """
[project]
name = "test"
version = "0.1.0"

[modules]
paths = ["./dsl"]

[notifications]
provider = "carrier_pigeon"
"""
        )
        with pytest.raises(ValueError, match="provider must be one of"):
            load_manifest(toml)


class TestBuildDispatcherFromManifest:
    def test_log_provider_returned_for_log_key(self):
        from dazzle.core.manifest import NotificationsConfig

        cfg = NotificationsConfig(provider="log", from_address="x@y.com")
        dispatcher = build_dispatcher_from_manifest(cfg)
        assert isinstance(dispatcher.provider, LogProvider)
        assert dispatcher.from_address == "x@y.com"

    def test_smtp_falls_back_to_log_with_warning(self, caplog):
        """Cycle 2 doesn't ship SmtpProvider yet — falls back to
        LogProvider with a warning so configured smtp installs still
        see something in dev."""
        from dazzle.core.manifest import NotificationsConfig

        cfg = NotificationsConfig(provider="smtp")
        with caplog.at_level(logging.WARNING, logger="dazzle.notifications"):
            dispatcher = build_dispatcher_from_manifest(cfg)
        assert isinstance(dispatcher.provider, LogProvider)
        assert "not yet implemented" in caplog.text
