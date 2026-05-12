"""Issue #1037 follow-on (Phase 1.B, v0.67.30): magic-link email
delivery seam.

The auth flow issues magic-link tokens via `magic_link.create_magic_link`
and needs a way to deliver the resulting URL to the user's inbox.
This module defines the `MagicLinkMailer` Protocol and a default
`LogMailer` that writes link URLs to the application log at INFO
level — sufficient for development and for environments without
SMTP wired up. Production deployments register a real mailer (SES,
SendGrid, SMTP) on `app.state.magic_link_mailer` to override.

The Protocol intentionally exposes ONE method (`send_magic_link`)
to keep the contract narrow. Real-mailer implementations route the
URL through whatever transport they want; the Dazzle runtime only
cares that delivery completed (or failed loud enough for the
operator to notice).
"""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

_logger = logging.getLogger(__name__)


@runtime_checkable
class MagicLinkMailer(Protocol):
    """Contract for delivering magic-link sign-in URLs.

    Implementations are responsible for choosing a transport (SMTP,
    transactional-email API, etc.) and rendering the URL into a
    message body that matches the deployment's brand voice.

    `send_magic_link` is fire-and-forget from the issuance route's
    perspective — return value indicates "delivery initiated", not
    "user received the email". Failures should be logged but not
    raised; the auth flow's account-enumeration guard means the
    user gets the same `/login/sent` page either way.
    """

    def send_magic_link(self, *, to_email: str, link_url: str) -> None:
        """Deliver `link_url` to `to_email`. Idempotent within a
        request lifecycle — caller may invoke once per issuance."""
        ...


class LogMailer:
    """Default `MagicLinkMailer` impl: writes the link URL to the
    application log at INFO level.

    Sufficient for development environments (paste from server log
    to complete the loop) and for CI environments where no real
    inbox exists. Production deployments should register a real
    mailer instead.

    Logged format is single-line for easy log-aggregator scraping:
    `Magic-link issued for <email>: <url>`.
    """

    def send_magic_link(self, *, to_email: str, link_url: str) -> None:
        _logger.info("Magic-link issued for %s: %s", to_email, link_url)


def get_mailer(app_state: object) -> MagicLinkMailer:
    """Look up the registered mailer on `app.state.magic_link_mailer`,
    falling back to `LogMailer` when no override is configured.

    Routes call this at request time so each request reads the
    currently-configured mailer (in case a deployment swaps it at
    runtime during operator drills)."""
    mailer = getattr(app_state, "magic_link_mailer", None)
    if mailer is None:
        return LogMailer()
    # Runtime-checkable Protocol — narrow to MagicLinkMailer for mypy.
    assert isinstance(mailer, MagicLinkMailer)
    return mailer
