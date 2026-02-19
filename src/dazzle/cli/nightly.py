"""
Nightly CLI commands.

Commands:
- nightly run: Execute quality steps in parallel
"""

from __future__ import annotations

import json
from typing import Any

import typer

nightly_app = typer.Typer(
    help="Run quality checks in parallel (faster pipeline).",
    no_args_is_help=True,
)


@nightly_app.command("run")
def nightly_run(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    detail: str = typer.Option(
        "issues",
        "--detail",
        "-d",
        help="Detail level: metrics (compact), issues (default), full",
    ),
    stop_on_error: bool = typer.Option(
        False,
        "--stop-on-error",
        help="Stop on first error",
    ),
    base_url: str = typer.Option(
        None,
        "--base-url",
        help="Base URL of running server (enables live test step)",
    ),
    workers: int = typer.Option(
        4,
        "--workers",
        "-w",
        help="Max parallel workers (default: 4)",
    ),
    format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format: table (default) or json",
    ),
) -> None:
    """Run quality checks in parallel.

    Same steps as ``dazzle pipeline run`` but fans out independent steps
    using a thread pool for faster wall-clock time.

    Examples:
        dazzle nightly run                          # Table output
        dazzle nightly run --format json             # JSON for CI
        dazzle nightly run --workers 8               # More parallelism
        dazzle nightly run --stop-on-error           # Stop on first failure
        dazzle nightly run --base-url http://localhost:8000  # Include live tests
    """
    from dazzle.cli.common import resolve_project, run_mcp_handler
    from dazzle.mcp.server.handlers.nightly import run_nightly_handler

    root = resolve_project(manifest)
    args: dict[str, object] = {
        "detail": detail,
        "stop_on_error": stop_on_error,
        "workers": workers,
    }
    if base_url:
        args["base_url"] = base_url

    def _inject_activity_store(a: dict[str, object]) -> None:
        from dazzle.mcp.server.state import get_activity_store

        a["_activity_store"] = get_activity_store()

    data = run_mcp_handler(
        root,
        "nightly",
        "run",
        run_nightly_handler,
        args,
        error_label="Nightly",
        setup=_inject_activity_store,
    )

    if format == "json":
        typer.echo(json.dumps(data, indent=2))
    else:
        _print_nightly_table(data)

    if data.get("status") != "passed":
        raise typer.Exit(code=1)


def _print_nightly_table(data: dict[str, Any]) -> None:
    """Render a human-readable nightly summary."""
    typer.secho("Nightly Quality Report (parallel)", bold=True)
    typer.echo("=" * 44)

    steps = data.get("steps", [])
    for step in steps:
        step_num = step.get("step", "?")
        operation = step.get("operation", "unknown")
        status = step.get("status", "unknown")
        duration = step.get("duration_ms")
        duration_str = f"{duration:.0f}ms" if duration is not None else ""

        if status == "passed":
            mark = typer.style(" \u2713 ", fg=typer.colors.GREEN)
        elif status == "error":
            mark = typer.style(" \u2717 ", fg=typer.colors.RED)
        elif status == "skipped":
            mark = typer.style(" - ", fg=typer.colors.YELLOW)
        else:
            mark = "   "

        line = f"{mark} {step_num:>2}. {operation:<30} {duration_str:>8}"

        if status == "error":
            error_msg = step.get("error", "")
            if error_msg:
                line += f"  \u2192 {error_msg}"

        typer.echo(line)

    # Summary
    summary = data.get("summary", {})
    passed = summary.get("passed", 0)
    failed = summary.get("failed", 0)
    skipped = summary.get("skipped", 0)
    total = summary.get("total_steps", 0)
    total_ms = data.get("total_duration_ms", 0)
    total_secs = total_ms / 1000

    meta = data.get("_meta", {})
    workers = meta.get("workers", "?")

    typer.echo()
    parts = [f"{passed}/{total} passed"]
    if failed:
        parts.append(f"{failed} failed")
    if skipped:
        parts.append(f"{skipped} skipped")
    parts.append(f"({total_secs:.1f}s wall, {workers} workers)")

    color = typer.colors.GREEN if failed == 0 else typer.colors.RED
    typer.secho(f"Summary: {', '.join(parts)}", fg=color, bold=True)
