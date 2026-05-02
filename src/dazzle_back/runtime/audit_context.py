"""Per-request user-id context for the audit emitter (#956 cycle 4).

The audit emitter (cycle 3) needs the current user's ID to populate
``AuditEntry.by_user_id``. Threading the user through every layer of
service callbacks would be invasive; a request-scoped ContextVar is
the lightest-weight integration point that keeps the emitter pure.

Cycle 4 just defines the ContextVar and a getter that's safe to call
from anywhere — returns None when no user is bound (system-initiated
writes, tests, or pre-auth-middleware code paths). Cycle 5 wires the
auth middleware / route_generator to set it on every authenticated
request entry.
"""

from __future__ import annotations

from contextvars import ContextVar, Token

# Module-level ContextVar — lives for the duration of the asyncio
# task / request. Default `None` means "no user bound" (system write
# or unauthenticated path); callers pass that through to the audit
# row's `by_user_id` column rather than failing.
_current_user_id: ContextVar[str | None] = ContextVar("dazzle_current_user_id", default=None)


def get_current_user_id() -> str | None:
    """Return the current user's ID for the active request, or None.

    Returns None when no user is bound — the caller must treat None as
    a valid value (system-initiated write) rather than an error.
    """
    return _current_user_id.get()


def set_current_user_id(user_id: str | None) -> Token[str | None]:
    """Bind the current user's ID for the active request.

    Returns a `Token` that callers should pass to
    :func:`reset_current_user_id` in the matching ``finally`` to avoid
    leaking the value into subsequent tasks (asyncio recycles tasks
    across requests in some servers).
    """
    return _current_user_id.set(user_id)


def reset_current_user_id(token: Token[str | None]) -> None:
    """Restore the prior bound user ID (or unbind if none was set)."""
    _current_user_id.reset(token)
