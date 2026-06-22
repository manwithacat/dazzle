"""In-process retry-event accumulator (#1194).

Keeps a per-integration ring of recent retry attempts driven by
``MappingExecutor``'s call into :func:`async_retrying_request`. The
state is:

* **Module-local** — a singleton, created on first access.
* **In-process** — not persisted to the operational DB.
* **Volatile** — resets on every restart of the application.

That trade-off is deliberate. Durable retry history is the
responsibility of the integration provider's own logs; this accumulator
exists purely to make in-flight / recent retry state inspectable via
``GET /_dazzle/integrations/{name}/retries`` without changing the
schema or scope of ``ops_db``.

The per-integration list is capped at
:data:`RetryAccumulator.MAX_EVENTS_PER_INTEGRATION` entries (default
100); the oldest entries are dropped FIFO when the cap is exceeded.
"""

import threading
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class RetryEvent:
    """A single retry-attempt outcome captured by ``MappingExecutor``.

    Fields are intentionally lightweight — primitives and short strings
    — so the accumulator never holds large response bodies or
    long-lived references.
    """

    integration: str
    mapping: str | None
    attempt: int
    max_attempts: int
    status_code: int | None = None
    error: str | None = None
    payload_summary: str | None = None
    last_attempt_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    next_retry_at: str | None = None
    backoff_seconds: float | None = None
    succeeded: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe dict (consumed by the API response model)."""
        return asdict(self)


class RetryAccumulator:
    """Thread-safe per-integration bounded queue of ``RetryEvent``.

    Designed for low-volume operational telemetry — every retry attempt
    is recorded but each integration is capped at
    :attr:`MAX_EVENTS_PER_INTEGRATION` to prevent unbounded growth.
    """

    #: Cap per integration. Oldest entries drop when exceeded.
    MAX_EVENTS_PER_INTEGRATION: int = 100

    def __init__(self) -> None:
        self._events: dict[str, deque[RetryEvent]] = {}
        self._lock = threading.Lock()

    def record(self, event: RetryEvent) -> None:
        """Append a retry event to the integration's queue.

        Drops the oldest entry first when the per-integration cap is
        reached (``deque(maxlen=...)`` semantics).
        """
        with self._lock:
            bucket = self._events.get(event.integration)
            if bucket is None:
                bucket = deque(maxlen=self.MAX_EVENTS_PER_INTEGRATION)
                self._events[event.integration] = bucket
            bucket.append(event)

    def events_for(self, integration: str) -> list[RetryEvent]:
        """Return a snapshot of every retained event for *integration*.

        The list is a copy — safe to iterate without holding the lock.
        Oldest event is first; callers wanting newest-first reverse it.
        """
        with self._lock:
            bucket = self._events.get(integration)
            return list(bucket) if bucket is not None else []

    def integrations(self) -> list[str]:
        """Return the integration names that have at least one event."""
        with self._lock:
            return list(self._events.keys())

    def clear(self) -> None:
        """Drop every recorded event (test-suite helper)."""
        with self._lock:
            self._events.clear()


# =============================================================================
# Per-app accumulator (ADR-0005 — ServerState, not a process-wide module global)
# =============================================================================


def app_retry_accumulator(app: Any) -> RetryAccumulator:
    """Get-or-create the per-app :class:`RetryAccumulator` on ``app.state``.

    ``MappingExecutor`` (writer) and the ``/_dazzle/integrations/{name}/retries``
    route (reader) are wired in two different subsystem-setup methods; both fetch
    the one shared instance here, scoped to the FastAPI app (the ADR-0005
    ServerState pattern) rather than a module-level process singleton (#1445).
    Volatile — resets on restart.
    """
    acc = getattr(app.state, "retry_accumulator", None)
    if acc is None:
        acc = RetryAccumulator()
        app.state.retry_accumulator = acc
    return acc
