"""Notification dispatch primitive (#952 cycle 2).

Cycle 1 added the email-shaped DSL surface (``subject:`` / ``template:``
on the existing ``notification`` block) and the linker propagation that
lands ``NotificationSpec`` in ``AppSpec``. Cycle 2 (this module) adds:

  * ``NotificationProvider`` protocol — the abstraction every adapter
    implements.
  * ``LogProvider`` — default adapter; writes a structured log line per
    send. Useful for dev / CI where SMTP is overkill.
  * ``NotificationDispatcher`` — coordinates spec lookup → render →
    provider.send. Renders ``subject``/``message``/``template`` against
    the trigger payload.
  * ``build_dispatcher_from_manifest()`` — constructs a dispatcher
    using the ``[notifications]`` block in ``dazzle.toml``.

What's deferred (#952 cycle 3+):

  * SmtpProvider (cycle 3): real ``smtplib`` send.
  * Trigger wiring (cycle 4): the existing event/channel pipeline picks
    up entity-change events and calls ``dispatcher.dispatch_for_event``
    automatically. Today, project code calls ``dispatcher.dispatch``
    directly.
  * Send queue + retry + dead-letter (cycle 5): depends on #953
    background-job primitive.
  * SendgridProvider / SesProvider (cycle 6).
"""

from __future__ import annotations

import logging
import re as _re
from dataclasses import dataclass, field
from typing import Any, Protocol

logger = logging.getLogger(__name__)

_JINJA_PLACEHOLDER_RE = _re.compile(r"\{\{\s*([^{}\s][^{}]*?)\s*\}\}")


@dataclass(frozen=True)
class RenderedNotification:
    """A ready-to-send notification — provider-agnostic.

    Attributes:
        notification_name: Source ``NotificationSpec.name``. Useful for
            logs + telemetry.
        recipient: Resolved destination (email address for ``email``
            channel, role name for ``in_app``, etc).
        channel: Channel value from the spec (``email`` | ``in_app`` | …).
        subject: Rendered subject line. Empty for non-email channels.
        body: Rendered message body — either the inline ``message:`` or
            the loaded ``template:``, with placeholders substituted.
    """

    notification_name: str
    recipient: str
    channel: str
    subject: str
    body: str


class NotificationProvider(Protocol):
    """Adapter that delivers a :class:`RenderedNotification`.

    Implementations should be idempotent under retry and never raise
    on transient failures — return False instead so the dispatcher can
    enqueue a retry (cycle 5). Permanent failures (malformed
    addresses, unknown content types) should raise so the dispatcher
    surfaces them to the audit log.
    """

    def send(self, notification: RenderedNotification) -> bool:
        """Send *notification*. Returns True on success, False on
        transient failure suitable for retry."""
        ...


@dataclass
class LogProvider:
    """Default :class:`NotificationProvider` — logs a structured entry.

    Useful for dev, CI, and the period before a project wires real
    SMTP / SendGrid / SES credentials. Templates author against this
    provider with confidence: subject/body are rendered the same way
    a real provider would see them, just without leaving the process.
    """

    log_level: int = logging.INFO

    def send(self, notification: RenderedNotification) -> bool:
        logger.log(
            self.log_level,
            "notification.send name=%s channel=%s recipient=%s subject=%r body_len=%d",
            notification.notification_name,
            notification.channel,
            notification.recipient,
            notification.subject,
            len(notification.body),
        )
        return True


@dataclass
class SmtpProvider:
    """SMTP-backed :class:`NotificationProvider` (#952 cycle 3).

    Sends email-channel notifications via :mod:`smtplib`. Non-email
    channels (``in_app`` / ``sms`` / ``slack``) fall through to the
    log path so a single mixed-channel spec doesn't accidentally try
    to email a Slack username.

    Constructed by :func:`build_dispatcher_from_manifest` from the
    ``[notifications.smtp]`` block in ``dazzle.toml`` — adopters
    don't normally call this directly.

    Failure semantics follow the :class:`NotificationProvider`
    protocol:

    * ``smtplib.SMTPServerDisconnected`` / connection errors / 4xx
      transient codes → return False (dispatcher can retry in cycle 5).
    * 5xx permanent codes / malformed addresses → raise so the
      dispatcher logs the audit entry and stops retrying.
    """

    host: str
    port: int = 587
    username: str = ""
    password: str = ""
    from_address: str = ""
    use_tls: bool = True
    timeout_seconds: int = 30

    def send(self, notification: RenderedNotification) -> bool:
        # Non-email channels stay on the log path — SMTP can't deliver them.
        if notification.channel != "email":
            logger.info(
                "smtp_provider: skipping non-email channel %s for %s",
                notification.channel,
                notification.notification_name,
            )
            return True

        if not notification.recipient:
            logger.warning(
                "smtp_provider: notification %r has no recipient — skipping",
                notification.notification_name,
            )
            return True

        msg = _build_email_message(
            sender=self.from_address,
            recipient=notification.recipient,
            subject=notification.subject,
            body=notification.body,
        )

        import smtplib

        try:
            with smtplib.SMTP(self.host, self.port, timeout=self.timeout_seconds) as smtp:
                if self.use_tls:
                    smtp.starttls()
                if self.username and self.password:
                    smtp.login(self.username, self.password)
                smtp.send_message(msg)
        except smtplib.SMTPResponseException as exc:
            # `SMTPResponseException` extends `OSError` in stdlib, so it
            # must come BEFORE the broader OSError clause below — otherwise
            # 5xx permanent failures get swallowed as transient.
            # 4xx → transient (return False so dispatcher retries in cycle 5).
            # 5xx → permanent (raise so dispatcher records audit entry).
            if 400 <= exc.smtp_code < 500:
                logger.warning(
                    "smtp_provider: 4xx response sending %r: %s %s",
                    notification.notification_name,
                    exc.smtp_code,
                    exc.smtp_error,
                )
                return False
            raise
        except (
            smtplib.SMTPServerDisconnected,
            smtplib.SMTPConnectError,
            TimeoutError,
            OSError,
        ) as exc:
            # Transient — dispatcher can retry in cycle 5.
            logger.warning(
                "smtp_provider: transient error sending %r to %s: %s",
                notification.notification_name,
                notification.recipient,
                exc,
            )
            return False

        logger.info(
            "smtp_provider: sent %r to %s via %s",
            notification.notification_name,
            notification.recipient,
            self.host,
        )
        return True


