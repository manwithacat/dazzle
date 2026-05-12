"""Generic background-job queue (#953 cycle 3).

Distinct from `llm_queue.py` — that's the LLM-specific specialisation
(token-bucket rate limits, per-model concurrency). This module is
the generic primitive a project author's `job X:` declarations get
enqueued into. Cycle 4 will add a Redis-backed implementation;
cycle 3 ships an asyncio in-memory queue that's enough to wire the
end-to-end flow and exercise the worker shape.

Design notes
------------

* `JobMessage` is a frozen dataclass — once enqueued, the message
  shouldn't mutate. Status / timing changes flow through ``JobRun``
  rows (cycle 2), not through the queue payload.
* `JobQueue` is a `Protocol` so the worker can swap implementations
  without inheritance. Cycle 4's `RedisJobQueue` will satisfy the
  same shape.
* `submit` returns the freshly-allocated `job_run_id` (also stored
  on the message) so the API caller can poll `JobRun` for status.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import uuid4


@dataclass(frozen=True)
class JobMessage:
    """One enqueued background-job execution.

    Attributes:
        job_name: The `JobSpec.name` to dispatch on.
        payload: Handler args. JSON-serialisable when the queue
            implementation crosses a process boundary; in-memory
            queue accepts any Python object.
        attempt: 1-indexed retry counter — bumped by the worker
            before re-enqueuing on transient failure.
        job_run_id: Foreign key to the `JobRun` row created at
            submit time. The worker writes status transitions
            against this row.
    """

    job_name: str
    payload: dict[str, Any] = field(default_factory=dict)
    attempt: int = 1
    job_run_id: str = ""


class JobQueue(Protocol):
    """Generic queue protocol for background jobs."""

    async def submit(
        self,
        job_name: str,
        payload: dict[str, Any] | None = None,
        *,
        attempt: int = 1,
    ) -> str:
        """Enqueue a job; return the new ``JobRun.id`` as a string."""
        ...

    async def dequeue(self, *, timeout: float | None = None) -> JobMessage | None:
        """Pull the next message, or None on timeout / empty.

        ``timeout=None`` blocks until a message arrives. ``timeout=0``
        is non-blocking (returns None when queue is empty).
        """
        ...

    async def size(self) -> int:
        """Current queue depth — for tests / metrics."""
        ...


class InMemoryJobQueue:
    """asyncio.Queue-backed implementation for tests + single-process
    deployments.

    Cycle 4's `RedisJobQueue` will satisfy the same protocol while
    surviving worker restarts and supporting multiple worker
    processes. For now this is enough to exercise the worker
    shape and unit-test handler dispatch end-to-end.
    """

    def __init__(self) -> None:
        self._queue: asyncio.Queue[JobMessage] = asyncio.Queue()

    async def submit(
        self,
        job_name: str,
        payload: dict[str, Any] | None = None,
        *,
        attempt: int = 1,
    ) -> str:
        job_run_id = str(uuid4())
        message = JobMessage(
            job_name=job_name,
            payload=dict(payload or {}),
            attempt=attempt,
            job_run_id=job_run_id,
        )
        await self._queue.put(message)
        return job_run_id

    async def dequeue(self, *, timeout: float | None = None) -> JobMessage | None:
        if timeout is None:
            return await self._queue.get()
        try:
            return await asyncio.wait_for(self._queue.get(), timeout=timeout)
        except TimeoutError:
            return None

    async def size(self) -> int:
        return self._queue.qsize()
