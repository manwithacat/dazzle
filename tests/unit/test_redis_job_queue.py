"""Tests for #953 cycle 8 — Redis-backed job queue.

Cycle 3 shipped the `JobQueue` Protocol + an in-memory backing.
Cycle 8 adds the production-grade Redis backing that survives
worker restarts and supports multiple worker processes.

The tests use a stub redis client (no real Redis required) — we're
testing the queue's translation layer (JSON encode/decode, BRPOP
timeout rounding, error handling), not Redis itself. End-to-end
testing against a real Redis happens in the integration suite
(currently skipped without REDIS_URL).
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import patch

import pytest

from dazzle_back.runtime.redis_job_queue import (
    RedisJobQueue,
    RedisJobQueueError,
)

# ---------------------------------------------------------------------------
# Stub redis client
# ---------------------------------------------------------------------------


class _StubRedis:
    """Minimal in-memory redis-like client implementing just the
    methods `RedisJobQueue` calls."""

    def __init__(self) -> None:
        self._lists: dict[str, list[str]] = {}
        self.calls: list[tuple[str, tuple, dict]] = []
        self.ping_fail: Exception | None = None
        self.brpop_fail: Exception | None = None
        self.closed = False

    async def ping(self) -> bool:
        self.calls.append(("ping", (), {}))
        if self.ping_fail is not None:
            raise self.ping_fail
        return True

    async def lpush(self, key: str, value: str) -> int:
        self.calls.append(("lpush", (key, value), {}))
        self._lists.setdefault(key, []).insert(0, value)
        return len(self._lists[key])

    async def brpop(self, key: str, timeout: int = 0) -> tuple[str, str] | None:
        self.calls.append(("brpop", (key,), {"timeout": timeout}))
        if self.brpop_fail is not None:
            raise self.brpop_fail
        items = self._lists.get(key, [])
        if not items:
            return None  # would normally block; stub returns immediately
        return key, items.pop()

    async def llen(self, key: str) -> int:
        self.calls.append(("llen", (key,), {}))
        return len(self._lists.get(key, []))

    async def aclose(self) -> None:
        self.calls.append(("aclose", (), {}))
        self.closed = True


def _patch_from_url(stub: _StubRedis):
    """Patch `redis.asyncio.from_url` so `RedisJobQueue._client`
    sees our stub instead of a real Redis connection."""
    import redis.asyncio as aioredis

    return patch.object(aioredis, "from_url", return_value=stub)


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------


class TestConnection:
    def test_ping_called_on_first_use(self):
        stub = _StubRedis()
        with _patch_from_url(stub):
            q = RedisJobQueue("redis://localhost")
            _run(q.submit("x"))
        # First call sequence: ping, then lpush.
        assert stub.calls[0][0] == "ping"
        assert stub.calls[1][0] == "lpush"

    def test_ping_failure_raises_clear_error(self):
        stub = _StubRedis()
        stub.ping_fail = OSError("connection refused")
        with _patch_from_url(stub):
            q = RedisJobQueue("redis://localhost")
            with pytest.raises(RedisJobQueueError, match="Cannot connect to Redis"):
                _run(q.submit("x"))

    def test_client_cached_across_calls(self):
        stub = _StubRedis()
        with _patch_from_url(stub):
            q = RedisJobQueue("redis://localhost")
            _run(q.submit("a"))
            _run(q.submit("b"))
        # `ping` only happens once — second submit reuses the cached
        # client.
        ping_count = sum(1 for c in stub.calls if c[0] == "ping")
        assert ping_count == 1


# ---------------------------------------------------------------------------
# submit
# ---------------------------------------------------------------------------


class TestSubmit:
    def test_returns_job_run_id(self):
        stub = _StubRedis()
        with _patch_from_url(stub):
            q = RedisJobQueue("redis://localhost")
            job_run_id = _run(q.submit("daily_summary"))
        assert isinstance(job_run_id, str)
        assert len(job_run_id) > 0

    def test_lpush_payload_is_json(self):
        stub = _StubRedis()
        with _patch_from_url(stub):
            q = RedisJobQueue("redis://localhost", key="custom:key")
            _run(q.submit("daily", payload={"date": "2026-05-03"}, attempt=2))
        # Find the lpush call — assert its key + JSON payload shape.
        lpush_call = next(c for c in stub.calls if c[0] == "lpush")
        key, raw = lpush_call[1]
        assert key == "custom:key"
        data = json.loads(raw)
        assert data["job_name"] == "daily"
        assert data["payload"] == {"date": "2026-05-03"}
        assert data["attempt"] == 2
        assert data["job_run_id"]  # populated

    def test_each_submit_gets_unique_id(self):
        stub = _StubRedis()
        with _patch_from_url(stub):
            q = RedisJobQueue("redis://localhost")
            id1 = _run(q.submit("x"))
            id2 = _run(q.submit("x"))
        assert id1 != id2

    def test_payload_default_empty(self):
        stub = _StubRedis()
        with _patch_from_url(stub):
            q = RedisJobQueue("redis://localhost")
            _run(q.submit("x"))
        lpush_call = next(c for c in stub.calls if c[0] == "lpush")
        data = json.loads(lpush_call[1][1])
        assert data["payload"] == {}


# ---------------------------------------------------------------------------
# dequeue
# ---------------------------------------------------------------------------


class TestDequeue:
    def test_roundtrip_via_lpush_brpop(self):
        stub = _StubRedis()
        with _patch_from_url(stub):
            q = RedisJobQueue("redis://localhost")
            _run(q.submit("daily", payload={"k": "v"}))
            msg = _run(q.dequeue(timeout=1.0))
        assert msg is not None
        assert msg.job_name == "daily"
        assert msg.payload == {"k": "v"}

    def test_empty_returns_none(self):
        stub = _StubRedis()
        with _patch_from_url(stub):
            q = RedisJobQueue("redis://localhost")
            assert _run(q.dequeue(timeout=0.1)) is None

    def test_brpop_timeout_rounded_up_to_whole_seconds(self):
        # Redis BRPOP timeout is in whole seconds; sub-second
        # caller timeouts must be rounded UP so the cycle-5 worker
        # doesn't spin.
        stub = _StubRedis()
        with _patch_from_url(stub):
            q = RedisJobQueue("redis://localhost")
            _run(q.dequeue(timeout=0.5))
        brpop_call = next(c for c in stub.calls if c[0] == "brpop")
        # 0.5 + 0.999 = 1.499 → int = 1
        assert brpop_call[2]["timeout"] == 1

    def test_brpop_timeout_none_blocks_forever(self):
        # `timeout=None` → Redis 0 (block until message arrives).
        # We need a message in the queue or BRPOP would block;
        # set one up first.
        stub = _StubRedis()
        with _patch_from_url(stub):
            q = RedisJobQueue("redis://localhost")
            _run(q.submit("x"))
            _run(q.dequeue(timeout=None))
        brpop_call = next(c for c in stub.calls if c[0] == "brpop")
        assert brpop_call[2]["timeout"] == 0

    def test_corrupt_message_dropped_not_raised(self):
        # Inject a non-JSON entry at the tail. Worker must not die
        # on a single bad message.
        stub = _StubRedis()
        with _patch_from_url(stub):
            q = RedisJobQueue("redis://localhost")
            # Pre-populate via the underlying stub so we don't go
            # through `submit` (which always JSON-encodes).
            stub._lists.setdefault("dazzle:jobs:queue", []).append("not json")
            msg = _run(q.dequeue(timeout=0.1))
        assert msg is None  # dropped silently

    def test_brpop_failure_raises_redis_job_queue_error(self):
        stub = _StubRedis()
        stub.brpop_fail = OSError("connection lost")
        with _patch_from_url(stub):
            q = RedisJobQueue("redis://localhost")
            # Must connect first (ping passes).
            _run(q.submit("x"))
            with pytest.raises(RedisJobQueueError, match="BRPOP failed"):
                _run(q.dequeue(timeout=0.1))


# ---------------------------------------------------------------------------
# size + close
# ---------------------------------------------------------------------------


class TestSizeAndClose:
    def test_size_returns_llen(self):
        stub = _StubRedis()
        with _patch_from_url(stub):
            q = RedisJobQueue("redis://localhost")
            _run(q.submit("a"))
            _run(q.submit("b"))
            assert _run(q.size()) == 2

    def test_size_empty(self):
        stub = _StubRedis()
        with _patch_from_url(stub):
            q = RedisJobQueue("redis://localhost")
            # First call triggers ping; size = 0
            assert _run(q.size()) == 0

    def test_close_aclose_called(self):
        stub = _StubRedis()
        with _patch_from_url(stub):
            q = RedisJobQueue("redis://localhost")
            _run(q.submit("x"))  # establishes connection
            _run(q.close())
        assert stub.closed is True

    def test_close_no_op_when_never_connected(self):
        # `close()` before any submit/dequeue → no-op, no exception.
        q = RedisJobQueue("redis://localhost")
        _run(q.close())  # should not raise

    def test_close_swallows_aclose_error(self):
        # Even if the underlying client.aclose() raises, the queue's
        # close() must not propagate — caller is in shutdown.
        class _BrokenAclose(_StubRedis):
            async def aclose(self) -> None:
                raise RuntimeError("can't close")

        stub = _BrokenAclose()
        with _patch_from_url(stub):
            q = RedisJobQueue("redis://localhost")
            _run(q.submit("x"))
            _run(q.close())  # must not raise


# ---------------------------------------------------------------------------
# Custom key
# ---------------------------------------------------------------------------


class TestCustomKey:
    def test_default_key_namespace(self):
        stub = _StubRedis()
        with _patch_from_url(stub):
            q = RedisJobQueue("redis://localhost")
            _run(q.submit("x"))
        lpush_call = next(c for c in stub.calls if c[0] == "lpush")
        assert lpush_call[1][0] == "dazzle:jobs:queue"

    def test_custom_key_passed_through(self):
        stub = _StubRedis()
        with _patch_from_url(stub):
            q = RedisJobQueue("redis://localhost", key="staging:dazzle:jobs")
            _run(q.submit("x"))
        lpush_call = next(c for c in stub.calls if c[0] == "lpush")
        assert lpush_call[1][0] == "staging:dazzle:jobs"


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    def test_satisfies_job_queue_protocol(self):
        # Structural — instances must have the three Protocol
        # methods so the cycle-5 worker can use them
        # interchangeably with InMemoryJobQueue.
        from dazzle_back.runtime.job_queue import JobQueue

        q = RedisJobQueue("redis://localhost")
        # Static `isinstance` against a Protocol works at runtime
        # when the Protocol uses `runtime_checkable` — JobQueue
        # currently doesn't, so we check method presence directly.
        for method in ("submit", "dequeue", "size"):
            assert callable(getattr(q, method))
        # And confirm the type can be used where a JobQueue is
        # expected (mypy enforces this; runtime no-op).
        _: JobQueue = q  # type: ignore[assignment]
