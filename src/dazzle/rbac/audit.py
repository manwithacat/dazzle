"""Access decision audit trail — types, sinks, and global sink management.

Layer 3 of the RBAC verification framework. Instruments evaluate_permission()
to emit structured records of every access decision.
"""

from __future__ import annotations

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

    def to_dict(self) -> dict:
        return asdict(self)


class AccessAuditSink(Protocol):
    """Protocol for audit sinks that receive access decision records."""

    def emit(self, record: AccessDecisionRecord) -> None: ...


class NullAuditSink:
    """No-op sink — default in production (zero overhead)."""

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
        self._file = open(self._path, "a")  # noqa: SIM115
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
    global _current_sink
    with _sink_lock:
        _current_sink = sink
