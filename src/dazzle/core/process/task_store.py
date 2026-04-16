"""Task store backend protocol for process human tasks (#787).

Decouples the Temporal-activity code from its persistence layer so
deployments can swap in a durable backend without touching activity
code. The default ``InMemoryTaskStore`` preserves the original
dict-based behaviour for dev / tests; production deployments can
register a database-backed implementation via :func:`set_task_store`
before the runtime starts.
"""

from __future__ import annotations

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
    process exits. Deployments that need durability across restarts should
    register a database-backed ``TaskStoreBackend`` via
    :func:`set_task_store` before creating a ``TemporalAdapter``.
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


# Process-wide default backend. Overridable via set_task_store() so
# deployments can inject a database-backed implementation at startup.
_DEFAULT_BACKEND: TaskStoreBackend = InMemoryTaskStore()


def get_task_store() -> TaskStoreBackend:
    """Return the currently active task store backend."""
    return _DEFAULT_BACKEND


def set_task_store(backend: TaskStoreBackend) -> None:
    """Override the process-wide task store backend.

    Call this once at startup before any ``TemporalAdapter`` instance is
    created. Swapping mid-flight will leave in-flight tasks stranded in
    the old backend.
    """
    global _DEFAULT_BACKEND
    _DEFAULT_BACKEND = backend


__all__ = [
    "InMemoryTaskStore",
    "TaskStoreBackend",
    "get_task_store",
    "set_task_store",
]
