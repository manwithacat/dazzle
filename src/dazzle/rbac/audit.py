"""Access-decision observability seam for the RBAC *verification* layer.

This module is the Layer-3 hook the RBAC verification framework uses to
*observe* `evaluate_permission()` decisions — for the `ConformanceMonitor`
and the dynamic RBAC verifier (`InMemoryAuditSink`), or for offline
analysis (`JsonFileAuditSink`). `set_audit_sink()` swaps the active sink.

It is **not** the production audit trail. In production the sink is
`NullAuditSink` *by design* (zero overhead) — the durable access-decision
audit trail is the runtime `AuditLogger` (`dazzle.http.runtime.audit_log`),
which writes every CRUD-route decision to the `_dazzle_audit_log`
PostgreSQL table. A `NullAuditSink` default here therefore does **not**
mean "auditing is off"; it means this verification seam is idle while the
production trail runs elsewhere (#1172).
"""

from __future__ import annotations  # required: forward reference

import json
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class AccessDecisionRecord:
    """Structured record of a single access decision."""

    timestamp: str
    request_id: str
    user_id: str
    roles: list[str]
    entity: str
    operation: str
    allowed: bool
    effect: str
    matched_rule: str
    record_id: str | None
    tier: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class AccessAuditSink(Protocol):
    """Protocol for audit sinks that receive access decision records."""

    def emit(self, record: AccessDecisionRecord) -> None: ...


class NullAuditSink:
    """No-op sink — the default, and what production runs with.

    Production auditing is *not* off: the durable access-decision trail
    is the runtime `AuditLogger` (`_dazzle_audit_log` table), not this
    verification seam. See the module docstring. Zero overhead.
    """

    def emit(self, record: AccessDecisionRecord) -> None:
        pass


class InMemoryAuditSink:
    """Collects records in memory — used by Layer 2 verifier during test runs."""

    def __init__(self) -> None:
        self.records: list[AccessDecisionRecord] = []

    def emit(self, record: AccessDecisionRecord) -> None:
        self.records.append(record)

    def clear(self) -> None:
        self.records.clear()


class JsonFileAuditSink:
    """Writes records as JSON Lines to a file."""

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._file = open(self._path, "a", encoding="utf-8")  # noqa: SIM115
        self._lock = threading.Lock()

    def emit(self, record: AccessDecisionRecord) -> None:
        line = json.dumps(record.to_dict(), default=str)
        with self._lock:
            self._file.write(line + "\n")
            self._file.flush()

    def close(self) -> None:
        self._file.close()


# Global audit sink — thread-safe access
_sink_lock = threading.Lock()
_current_sink: AccessAuditSink = NullAuditSink()


def get_audit_sink() -> AccessAuditSink:
    with _sink_lock:
        return _current_sink


def set_audit_sink(sink: AccessAuditSink) -> None:
    global _current_sink  # noqa: PLW0603  # thread-safe audit sink swap for testing
    with _sink_lock:
        _current_sink = sink
