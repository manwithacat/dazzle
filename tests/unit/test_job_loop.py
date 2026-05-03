"""Tests for #953 cycle 5 — `run_worker_loop` async pump.

Cycle 4 added `process_one` (single-job lifecycle). Cycle 5 wraps
it in a long-running async loop with graceful-shutdown via
`stop_event`. Cycle 5b will plumb SIGINT/SIGTERM through the CLI;
this cycle ships the loop primitive that cycle-5b will instantiate.

Tests verify:

  * Stop event terminates the loop promptly
  * Multiple jobs processed in submission order
  * Idle dequeues counted in stats
  * Per-message exception in `process_one` doesn't kill the loop
  * Queue exception (Redis-down etc.) is swallowed + counted
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import patch

from dazzle_back.runtime.job_loop import run_worker_loop
from dazzle_back.runtime.job_queue import InMemoryJobQueue, JobMessage
from dazzle_back.runtime.job_worker import WorkerOutcome

# ---------------------------------------------------------------------------
# Shared handlers + stubs
# ---------------------------------------------------------------------------


_call_log: list[str] = []


def handler_ok(**kwargs: Any) -> str:
    _call_log.append(kwargs.get("name", "?"))
    return "ok"


@dataclass
class _SpecStub:
    name: str
    run: str
    retry: int = 0
    dead_letter: str = ""


@dataclass
class _JobServiceStub:
    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    async def update(self, job_run_id: str, fields: dict[str, Any]) -> None:
        self.calls.append((job_run_id, dict(fields)))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestStopEvent:
    def test_stop_event_set_before_start_returns_immediately(self):
        async def go():
            stop = asyncio.Event()
            stop.set()
            return await run_worker_loop(
                queue=InMemoryJobQueue(),
                job_specs={},
                job_service=None,
                stop_event=stop,
                idle_timeout=0.05,
            )

        stats = asyncio.run(go())
        # Loop never entered — all counters at zero.
        assert stats["polled"] == 0
        assert stats[WorkerOutcome.COMPLETED] == 0

    def test_stop_event_set_during_idle_terminates_loop(self):
        async def go():
            stop = asyncio.Event()
            queue = InMemoryJobQueue()
            # Schedule the stop after a couple of idle ticks.
            loop = asyncio.get_running_loop()
            loop.call_later(0.12, stop.set)
            return await run_worker_loop(
                queue=queue,
                job_specs={},
                job_service=None,
                stop_event=stop,
                idle_timeout=0.05,
            )

        stats = asyncio.run(go())
        # At least one idle dequeue happened before stop fired.
        assert stats["polled"] >= 1


class TestProcessing:
    def test_processes_multiple_messages(self):
        async def go():
            _call_log.clear()
            stop = asyncio.Event()
            queue = InMemoryJobQueue()
            await queue.submit("x", payload={"name": "first"})
            await queue.submit("x", payload={"name": "second"})

            spec = _SpecStub(name="x", run="tests.unit.test_job_loop:handler_ok")

            # Stop the loop slightly after both jobs should be processed.
            loop = asyncio.get_running_loop()
            loop.call_later(0.2, stop.set)

            return await run_worker_loop(
                queue=queue,
                job_specs={"x": spec},
                job_service=_JobServiceStub(),
                stop_event=stop,
                idle_timeout=0.05,
            )

        stats = asyncio.run(go())
        assert stats[WorkerOutcome.COMPLETED] == 2
        # Handlers ran in submission order.
        assert _call_log == ["first", "second"]


class TestExceptionResilience:
    def test_queue_exception_counted_and_loop_continues(self):
        # The queue raises on every dequeue. The loop must back off
        # (sleep idle_timeout) and keep going until stop fires —
        # never propagating the exception.
        class _BrokenQueue:
            async def submit(self, *_: Any, **__: Any) -> str:
                return ""

            async def dequeue(self, *, timeout: float | None = None) -> JobMessage | None:
                raise RuntimeError("Redis down")

            async def size(self) -> int:
                return 0

        async def go():
            stop = asyncio.Event()
            loop = asyncio.get_running_loop()
            loop.call_later(0.15, stop.set)
            return await run_worker_loop(
                queue=_BrokenQueue(),
                job_specs={},
                job_service=None,
                stop_event=stop,
                idle_timeout=0.05,
            )

        stats = asyncio.run(go())
        # At least one dequeue error counted.
        assert stats["loop_errors"] >= 1

    def test_process_one_exception_counted_not_propagated(self):
        # If process_one itself raises (worker plumbing bug), the
        # loop counts loop_errors and continues rather than dying.
        async def _raising_process_one(*args: Any, **kwargs: Any) -> str:
            raise RuntimeError("plumbing bug")

        async def go():
            _call_log.clear()
            stop = asyncio.Event()
            queue = InMemoryJobQueue()
            await queue.submit("x")
            spec = _SpecStub(name="x", run="tests.unit.test_job_loop:handler_ok")

            loop = asyncio.get_running_loop()
            loop.call_later(0.2, stop.set)

            with patch(
                "dazzle_back.runtime.job_loop.process_one",
                side_effect=_raising_process_one,
            ):
                return await run_worker_loop(
                    queue=queue,
                    job_specs={"x": spec},
                    job_service=None,
                    stop_event=stop,
                    idle_timeout=0.05,
                )

        stats = asyncio.run(go())
        assert stats["loop_errors"] >= 1
        # No outcome counters incremented because process_one never
        # returned a value.
        assert stats[WorkerOutcome.COMPLETED] == 0


class TestStatsShape:
    def test_stats_includes_all_outcomes(self):
        async def go():
            stop = asyncio.Event()
            stop.set()  # immediate exit
            return await run_worker_loop(
                queue=InMemoryJobQueue(),
                job_specs={},
                job_service=None,
                stop_event=stop,
            )

        stats = asyncio.run(go())
        # Pre-initialised so the cycle-5b CLI / dashboards can rely
        # on every outcome key being present even with zero traffic.
        for key in (
            WorkerOutcome.COMPLETED,
            WorkerOutcome.FAILED,
            WorkerOutcome.DEAD_LETTER,
            WorkerOutcome.RETRIED,
            WorkerOutcome.NO_SPEC,
            "polled",
            "loop_errors",
        ):
            assert key in stats
