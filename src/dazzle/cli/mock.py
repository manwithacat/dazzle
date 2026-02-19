"""
CLI commands for vendor mock management.

Provides ``dazzle mock`` command group for starting, stopping, and
configuring vendor mock servers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer

from dazzle.cli.utils import load_project_appspec

mock_app = typer.Typer(help="Vendor mock server management")


@mock_app.command(name="list")
def list_vendors(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
) -> None:
    """List API pack vendors discovered from the current project's AppSpec."""
    project_root = Path(manifest).resolve().parent if manifest != "dazzle.toml" else Path.cwd()

    try:
        appspec = load_project_appspec(project_root)
    except Exception as e:
        typer.echo(f"Error loading spec: {e}", err=True)
        raise typer.Exit(code=1)

    from dazzle.testing.vendor_mock.orchestrator import discover_packs_from_appspec

    packs = discover_packs_from_appspec(appspec)
    if not packs:
        typer.echo("No API pack references found in AppSpec.")
        typer.echo("Add services with spec_inline='pack:<name>' to enable vendor mocks.")
        return

    typer.echo(f"Discovered {len(packs)} vendor(s):")
    for name in packs:
        from dazzle.api_kb.loader import load_pack

        pack = load_pack(name)
        provider = pack.provider if pack else "unknown"
        typer.echo(f"  • {name} ({provider})")


@mock_app.command(name="run")
def run_mocks(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    port: int = typer.Option(9001, "--port", "-p", help="Base port for mock servers"),
    seed: int = typer.Option(42, "--seed", "-s", help="Seed for deterministic data"),
    vendor: str | None = typer.Option(None, "--vendor", "-v", help="Start specific vendor only"),
) -> None:
    """Start vendor mock servers for the current project.

    Discovers API packs from the AppSpec and starts FastAPI mock servers
    with stateful CRUD, auth validation, and request logging.
    """
    project_root = Path(manifest).resolve().parent if manifest != "dazzle.toml" else Path.cwd()

    try:
        appspec = load_project_appspec(project_root)
    except Exception as e:
        typer.echo(f"Error loading spec: {e}", err=True)
        raise typer.Exit(code=1)

    from dazzle.testing.vendor_mock.orchestrator import MockOrchestrator

    if vendor:
        orch = MockOrchestrator(seed=seed, base_port=port)
        try:
            orch.add_vendor(vendor)
        except ValueError as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(code=1)
    else:
        orch = MockOrchestrator.from_appspec(appspec, seed=seed, base_port=port)

    if not orch.vendors:
        typer.echo("No vendors to mock. Use --vendor to specify one directly.")
        raise typer.Exit(code=0)

    typer.echo(f"Starting {len(orch.vendors)} mock server(s)...")
    orch.start()

    for name, mock in orch.vendors.items():
        typer.echo(f"  • {mock.provider} ({name}): http://{mock.base_url.split('//')[1]}")
        typer.echo(f"    {mock.env_var}={mock.base_url}")

    typer.echo("\nPress Ctrl+C to stop")
    try:
        import time

        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        typer.echo("\nStopping mocks...")
        orch.stop()
        typer.echo("Done.")


@mock_app.command(name="scenario")
def scenario_cmd(
    vendor: str = typer.Argument(..., help="Vendor name (e.g. sumsub_kyc)"),
    name: str | None = typer.Argument(None, help="Scenario name (e.g. kyc_rejected)"),
    list_all: bool = typer.Option(False, "--list", "-l", help="List available scenarios"),
) -> None:
    """List or inspect vendor mock scenarios.

    Use --list to see all available scenarios for a vendor.
    """
    from dazzle.testing.vendor_mock.scenarios import ScenarioEngine

    engine = ScenarioEngine()

    if list_all or name is None:
        scenarios = engine.list_scenarios(vendor=vendor)
        if not scenarios:
            typer.echo(f"No scenarios found for vendor '{vendor}'.")
            return
        typer.echo(f"Available scenarios for {vendor}:")
        for s in scenarios:
            scenario_name = s.split("/", 1)[1]
            try:
                loaded = engine.load_scenario(vendor, scenario_name)
                typer.echo(f"  • {scenario_name}: {loaded.description}")
                engine.reset()
            except Exception:
                typer.echo(f"  • {scenario_name}")
        return

    try:
        scenario = engine.load_scenario(vendor, name)
    except FileNotFoundError:
        typer.echo(f"Scenario '{name}' not found for vendor '{vendor}'.", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Scenario: {scenario.name}")
    typer.echo(f"Description: {scenario.description}")
    typer.echo(f"Vendor: {scenario.vendor}")
    typer.echo(f"Steps ({len(scenario.steps)}):")
    for step in scenario.steps:
        parts = [f"  • {step.operation}"]
        if step.status_override:
            parts.append(f"status={step.status_override}")
        if step.delay_ms:
            parts.append(f"delay={step.delay_ms}ms")
        if step.response_override:
            keys = list(step.response_override.keys())
            parts.append(f"overrides={keys}")
        typer.echo("  ".join(parts))


@mock_app.command(name="webhook")
def webhook_cmd(
    vendor: str = typer.Argument(..., help="Vendor name (e.g. sumsub_kyc)"),
    event: str | None = typer.Argument(None, help="Event name (e.g. applicant_reviewed)"),
    target: str = typer.Option("http://localhost:8000", "--target", "-t", help="Target URL"),
    data: str | None = typer.Option(None, "--data", "-d", help="JSON payload overrides"),
    list_all: bool = typer.Option(False, "--list", "-l", help="List available events"),
) -> None:
    """Fire or list vendor webhook events.

    Use --list to see available events. Without --list, fires the event
    to the target URL with vendor-appropriate HMAC signing.
    """
    from dazzle.testing.vendor_mock.webhooks import WebhookDispatcher

    dispatcher = WebhookDispatcher(target_base_url=target)

    if list_all or event is None:
        events = dispatcher.list_events(vendor=vendor)
        if not events:
            typer.echo(f"No webhook events defined for vendor '{vendor}'.")
            return
        typer.echo(f"Available webhook events for {vendor}:")
        for e in events:
            typer.echo(f"  • {e.split('/', 1)[1]}")
        return

    import json as json_mod

    overrides: dict[str, Any] | None = None
    if data:
        try:
            overrides = json_mod.loads(data)
        except json_mod.JSONDecodeError as e:
            typer.echo(f"Invalid JSON data: {e}", err=True)
            raise typer.Exit(code=1)

    try:
        attempt = dispatcher.fire_sync(vendor, event, overrides=overrides)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)

    if attempt.error:
        typer.echo(f"Delivery failed: {attempt.error}")
    else:
        typer.echo(f"Webhook delivered: {attempt.status_code} ({attempt.elapsed_ms:.0f}ms)")
        typer.echo(f"  Target: {attempt.target_url}")
        typer.echo(f"  Event: {event}")
