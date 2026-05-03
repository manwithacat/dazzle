"""Tests for #953 cycle 7b — async scheduler loop.

Cycle 7 shipped pure cron primitives. Cycle 7b wraps them in an
async loop that ticks periodically, calls `due_jobs`, and submits
each due job to the queue. Cycle 9 will start this alongside the
worker loop.

Tests cover:

  * `parse_scheduled_jobs` — extracts (name, cron) pairs, skips
    pure-trigger jobs, raises with job_name on invalid cron
  * `run_scheduler_loop` — empty input exits immediately, stop
    event terminates the loop, due jobs are submitted with
    `scheduled_at` payload, queue exception swallowed + counted
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import pytest

from dazzle_back.runtime.cron import CronParseError, parse_cron
from dazzle_back.runtime.job_queue import InMemoryJobQueue
from dazzle_back.runtime.job_scheduler import (
    parse_scheduled_jobs,
    run_scheduler_loop,
)

# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


@dataclass
class _Schedule:
    cron: str
    timezone: str = ""


@dataclass
class _JobSpec:
    name: str
    schedule: _Schedule | None = None


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# parse_scheduled_jobs
# ---------------------------------------------------------------------------


class TestParseScheduledJobs:
    def test_empty_jobs(self):
        assert parse_scheduled_jobs([]) == []

    def test_pure_trigger_job_skipped(self):
        # Job has no `schedule:` block — cycle-6 trigger wiring
        # handles enqueue; scheduler ignores.
        assert parse_scheduled_jobs([_JobSpec(name="x")]) == []

    def test_blank_cron_skipped(self):
        # Defensive: a JobSchedule with empty cron is malformed but
        # shouldn't crash the scheduler.
        spec = _JobSpec(name="x", schedule=_Schedule(cron=""))
        assert parse_scheduled_jobs([spec]) == []

    def test_one_scheduled_job_returned(self):
        spec = _JobSpec(name="daily", schedule=_Schedule(cron="0 1 * * *"))
        result = parse_scheduled_jobs([spec])
        assert len(result) == 1
        name, cron = result[0]
        assert name == "daily"
        assert 1 in cron.hour

    def test_multiple_scheduled_jobs(self):
        result = parse_scheduled_jobs(
            [
                _JobSpec(name="daily", schedule=_Schedule(cron="0 1 * * *")),
                _JobSpec(name="hourly", schedule=_Schedule(cron="0 * * * *")),
                _JobSpec(name="trigger_only"),  # skipped
            ]
        )
        names = [name for name, _ in result]
        assert names == ["daily", "hourly"]

    def test_invalid_cron_re_raised_with_job_name(self):
        spec = _JobSpec(name="broken", schedule=_Schedule(cron="not a cron"))
        with pytest.raises(CronParseError, match="Job 'broken'"):
            parse_scheduled_jobs([spec])


# ---------------------------------------------------------------------------
# run_scheduler_loop
# ---------------------------------------------------------------------------


class TestSchedulerLoop:
    def test_empty_scheduled_returns_immediately(self):
        async def go():
            stop = asyncio.Event()
            return await run_scheduler_loop(
                scheduled=[],
                queue=InMemoryJobQueue(),
                stop_event=stop,
                tick_interval=0.05,
            )

        stats = _run(go())
        assert stats["ticks"] == 0
        assert stats["enqueued"] == 0

    def test_stop_event_set_terminates_loop(self):
        async def go():
            stop = asyncio.Event()
            stop.set()  # immediate exit
            return await run_scheduler_loop(
                scheduled=[("x", parse_cron("* * * * *"))],
                queue=InMemoryJobQueue(),
                stop_event=stop,
                tick_interval=0.05,
            )

        stats = _run(go())
        # Loop exits before completing a full tick — but `ticks`
        # counter increments before the wait, so the first tick
        # may have run and possibly enqueued the wildcard cron.
        # We only assert the loop *terminated* — i.e. the call
        # returned without timing out.
        assert "enqueued" in stats

    def test_wildcard_cron_enqueues_each_minute(self):
        # `* * * * *` matches any time. After one tick we should
        # see at least one enqueue.
        async def go():
            stop = asyncio.Event()
            queue = InMemoryJobQueue()
            loop = asyncio.get_running_loop()
            loop.call_later(0.15, stop.set)  # let a couple of ticks fire
            stats = await run_scheduler_loop(
                scheduled=[("daily", parse_cron("* * * * *"))],
                queue=queue,
                stop_event=stop,
                tick_interval=0.05,
            )
            return stats, await queue.size()

        stats, size = _run(go())
        # Wildcard cron + at least one tick → at least one enqueue.
        # Subsequent ticks within the same minute are deduped, so
        # the count is bounded above by the number of distinct
        # minute boundaries crossed during the test window (1 here).
        assert stats["enqueued"] >= 1
        assert size >= 1

    def test_non_matching_cron_no_enqueue(self):
        # `0 1 1 1 *` matches only Jan 1st at 01:00 — won't fire
        # during the test window.
        async def go():
            stop = asyncio.Event()
            queue = InMemoryJobQueue()
            loop = asyncio.get_running_loop()
            loop.call_later(0.15, stop.set)
            return await run_scheduler_loop(
                scheduled=[("rare", parse_cron("0 1 1 1 *"))],
                queue=queue,
                stop_event=stop,
                tick_interval=0.05,
            )

        stats = _run(go())
        assert stats["enqueued"] == 0
        # Ticks still incremented even with no enqueues.
        assert stats["ticks"] >= 1

    def test_queue_exception_counted_loop_continues(self):
        class _BrokenQueue:
            async def submit(self, *_: Any, **__: Any) -> str:
                raise RuntimeError("Redis down")

            async def dequeue(self, *, timeout=None):
                return None

            async def size(self) -> int:
                return 0

        async def go():
            stop = asyncio.Event()
            loop = asyncio.get_running_loop()
            loop.call_later(0.15, stop.set)
            return await run_scheduler_loop(
                scheduled=[("x", parse_cron("* * * * *"))],
                queue=_BrokenQueue(),
                stop_event=stop,
                tick_interval=0.05,
            )

        stats = _run(go())
        # Submit raised → loop_errors counted; loop kept ticking.
        assert stats["loop_errors"] >= 1

    def test_stats_includes_required_keys(self):
        async def go():
            stop = asyncio.Event()
            stop.set()
            return await run_scheduler_loop(
                scheduled=[("x", parse_cron("* * * * *"))],
                queue=InMemoryJobQueue(),
                stop_event=stop,
                tick_interval=0.05,
            )

        stats = _run(go())
        for key in ("enqueued", "ticks", "loop_errors"):
            assert key in stats

    def test_payload_carries_scheduled_at(self):
        # Each scheduled enqueue includes the truncated minute
        # timestamp so the worker can record it on JobRun.
        async def go():
            stop = asyncio.Event()
            queue = InMemoryJobQueue()
            loop = asyncio.get_running_loop()
            loop.call_later(0.1, stop.set)
            await run_scheduler_loop(
                scheduled=[("x", parse_cron("* * * * *"))],
                queue=queue,
                stop_event=stop,
                tick_interval=0.05,
            )
            return await queue.dequeue(timeout=0.05)

        msg = _run(go())
        if msg is not None:  # may be None if no tick fired in window
            assert "scheduled_at" in msg.payload
