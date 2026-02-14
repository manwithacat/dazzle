"""
Pipeline CLI commands.

Commands:
- pipeline run: Execute the full deterministic quality pipeline
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer

pipeline_app = typer.Typer(
    help="Run the deterministic quality pipeline.",
    no_args_is_help=True,
)


@pipeline_app.command("run")
def pipeline_run(
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
        help="Stop pipeline on first error",
    ),
    base_url: str = typer.Option(
        None,
        "--base-url",
        help="Base URL of running server (enables live test step)",
    ),
    format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format: table (default) or json",
    ),
) -> None:
    """Run the full deterministic quality pipeline.

    Chains validation, linting, fidelity, composition, test generation,
    coverage, and semantic checks into a single run.

    Examples:
        dazzle pipeline run                         # Table output
        dazzle pipeline run --format json            # JSON for CI
        dazzle pipeline run --detail full            # Full detail
        dazzle pipeline run --stop-on-error          # Stop on first failure
        dazzle pipeline run --base-url http://localhost:8000  # Include live tests
    """
    from dazzle.mcp.server.handlers.pipeline import run_pipeline_handler

    manifest_path = Path(manifest).resolve()
    root = manifest_path.parent

    if not (root / "dazzle.toml").exists():
        typer.echo(f"No dazzle.toml found in {root}", err=True)
        raise typer.Exit(code=1)

    args: dict[str, object] = {
        "detail": detail,
        "stop_on_error": stop_on_error,
    }
    if base_url:
        args["base_url"] = base_url

    try:
        from dazzle.cli.activity import cli_activity

        with cli_activity(root, "pipeline", "run") as progress:
            args["_progress"] = progress
            raw = run_pipeline_handler(root, args)
        data = json.loads(raw)
    except Exception as e:
        typer.echo(f"Pipeline error: {e}", err=True)
        raise typer.Exit(code=1)

    if format == "json":
        typer.echo(json.dumps(data, indent=2))
    else:
        _print_pipeline_table(data)

    # Exit 1 if any step failed
    if data.get("status") != "passed":
        raise typer.Exit(code=1)


def _print_pipeline_table(data: dict[str, Any]) -> None:
    """Render a human-readable pipeline summary."""
    typer.secho("Pipeline Quality Report", bold=True)
    typer.echo("=" * 40)

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

    typer.echo()
    parts = [f"{passed}/{total} passed"]
    if failed:
        parts.append(f"{failed} failed")
    if skipped:
        parts.append(f"{skipped} skipped")
    parts.append(f"({total_secs:.1f}s total)")

    color = typer.colors.GREEN if failed == 0 else typer.colors.RED
    typer.secho(f"Summary: {', '.join(parts)}", fg=color, bold=True)
