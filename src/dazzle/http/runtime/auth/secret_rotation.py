"""Connection secret-rotation helpers (#1342 — grace window + audit).

Pure, store-free: the grace-duration parser used by the rotate CLI and the audit
event-name constants (the ``connection_secret_events`` DDL lives in
``store_enterprise``). Kept separate from the DSL lexer's ``parse_duration`` so the
auth store doesn't depend on the core parser.
"""

from __future__ import annotations

import re
from datetime import timedelta

# Audit event names (written to connection_secret_events.event).
SECRET_EVENT_ROTATED = "rotated"
SECRET_EVENT_REVOKED_PREVIOUS = "revoked_previous"
SECRET_EVENT_KEY_REWRAPPED = "encryption_key_rewrapped"

_GRACE_UNITS = {"m": "minutes", "h": "hours", "d": "days", "w": "weeks"}
# A single positive integer (no leading zero) + one unit suffix.
_GRACE_RE = re.compile(r"^([1-9][0-9]*)([mhdw])$")


def parse_grace_duration(text: str) -> timedelta:
    """``'24h'`` / ``'7d'`` / ``'30m'`` / ``'2w'`` -> timedelta.

    A single positive integer + one unit suffix (m/h/d/w). Raises ``ValueError``
    on anything else (empty, zero/negative, no unit, compound, fractional, 'y',
    leading-zero).
    """
    match = _GRACE_RE.match(text.strip())
    if match is None:
        raise ValueError(f"invalid grace duration {text!r} — use <positive int><m|h|d|w>, e.g. 24h")
    amount = int(match.group(1))
    try:
        return timedelta(**{_GRACE_UNITS[match.group(2)]: amount})
    except OverflowError as exc:
        # An astronomically large but well-formed duration overflows timedelta's C int —
        # honor the documented ValueError contract (callers only catch ValueError).
        raise ValueError(f"grace duration {text!r} is too large") from exc
