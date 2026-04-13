"""`dazzle e2e env` subcommands — start/status/stop/logs for Mode A.

Thin wrappers around the async dazzle.e2e.runner primitives. `start` is
foreground (blocks until Ctrl+C or subprocess exits); the other commands
are one-shot reads or signals.
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import time
from pathlib import Path

import typer

from dazzle.e2e.lifecycle import LockFile
from dazzle.e2e.modes import get_mode
from dazzle.e2e.runner import ModeRunner

env_app = typer.Typer(
    name="env",
    help="Manage live example-app environments for Mode A fitness runs.",
    no_args_is_help=True,
)


def _find_repo_root() -> Path:
    """Walk upward from cwd to find the directory containing `examples/`."""
    cwd = Path.cwd()
    for parent in (cwd, *cwd.parents):
        if (parent / "examples").exists():
            return parent
    return cwd


def _example_root(example: str) -> Path:
    """Resolve an example name to its project root (examples/<name>)."""
    repo_root = _find_repo_root()
    candidate = repo_root / "examples" / example
    if candidate.exists() and (candidate / "dazzle.toml").exists():
        return candidate
    typer.echo(
        f"Could not find examples/{example}/ with dazzle.toml — run from within the Dazzle repo.",
        err=True,
    )
    raise typer.Exit(code=2)


@env_app.command("start")
def env_start(
    example: str = typer.Argument(..., help="Example app name (e.g. support_tickets)"),
    mode: str = typer.Option("a", "--mode", help="Mode name from MODE_REGISTRY"),
    fresh: bool = typer.Option(False, "--fresh", help="Force baseline rebuild / DB reset"),
    personas: str = typer.Option(
        "", "--personas", help="Comma-separated persona IDs for QA mode flags"
    ),
    db_policy: str = typer.Option(
        "", "--db-policy", help="Override default policy: preserve|fresh|restore"
    ),
) -> None:
    """Launch Mode A against an example app. Blocks until Ctrl+C."""
    project_root = _example_root(example)
    mode_spec = get_mode(mode)
    persona_list = [p.strip() for p in personas.split(",") if p.strip()] or None
    policy = db_policy or None

    async def _main() -> None:
        async with ModeRunner(
            mode_spec=mode_spec,
            project_root=project_root,
            personas=persona_list,
            db_policy=policy,  # type: ignore[arg-type]
            fresh=fresh,
        ) as conn:
            typer.echo(f"[mode-{mode_spec.name}] running at {conn.site_url}")
            typer.echo(f"[mode-{mode_spec.name}] api at {conn.api_url}")
            typer.echo(f"[mode-{mode_spec.name}] Ctrl+C to stop.")
            stop_event = asyncio.Event()

            # Cooperate with asyncio's signal machinery instead of replacing
            # ModeRunner's SIGINT handler. add_signal_handler works at a
            # different layer than signal.signal and doesn't overwrite the
            # runner's cleanup path.
            loop = asyncio.get_running_loop()
            try:
                loop.add_signal_handler(signal.SIGINT, stop_event.set)
            except NotImplementedError:
                # Windows asyncio doesn't support add_signal_handler.
                # Fall back to signal.signal there (runs in main thread).
                signal.signal(
                    signal.SIGINT,
                    lambda signum, frame: stop_event.set(),
                )

            try:
                await stop_event.wait()
            finally:
                try:
                    loop.remove_signal_handler(signal.SIGINT)
                except (NotImplementedError, ValueError):
                    pass

    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        pass


@env_app.command("status")
def env_status(
    example: str = typer.Argument("", help="Example name, or empty to list all examples"),
) -> None:
    """Show lock + runtime state for one or all examples."""
    if example:
        examples = [example]
    else:
        repo_root = _find_repo_root()
        examples_dir = repo_root / "examples"
        if not examples_dir.exists():
            typer.echo("No examples/ directory found.", err=True)
            raise typer.Exit(code=2)
        examples = sorted(
            p.name for p in examples_dir.iterdir() if p.is_dir() and (p / "dazzle.toml").exists()
        )

    for ex in examples:
        try:
            project_root = _example_root(ex)
        except typer.Exit:
            continue

        lock_path = project_root / ".dazzle" / "mode_a.lock"
        runtime_path = project_root / ".dazzle" / "runtime.json"

        lock = LockFile(lock_path)
        holder = lock.read_holder()

        runtime_data = None
        if runtime_path.exists():
            try:
                runtime_data = json.loads(runtime_path.read_text())
            except (OSError, json.JSONDecodeError):
                pass

        typer.echo(f"\n{ex}:")
        if holder is None:
            typer.echo("  lock:    (none)")
        else:
            typer.echo(
                f"  lock:    pid {holder['pid']} mode {holder['mode']} "
                f"(started {holder.get('started_at', '?')})"
            )
        if runtime_data is None:
            typer.echo("  runtime: (no runtime.json)")
        else:
            typer.echo(
                f"  runtime: ui {runtime_data.get('ui_url', '?')} "
                f"api {runtime_data.get('api_url', '?')}"
            )


@env_app.command("stop")
def env_stop(
    example: str = typer.Argument(..., help="Example app name"),
) -> None:
    """Kill any Mode A subprocess holding the lock for this example."""
    project_root = _example_root(example)
    lock_path = project_root / ".dazzle" / "mode_a.lock"

    lock = LockFile(lock_path)
    holder = lock.read_holder()
    if holder is None:
        typer.echo(f"[mode-a] no lock file at {lock_path}")
        return

    pid = holder.get("pid")
    if not isinstance(pid, int):
        typer.echo("[mode-a] malformed lock file — deleting")
        lock.release()
        return

    try:
        os.kill(pid, signal.SIGTERM)
        typer.echo(f"[mode-a] sent SIGTERM to pid {pid}")
    except ProcessLookupError:
        typer.echo(f"[mode-a] pid {pid} not alive — deleting stale lock")
        lock.release()
        return

    # Wait briefly for clean shutdown then escalate
    for _ in range(10):
        time.sleep(0.5)
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
    else:
        try:
            os.kill(pid, signal.SIGKILL)
            typer.echo(f"[mode-a] escalated to SIGKILL for pid {pid}")
        except ProcessLookupError:
            pass

    lock.release()


@env_app.command("logs")
def env_logs(
    example: str = typer.Argument(..., help="Example app name"),
    tail: int = typer.Option(50, "--tail", help="Number of trailing lines"),
) -> None:
    """Print the tail of the most recent Mode A log for this example."""
    project_root = _example_root(example)
    log_dir = project_root / ".dazzle" / "e2e-logs"
    if not log_dir.exists():
        typer.echo("(no logs)")
        return

    logs = sorted(log_dir.glob("mode_a-*.log"), key=lambda p: p.stat().st_mtime)
    if not logs:
        typer.echo("(no logs)")
        return

    latest = logs[-1]
    text = latest.read_text(errors="replace")
    lines = text.splitlines()
    typer.echo(f"--- {latest.name} (last {tail} lines) ---")
    for line in lines[-tail:]:
        typer.echo(line)
