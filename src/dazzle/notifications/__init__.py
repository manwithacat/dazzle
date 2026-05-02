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

    Cycle 2 only knows how to construct :class:`LogProvider` — the
    other provider keys (``smtp`` / ``sendgrid`` / ``ses``) log a
    deferred-cycle message and fall back to :class:`LogProvider` so
    sends still happen visibly during dev. Cycle 3+ adds the real
    adapters; the same builder picks them up by key.
    """
    provider_key = getattr(manifest_notifications, "provider", "log")
    if provider_key == "log":
        provider: NotificationProvider = LogProvider()
    else:
        logger.warning(
            "Notification provider %r not yet implemented (cycle 3+) — "
            "falling back to LogProvider so dispatch is still visible.",
            provider_key,
        )
        provider = LogProvider()
    return NotificationDispatcher(
        provider=provider,
        from_address=getattr(manifest_notifications, "from_address", "") or "",
    )


__all__ = [
    "LogProvider",
    "NotificationDispatcher",
    "NotificationProvider",
    "RenderedNotification",
    "build_dispatcher_from_manifest",
]
