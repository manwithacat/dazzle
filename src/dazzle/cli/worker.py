"""`dazzle worker` CLI (#953 cycle 9, service wiring #992).

Starts the background-job worker + scheduler loops alongside (or
instead of) `dazzle serve`. Picks the queue backing per
`REDIS_URL` env presence — Redis when set, in-memory otherwise.

Wires SIGINT/SIGTERM to a shared `stop_event` so a Ctrl+C in dev
or a `kill -TERM` from systemd shuts both loops down cleanly,
draining in-flight jobs.

The worker opens its own DB pool (separate from `dazzle serve`'s)
and builds CRUD services for `JobRun` + `AuditEntry`, so status
transitions persist and the retention sweep actually deletes
expired rows. Without `DATABASE_URL` set, falls back to log-only
behaviour.
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
    from dazzle.http.runtime.job_loop import run_worker_loop
    from dazzle.http.runtime.job_scheduler import (
        parse_scheduled_jobs,
        run_scheduler_loop,
    )
    from dazzle.http.runtime.retention_loop import run_retention_loop

    queue, queue_kind = _build_queue(redis_key)
    typer.echo(f"Queue backing: {queue_kind}")

    # Build and start the process adapter (CONSUME side of the dual-boot-path).
    process_adapter = await _start_process_adapter()

    job_specs = {job.name: job for job in appspec.jobs}
    scheduled = parse_scheduled_jobs(list(appspec.jobs))
    if scheduled:
        typer.echo(f"Scheduler: {len(scheduled)} scheduled job{'' if len(scheduled) == 1 else 's'}")

    audits = list(getattr(appspec, "audits", []) or [])
    typer.echo(
        f"Retention: JobRun + {len(audits)} audit"
        f"{'' if len(audits) == 1 else 's'} (daily 03:00 UTC)"
    )

    services, db_manager = await _build_services(appspec)
    if services:
        typer.echo(f"Services: {', '.join(sorted(services.keys()))} (writes will persist)")
    else:
        typer.echo("Services: none (DATABASE_URL not set — writes are log-only)")

    stop_event = asyncio.Event()
    _install_signal_handlers(stop_event)

    typer.echo("Worker started — Ctrl+C to stop")
    try:
        worker_task = asyncio.create_task(
            run_worker_loop(
                queue=queue,
                job_specs=job_specs,
                job_service=services.get("JobRun"),
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
        retention_task = asyncio.create_task(
            run_retention_loop(
                services=services,
                audits=audits,
                stop_event=stop_event,
            )
        )
        worker_stats, scheduler_stats, retention_stats = await asyncio.gather(
            worker_task, scheduler_task, retention_task
        )
    finally:
        await _teardown(queue=queue, process_adapter=process_adapter, db_manager=db_manager)

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


async def _start_process_adapter(
    adapter_cls: type | None = None,
) -> Any | None:
    """Build and initialise the process adapter (CONSUME side).

    This is the CONSUME side of the dual-boot-path (#1422/#1428 lesson):
    the same factory + auto-detect logic that ProcessSubsystem uses on the
    http (enqueue) side so both paths agree on the same backend.

    Returns the initialised adapter, or ``None`` if no backend is available
    or initialisation fails (process runs will not be consumed but the job
    worker continues).
    """
    adapter = _build_process_adapter(adapter_cls)
    if adapter is None:
        typer.echo("Process adapter: none (set DATABASE_URL or REDIS_URL to enable)")
        return None
    try:
        await adapter.initialize()
        typer.echo(
            f"Process adapter: {type(adapter).__name__} (consumer + scheduler loops started)"
        )
        return adapter
    except Exception as exc:
        logger.warning(
            "Process adapter initialization failed (process runs will not be consumed): %s",
            exc,
        )
        return None


async def _teardown(
    *,
    queue: Any,
    process_adapter: Any | None,
    db_manager: Any | None,
) -> None:
    """Best-effort teardown of queue, process adapter, and DB pool."""
    if hasattr(queue, "close"):
        try:
            await queue.close()
        except Exception:
            logger.warning("queue.close() failed", exc_info=True)
    if process_adapter is not None and hasattr(process_adapter, "shutdown"):
        try:
            await process_adapter.shutdown()
        except Exception:
            logger.warning("process_adapter.shutdown() failed", exc_info=True)
    if db_manager is not None:
        try:
            db_manager.close_pool()
        except Exception:
            logger.warning("db_manager.close_pool() failed", exc_info=True)


async def _build_services(appspec: Any) -> tuple[dict[str, Any], Any | None]:
    """Build the worker's CRUD services for `JobRun` + `AuditEntry` (#992).

    Returns ``({}, None)`` when ``DATABASE_URL`` is unset — the
    worker still runs, but loops degrade to log-only persistence.
    The same fallback is used when service construction fails so a
    transient DB hiccup at boot doesn't block the queue from
    pumping (writes will retry next restart).
    """
    db_url = os.environ.get("DATABASE_URL", "").strip()
    if not db_url:
        return {}, None

    try:
        from dazzle.http.runtime.worker_services import build_worker_services

        return build_worker_services(appspec, db_url)
    except Exception as exc:
        logger.warning("Service wiring failed (writes will be log-only): %s", exc)
        return {}, None


def _build_process_adapter(
    adapter_cls: type | None = None,
) -> Any | None:
    """Build the process adapter for the CONSUME side (dazzle worker).

    Routes through ``create_adapter(ProcessConfig())`` so auto-detection
    matches exactly what ``ProcessSubsystem`` uses on the http ENQUEUE side —
    the dual-boot-path agreement required by #1422/#1428.

    * DATABASE_URL set (no REDIS_URL) → ``PostgresProcessAdapter``
    * REDIS_URL set (no DATABASE_URL) → ``EventBusProcessAdapter``
    * Both set → Postgres (factory preference: Postgres > EventBus)
    * Neither set → returns ``None`` (graceful: process runs skipped)

    The optional *adapter_cls* parameter is the test-injection escape hatch;
    it mirrors the ``config.process_adapter_class`` field in ``ProcessSubsystem``.
    """
    if adapter_cls is not None:
        return adapter_cls()

    try:
        from dazzle.core.process.factory import ProcessConfig, create_adapter

        return create_adapter(ProcessConfig())
    except ValueError:
        # No backend available (neither DATABASE_URL nor REDIS_URL set).
        return None
    except Exception as exc:
        logger.warning("Process adapter construction failed: %s", exc)
        return None


def _build_queue(redis_key: str) -> tuple[Any, str]:
    """Pick the queue backing per ``REDIS_URL`` env presence.

    Returns (queue, label) — label printed at startup so the
    operator can see which backing was chosen.
    """
    redis_url = os.environ.get("REDIS_URL", "")
    if redis_url:
        from dazzle.http.runtime.redis_job_queue import RedisJobQueue

        return RedisJobQueue(redis_url, key=redis_key), f"Redis ({redis_key})"
    from dazzle.http.runtime.job_queue import InMemoryJobQueue

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
