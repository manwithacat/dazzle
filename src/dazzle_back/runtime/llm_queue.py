"""
Background job queue for async LLM intent execution.

Provides:
- In-process async queue with configurable workers
- Per-model semaphore (concurrency cap)
- Per-model token bucket (rate limiting)
- AIJob lifecycle management (pending → running → completed/failed)
- LLM event emission on completion/failure
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from dazzle_back.runtime.event_bus import LLMEventType

if TYPE_CHECKING:
    from dazzle_back.runtime.llm_executor import ExecutionResult, LLMIntentExecutor

logger = logging.getLogger(__name__)


# =============================================================================
# Token Bucket
# =============================================================================


class TokenBucket:
    """Rate limiter using the token bucket algorithm.

    Allows up to ``rate`` requests per minute, with burst capacity
    equal to the rate.
    """

    def __init__(self, rate_per_minute: int):
        self.rate = rate_per_minute
        self.tokens = float(rate_per_minute)
        self.max_tokens = float(rate_per_minute)
        self._refill_rate = rate_per_minute / 60.0  # tokens per second
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self.tokens = min(self.max_tokens, self.tokens + elapsed * self._refill_rate)
        self._last_refill = now

    async def acquire(self) -> None:
        """Wait until a token is available, then consume it."""
        while True:
            async with self._lock:
                self._refill()
                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return
            # Wait a short interval before retrying
            await asyncio.sleep(0.1)


# =============================================================================
# Job Data
# =============================================================================

CompletionCallback = Callable[["ExecutionResult", "LLMJob"], Awaitable[None]]


@dataclass
class LLMJob:
    """A queued LLM intent execution job."""

    job_id: str
    intent_name: str
    input_data: dict[str, Any]
    user_id: str | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    callback: CompletionCallback | None = None


# =============================================================================
# Job Queue
# =============================================================================


class LLMJobQueue:
    """Async job queue for LLM intent execution.

    Manages background workers that dequeue jobs, enforce rate limits
    and concurrency, execute intents, and emit events.
    """

    def __init__(
        self,
        executor: LLMIntentExecutor,
        ai_job_service: Any | None = None,
        event_bus: Any | None = None,
        rate_limits: dict[str, int] | None = None,
        concurrency: dict[str, int] | None = None,
    ):
        self._executor = executor
        self._ai_job_service = ai_job_service
        self._event_bus = event_bus
        self._queue: asyncio.Queue[LLMJob] = asyncio.Queue()
        self._workers: list[asyncio.Task[None]] = []
        self._running = False

        # Per-model rate limiters
        self._buckets: dict[str, TokenBucket] = {}
        for model, rate in (rate_limits or {}).items():
            self._buckets[model] = TokenBucket(rate)

        # Per-model concurrency limiters
        self._semaphores: dict[str, asyncio.Semaphore] = {}
        for model, limit in (concurrency or {}).items():
            self._semaphores[model] = asyncio.Semaphore(limit)

    async def submit(
        self,
        intent_name: str,
        input_data: dict[str, Any],
        *,
        user_id: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        callback: CompletionCallback | None = None,
    ) -> str:
        """Submit an intent for async execution.

        Returns the job_id immediately.
        """
        import uuid

        job_id = str(uuid.uuid4())

        # Create AIJob record with pending status
        if self._ai_job_service:
            try:
                resp = await asyncio.to_thread(
                    self._ai_job_service.execute,
                    action="create",
                    data={
                        "id": job_id,
                        "intent": intent_name,
                        "model": "",
                        "provider": "",
                        "status": "pending",
                        "entity_type": entity_type,
                        "entity_id": entity_id,
                        "user_id": user_id,
                    },
                )
                if resp and hasattr(resp, "get"):
                    job_id = resp.get("id", job_id)
            except Exception:
                logger.debug("Could not create AIJob record for %s", intent_name)

        job = LLMJob(
            job_id=job_id,
            intent_name=intent_name,
            input_data=input_data,
            user_id=user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            callback=callback,
        )
        await self._queue.put(job)
        logger.info("Queued LLM job %s for intent %s", job_id, intent_name)
        return job_id

    def _resolve_model_name(self, intent_name: str) -> str | None:
        """Resolve the model name for an intent (for rate limit lookup)."""
        intents = {i.name: i for i in (self._executor._appspec.llm_intents or [])}
        intent = intents.get(intent_name)
        if not intent:
            return None
        if intent.model_ref:
            return intent.model_ref
        config = self._executor._appspec.llm_config
        return config.default_model if config else None

    async def _execute_job(self, job: LLMJob) -> None:
        """Execute a single job with rate limiting and concurrency control."""
        model_name = self._resolve_model_name(job.intent_name)

        # Update status to running
        if self._ai_job_service:
            try:
                await asyncio.to_thread(
                    self._ai_job_service.execute,
                    action="update",
                    record_id=job.job_id,
                    data={"status": "running"},
                )
            except Exception:
                logger.debug("Failed to update AI job status", exc_info=True)

        # Acquire semaphore (concurrency limit)
        sem = self._semaphores.get(model_name) if model_name else None
        if sem:
            await sem.acquire()

        try:
            # Acquire token bucket (rate limit)
            bucket = self._buckets.get(model_name) if model_name else None
            if bucket:
                await bucket.acquire()

            # Execute the intent
            result = await self._executor.execute(
                job.intent_name,
                job.input_data,
                user_id=job.user_id,
            )

            # Emit event
            await self._emit_event(job, result)

            # Run callback (e.g. write-back)
            if job.callback:
                try:
                    await job.callback(result, job)
                except Exception:
                    logger.exception("Callback failed for job %s", job.job_id)

        finally:
            if sem:
                sem.release()

    async def _emit_event(self, job: LLMJob, result: ExecutionResult) -> None:
        """Emit llm_intent:completed or llm_intent:failed event."""
        if not self._event_bus:
            return

        event_type = LLMEventType.INTENT_COMPLETED if result.success else LLMEventType.INTENT_FAILED
        event_data = {
            "event_type": event_type.value,
            "intent_name": job.intent_name,
            "job_id": job.job_id,
            "success": result.success,
            "output": result.output,
            "tokens_in": result.tokens_in,
            "tokens_out": result.tokens_out,
            "cost_usd": str(result.cost_usd) if result.cost_usd else None,
            "duration_ms": result.duration_ms,
            "entity_type": job.entity_type,
            "entity_id": job.entity_id,
            "error": result.error,
        }

        # Use the event bus's handler mechanism
        from dazzle_back.runtime.event_bus import EntityEvent, EntityEventType

        event = EntityEvent(
            event_type=EntityEventType.UPDATED,  # Piggyback on entity event bus
            entity_name="AIJob",
            entity_id=job.job_id,
            data=event_data,
            user_id=job.user_id,
        )
        try:
            for handler in self._event_bus._handlers:
                await handler(event)
        except Exception:
            logger.debug("Failed to emit LLM event for job %s", job.job_id)

    async def _worker(self) -> None:
        """Background worker that processes queued jobs."""
        while self._running:
            try:
                job = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except TimeoutError:
                continue

            try:
                await self._execute_job(job)
            except Exception:
                logger.exception("Job %s failed unexpectedly", job.job_id)
            finally:
                self._queue.task_done()

    async def start(self, num_workers: int = 3) -> None:
        """Start background worker tasks."""
        if self._running:
            return
        self._running = True
        for i in range(num_workers):
            task = asyncio.create_task(self._worker(), name=f"llm-worker-{i}")
            self._workers.append(task)
        logger.info("Started %d LLM queue workers", num_workers)

    async def shutdown(self) -> None:
        """Drain queue and cancel workers."""
        self._running = False
        for task in self._workers:
            task.cancel()
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        logger.info("LLM queue shut down")

    @property
    def pending_count(self) -> int:
        """Number of jobs waiting in the queue."""
        return self._queue.qsize()
