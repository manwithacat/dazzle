"""Abstract ``FitnessLedger`` interface for per-run observation storage.

Three implementations are planned:

- ``SnapshotLedger`` (v1) — polls repr-declared tables before/after each step
- ``SavepointLedger`` (v1.1) — wraps each step in a SAVEPOINT
- ``WalLedger`` (v1.2) — subscribes to a logical replication slot

All three produce the same ``FitnessDiff`` shape.

v1 note (see plan Task 0 retarget): Dazzle's runtime uses **sync** psycopg v3
via ``PostgresBackend.connection()``. The interface is therefore sync. Async
variants can be added later by introducing a parallel ``AsyncFitnessLedger``
abstract class if we ever need one, but v1 does not.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Protocol

from dazzle.fitness.models import FitnessDiff, LedgerStep


class SnapshotSource(Protocol):
    """Read-only table snapshot source.

    The v1 ``SnapshotLedger`` uses a ``SnapshotSource`` so that unit tests can
    pass an in-memory stub and the real adapter (backed by ``PostgresBackend``)
    is wired in at engine construction time (Task 19). This keeps the ledger
    itself free of any DB driver imports.
    """

    def fetch_rows(self, table: str, columns: list[str]) -> list[dict[str, Any]]: ...


class FitnessLedger(ABC):
    """Abstract interface for per-run fitness observation storage."""

    @abstractmethod
    def open(self, run_id: str) -> None: ...

    @abstractmethod
    def record_intent(self, step: int, expect: str, action_desc: str) -> None: ...

    @abstractmethod
    def observe_step(self, step: int, observed_ui: str) -> None: ...

    @abstractmethod
    def current_step(self) -> LedgerStep | None: ...

    @abstractmethod
    def summarize(self) -> FitnessDiff: ...

    @abstractmethod
    def close(self, rollback: bool = False) -> None: ...