def _build_email_message(sender: str, recipient: str, subject: str, body: str) -> Any:
    """Build an :class:`email.message.EmailMessage` with sane defaults.

    HTML is detected via a leading ``<`` token after stripping
    whitespace — adopters who want explicit content negotiation
    can wait for cycle 4's MIME-multipart support, but the simple
    "starts with a tag → text/html" heuristic covers the welcome /
    password-reset / receipt patterns that drive 80%+ of
    transactional email volume.
    """
    from email.message import EmailMessage

    msg = EmailMessage()
    msg["From"] = sender or "noreply@localhost"
    msg["To"] = recipient
    msg["Subject"] = subject
    if body.strip().startswith("<"):
        msg.set_content(_strip_html_tags(body))
        msg.add_alternative(body, subtype="html")
    else:
        msg.set_content(body)
    return msg


def _strip_html_tags(html: str) -> str:
    """Crude HTML-to-text fallback for the ``text/plain`` alternative.

    Strips tags, decodes a couple of common entities. Cycle 4 will
    let projects supply both halves explicitly; for now the goal is
    "render something readable in plain-text-only clients" rather
    than a faithful conversion.
    """
    import re as _re

    text = _re.sub(r"<[^>]+>", "", html)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    text = text.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
    return _re.sub(r"\n\s*\n\s*\n+", "\n\n", text).strip() + "\n"


def _render(template: str, payload: dict[str, Any]) -> str:
    """Render a single Jinja-ish placeholder string against *payload*.

    Cycle 2 keeps this minimal: matches ``{{ name }}`` (with optional
    surrounding whitespace) and substitutes ``payload[name]``. Missing
    keys land as the literal ``{name}`` token rather than raising — a
    visibly-broken email is more helpful than nothing. Cycle 3 swaps
    this for the project's Jinja env so templates can use filters/loops.
    """
    if not template:
        return ""

    def _sub(match: _re.Match[str]) -> str:
        key = match.group(1).strip()
        if key in payload:
            return str(payload[key])
        return "{" + key + "}"

    try:
        result: str = _JINJA_PLACEHOLDER_RE.sub(_sub, template)
        return result
    except (KeyError, IndexError, ValueError) as exc:
        logger.warning("Notification render failed for template %r: %s", template, exc)
        return template


