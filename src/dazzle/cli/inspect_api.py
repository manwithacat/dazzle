"""
`dazzle inspect-api` — emit and diff the public API surface snapshot.

Cycle 1 covers the DSL-constructs surface only. Future cycles (per #961) will
add IR types, MCP tool schemas, public helpers, runtime URLs, and config.
"""

import sys

import typer

from dazzle.api_surface import (
    BASELINE_PATH,
    diff_against_baseline,
    snapshot_dsl_constructs,
)

inspect_api_app = typer.Typer(
    help="Inspect and snapshot the framework's public API surface.",
    no_args_is_help=True,
)


@inspect_api_app.command("dsl-constructs")
def dsl_constructs_command(
    write: bool = typer.Option(
        False,
        "--write",
        help="Overwrite the on-disk baseline at docs/api-surface/dsl-constructs.txt",
    ),
    diff: bool = typer.Option(
        False,
        "--diff",
        help="Print a unified diff against the on-disk baseline (exit 1 if drift)",
    ),
) -> None:
    """Snapshot the DSL constructs surface."""
    snapshot = snapshot_dsl_constructs()

    if write:
        BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
        BASELINE_PATH.write_text(snapshot)
        typer.echo(f"Wrote {BASELINE_PATH.relative_to(BASELINE_PATH.parents[2])}")
        return

    if diff:
        result = diff_against_baseline(snapshot)
        if not result:
            typer.echo("No drift.")
            return
        typer.echo(result, nl=False)
        sys.exit(1)

    typer.echo(snapshot, nl=False)
