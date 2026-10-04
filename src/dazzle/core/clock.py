"""One clock for the framework.

Twelve modules each defined their own ``_utcnow() -> datetime.now(UTC)`` — the
exact-body clone ratchet counted them as one cluster of 9, and the copies had
drifted in all but name (some with a docstring, some without). A helper whose
entire body is "now" does not need to exist per module: a test that wants to
freeze time patches one name, not twelve.

Timezone-aware UTC everywhere; naive local time is never returned by accident.
"""

from __future__ import annotations

from datetime import UTC, datetime

__all__ = ["utcnow"]


def utcnow() -> datetime:
    """Current UTC datetime, timezone-aware.

    The single seam for "now" in the framework. Patch this one name to freeze
    time in a test.
    """
    return datetime.now(UTC)
