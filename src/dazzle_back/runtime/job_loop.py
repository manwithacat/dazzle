"""Worker loop wrapping cycle-4's `process_one` (#953 cycle 5).

Long-running async loop that pulls messages off a `JobQueue` and
runs them through `process_one` until a stop event fires. The
`dazzle worker` CLI (cycle 5b, once server-side service wiring
lands) will instantiate this and connect SIGINT/SIGTERM to the
stop event.

Design notes
------------

* `stop_event` is `asyncio.Event` (not `threading.Event`) — the
  loop is fully async and runs in a single asyncio task.
* `idle_timeout` controls how often the loop wakes to check
  `stop_event` when the queue is empty. Default 1.0s balances
  shutdown responsiveness against wakeup overhead.
* The loop never raises — every per-message exception is caught
  and logged. Only a `stop_event.set()` (or the asyncio task
  itself being cancelled) ends the loop.
* Returns ``stats`` dict so tests + cycle-5b CLI can surface
  throughput / outcome counts to the operator.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from typing import Any

from dazzle_back.runtime.job_queue import JobQueue
from dazzle_back.runtime.job_worker import WorkerOutcome, process_one

logger = logging.getLogger(__name__)


async def run_worker_loop(
    *,
    queue: JobQueue,
    job_specs: Mapping[str, Any],
    job_service: Any,
    stop_event: asyncio.Event,
    idle_timeout: float = 1.0,
) -> dict[str, int]:
    """Pump the queue until ``stop_event`` is set.

    Args:
        queue: The `JobQueue` to dequeue from. cycle 3's
            `InMemoryJobQueue` for tests / single-process; cycle 8
            will add a `RedisJobQueue` satisfying the same Protocol.
        job_specs: ``{job_name: JobSpec}`` from ``appspec.jobs``.
        job_service: The framework's `JobRun` service. None
            tolerated for early-bootstrap paths (matches
            `process_one`).
        stop_event: Trip this to end the loop. Cycle-5b CLI will
            wire SIGINT / SIGTERM to ``stop_event.set()``.
        idle_timeout: Seconds to wait per dequeue when the queue is
            empty — bounds the shutdown latency.

    Returns:
        Stats dict mapping outcome code → count, plus a
        ``"polled"`` key counting empty dequeues. Useful for
        per-loop metrics and end-of-test assertions.
    """
    stats: dict[str, int] = {
        WorkerOutcome.COMPLETED: 0,
        WorkerOutcome.FAILED: 0,
        WorkerOutcome.DEAD_LETTER: 0,
        WorkerOutcome.RETRIED: 0,
        WorkerOutcome.NO_SPEC: 0,
        "polled": 0,
        "loop_errors": 0,
    }

    logger.info("Worker loop starting (idle_timeout=%.1fs)", idle_timeout)

    while not stop_event.is_set():
        try:
            message = await queue.dequeue(timeout=idle_timeout)
        except Exception:
            # Queue impl could blow up (Redis down, etc.) — log and
            # back off. Cycle 8's RedisJobQueue will have its own
            # reconnect logic; this is the outer safety net.
            stats["loop_errors"] += 1
            logger.warning("Queue dequeue failed — backing off", exc_info=True)
            await asyncio.sleep(idle_timeout)
            continue

        if message is None:
            # Idle tick — let the stop_event check at the top of
            # the next loop fire promptly.
            stats["polled"] += 1
            continue

        try:
            outcome = await process_one(
                message,
                job_specs=dict(job_specs),
                job_service=job_service,
                queue=queue,
            )
            stats[outcome] = stats.get(outcome, 0) + 1
        except Exception:
            # `process_one` already swallows handler exceptions; an
            # exception here means the worker plumbing itself blew
            # up. Count it but keep the loop alive.
            stats["loop_errors"] += 1
            logger.exception(
                "process_one crashed for job %s — continuing loop",
                message.job_name,
            )

    logger.info("Worker loop exiting; stats=%s", stats)
    return stats
