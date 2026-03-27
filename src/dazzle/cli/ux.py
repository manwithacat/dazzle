"""CLI commands for UX verification."""

import asyncio
from pathlib import Path

import typer
from rich.console import Console

console = Console()

ux_app = typer.Typer(
    help="UX verification — deterministic interaction testing.",
    no_args_is_help=True,
)


def _run_structural_only() -> int:
    """Run structural checks only (no browser, no database)."""
    from dazzle.core.appspec_loader import load_project_appspec
    from dazzle.testing.ux.inventory import generate_inventory
    from dazzle.testing.ux.report import generate_report

    project_root = Path.cwd().resolve()
    appspec = load_project_appspec(project_root)
    inventory = generate_inventory(appspec)

    console.print(f"[dim]Inventory: {len(inventory)} interactions enumerated[/dim]")
    console.print("[yellow]Structural-only mode — skipping browser tests[/yellow]")

    # For structural, we'd need rendered HTML. For now, report the inventory.
    report = generate_report([], [])
    console.print(report.to_markdown())
    return 0


@ux_app.command("verify")
def verify_command(
    structural: bool = typer.Option(
        False, "--structural", help="Structural checks only (no browser)"
    ),
    persona: str = typer.Option("", "--persona", help="Filter to specific persona"),
    entity: str = typer.Option("", "--entity", help="Filter to specific entity"),
    keep_db: bool = typer.Option(False, "--keep-db", help="Keep test database after verification"),
    db_url: str = typer.Option("", "--db-url", help="Postgres URL override"),
    format_: str = typer.Option(
        "markdown", "--format", "-f", help="Output format: markdown or json"
    ),
    headless: bool = typer.Option(True, "--headless/--headed", help="Run browser headless"),
) -> None:
    """Run UX verification against the current project.

    Derives an interaction inventory from the DSL, boots the app against
    a test database, and verifies every framework-generated interaction.

    Examples:
        dazzle ux verify                    # Full verification
        dazzle ux verify --structural       # HTML checks only (fast)
        dazzle ux verify --persona teacher  # Filter by persona
        dazzle ux verify --headed           # Watch the browser
    """
    if structural:
        raise typer.Exit(_run_structural_only())

    from dazzle.core.appspec_loader import load_project_appspec
    from dazzle.core.manifest import resolve_api_url, resolve_site_url
    from dazzle.testing.ux.harness import PostgresHarness, check_postgres_available
    from dazzle.testing.ux.inventory import generate_inventory
    from dazzle.testing.ux.report import generate_report
    from dazzle.testing.ux.runner import InteractionRunner

    project_root = Path.cwd().resolve()
    project_name = project_root.name

    # Load AppSpec
    try:
        appspec = load_project_appspec(project_root)
    except Exception as e:
        console.print(f"[red]Failed to load project: {e}[/red]")
        raise typer.Exit(1)

    # Generate inventory
    inventory = generate_inventory(appspec)
    console.print(f"[dim]Inventory: {len(inventory)} interactions enumerated[/dim]")

    # Filter if requested
    if persona:
        inventory = [i for i in inventory if i.persona == persona]
        console.print(f"[dim]Filtered to persona '{persona}': {len(inventory)} interactions[/dim]")
    if entity:
        inventory = [i for i in inventory if i.entity == entity]
        console.print(f"[dim]Filtered to entity '{entity}': {len(inventory)} interactions[/dim]")

    if not inventory:
        console.print("[yellow]No interactions to test.[/yellow]")
        raise typer.Exit(0)

    # Check Postgres
    harness_url = db_url or "postgresql://localhost:5432/postgres"
    if not check_postgres_available(harness_url):
        console.print(
            "[red]Postgres is not available.[/red]\n"
            "  Ensure PostgreSQL is running locally.\n"
            "  macOS: brew services start postgresql@16\n"
            "  Or set --db-url to a reachable Postgres instance."
        )
        raise typer.Exit(1)

    # Run with harness (TODO: use harness to boot app, seed, and teardown)
    _harness = PostgresHarness(
        project_name=project_name,
        db_url=harness_url,
        keep_db=keep_db,
    )

    site_url = resolve_site_url()
    api_url = resolve_api_url()

    runner = InteractionRunner(
        site_url=site_url,
        api_url=api_url,
        headless=headless,
    )

    console.print(f"[bold]Running UX verification for {project_name}...[/bold]")

    # TODO: Full harness integration (boot app, seed, run, teardown)
    # For now, assume app is already running
    results = asyncio.run(runner.run_all(inventory))

    report = generate_report(results, [])

    if format_ == "json":
        import json

        console.print_json(json.dumps(report.to_json(), indent=2))
    else:
        console.print(report.to_markdown())

    if report.failed > 0:
        raise typer.Exit(1)
