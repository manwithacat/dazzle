"""In-process LRU cache for tenant resolution lookups (#1289).

Stores positive hits (typed resolver results) plus a `NEGATIVE` sentinel
that memoises cache-misses so a flood of requests for an unknown slug
doesn't trigger a flood of DB lookups.

Configurable via `max_entries` and `ttl_seconds`. Designed as a small
pure-logic unit; the resolver and middleware compose on top of it.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from threading import Lock
from typing import Any, Final


class _Negative:
    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - debug only
        return "<NEGATIVE>"


NEGATIVE: Final[_Negative] = _Negative()


class TenantCache:
    """Thread-safe LRU + ttl cache for tenant resolution results."""

    def __init__(self, *, max_entries: int = 1024, ttl_seconds: float = 60.0) -> None:
        self._max = max_entries
        self._ttl = ttl_seconds
        self._lock = Lock()
        self._store: OrderedDict[str, tuple[Any, float]] = OrderedDict()

    def get(self, slug: str) -> Any | None:
        now = time.monotonic()
        with self._lock:
            entry = self._store.get(slug)
            if entry is None:
                return None
            value, expires_at = entry
            if expires_at <= now:
                del self._store[slug]
                return None
            self._store.move_to_end(slug)  # mark recently used
            return value

    def set(self, slug: str, value: Any) -> None:
        with self._lock:
            self._store[slug] = (value, time.monotonic() + self._ttl)
            self._store.move_to_end(slug)
            while len(self._store) > self._max:
                self._store.popitem(last=False)

    def bust(self, slug: str) -> None:
        with self._lock:
            self._store.pop(slug, None)

    def clear(self) -> None:  # pragma: no cover - convenience for tests
        with self._lock:
            self._store.clear()
