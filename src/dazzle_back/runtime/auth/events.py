"""Auth lifecycle event emission.

Emits events to the EventFramework bus after successful auth operations:
- ``auth.user.registered`` — after user registration
- ``auth.user.logged_in`` — after login (including 2FA completion)
- ``auth.user.password_changed`` — after password change

Events are fire-and-forget: failures are logged but never block the auth
response.  When the EventFramework is not running (e.g. in tests or
lightweight dev mode) events are silently skipped.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from dazzle_back.events.envelope import EventEnvelope

if TYPE_CHECKING:
    from .models import UserRecord

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level event framework reference (set once at startup)
# ---------------------------------------------------------------------------

_event_framework: Any = None


def configure_auth_events(framework: Any) -> None:
    """Set the event framework for auth event publishing.

    Called once during ``EventsSubsystem.startup()`` so that ``_publish()``
    can reach the bus without importing a global singleton.
    """
    global _event_framework  # noqa: PLW0603  # clean setter called once at startup
    _event_framework = framework


# ---------------------------------------------------------------------------
# Event type constants
# ---------------------------------------------------------------------------

AUTH_USER_REGISTERED = "auth.user.registered"
AUTH_USER_LOGGED_IN = "auth.user.logged_in"
AUTH_USER_PASSWORD_CHANGED = "auth.user.password_changed"


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


async def emit_user_registered(user: UserRecord, *, session_id: str | None = None) -> None:
    """Emit ``auth.user.registered`` after successful registration."""
    envelope = EventEnvelope.create(
        event_type=AUTH_USER_REGISTERED,
        key=str(user.id),
        payload={
            "user_id": str(user.id),
            "email": user.email,
            "username": user.username,
            "roles": user.roles,
            "timestamp": datetime.now(UTC).isoformat(),
        },
        producer="dazzle-auth",
    )
    if session_id:
        envelope.headers["session_id"] = session_id
    await _publish(envelope)


async def emit_user_logged_in(
    user: UserRecord,
    *,
    session_id: str | None = None,
    method: str = "password",
) -> None:
    """Emit ``auth.user.logged_in`` after successful login.

    Args:
        user: The authenticated user.
        session_id: The session ID created for this login.
        method: How the user authenticated (``password``, ``2fa``, ``jwt``).
    """
    envelope = EventEnvelope.create(
        event_type=AUTH_USER_LOGGED_IN,
        key=str(user.id),
        payload={
            "user_id": str(user.id),
            "email": user.email,
            "session_id": session_id or "",
            "method": method,
            "timestamp": datetime.now(UTC).isoformat(),
        },
        producer="dazzle-auth",
    )
    if session_id:
        envelope.headers["session_id"] = session_id
    await _publish(envelope)


async def emit_user_password_changed(user: UserRecord) -> None:
    """Emit ``auth.user.password_changed`` after a password change."""
    envelope = EventEnvelope.create(
        event_type=AUTH_USER_PASSWORD_CHANGED,
        key=str(user.id),
        payload={
            "user_id": str(user.id),
            "timestamp": datetime.now(UTC).isoformat(),
        },
        producer="dazzle-auth",
    )
    await _publish(envelope)


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------


async def _publish(envelope: EventEnvelope) -> None:
    """Publish *envelope* via the EventFramework bus.

    Failures are logged at warning level and swallowed so that auth
    responses are never blocked by event infrastructure issues.
    """
    try:
        framework = _event_framework
        bus = framework.get_bus() if framework else None
        if bus:
            await bus.publish(envelope.topic, envelope)
            logger.debug("Published %s for key=%s", envelope.event_type, envelope.key)
        else:
            logger.debug("Event bus not available, skipping %s", envelope.event_type)
    except Exception:
        # Never block auth on event failures.
        logger.warning(
            "Failed to publish auth event %s — continuing without event emission",
            envelope.event_type,
            exc_info=True,
        )
