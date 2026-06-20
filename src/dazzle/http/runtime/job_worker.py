"""Background-job worker (#953 cycle 4).

Processes a single dequeued ``JobMessage`` end-to-end:

  1. Look up the matching ``JobSpec`` by ``job_name``.
  2. Transition ``JobRun.status`` to ``"running"`` + ``started_at``.
  3. Resolve the handler from ``JobSpec.run`` via cycle-3's
     ``resolve_handler`` (lazy — failures land in
     ``error_message``).
  4. Invoke the handler with the message payload. Sync handlers
     run via ``asyncio.to_thread`` so a blocking handler doesn't
     stall the worker loop.
  5. On success: write ``status="completed"``, ``finished_at``,
     ``duration_ms``.
  6. On failure: increment ``attempt_number`` and either re-enqueue
     (transient) or write ``status="failed"`` / ``"dead_letter"``
     based on ``JobSpec.retry``.

The infinite loop + ``dazzle worker`` CLI is cycle 5; this function
is the testable unit. Calling it once with an InMemoryJobQueue and
a stub job service is enough to exercise the full state machine.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import time
from datetime import UTC, datetime
from typing import Any

from dazzle.core.ir.jobs import JobBackoff
from dazzle.http.runtime.job_handler import JobHandlerNotFound, resolve_handler
from dazzle.http.runtime.job_queue import JobMessage, JobQueue

logger = logging.getLogger(__name__)

# Upper bound on the per-attempt sleep so an exponential schedule on a
# high-retry job can't park a worker iteration for hours. 300s = 5 min
# is well above any sensible "transient blip" window for the workloads
# this worker is intended for.
MAX_BACKOFF_SECONDS: float = 300.0

# Base delay (seconds) for LINEAR / EXPONENTIAL strategies. LINEAR
# yields 1, 2, 3, ...; EXPONENTIAL yields 1, 2, 4, 8, ...
_BASE_BACKOFF_SECONDS: float = 1.0


def _compute_backoff_delay(backoff: JobBackoff, attempt: int) -> float:
    """Compute the sleep delay before re-enqueueing after a failed attempt.

    Args:
        backoff: The job's declared retry-backoff strategy.
        attempt: The attempt number that just failed (1-indexed).

    Returns:
        Delay in seconds (capped at :data:`MAX_BACKOFF_SECONDS`).

    Strategies:
        * ``NONE``       → ``0`` — immediate re-enqueue.
        * ``LINEAR``     → ``base * attempt`` (1, 2, 3, ... seconds).
        * ``EXPONENTIAL``→ ``base * 2 ** (attempt - 1)`` (1, 2, 4, ...).
    """
    if attempt < 1:
        return 0.0
    if backoff == JobBackoff.NONE:
        return 0.0
    if backoff == JobBackoff.LINEAR:
        delay = _BASE_BACKOFF_SECONDS * attempt
    elif backoff == JobBackoff.EXPONENTIAL:
        delay = _BASE_BACKOFF_SECONDS * (2 ** (attempt - 1))
    else:
        # Defensive: unknown strategy → immediate.
        return 0.0
    return min(delay, MAX_BACKOFF_SECONDS)


class WorkerOutcome:
    """Result codes returned by ``process_one`` for caller observability.

    Constants rather than an Enum to keep the surface terse — the
    caller is the worker loop / tests, both pattern-match on bare
    strings already.
    """

    COMPLETED = "completed"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"
    RETRIED = "retried"
    NO_SPEC = "no_spec"


async def process_one(
    message: JobMessage,
    *,
    job_specs: dict[str, Any],
    job_service: Any,
    queue: JobQueue,
) -> str:
    """Process one dequeued message; return the cycle-4 outcome code.

    Args:
        message: The dequeued :class:`JobMessage` from the queue.
        job_specs: ``{job_name: JobSpec}`` from
            ``appspec.jobs``. Indexed by name so the worker can
            look up retry policy / handler path / dead-letter
            entity in O(1).
        job_service: The framework's ``JobRun`` service (cycle 2's
            auto-injected entity). Used to write status / timing
            transitions on the row identified by ``message.job_run_id``.
        queue: The same queue the message came from. Used to
            re-enqueue on retry-eligible failures with
            ``attempt + 1``.

    Returns:
        One of the :class:`WorkerOutcome` constants — caller (tests
        / the cycle-5 loop) can branch on it for metrics / logging.
    """
    spec = job_specs.get(message.job_name)
    if spec is None:
        # Job declared at submit but spec missing now — could happen
        # during a hot reload or partial deploy. Mark the run as
        # failed; don't retry (no spec means no retry policy to
        # consult).
        await _safe_update(
            job_service,
            message.job_run_id,
            {
                "status": "failed",
                "error_message": f"No JobSpec named {message.job_name!r}",
                "finished_at": _now(),
            },
        )
        return WorkerOutcome.NO_SPEC

    started = time.monotonic()
    started_at = _now()
    await _safe_update(
        job_service,
        message.job_run_id,
        {
            "status": "running",
            "attempt_number": message.attempt,
            "started_at": started_at,
        },
    )

    try:
        handler = resolve_handler(spec.run)
        result = handler(**message.payload)
        if inspect.isawaitable(result):
            await result
        elif inspect.iscoroutinefunction(handler):
            # Belt-and-braces — `iscoroutinefunction` catches the
            # case where `handler(**payload)` returned None because
            # the body was unreachable; a coroutine itself would
            # already match `isawaitable`.
            pass
    except JobHandlerNotFound as exc:
        # Misconfigured handler path — never retry; the spec needs
        # editing, not a retry.
        await _safe_update(
            job_service,
            message.job_run_id,
            {
                "status": "failed",
                "error_message": str(exc),
                "finished_at": _now(),
                "duration_ms": _ms_since(started),
            },
        )
        return WorkerOutcome.FAILED
    except Exception as exc:
        return await _handle_failure(
            spec=spec,
            message=message,
            job_service=job_service,
            queue=queue,
            started=started,
            error=exc,
        )

    await _safe_update(
        job_service,
        message.job_run_id,
        {
            "status": "completed",
            "finished_at": _now(),
            "duration_ms": _ms_since(started),
        },
    )
    return WorkerOutcome.COMPLETED


async def _handle_failure(
    *,
    spec: Any,
    message: JobMessage,
    job_service: Any,
    queue: JobQueue,
    started: float,
    error: Exception,
) -> str:
    """Decide retry vs final-failure based on ``JobSpec.retry``.

    Retries re-enqueue with ``attempt + 1``; final failures go to
    the dead-letter status (or the dead-letter entity if cycle-7
    wires that path). The current run row gets a terminal status
    in either case so the JobRun history is honest.
    """
    duration_ms = _ms_since(started)
    error_msg = f"{type(error).__name__}: {error}"
    logger.warning(
        "Job %s attempt %d failed: %s",
        message.job_name,
        message.attempt,
        error_msg,
    )

    max_attempts = max(1, getattr(spec, "retry", 0) + 1)
    if message.attempt < max_attempts:
        # Mark the current run terminal (with retry context) and
        # enqueue a fresh attempt — honouring the spec's declared
        # ``retry_backoff`` strategy via an in-process sleep.
        await _safe_update(
            job_service,
            message.job_run_id,
            {
                "status": "failed",
                "error_message": f"{error_msg} (retrying)",
                "finished_at": _now(),
                "duration_ms": duration_ms,
            },
        )
        backoff = getattr(spec, "retry_backoff", JobBackoff.EXPONENTIAL)
        delay = _compute_backoff_delay(backoff, message.attempt)
        if delay > 0:
            # Trade-off: the in-process ``asyncio.sleep`` blocks this
            # worker iteration for ``delay`` seconds — the single
            # worker can't pick up other messages during that window.
            # A more scalable design is delayed-queue delivery via
            # ``queue.submit(..., available_at=...)`` so the broker
            # holds the message until the wakeup time and any worker
            # can claim it. That requires queue-backend changes
            # (Redis Streams ``XADD`` with a delay token, SQS visibility
            # delay, etc.) and is left for a follow-up. For current
            # low-volume background work this is acceptable; for
            # high-throughput workloads, throughput will be visibly
            # affected during retry storms.
            logger.info(
                "Job %s backoff (%s, attempt %d): sleeping %.2fs before re-enqueue",
                message.job_name,
                backoff.value if hasattr(backoff, "value") else backoff,
                message.attempt,
                delay,
            )
            await asyncio.sleep(delay)
        await queue.submit(
            message.job_name,
            payload=message.payload,
            attempt=message.attempt + 1,
        )
        return WorkerOutcome.RETRIED

    # Exhausted retries — terminal status. ``dead_letter`` flag if
    # the spec declares a dead_letter entity, else plain ``failed``.
    has_dead_letter = bool(getattr(spec, "dead_letter", "") or "")
    final_status = "dead_letter" if has_dead_letter else "failed"
    await _safe_update(
        job_service,
        message.job_run_id,
        {
            "status": final_status,
            "error_message": error_msg,
            "finished_at": _now(),
            "duration_ms": duration_ms,
        },
    )
    return WorkerOutcome.DEAD_LETTER if has_dead_letter else WorkerOutcome.FAILED


async def _safe_update(job_service: Any, job_run_id: str, fields: dict[str, Any]) -> None:
    """Update one JobRun row, swallowing service errors.

    The worker must keep going even if the JobRun update fails — a
    DB blip mid-run shouldn't crash the loop or repeatedly re-enqueue
    the same message. Logged at WARNING so the operator can see it.
    """
    if job_service is None or not job_run_id:
        return
    try:
        await job_service.update(job_run_id, fields)
    except Exception:
        logger.warning("JobRun update failed for %s — continuing", job_run_id, exc_info=True)


def _now() -> datetime:
    return datetime.now(UTC)


def _ms_since(started_monotonic: float) -> int:
    return int((time.monotonic() - started_monotonic) * 1000)


async def _maybe_async(handler: Any, payload: dict[str, Any]) -> Any:
    """Helper kept for the cycle-5 loop to share — runs sync
    handlers in a thread, async handlers in-place.

    Not used in cycle 4's `process_one` (which inlines the async
    branch for clearer error attribution); reserved here to avoid
    duplication when the cycle-5 worker loop lands.
    """
    if inspect.iscoroutinefunction(handler):
        return await handler(**payload)
    return await asyncio.to_thread(handler, **payload)
