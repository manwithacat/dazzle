"""Tests for LLM job queue, token bucket, and semaphore."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from dazzle_back.runtime.llm_queue import LLMJobQueue, TokenBucket

# ---------------------------------------------------------------------------
# Token Bucket
# ---------------------------------------------------------------------------


class TestTokenBucket:
    @pytest.mark.asyncio
    async def test_acquire_consumes_token(self):
        bucket = TokenBucket(rate_per_minute=60)
        assert bucket.tokens == 60.0
        await bucket.acquire()
        assert bucket.tokens < 60.0

    @pytest.mark.asyncio
    async def test_bucket_refills_over_time(self):
        bucket = TokenBucket(rate_per_minute=600)  # 10/sec
        # Drain some tokens
        for _ in range(5):
            await bucket.acquire()
        tokens_after_drain = bucket.tokens
        # Wait a tiny bit for refill
        await asyncio.sleep(0.15)
        # Force refill by acquiring
        async with bucket._lock:
            bucket._refill()
        assert bucket.tokens > tokens_after_drain

    @pytest.mark.asyncio
    async def test_bucket_caps_at_max(self):
        bucket = TokenBucket(rate_per_minute=60)
        # Tokens should not exceed max even after long wait
        await asyncio.sleep(0.1)
        async with bucket._lock:
            bucket._refill()
        assert bucket.tokens <= bucket.max_tokens


# ---------------------------------------------------------------------------
# LLMJobQueue
# ---------------------------------------------------------------------------


def _mock_executor(appspec=None):
    executor = MagicMock()
    executor._appspec = appspec or MagicMock()
    executor._appspec.llm_intents = []
    executor._appspec.llm_config = MagicMock()
    executor._appspec.llm_config.default_model = "claude"

    async def mock_execute(intent_name, input_data, user_id=None):
        result = MagicMock()
        result.success = True
        result.output = '{"category": "billing"}'
        result.tokens_in = 100
        result.tokens_out = 50
        result.cost_usd = None
        result.duration_ms = 200
        result.error = None
        result.job_id = None
        return result

    executor.execute = mock_execute
    return executor


class TestLLMJobQueue:
    @pytest.mark.asyncio
    async def test_submit_returns_job_id(self):
        queue = LLMJobQueue(executor=_mock_executor())
        job_id = await queue.submit("classify", {"title": "test"})
        assert isinstance(job_id, str)
        assert len(job_id) > 0

    @pytest.mark.asyncio
    async def test_submit_enqueues_job(self):
        queue = LLMJobQueue(executor=_mock_executor())
        await queue.submit("classify", {"title": "test"})
        assert queue.pending_count == 1

    @pytest.mark.asyncio
    async def test_worker_processes_job(self):
        executor = _mock_executor()
        queue = LLMJobQueue(executor=executor)
        await queue.start(num_workers=1)

        await queue.submit("classify", {"title": "test"})
        # Wait for worker to process
        await asyncio.sleep(0.3)

        assert queue.pending_count == 0
        await queue.shutdown()

    @pytest.mark.asyncio
    async def test_callback_called_on_completion(self):
        executor = _mock_executor()
        queue = LLMJobQueue(executor=executor)
        await queue.start(num_workers=1)

        callback = AsyncMock()
        await queue.submit("classify", {"title": "test"}, callback=callback)

        await asyncio.sleep(0.3)
        callback.assert_called_once()
        await queue.shutdown()

    @pytest.mark.asyncio
    async def test_shutdown_cancels_workers(self):
        queue = LLMJobQueue(executor=_mock_executor())
        await queue.start(num_workers=2)
        assert len(queue._workers) == 2
        await queue.shutdown()
        assert len(queue._workers) == 0

    @pytest.mark.asyncio
    async def test_semaphore_limits_concurrency(self):
        queue = LLMJobQueue(
            executor=_mock_executor(),
            concurrency={"claude": 1},
        )
        assert "claude" in queue._semaphores
        assert queue._semaphores["claude"]._value == 1

    @pytest.mark.asyncio
    async def test_rate_limits_create_buckets(self):
        queue = LLMJobQueue(
            executor=_mock_executor(),
            rate_limits={"claude": 60},
        )
        assert "claude" in queue._buckets
        assert queue._buckets["claude"].rate == 60

    @pytest.mark.asyncio
    async def test_start_is_idempotent(self):
        queue = LLMJobQueue(executor=_mock_executor())
        await queue.start(num_workers=2)
        await queue.start(num_workers=2)  # Should not add more workers
        assert len(queue._workers) == 2
        await queue.shutdown()
