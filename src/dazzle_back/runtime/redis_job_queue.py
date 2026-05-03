"""Redis-backed job queue (#953 cycle 8).

Production-grade implementation of cycle-3's `JobQueue` Protocol.
Survives worker restarts, supports multiple worker processes, and
plays nicely with the existing redis.asyncio infra (api_cache,
metrics emitter).

Design
------

* **LPUSH / BRPOP** for FIFO semantics. New messages get added to
  the head; workers block-pop from the tail. With a single worker
  this is FIFO; with multiple workers it's "first available
  worker", which is what we want for parallel job processing.
* **JSON-serialised messages.** Each Redis list entry is a JSON
  blob with the cycle-3 `JobMessage` fields. Keeps the schema
  human-inspectable via `redis-cli`.
* **Lazy connection** — the cycle-3 worker may instantiate the
  queue at startup but only call `submit`/`dequeue` once
  triggers fire. Connection is established on first use; failure
  raises `RedisJobQueueError` with a clear message.
* **Default key namespace** is `dazzle:jobs:queue`. Cycle-9 CLI
  can override per environment so dev / staging / prod don't
  collide on a shared Redis.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import uuid4

from dazzle_back.runtime.job_queue import JobMessage

logger = logging.getLogger(__name__)


class RedisJobQueueError(RuntimeError):
    """Raised when the Redis client can't be established or used."""


class RedisJobQueue:
    """Cycle-3 `JobQueue` implementation backed by a Redis LIST.

    Satisfies the same Protocol as `InMemoryJobQueue` so the cycle-5
    worker loop can use either without code changes — the cycle-9
    CLI picks per `REDIS_URL` env presence.
    """

    def __init__(self, redis_url: str, *, key: str = "dazzle:jobs:queue") -> None:
        self._redis_url = redis_url
        self._key = key
        self._redis: Any = None

    async def _client(self) -> Any:
        """Lazy-connect to Redis; cache the client for re-use."""
        if self._redis is not None:
            return self._redis
        try:
            import redis.asyncio as aioredis

            self._redis = aioredis.from_url(self._redis_url, decode_responses=True)
            # `ping` surfaces auth / network errors at first use
            # rather than on the next `lpush`.
            await self._redis.ping()
            logger.info("RedisJobQueue connected (key=%r)", self._key)
        except ImportError as exc:
            raise RedisJobQueueError(
                "redis.asyncio is not available — install with `pip install redis>=5.0`"
            ) from exc
        except Exception as exc:
            self._redis = None
            raise RedisJobQueueError(f"Cannot connect to Redis: {exc}") from exc
        return self._redis

    async def submit(
        self,
        job_name: str,
        payload: dict[str, Any] | None = None,
        *,
        attempt: int = 1,
    ) -> str:
        """Enqueue a job; return the new `JobRun.id`."""
        job_run_id = str(uuid4())
        message_body = json.dumps(
            {
                "job_name": job_name,
                "payload": payload or {},
                "attempt": attempt,
                "job_run_id": job_run_id,
            },
            default=str,
        )
        client = await self._client()
        await client.lpush(self._key, message_body)
        return job_run_id

    async def dequeue(self, *, timeout: float | None = None) -> JobMessage | None:
        """Pop the next message, or None on timeout / empty.

        Redis BRPOP takes a timeout in **whole seconds** (0 = block
        indefinitely). Python None blocks indefinitely; numeric
        timeout is rounded up to the next whole second so the
        cycle-5 worker's idle ticks don't spin.
        """
        client = await self._client()
        if timeout is None:
            redis_timeout = 0  # block forever
        else:
            # Round up so a 0.5s caller timeout becomes 1s on the
            # wire (Redis can't represent sub-second waits here).
            # 0 has special meaning so floor at 1s.
            redis_timeout = max(1, int(timeout + 0.999))

        try:
            result = await client.brpop(self._key, timeout=redis_timeout)
        except Exception as exc:
            raise RedisJobQueueError(f"BRPOP failed: {exc}") from exc

        if result is None:
            return None  # timeout, empty queue
        # BRPOP returns (key, value) when it pops something.
        _key, raw = result
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError) as exc:
            # Corrupt / wrong-format entry. Log + drop so the
            # worker loop doesn't die on a single bad message.
            logger.warning("Discarding malformed Redis message %r: %s", raw, exc)
            return None
        return JobMessage(
            job_name=data.get("job_name", ""),
            payload=dict(data.get("payload") or {}),
            attempt=int(data.get("attempt", 1)),
            job_run_id=str(data.get("job_run_id", "")),
        )

    async def size(self) -> int:
        """Current queue depth — for tests / metrics."""
        client = await self._client()
        return int(await client.llen(self._key))

    async def close(self) -> None:
        """Release the Redis connection — call from cycle-9 CLI
        on shutdown to avoid leaking sockets."""
        if self._redis is None:
            return
        try:
            await self._redis.aclose()
        except Exception:
            logger.warning("RedisJobQueue close failed", exc_info=True)
        finally:
            self._redis = None
