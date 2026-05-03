"""Retention sweep loop (#953 cycle 12 / #956 cycle 12).

Wraps cycle-11's ``run_retention_sweep`` orchestrator in an async
loop that fires daily on a configurable cron. Runs alongside the
cycle-5 worker loop and cycle-7b scheduler loop in the cycle-9
``dazzle worker`` CLI.

Why a separate loop rather than a synthetic JobSpec piped through
the regular scheduler?

  * Retention is **framework-internal** — it doesn't go through
    `JobSpec.run` resolution (cycle 3) because there's no
    user-author callable to dispatch.
  * Calling `run_retention_sweep` directly avoids a needless
    queue round-trip and keeps retention failures from showing
    up in the user's `JobRun` table as a generic "job failed"
    row.
  * Same cycle-7b cron infra is reused — `parse_cron`,
    `cron_matches`, `due_jobs`-equivalent dedupe — so retention
    fires at the operator-controlled minute, not "every tick".
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from dazzle_back.runtime.cron import CronParseError, cron_matches, parse_cron
from dazzle_back.runtime.retention_runner import run_retention_sweep

logger = logging.getLogger(__name__)


async def run_retention_loop(
    *,
    services: dict[str, Any],
    audits: list[Any] | None = None,
    stop_event: asyncio.Event,
    cron: str = "0 3 * * *",
    jobrun_retention_days: int = 30,
    tick_interval: float = 60.0,
) -> dict[str, int]:
    """Tick every ``tick_interval`` seconds, run retention when the
    cron matches.

    Args:
        services: Same ``{entity_name: BaseService}`` dict the
            cycle-9 CLI passes around. Looks up ``JobRun`` and
            ``AuditEntry`` lazily inside the runner.
        audits: ``appspec.audits`` list. None / empty = no audit
            cleanup (only JobRun retention runs).
        stop_event: Trip to end the loop. Cycle-9 CLI shares this
            with the worker + scheduler loops.
        cron: When to run. Default ``"0 3 * * *"`` = 03:00 UTC
            daily. Operators can override per environment to
            avoid clashing with backup windows.
        jobrun_retention_days: How long to keep `JobRun` rows
            (cycle-11 default 30).
        tick_interval: Seconds between cron-match checks. Default
            60s = once a minute, which is the resolution the
            5-field cron expression supports anyway.

    Returns:
        Stats dict with `runs` (count of retention sweeps),
        `ticks` (loop iterations), `loop_errors`, and the most
        recent per-source delete counts under
        ``last_*`` keys for cycle-9 CLI summary output.
    """
    stats: dict[str, int] = {"runs": 0, "ticks": 0, "loop_errors": 0}

    try:
        parsed_cron = parse_cron(cron)
    except CronParseError as exc:
        logger.error("Invalid retention cron %r: %s — loop disabled", cron, exc)
        return stats

    last_fired: datetime | None = None

    logger.info(
        "Retention loop starting (cron=%r, jobrun_retention_days=%d)",
        cron,
        jobrun_retention_days,
    )

    while not stop_event.is_set():
        stats["ticks"] += 1
        try:
            now = datetime.now(UTC).replace(second=0, microsecond=0)
            if cron_matches(parsed_cron, now) and last_fired != now:
                logger.info("Retention sweep firing at %s", now.isoformat())
                try:
                    sweep_stats = await run_retention_sweep(
                        services=services,
                        audits=audits or [],
                        jobrun_retention_days=jobrun_retention_days,
                    )
                    stats["runs"] += 1
                    for k, v in sweep_stats.items():
                        stats[f"last_{k}"] = v
                    last_fired = now
                except Exception:
                    stats["loop_errors"] += 1
                    logger.exception("Retention sweep failed — will retry next tick")
        except Exception:
            stats["loop_errors"] += 1
            logger.exception("Retention tick crashed — continuing")

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=tick_interval)
        except TimeoutError:
            pass

    logger.info("Retention loop exiting; stats=%s", stats)
    return stats
