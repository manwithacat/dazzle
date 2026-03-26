"""
CLI commands for API pack management.

Commands:
- api-pack generate-dsl: Generate DSL blocks from an API pack
- api-pack env-vars: Generate .env.example for packs
- api-pack infrastructure: Discover infrastructure requirements from DSL services
- api-pack scaffold: Scaffold a new API pack TOML from OpenAPI or blank template
"""

import json
from pathlib import Path
from typing import Any

import typer

api_pack_app = typer.Typer(
    help="API pack management — generate DSL, scaffold packs, inspect infrastructure.",
    no_args_is_help=True,
)


@api_pack_app.command("generate-dsl")
def generate_dsl(
    pack_name: str = typer.Argument(..., help="Name of the API pack"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Generate DSL service and foreign_model blocks from an API pack."""
    from dazzle.cli._output import format_output
    from dazzle.mcp.server.handlers.api_packs import api_pack_generate_dsl_impl

    result = api_pack_generate_dsl_impl(pack_name=pack_name)

    if "error" in result:
        typer.echo(f"Error: {result['error']}", err=True)
        raise typer.Exit(code=1)

    if json_output:
        typer.echo(format_output(result, as_json=True))
    else:
        typer.echo(result.get("dsl", ""))
        if result.get("env_vars_required"):
            typer.echo()
            typer.echo("Required env vars:")
            for var in result["env_vars_required"]:
                typer.echo(f"  {var}")
        if result.get("hint"):
            typer.echo()
            typer.echo(result["hint"])


@api_pack_app.command("env-vars")
def env_vars(
    pack_names: list[str] = typer.Argument(None, help="Pack names (omit for all packs)"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Get .env.example content for specified packs or all packs."""
    from dazzle.cli._output import format_output
    from dazzle.mcp.server.handlers.api_packs import api_pack_env_vars_impl

    names: list[str] | None = pack_names if pack_names else None
    result = api_pack_env_vars_impl(pack_names=names)

    if json_output:
        typer.echo(format_output(result, as_json=True))
    else:
        typer.echo(result.get("env_example", ""))
        if result.get("hint"):
            typer.echo()
            typer.echo(result["hint"])


@api_pack_app.command("infrastructure")
def infrastructure(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Discover infrastructure requirements for services declared in DSL."""
    from dazzle.cli._output import format_output
    from dazzle.cli.common import resolve_project
    from dazzle.mcp.server.handlers.api_packs import api_pack_infrastructure_impl

    root = resolve_project(manifest)
    result = api_pack_infrastructure_impl(root)

    if json_output:
        typer.echo(format_output(result, as_json=True))
    else:
        total = result.get("service_count", 0)
        typer.secho(f"\nInfrastructure: {total} service(s)", bold=True)
        typer.echo(f"  Self-hosted: {result.get('self_hosted_count', 0)}")
        typer.echo(f"  Cloud-only:  {result.get('cloud_only_count', 0)}")
        typer.echo(f"  Unknown:     {result.get('unknown_count', 0)}")

        for svc in result.get("services", []):
            name = svc.get("service", "?")
            pack = svc.get("pack") or "no pack"
            typer.echo(f"\n  {name} ({pack})")
            infra = svc.get("infrastructure")
            if infra:
                typer.echo(f"    hosting: {infra.get('hosting', '?')}")
                docker = infra.get("docker")
                if docker:
                    typer.echo(f"    docker:  {docker.get('image', '?')}")
            elif svc.get("hint"):
                typer.echo(f"    {svc['hint']}")

        typer.echo()


@api_pack_app.command("scaffold")
def scaffold(
    provider: str = typer.Option("MyVendor", "--provider", help="Provider name"),
    category: str = typer.Option("api", "--category", help="Pack category"),
    pack_name: str = typer.Option("", "--name", "-n", help="Pack name (auto-derived if empty)"),
    openapi_url: str | None = typer.Option(None, "--openapi-url", help="URL to OpenAPI spec"),
    openapi_file: Path | None = typer.Option(
        None, "--openapi-file", help="Path to OpenAPI spec JSON file"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Scaffold a new API pack TOML from OpenAPI spec or blank template."""
    from dazzle.cli._output import format_output
    from dazzle.mcp.server.handlers.api_packs import api_pack_scaffold_impl

    openapi_spec: dict[str, Any] | None = None
    if openapi_file is not None:
        try:
            openapi_spec = json.loads(openapi_file.read_text())
        except Exception as e:
            typer.echo(f"Error reading OpenAPI file: {e}", err=True)
            raise typer.Exit(code=1)

    result = api_pack_scaffold_impl(
        openapi_spec=openapi_spec,
        openapi_url=openapi_url,
        provider=provider,
        category=category,
        pack_name=pack_name,
    )

    if "error" in result:
        typer.echo(f"Error: {result['error']}", err=True)
        raise typer.Exit(code=1)

    if json_output:
        typer.echo(format_output(result, as_json=True))
    else:
        typer.echo(result.get("toml", ""))
        if result.get("hint"):
            typer.echo()
            typer.echo(result["hint"])
