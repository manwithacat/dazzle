"""
CLI commands for demo data management.

Commands:
  dazzle demo load      — Load seed data into a running instance
  dazzle demo validate  — Validate seed files against DSL
  dazzle demo reset     — Clear and reload demo data
"""

from __future__ import annotations

from pathlib import Path

import typer

demo_app = typer.Typer(help="Demo data management commands.", no_args_is_help=True)


def _find_data_dir(project_root: Path) -> Path | None:
    """Find the demo data directory, checking demo_data/ then .dazzle/demo_data/."""
    for candidate in [
        project_root / "demo_data",
        project_root / ".dazzle" / "demo_data",
    ]:
        if candidate.is_dir():
            return candidate
    return None


@demo_app.command(name="load")
def load_command(
    base_url: str = typer.Option(
        "http://localhost:8000",
        "--base-url",
        "-u",
        help="Base URL of the running Dazzle instance",
    ),
    email: str = typer.Option(
        None,
        "--email",
        "-e",
        help="Admin email for authentication",
    ),
    password: str = typer.Option(
        None,
        "--password",
        "-p",
        help="Admin password for authentication",
    ),
    data_dir: Path | None = typer.Option(
        None,
        "--data-dir",
        "-d",
        help="Path to seed data directory (auto-detected if omitted)",
    ),
    entities: str | None = typer.Option(
        None,
        "--entities",
        help="Comma-separated entity names to load (default: all)",
    ),
    project_root: Path = typer.Option(
        Path("."),
        "--project",
        help="Project root directory",
    ),
) -> None:
    """Load demo seed data into a running Dazzle instance."""
    from dazzle.demo_data.loader import DemoDataLoader, topological_sort_entities

    project_root = project_root.resolve()

    # Parse DSL to get entity graph
    typer.echo("Parsing DSL...")
    try:
        from dazzle.cli.utils import load_project_appspec

        appspec = load_project_appspec(project_root)
    except Exception as e:
        typer.echo(f"Failed to parse DSL: {e}", err=True)
        raise typer.Exit(1)

    # Find data directory
    if data_dir is None:
        data_dir = _find_data_dir(project_root)
        if data_dir is None:
            typer.echo(
                "No demo data directory found. Run 'dazzle demo_data generate' first.", err=True
            )
            raise typer.Exit(1)
    typer.echo(f"Data directory: {data_dir}")

    # Topological sort
    entity_order = topological_sort_entities(appspec.domain.entities)
    typer.echo(f"Entity load order: {', '.join(entity_order)}")

    # Parse entity filter
    entities_filter = [e.strip() for e in entities.split(",")] if entities else None

    # Load
    with DemoDataLoader(base_url=base_url, email=email, password=password) as loader:
        if email and password:
            typer.echo("Authenticating...")
            try:
                loader.authenticate()
            except RuntimeError as e:
                typer.echo(f"Authentication failed: {e}", err=True)
                raise typer.Exit(1)

        typer.echo("Loading demo data...")
        report = loader.load_all(data_dir, entity_order, entities_filter=entities_filter)

    typer.echo("")
    typer.echo(report.summary())

    if report.total_failed > 0:
        raise typer.Exit(1)


@demo_app.command(name="validate")
def validate_command(
    data_dir: Path | None = typer.Option(
        None,
        "--data-dir",
        "-d",
        help="Path to seed data directory (auto-detected if omitted)",
    ),
    project_root: Path = typer.Option(
        Path("."),
        "--project",
        help="Project root directory",
    ),
) -> None:
    """Validate seed files against the DSL entity definitions."""
    from dazzle.demo_data.loader import validate_seed_data

    project_root = project_root.resolve()

    # Parse DSL
    typer.echo("Parsing DSL...")
    try:
        from dazzle.cli.utils import load_project_appspec

        appspec = load_project_appspec(project_root)
    except Exception as e:
        typer.echo(f"Failed to parse DSL: {e}", err=True)
        raise typer.Exit(1)

    # Find data directory
    if data_dir is None:
        data_dir = _find_data_dir(project_root)
        if data_dir is None:
            typer.echo("No demo data directory found.", err=True)
            raise typer.Exit(1)

    typer.echo(f"Validating seed data in {data_dir}...")
    errors = validate_seed_data(data_dir, appspec.domain.entities)

    if errors:
        typer.echo(f"\n{len(errors)} validation errors found:")
        for err in errors:
            typer.echo(f"  - {err}")
        raise typer.Exit(1)
    else:
        typer.echo("All seed data is valid.")


@demo_app.command(name="reset")
def reset_command(
    base_url: str = typer.Option(
        "http://localhost:8000",
        "--base-url",
        "-u",
        help="Base URL of the running Dazzle instance",
    ),
    email: str = typer.Option(
        None,
        "--email",
        "-e",
        help="Admin email for authentication",
    ),
    password: str = typer.Option(
        None,
        "--password",
        "-p",
        help="Admin password for authentication",
    ),
    data_dir: Path | None = typer.Option(
        None,
        "--data-dir",
        "-d",
        help="Path to seed data directory (auto-detected if omitted)",
    ),
    project_root: Path = typer.Option(
        Path("."),
        "--project",
        help="Project root directory",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip confirmation prompt",
    ),
) -> None:
    """Clear all entity data and reload from seed files.

    WARNING: This deletes all existing data in reverse dependency order,
    then reloads from seed files.
    """
    from dazzle.demo_data.loader import DemoDataLoader, topological_sort_entities

    project_root = project_root.resolve()

    if not yes:
        confirm = typer.confirm("This will DELETE all entity data and reload. Continue?")
        if not confirm:
            raise typer.Abort()

    # Parse DSL
    typer.echo("Parsing DSL...")
    try:
        from dazzle.cli.utils import load_project_appspec

        appspec = load_project_appspec(project_root)
    except Exception as e:
        typer.echo(f"Failed to parse DSL: {e}", err=True)
        raise typer.Exit(1)

    # Find data directory
    if data_dir is None:
        data_dir = _find_data_dir(project_root)
        if data_dir is None:
            typer.echo("No demo data directory found.", err=True)
            raise typer.Exit(1)

    entity_order = topological_sort_entities(appspec.domain.entities)

    with DemoDataLoader(base_url=base_url, email=email, password=password) as loader:
        if email and password:
            typer.echo("Authenticating...")
            try:
                loader.authenticate()
            except RuntimeError as e:
                typer.echo(f"Authentication failed: {e}", err=True)
                raise typer.Exit(1)

        # Delete in reverse order (children first)
        client = loader._get_client()
        typer.echo("Deleting existing data (reverse dependency order)...")
        for entity_name in reversed(entity_order):
            from dazzle.core.strings import to_api_plural

            endpoint = f"/{to_api_plural(entity_name)}"
            try:
                resp = client.delete(endpoint, headers=loader._headers())
                if resp.status_code in (200, 204):
                    typer.echo(f"  Cleared {entity_name}")
                elif resp.status_code == 404:
                    typer.echo(f"  {entity_name}: no delete endpoint")
                else:
                    typer.echo(f"  {entity_name}: HTTP {resp.status_code}")
            except Exception as e:
                typer.echo(f"  {entity_name}: {e}")

        # Reload
        typer.echo("\nReloading demo data...")
        report = loader.load_all(data_dir, entity_order)

    typer.echo("")
    typer.echo(report.summary())

    if report.total_failed > 0:
        raise typer.Exit(1)
