"""Tests for #953 cycle 12 / #956 cycle 12 — retention loop.

Cycle 11 shipped the orchestrator. Cycle 12 wraps it in an async
loop that fires daily on a configurable cron, runs alongside the
worker + scheduler loops in the cycle-9 CLI.

Tests cover:

  * Stop event terminates the loop promptly
  * Loop ticks but doesn't fire when cron doesn't match
  * Loop fires when wildcard cron matches; dedupes within the
    same minute
  * `run_retention_sweep` exception swallowed + counted
  * Invalid cron logs error + returns immediately
  * Stats keys present in returned dict
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import patch

from dazzle_back.runtime.retention_loop import run_retention_loop


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Stop event + loop termination
# ---------------------------------------------------------------------------


class TestStopEvent:
    def test_stop_event_set_before_start_returns_immediately(self):
        async def go():
            stop = asyncio.Event()
            stop.set()
            return await run_retention_loop(
                services={},
                audits=[],
                stop_event=stop,
                tick_interval=0.05,
            )

        stats = _run(go())
        assert stats["ticks"] == 0
        assert stats["runs"] == 0

    def test_stop_event_set_during_idle_terminates_loop(self):
        async def go():
            stop = asyncio.Event()
            loop = asyncio.get_running_loop()
            loop.call_later(0.12, stop.set)
            return await run_retention_loop(
                services={},
                audits=[],
                stop_event=stop,
                cron="0 1 1 1 *",  # never matches in test window
                tick_interval=0.05,
            )

        stats = _run(go())
        assert stats["ticks"] >= 1
        assert stats["runs"] == 0


# ---------------------------------------------------------------------------
# Cron-driven firing
# ---------------------------------------------------------------------------


class TestCronFiring:
    def test_wildcard_cron_fires_at_least_once(self):
        # Patch run_retention_sweep to be a fast no-op so the test
        # can verify the loop body executes without doing actual
        # DB work.
        async def _stub_sweep(**_kwargs: Any) -> dict[str, int]:
            return {"JobRun": 0}

        async def go():
            stop = asyncio.Event()
            loop = asyncio.get_running_loop()
            loop.call_later(0.15, stop.set)
            with patch(
                "dazzle_back.runtime.retention_loop.run_retention_sweep",
                side_effect=_stub_sweep,
            ):
                return await run_retention_loop(
                    services={},
                    audits=[],
                    stop_event=stop,
                    cron="* * * * *",
                    tick_interval=0.05,
                )

        stats = _run(go())
        assert stats["runs"] >= 1

    def test_dedupes_within_same_minute(self):
        # With tick_interval=0.05 and cron="* * * * *", multiple
        # ticks fall within the same minute. The loop must fire
        # AT MOST ONCE per minute even with many ticks.
        call_count = {"n": 0}

        async def _counting_sweep(**_kwargs: Any) -> dict[str, int]:
            call_count["n"] += 1
            return {}

        async def go():
            stop = asyncio.Event()
            loop = asyncio.get_running_loop()
            loop.call_later(0.2, stop.set)
            with patch(
                "dazzle_back.runtime.retention_loop.run_retention_sweep",
                side_effect=_counting_sweep,
            ):
                await run_retention_loop(
                    services={},
                    audits=[],
                    stop_event=stop,
                    cron="* * * * *",
                    tick_interval=0.02,
                )

        _run(go())
        # ~10 ticks in 0.2s but only one minute boundary →
        # exactly one call.
        assert call_count["n"] == 1

    def test_non_matching_cron_no_runs(self):
        async def _stub_sweep(**_kwargs: Any) -> dict[str, int]:
            return {}

        async def go():
            stop = asyncio.Event()
            loop = asyncio.get_running_loop()
            loop.call_later(0.15, stop.set)
            with patch(
                "dazzle_back.runtime.retention_loop.run_retention_sweep",
                side_effect=_stub_sweep,
            ):
                return await run_retention_loop(
                    services={},
                    audits=[],
                    stop_event=stop,
                    cron="0 1 1 1 *",  # Jan 1st 01:00 only
                    tick_interval=0.05,
                )

        stats = _run(go())
        assert stats["runs"] == 0
        assert stats["ticks"] >= 1  # ticked but no fire


# ---------------------------------------------------------------------------
# Resilience
# ---------------------------------------------------------------------------


class TestResilience:
    def test_sweep_exception_counted_loop_continues(self):
        async def _broken_sweep(**_kwargs: Any) -> dict[str, int]:
            raise RuntimeError("DB blip")

        async def go():
            stop = asyncio.Event()
            loop = asyncio.get_running_loop()
            loop.call_later(0.15, stop.set)
            with patch(
                "dazzle_back.runtime.retention_loop.run_retention_sweep",
                side_effect=_broken_sweep,
            ):
                return await run_retention_loop(
                    services={},
                    audits=[],
                    stop_event=stop,
                    cron="* * * * *",
                    tick_interval=0.05,
                )

        stats = _run(go())
        # Exception swallowed + counted; loop kept ticking.
        assert stats["loop_errors"] >= 1
        assert stats["runs"] == 0

    def test_invalid_cron_returns_immediately(self):
        async def go():
            stop = asyncio.Event()
            return await run_retention_loop(
                services={},
                audits=[],
                stop_event=stop,
                cron="not a cron",
                tick_interval=0.05,
            )

        stats = _run(go())
        assert stats["ticks"] == 0
        assert stats["runs"] == 0


# ---------------------------------------------------------------------------
# Stats shape
# ---------------------------------------------------------------------------


class TestStatsShape:
    def test_baseline_keys_always_present(self):
        async def go():
            stop = asyncio.Event()
            stop.set()
            return await run_retention_loop(
                services={},
                audits=[],
                stop_event=stop,
            )

        stats = _run(go())
        for key in ("runs", "ticks", "loop_errors"):
            assert key in stats

    def test_last_source_keys_added_after_run(self):
        async def _sweep_with_stats(**_kwargs: Any) -> dict[str, int]:
            return {"JobRun": 5, "AuditEntry:Manuscript": 3}

        async def go():
            stop = asyncio.Event()
            loop = asyncio.get_running_loop()
            loop.call_later(0.12, stop.set)
            with patch(
                "dazzle_back.runtime.retention_loop.run_retention_sweep",
                side_effect=_sweep_with_stats,
            ):
                return await run_retention_loop(
                    services={},
                    audits=[],
                    stop_event=stop,
                    cron="* * * * *",
                    tick_interval=0.05,
                )

        stats = _run(go())
        assert stats.get("last_JobRun") == 5
        assert stats.get("last_AuditEntry:Manuscript") == 3