@dataclass
class NotificationDispatcher:
    """Renders + dispatches notifications via a configured provider.

    Cycle 2 surface — adopters call ``dispatch(spec, payload)`` directly.
    Cycle 4 will wire the event/channel pipeline so entity-change events
    auto-dispatch matching specs.

    Attributes:
        provider: The :class:`NotificationProvider` that delivers
            rendered notifications. Defaults to :class:`LogProvider`.
        from_address: Default ``From:`` for outbound email (set from
            ``[notifications] from`` in dazzle.toml).
        templates: Optional ``{template_path: template_source}`` map
            looked up when a spec sets ``template:``. Cycle 3 replaces
            this with a Jinja loader rooted at the project's
            ``templates/`` directory.
    """

    provider: NotificationProvider = field(default_factory=LogProvider)
    from_address: str = ""
    templates: dict[str, str] = field(default_factory=dict)

    def dispatch(
        self,
        spec: Any,  # ir.NotificationSpec — typed Any to avoid runtime import
        payload: dict[str, Any],
        *,
        recipient: str | None = None,
    ) -> list[RenderedNotification]:
        """Render *spec* against *payload* and dispatch one
        :class:`RenderedNotification` per channel via the provider.

        Returns the list of dispatched notifications (post-render,
        pre-provider mutation) so callers can audit the work.

        *recipient* overrides the spec's ``recipients:`` resolution —
        useful for tests + cycle-3 trigger wiring that has the resolved
        target before this call.
        """
        body_template = self._resolve_body_template(spec)
        rendered_subject = _render(getattr(spec, "subject", ""), payload)
        rendered_body = _render(body_template, payload)
        target = recipient or self._resolve_recipient(spec, payload)
        out: list[RenderedNotification] = []
        for channel in getattr(spec, "channels", []) or []:
            channel_value = getattr(channel, "value", str(channel))
            rendered = RenderedNotification(
                notification_name=getattr(spec, "name", "<unknown>"),
                recipient=target,
                channel=channel_value,
                subject=rendered_subject,
                body=rendered_body,
            )
            try:
                self.provider.send(rendered)
            except Exception:
                # Permanent failure — log so the audit pipeline (cycle 5)
                # can pick it up. Don't re-raise so a single channel
                # failure doesn't abort the others.
                logger.exception(
                    "Notification %r send failed on channel %s",
                    rendered.notification_name,
                    channel_value,
                )
            out.append(rendered)
        return out

    def _resolve_body_template(self, spec: Any) -> str:
        """Pick the body template per the cycle-1 contract: ``template:``
        wins over ``message:`` when both are set."""
        template_path = getattr(spec, "template", "") or ""
        if template_path:
            template_source = self.templates.get(template_path)
            if template_source is not None:
                return template_source
            # No template registered with this name — fall back to
            # `message` so the dispatch still produces something
            # rather than silently sending an empty body.
            logger.warning(
                "Notification %r references template %r which is not registered",
                getattr(spec, "name", "<unknown>"),
                template_path,
            )
        return getattr(spec, "message", "") or ""

    def _resolve_recipient(self, spec: Any, payload: dict[str, Any]) -> str:
        """Resolve recipient from the spec + payload.

        Cycle 2 supports the ``field(<name>)`` form against the payload
        only — pulls ``payload[field_name]`` and returns its string.
        Other recipient kinds (``role``, ``creator``) are deferred to
        cycle 4 where the trigger pipeline knows about user lookup.
        """
        recipient_spec = getattr(spec, "recipients", None)
        if recipient_spec is None:
            return ""
        kind = getattr(recipient_spec, "kind", "")
        value = getattr(recipient_spec, "value", "")
        if kind == "field" and value:
            payload_value = payload.get(value)
            if payload_value is not None:
                return str(payload_value)
        # Cycle 4 will resolve role-based recipients via the user-management
        # pipeline. For now log + return empty so adopters know to pass
        # `recipient=` explicitly until that lands.
        logger.debug(
            "Notification %r recipients.kind=%r — cycle-2 dispatcher only "
            "resolves field-based recipients; pass recipient= explicitly",
            getattr(spec, "name", "<unknown>"),
            kind,
        )
        return ""


def build_dispatcher_from_manifest(
    manifest_notifications: Any,  # NotificationsConfig — Any avoids cycle
) -> NotificationDispatcher:
    """Build a :class:`NotificationDispatcher` from
    :class:`~dazzle.core.manifest.NotificationsConfig`.

    Provider mapping (#952):

    * ``log`` (default) → :class:`LogProvider`
    * ``smtp`` (cycle 3) → :class:`SmtpProvider` — requires a non-empty
      ``smtp_host``; falls back to :class:`LogProvider` with a warning
      when host is missing so dispatch still runs visibly during dev.
    * ``sendgrid`` / ``ses`` (cycle 6+) → not yet implemented; logs a
      deferred-cycle warning and falls back to :class:`LogProvider`.
    """
    provider_key = getattr(manifest_notifications, "provider", "log")
    from_address = getattr(manifest_notifications, "from_address", "") or ""

    if provider_key == "log":
        provider: NotificationProvider = LogProvider()
    elif provider_key == "smtp":
        smtp_host = getattr(manifest_notifications, "smtp_host", "") or ""
        if not smtp_host:
            logger.warning(
                "Notification provider 'smtp' requires [notifications.smtp] host "
                "— falling back to LogProvider until configured."
            )
            provider = LogProvider()
        else:
            provider = SmtpProvider(
                host=smtp_host,
                port=int(getattr(manifest_notifications, "smtp_port", 587) or 587),
                username=getattr(manifest_notifications, "smtp_username", "") or "",
                password=getattr(manifest_notifications, "smtp_password", "") or "",
                from_address=from_address,
            )
    else:
        logger.warning(
            "Notification provider %r not yet implemented (cycle 6+) — "
            "falling back to LogProvider so dispatch is still visible.",
            provider_key,
        )
        provider = LogProvider()
    return NotificationDispatcher(
        provider=provider,
        from_address=from_address,
    )


__all__ = [
    "LogProvider",
    "NotificationDispatcher",
    "NotificationProvider",
    "RenderedNotification",
    "SmtpProvider",
    "build_dispatcher_from_manifest",
]
