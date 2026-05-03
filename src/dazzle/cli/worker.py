"""`dazzle worker` CLI (#953 cycle 9).

Starts the background-job worker + scheduler loops alongside (or
instead of) `dazzle serve`. Picks the queue backing per
`REDIS_URL` env presence — Redis when set, in-memory otherwise.

Wires SIGINT/SIGTERM to a shared `stop_event` so a Ctrl+C in dev
or a `kill -TERM` from systemd shuts both loops down cleanly,
draining in-flight jobs.

Job-run service wiring is deferred to a follow-up cycle — when
running standalone, status transitions are logged but not
persisted to `JobRun` rows. Cycle-2's `JobRun` entity is still
auto-injected by the linker; the eventual repository wiring will
let the worker write through it.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
from pathlib import Path
from typing import Any

import typer

from dazzle.cli.utils import load_project_appspec

worker_app = typer.Typer(help="Background-job worker + scheduler.")

logger = logging.getLogger(__name__)


@worker_app.callback(invoke_without_command=True)
def run(
    project_path: Path = typer.Option(  # noqa: B008
        Path("."),
        "--project",
        "-p",
        help="Path to the project root (defaults to current directory).",
    ),
    tick_interval: float = typer.Option(
        30.0,
        "--scheduler-tick",
        help="Seconds between scheduler ticks (default 30s).",
    ),
    idle_timeout: float = typer.Option(
        1.0,
        "--worker-idle",
        help="Seconds to wait per dequeue when the queue is empty.",
    ),
    redis_key: str = typer.Option(
        "dazzle:jobs:queue",
        "--redis-key",
        help="Redis list key (override per environment to avoid collisions).",
    ),
) -> None:
    """Run the background-job worker + scheduler until SIGINT/SIGTERM.

    The worker pulls jobs off the queue and runs them via the cycle-4
    `process_one`. The scheduler ticks every ``--scheduler-tick``
    seconds and submits any cron-due jobs to the same queue.

    Both loops share a stop event — closing one closes both.
    """
    typer.echo(f"Loading AppSpec from {project_path}")
    appspec = load_project_appspec(project_path)
    job_count = len(getattr(appspec, "jobs", []) or [])
    if job_count == 0:
        typer.echo("No `job:` declarations in this AppSpec. Worker has nothing to do.")
        raise typer.Exit(code=0)

    typer.echo(f"Found {job_count} job declaration{'' if job_count == 1 else 's'}")
    asyncio.run(
        _run_worker(
            appspec=appspec,
            tick_interval=tick_interval,
            idle_timeout=idle_timeout,
            redis_key=redis_key,
        )
    )


async def _run_worker(
    *,
    appspec: Any,
    tick_interval: float,
    idle_timeout: float,
    redis_key: str,
) -> None:
    """Main async entry — picks queue, wires signals, runs all loops."""
    from dazzle_back.runtime.job_loop import run_worker_loop
    from dazzle_back.runtime.job_scheduler import (
        parse_scheduled_jobs,
        run_scheduler_loop,
    )
    from dazzle_back.runtime.retention_loop import run_retention_loop

    queue, queue_kind = _build_queue(redis_key)
    typer.echo(f"Queue backing: {queue_kind}")

    job_specs = {job.name: job for job in appspec.jobs}
    scheduled = parse_scheduled_jobs(list(appspec.jobs))
    if scheduled:
        typer.echo(f"Scheduler: {len(scheduled)} scheduled job{'' if len(scheduled) == 1 else 's'}")

    audits = list(getattr(appspec, "audits", []) or [])
    typer.echo(
        f"Retention: JobRun + {len(audits)} audit"
        f"{'' if len(audits) == 1 else 's'} (daily 03:00 UTC)"
    )

    stop_event = asyncio.Event()
    _install_signal_handlers(stop_event)

    typer.echo("Worker started — Ctrl+C to stop")
    try:
        worker_task = asyncio.create_task(
            run_worker_loop(
                queue=queue,
                job_specs=job_specs,
                job_service=None,
                stop_event=stop_event,
                idle_timeout=idle_timeout,
            )
        )
        scheduler_task = asyncio.create_task(
            run_scheduler_loop(
                scheduled=scheduled,
                queue=queue,
                stop_event=stop_event,
                tick_interval=tick_interval,
            )
        )
        # #953 cycle 12 / #956 cycle 12 — retention loop alongside
        # worker + scheduler. Standalone worker has no service
        # dict yet (services live in the running FastAPI server),
        # so the retention loop runs but no-ops on missing
        # JobRun / AuditEntry until a follow-up cycle wires
        # services into the worker process.
        retention_task = asyncio.create_task(
            run_retention_loop(
                services={},
                audits=audits,
                stop_event=stop_event,
            )
        )
        worker_stats, scheduler_stats, retention_stats = await asyncio.gather(
            worker_task, scheduler_task, retention_task
        )
    finally:
        # Best-effort close — worker shuts down even if the queue's
        # already gone away.
        if hasattr(queue, "close"):
            try:
                await queue.close()
            except Exception:
                logger.warning("queue.close() failed", exc_info=True)

    typer.echo("")
    typer.echo("Worker stats:")
    for k, v in sorted(worker_stats.items()):
        typer.echo(f"  {k}: {v}")
    typer.echo("Scheduler stats:")
    for k, v in sorted(scheduler_stats.items()):
        typer.echo(f"  {k}: {v}")
    typer.echo("Retention stats:")
    for k, v in sorted(retention_stats.items()):
        typer.echo(f"  {k}: {v}")


def _build_queue(redis_key: str) -> tuple[Any, str]:
    """Pick the queue backing per ``REDIS_URL`` env presence.

    Returns (queue, label) — label printed at startup so the
    operator can see which backing was chosen.
    """
    redis_url = os.environ.get("REDIS_URL", "")
    if redis_url:
        from dazzle_back.runtime.redis_job_queue import RedisJobQueue

        return RedisJobQueue(redis_url, key=redis_key), f"Redis ({redis_key})"
    from dazzle_back.runtime.job_queue import InMemoryJobQueue

    return InMemoryJobQueue(), "in-memory (set REDIS_URL for persistence)"


def _install_signal_handlers(stop_event: asyncio.Event) -> None:
    """Wire SIGINT + SIGTERM to ``stop_event.set()``.

    asyncio's signal handler API requires the running loop, so this
    must be called from inside an async context.
    """
    loop = asyncio.get_running_loop()

    def _stop() -> None:
        if not stop_event.is_set():
            typer.echo("\nShutdown signal received — draining…")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _stop)
        except (NotImplementedError, RuntimeError):
            # Windows / some test environments don't support
            # signal handlers on the event loop. Fall back to
            # default Python behaviour (KeyboardInterrupt for
            # SIGINT, immediate for SIGTERM).
            logger.debug("Signal handler not installed for %s", sig)
