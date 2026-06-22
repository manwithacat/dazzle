"""Task store backend protocol for process human tasks (#787).

Decouples the Temporal-activity code from its persistence layer via the
``TaskStoreBackend`` protocol. The default ``InMemoryTaskStore`` preserves the
original dict-based behaviour for dev / tests / single-node use.

The process-wide backend is the single instance returned by
:func:`get_task_store` (memoised — no module-level mutable global, ADR-0005 /
#1445). A future durable, database-backed backend would be introduced through
explicit dependency injection rather than a swap hook; the unused
``set_task_store`` swap was removed in #1445 (it never had a caller).
"""

from __future__ import annotations

import functools
import logging
import threading
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

from .adapter import ProcessTask, TaskStatus

logger = logging.getLogger(__name__)


@runtime_checkable
class TaskStoreBackend(Protocol):
    """Persistence contract for ``ProcessTask`` records."""

    async def save(self, task: ProcessTask) -> None:
        """Persist a newly created task."""
        ...

    async def get(self, task_id: str) -> ProcessTask | None:
        """Fetch a task by id."""
        ...

    async def list(
        self,
        *,
        run_id: str | None = None,
        assignee_id: str | None = None,
        status: TaskStatus | None = None,
        limit: int = 100,
    ) -> list[ProcessTask]:
        """Return tasks matching the supplied filters."""
        ...

    async def complete(
        self,
        task_id: str,
        outcome: str,
        outcome_data: dict[str, Any] | None = None,
        completed_by: str | None = None,
    ) -> bool:
        """Mark a task completed. Returns ``True`` iff a task was updated."""
        ...

    async def reassign(
        self,
        task_id: str,
        new_assignee_id: str,
        reason: str | None = None,
    ) -> bool:
        """Reassign a task to ``new_assignee_id``. Returns ``True`` on success."""
        ...

    async def escalate(self, task_id: str) -> bool:
        """Mark a task escalated. Returns ``True`` iff a task was updated."""
        ...

    async def clear(self) -> None:
        """Remove all tasks — intended for tests."""
        ...


class InMemoryTaskStore:
    """Dict-backed implementation — suitable for dev, tests, single-node use.

    Thread-safe via a single lock. Not durable — state is lost when the
    process exits. Durability across restarts would require a database-backed
    ``TaskStoreBackend`` wired in through explicit dependency injection (the
    process-wide default is whatever :func:`get_task_store` returns).
    """

    def __init__(self) -> None:
        self._store: dict[str, ProcessTask] = {}
        self._lock = threading.Lock()

    async def save(self, task: ProcessTask) -> None:
        with self._lock:
            self._store[task.task_id] = task

    async def get(self, task_id: str) -> ProcessTask | None:
        with self._lock:
            return self._store.get(task_id)

    async def list(
        self,
        *,
        run_id: str | None = None,
        assignee_id: str | None = None,
        status: TaskStatus | None = None,
        limit: int = 100,
    ) -> list[ProcessTask]:
        with self._lock:
            tasks = list(self._store.values())
        if run_id:
            tasks = [t for t in tasks if t.run_id == run_id]
        if assignee_id:
            tasks = [t for t in tasks if t.assignee_id == assignee_id]
        if status:
            tasks = [t for t in tasks if t.status == status]
        return tasks[:limit]

    async def complete(
        self,
        task_id: str,
        outcome: str,
        outcome_data: dict[str, Any] | None = None,
        completed_by: str | None = None,
    ) -> bool:
        with self._lock:
            task = self._store.get(task_id)
            if task is None:
                return False
            task.status = TaskStatus.COMPLETED
            task.outcome = outcome
            task.outcome_data = outcome_data
            task.completed_at = datetime.now(UTC)
        logger.info("Task %s completed with outcome %r", task_id, outcome)
        return True

    async def reassign(
        self,
        task_id: str,
        new_assignee_id: str,
        reason: str | None = None,
    ) -> bool:
        with self._lock:
            task = self._store.get(task_id)
            if task is None:
                return False
            old_assignee = task.assignee_id
            task.assignee_id = new_assignee_id
        detail = f": {reason}" if reason else ""
        logger.info(
            "Task %s reassigned from %s to %s%s",
            task_id,
            old_assignee,
            new_assignee_id,
            detail,
        )
        return True

    async def escalate(self, task_id: str) -> bool:
        with self._lock:
            task = self._store.get(task_id)
            if task is None:
                return False
            task.status = TaskStatus.ESCALATED
            task.escalated_at = datetime.now(UTC)
        return True

    async def clear(self) -> None:
        with self._lock:
            self._store.clear()


@functools.cache
def get_task_store() -> TaskStoreBackend:
    """Return the process-wide task store backend.

    Memoised, so every caller (the free-function Temporal activities in
    ``activities.py`` and the ``TemporalAdapter`` methods) shares one
    ``InMemoryTaskStore`` instance — no module-level mutable global (#1445).
    Tests that need a clean store call ``get_task_store().clear()`` (or
    ``get_task_store.cache_clear()`` to drop the instance entirely).
    """
    return InMemoryTaskStore()


__all__ = [
    "InMemoryTaskStore",
    "TaskStoreBackend",
    "get_task_store",
]
