"""
`dazzle inspect-api` — emit and diff the public API surface snapshot.

Each subcommand owns one lens onto the public surface (cycle of #961):

- `dsl-constructs`   — cycle 1: parser dispatch → IR class mapping
- `ir-types`         — cycle 2: every IR type re-exported from `dazzle.core.ir`

Future cycles add MCP tool schemas, public helpers, runtime URLs.
"""

import sys
from pathlib import Path

import typer

from dazzle.api_surface import (
    dsl_constructs_module,
    ir_types_module,
    mcp_tools_module,
)

inspect_api_app = typer.Typer(
    help="Inspect and snapshot the framework's public API surface.",
    no_args_is_help=True,
)


def _emit(snapshot: str, baseline_path: Path, write: bool, diff: bool) -> None:
    if write:
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(snapshot)
        typer.echo(f"Wrote {baseline_path.relative_to(baseline_path.parents[2])}")
        return

    if diff:
        if not baseline_path.exists():
            typer.echo(f"(no baseline at {baseline_path} — run with --write)")
            sys.exit(1)
        baseline = baseline_path.read_text()
        if baseline == snapshot:
            typer.echo("No drift.")
            return
        import difflib

        diff_text = "".join(
            difflib.unified_diff(
                baseline.splitlines(keepends=True),
                snapshot.splitlines(keepends=True),
                fromfile=str(baseline_path),
                tofile="(live)",
                n=3,
            )
        )
        typer.echo(diff_text, nl=False)
        sys.exit(1)

    typer.echo(snapshot, nl=False)


@inspect_api_app.command("dsl-constructs")
def dsl_constructs_command(
    write: bool = typer.Option(False, "--write", help="Overwrite the on-disk baseline"),
    diff: bool = typer.Option(False, "--diff", help="Print unified diff vs baseline"),
) -> None:
    """Cycle 1: snapshot the DSL constructs surface."""
    _emit(
        dsl_constructs_module.snapshot_dsl_constructs(),
        dsl_constructs_module.BASELINE_PATH,
        write,
        diff,
    )


@inspect_api_app.command("ir-types")
def ir_types_command(
    write: bool = typer.Option(False, "--write", help="Overwrite the on-disk baseline"),
    diff: bool = typer.Option(False, "--diff", help="Print unified diff vs baseline"),
) -> None:
    """Cycle 2: snapshot every IR type re-exported from dazzle.core.ir."""
    _emit(
        ir_types_module.snapshot_ir_types(),
        ir_types_module.BASELINE_PATH,
        write,
        diff,
    )


@inspect_api_app.command("mcp-tools")
def mcp_tools_command(
    write: bool = typer.Option(False, "--write", help="Overwrite the on-disk baseline"),
    diff: bool = typer.Option(False, "--diff", help="Print unified diff vs baseline"),
) -> None:
    """Cycle 3: snapshot the MCP tool registry (names + input schemas)."""
    _emit(
        mcp_tools_module.snapshot_mcp_tools(),
        mcp_tools_module.BASELINE_PATH,
        write,
        diff,
    )
