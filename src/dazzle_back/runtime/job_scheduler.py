"""Cron-driven job scheduler loop (#953 cycle 7b).

Wraps cycle-7's pure cron primitives in an async loop that submits
jobs to the cycle-3 queue when their cron matches. Cycle-9's
`dazzle worker` CLI will start this alongside the worker loop.

Design notes
------------

* Each tick reads the current UTC time, calls `due_jobs`, and
  enqueues each due job. `last_fired_minute` is tracked per job
  to prevent double-firing if the loop ticks faster than a minute
  or catches up after a slow cycle.
* `tick_interval` defaults to 30s — fires twice per minute so a
  cron-on-the-minute job is enqueued within 30s of its trigger
  time. Tests can pass smaller values for fast feedback.
* All exceptions inside the loop body are caught + logged + counted
  in `loop_errors` — the scheduler must keep ticking even if a
  single submit blows up (queue down, etc.). Mirrors the cycle-5
  worker loop's resilience contract.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from dazzle_back.runtime.cron import (
    CronExpression,
    CronParseError,
    due_jobs,
    parse_cron,
)
from dazzle_back.runtime.job_queue import JobQueue

logger = logging.getLogger(__name__)


def parse_scheduled_jobs(jobs: list[Any]) -> list[tuple[str, CronExpression]]:
    """Extract `(job_name, parsed_cron)` pairs from `appspec.jobs`.

    Pure-trigger jobs (no `schedule:`) are silently skipped — the
    cycle-6 trigger wiring handles them. `CronParseError` from any
    invalid cron is *re-raised* with the job_name attached so the
    caller (cycle-9 startup) can surface a useful error rather
    than letting the scheduler silently no-op.
    """
    scheduled: list[tuple[str, CronExpression]] = []
    for job in jobs:
        schedule = getattr(job, "schedule", None)
        if schedule is None:
            continue
        cron_text = getattr(schedule, "cron", "") or ""
        if not cron_text:
            continue
        try:
            scheduled.append((job.name, parse_cron(cron_text)))
        except CronParseError as exc:
            raise CronParseError(
                f"Job {job.name!r} has invalid schedule {cron_text!r}: {exc}"
            ) from exc
    return scheduled


async def run_scheduler_loop(
    *,
    scheduled: list[tuple[str, CronExpression]],
    queue: JobQueue,
    stop_event: asyncio.Event,
    tick_interval: float = 30.0,
) -> dict[str, int]:
    """Tick every `tick_interval` seconds, submitting due jobs.

    Args:
        scheduled: `(job_name, parsed_cron)` pairs from
            `parse_scheduled_jobs`. Empty list = scheduler returns
            immediately (no purely-scheduled jobs in this app).
        queue: Cycle-3 `JobQueue`. Each due job becomes one
            submit per minute.
        stop_event: Trip to end the loop. Cycle-9 CLI wires
            SIGINT/SIGTERM to `stop_event.set()`.
        tick_interval: Seconds between ticks. Default 30s ensures
            cron-on-the-minute jobs fire within 30s. Tests pass
            smaller values for fast feedback.

    Returns:
        Stats dict with `enqueued` (count of submits), `ticks`,
        `loop_errors`. Dashboards / tests can rely on these keys
        being present even with zero scheduled jobs.
    """
    stats: dict[str, int] = {"enqueued": 0, "ticks": 0, "loop_errors": 0}
    last_fired: dict[str, datetime] = {}

    if not scheduled:
        logger.info("Scheduler loop: no scheduled jobs — exiting")
        return stats

    logger.info(
        "Scheduler loop starting (%d scheduled job%s, tick_interval=%.1fs)",
        len(scheduled),
        "" if len(scheduled) == 1 else "s",
        tick_interval,
    )

    while not stop_event.is_set():
        stats["ticks"] += 1
        try:
            now = datetime.now(UTC)
            due = due_jobs(scheduled, now=now, last_fired_minute=last_fired)
            minute_now = now.replace(second=0, microsecond=0)
            for name in due:
                try:
                    await queue.submit(name, payload={"scheduled_at": minute_now.isoformat()})
                    last_fired[name] = minute_now
                    stats["enqueued"] += 1
                except Exception:
                    stats["loop_errors"] += 1
                    logger.warning(
                        "Scheduler enqueue failed for %s — skipping this tick",
                        name,
                        exc_info=True,
                    )
        except Exception:
            # The cycle's own dispatch (due_jobs / now()) blew up —
            # rare but log + count + keep ticking.
            stats["loop_errors"] += 1
            logger.exception("Scheduler tick crashed — continuing")

        # Wait for the next tick OR the stop event, whichever comes
        # first. Using wait_for(stop_event.wait(), timeout=...) keeps
        # shutdown latency bounded by tick_interval.
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=tick_interval)
        except TimeoutError:
            pass  # Normal — next tick

    logger.info("Scheduler loop exiting; stats=%s", stats)
    return stats
