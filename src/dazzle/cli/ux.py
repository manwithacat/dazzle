"""CLI commands for UX verification."""

import asyncio
import json as _json
from pathlib import Path

import typer
from rich.console import Console

console = Console()

ux_app = typer.Typer(
    help="UX verification — deterministic interaction testing.",
    no_args_is_help=True,
)


def _resolve_runtime_urls(project_root: Path) -> tuple[str, str]:
    """Resolve site_url and api_url from runtime.json or env/manifest.

    Priority:
        1. DAZZLE_SITE_URL / DAZZLE_API_URL environment variables
        2. .dazzle/runtime.json written by ``dazzle serve``
        3. Manifest [urls] section
        4. Defaults (localhost:3000 / localhost:8000)

    In DNR mode the UI and API share a single port, so api_url falls back
    to site_url when runtime.json is present but api_url is unreachable.
    """
    import os

    from dazzle.core.manifest import resolve_api_url, resolve_site_url

    env_site = os.environ.get("DAZZLE_SITE_URL", "")
    env_api = os.environ.get("DAZZLE_API_URL", "")
    if env_site and env_api:
        return env_site.rstrip("/"), env_api.rstrip("/")

    runtime_json = project_root / ".dazzle" / "runtime.json"
    if runtime_json.exists():
        try:
            data = _json.loads(runtime_json.read_text())
            site = data.get("ui_url", "")
            if site:
                # DNR serves UI + API on the same port; api_url in
                # runtime.json points at a separate port that only exists
                # in Docker/split mode.  Use site_url for both.
                return site.rstrip("/"), site.rstrip("/")
        except Exception:
            pass

    return resolve_site_url(), resolve_api_url()


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

    Assumes the app is already running via ``dazzle serve --local``.
    The command reads ``.dazzle/runtime.json`` to discover the server URL.

    Examples:
        dazzle ux verify                    # Full verification
        dazzle ux verify --structural       # HTML checks only (fast)
        dazzle ux verify --persona teacher  # Filter by persona
        dazzle ux verify --headed           # Watch the browser
    """
    if structural:
        raise typer.Exit(_run_structural_only())

    from dazzle.core.appspec_loader import load_project_appspec
    from dazzle.testing.ux.harness import check_postgres_available
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

    # Resolve URLs from runtime.json (written by dazzle serve)
    site_url, api_url = _resolve_runtime_urls(project_root)

    runner = InteractionRunner(
        site_url=site_url,
        api_url=api_url,
        headless=headless,
    )

    console.print(f"[bold]Running UX verification for {project_name}...[/bold]")
    console.print(f"[dim]  site: {site_url}  api: {api_url}[/dim]")

    # Reset + seed test data so we start from a known state
    import httpx

    from dazzle.testing.ux.fixtures import generate_seed_payload

    headers = runner._test_headers()
    console.print("[dim]  resetting test data...[/dim]")
    try:
        resp = httpx.post(f"{api_url}/__test__/reset", headers=headers, timeout=10)
        if resp.status_code == 200:
            console.print("[dim]  reset OK[/dim]")
        else:
            console.print(f"[yellow]  reset returned {resp.status_code}[/yellow]")
    except Exception as e:
        console.print(f"[yellow]  reset failed: {e}[/yellow]")

    seed_payload = generate_seed_payload(appspec)
    fixtures = seed_payload.get("fixtures", [])
    if fixtures:
        # Seed per-entity to avoid one failure blocking all entities
        by_entity: dict[str, list[dict[str, object]]] = {}
        for f in fixtures:
            by_entity.setdefault(f["entity"], []).append(f)

        seeded = 0
        for entity_name, entity_fixtures in by_entity.items():
            try:
                resp = httpx.post(
                    f"{api_url}/__test__/seed",
                    json={"fixtures": entity_fixtures},
                    headers=headers,
                    timeout=15,
                )
                if resp.status_code == 200:
                    seeded += len(entity_fixtures)
                else:
                    console.print(f"[yellow]  seed {entity_name}: {resp.text[:120]}[/yellow]")
            except Exception as e:
                console.print(f"[yellow]  seed {entity_name}: {e}[/yellow]")
        console.print(f"[dim]  seeded {seeded}/{len(fixtures)} fixtures[/dim]")

    results = asyncio.run(runner.run_all(inventory))

    report = generate_report(results, [])

    if format_ == "json":
        console.print_json(_json.dumps(report.to_json(), indent=2))
    else:
        console.print(report.to_markdown())

    if report.failed > 0:
        raise typer.Exit(1)
