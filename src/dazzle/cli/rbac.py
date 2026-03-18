"""RBAC verification CLI commands."""

from __future__ import annotations

import json

import typer

from dazzle.cli.common import resolve_project

rbac_app = typer.Typer(help="RBAC verification and compliance.", no_args_is_help=True)


@rbac_app.command("matrix")
def matrix(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m", help="Path to dazzle.toml"),
    format: str = typer.Option("table", "--format", "-f", help="Output format: table, json, csv"),
) -> None:
    """Generate static access matrix from DSL (no server required)."""
    from dazzle.core.appspec_loader import load_project_appspec
    from dazzle.rbac.matrix import generate_access_matrix

    root = resolve_project(manifest)
    appspec = load_project_appspec(root)
    access_matrix = generate_access_matrix(appspec)

    if format == "json":
        typer.echo(json.dumps(access_matrix.to_json(), indent=2))
    elif format == "csv":
        typer.echo(access_matrix.to_csv())
    else:
        typer.echo(access_matrix.to_table())

    for w in access_matrix.warnings:
        typer.echo(f"WARNING: {w.message}", err=True)
