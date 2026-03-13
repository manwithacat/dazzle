"""
E2E testing CLI commands.

Docker-based E2E tests and impl-based commands for check-infra, coverage,
list-flows, tier-guidance, and viewport testing.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import typer

e2e_app = typer.Typer(
    help="E2E testing with UX coverage tracking.",
    no_args_is_help=True,
)


@e2e_app.command("run")
def e2e_run(
    example: str = typer.Argument(
        ...,
        help="Name of the example to test (e.g., 'simple_task', 'contact_manager')",
    ),
    coverage_threshold: int = typer.Option(
        0,
        "--coverage-threshold",
        "-c",
        help="Minimum UX coverage percentage required (0-100)",
    ),
    copy_screenshots: bool = typer.Option(
        False,
        "--copy-screenshots",
        help="Copy screenshots to example directory after test",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show detailed output",
    ),
) -> None:
    """
    Run E2E tests for an example project using Docker.

    This command handles the full Docker lifecycle:
    1. Builds the DNR container with the specified example
    2. Starts containers with health checks
    3. Runs Playwright tests
    4. Captures screenshots and UX coverage
    5. Cleans up containers

    Examples:
        dazzle e2e run simple_task                    # Test simple_task example
        dazzle e2e run contact_manager -c 80          # Require 80% coverage
        dazzle e2e run ops_dashboard --copy-screenshots  # Copy screenshots after
    """
    # Find the run_ux_coverage.sh script
    try:
        import dazzle

        dazzle_root = Path(dazzle.__file__).parent.parent.parent
    except Exception:
        dazzle_root = Path.cwd()

    script_path = dazzle_root / "tests" / "e2e" / "docker" / "run_ux_coverage.sh"

    if not script_path.exists():
        typer.echo(f"E2E test script not found: {script_path}", err=True)
        typer.echo("Make sure you're running from the Dazzle repository.", err=True)
        raise typer.Exit(code=2)

    # Validate example exists
    examples_dir = dazzle_root / "examples"
    example_path = examples_dir / example

    if not example_path.exists():
        typer.echo(f"Example '{example}' not found at {example_path}", err=True)
        available = ", ".join(d.name for d in examples_dir.iterdir() if d.is_dir())
        typer.echo(f"Available examples: {available}", err=True)
        raise typer.Exit(code=2)

    # Check Docker is available
    try:
        subprocess.run(
            ["docker", "info"],
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError:
        typer.echo("Docker is not running. Please start Docker first.", err=True)
        raise typer.Exit(code=2)
    except FileNotFoundError:
        typer.echo("Docker not found. Please install Docker.", err=True)
        raise typer.Exit(code=2)

    typer.echo(f"Running E2E tests for '{example}'...")
    if coverage_threshold > 0:
        typer.echo(f"Coverage threshold: {coverage_threshold}%")

    # Build command
    cmd = [str(script_path), example]
    if coverage_threshold > 0:
        cmd.extend(["--coverage-threshold", str(coverage_threshold)])

    # Run the script
    try:
        result = subprocess.run(
            cmd,
            cwd=dazzle_root,
            capture_output=not verbose,
            text=True,
        )

        if result.returncode == 0:
            typer.secho("✓ E2E tests passed!", fg=typer.colors.GREEN)
        elif result.returncode == 1:
            typer.secho("✗ Coverage below threshold", fg=typer.colors.YELLOW)
        else:
            typer.secho("✗ E2E tests failed", fg=typer.colors.RED)
            if not verbose and result.stderr:
                typer.echo(result.stderr)

        # Copy screenshots if requested
        if copy_screenshots:
            screenshots_src = dazzle_root / "tests" / "e2e" / "docker" / "screenshots" / example
            screenshots_dst = example_path / "screenshots"

            if screenshots_src.exists():
                screenshots_dst.mkdir(exist_ok=True)
                for png in screenshots_src.glob("*.png"):
                    shutil.copy2(png, screenshots_dst / png.name)
                typer.echo(f"Copied screenshots to {screenshots_dst}")

        raise typer.Exit(code=result.returncode)

    except KeyboardInterrupt:
        typer.echo("\nTest interrupted. Cleaning up containers...")
        raise typer.Exit(code=2)


@e2e_app.command("run-all")
def e2e_run_all(
    coverage_threshold: int = typer.Option(
        0,
        "--coverage-threshold",
        "-c",
        help="Minimum UX coverage percentage required (0-100)",
    ),
    copy_screenshots: bool = typer.Option(
        False,
        "--copy-screenshots",
        help="Copy screenshots to example directories after tests",
    ),
    stop_on_failure: bool = typer.Option(
        False,
        "--stop-on-failure",
        help="Stop at first failure",
    ),
) -> None:
    """
    Run E2E tests for all example projects.

    Examples:
        dazzle e2e run-all                          # Test all examples
        dazzle e2e run-all --copy-screenshots       # Copy screenshots after
        dazzle e2e run-all --stop-on-failure        # Stop at first failure
    """
    try:
        import dazzle

        dazzle_root = Path(dazzle.__file__).parent.parent.parent
    except Exception:
        dazzle_root = Path.cwd()

    examples_dir = dazzle_root / "examples"
    examples = sorted(
        d.name for d in examples_dir.iterdir() if d.is_dir() and (d / "dazzle.toml").exists()
    )

    if not examples:
        typer.echo("No examples found with dazzle.toml", err=True)
        raise typer.Exit(code=2)

    # Find dazzle CLI executable once
    dazzle_cmd = shutil.which("dazzle")
    if not dazzle_cmd:
        # Fallback: try to find it relative to sys.executable
        dazzle_cmd = str(Path(sys.executable).parent / "dazzle")
        if not Path(dazzle_cmd).exists():
            typer.echo("Could not find dazzle CLI executable", err=True)
            raise typer.Exit(code=2)

    typer.echo(f"Running E2E tests for {len(examples)} examples: {', '.join(examples)}\n")

    results: dict[str, str] = {}

    for example in examples:
        typer.echo(f"\n{'=' * 60}")
        typer.echo(f"Testing: {example}")
        typer.echo(f"{'=' * 60}")

        cmd = [dazzle_cmd, "e2e", "run", example]
        if coverage_threshold > 0:
            cmd.extend(["--coverage-threshold", str(coverage_threshold)])
        if copy_screenshots:
            cmd.append("--copy-screenshots")

        result = subprocess.run(cmd, cwd=dazzle_root)

        if result.returncode == 0:
            results[example] = "PASS"
        elif result.returncode == 1:
            results[example] = "COVERAGE"
        else:
            results[example] = "FAIL"
            if stop_on_failure:
                typer.echo(f"\nStopping due to failure in {example}")
                break

    # Summary
    typer.echo(f"\n{'=' * 60}")
    typer.echo("E2E Test Summary")
    typer.echo(f"{'=' * 60}")

    for example, status in results.items():
        color = {
            "PASS": typer.colors.GREEN,
            "COVERAGE": typer.colors.YELLOW,
            "FAIL": typer.colors.RED,
        }.get(status, typer.colors.WHITE)
        typer.secho(f"  {example}: {status}", fg=color)

    passed = sum(1 for s in results.values() if s == "PASS")
    total = len(results)
    typer.echo(f"\n{passed}/{total} examples passed")

    if passed < total:
        raise typer.Exit(code=1)


@e2e_app.command("clean")
def e2e_clean() -> None:
    """
    Clean up any lingering E2E test containers.

    Use this if containers are left running after a failed test.
    """
    typer.echo("Cleaning up E2E test containers...")

    # Check Docker is available
    try:
        subprocess.run(
            ["docker", "info"],
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError:
        typer.echo("Docker is not running. Please start Docker first.", err=True)
        raise typer.Exit(code=2)
    except FileNotFoundError:
        typer.echo("Docker not found. Please install Docker.", err=True)
        raise typer.Exit(code=2)

    # Find and stop dazzle-e2e containers (don't use check=True since empty result is OK)
    result = subprocess.run(
        ["docker", "ps", "-a", "--filter", "name=dazzle-e2e", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        typer.echo(f"Error listing containers: {result.stderr}", err=True)
        raise typer.Exit(code=2)

    containers = result.stdout.strip().split("\n")
    containers = [c for c in containers if c]

    if not containers:
        typer.echo("No E2E containers found.")
        return

    typer.echo(f"Found {len(containers)} containers: {', '.join(containers)}")

    for container in containers:
        subprocess.run(["docker", "stop", container], capture_output=True)
        subprocess.run(["docker", "rm", container], capture_output=True)
        typer.echo(f"  Removed: {container}")

    typer.secho("✓ Cleanup complete", fg=typer.colors.GREEN)


# ---------------------------------------------------------------------------
# impl-based commands
# ---------------------------------------------------------------------------


@e2e_app.command("check-infra")
def e2e_check_infra(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Check E2E test infrastructure requirements.

    Examples:
        dazzle e2e check-infra
        dazzle e2e check-infra --json
    """
    from dazzle.cli._output import format_output
    from dazzle.mcp.server.handlers.testing import check_test_infrastructure_impl

    result = check_test_infrastructure_impl()
    typer.echo(format_output(result, as_json=json_output))


@e2e_app.command("coverage")
def e2e_coverage(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Analyze E2E test coverage for the project.

    Examples:
        dazzle e2e coverage
        dazzle e2e coverage --json
    """
    from dazzle.cli._output import format_output
    from dazzle.cli.common import resolve_project
    from dazzle.mcp.server.handlers.testing import get_e2e_test_coverage_impl

    root = resolve_project(manifest)
    result = get_e2e_test_coverage_impl(root)
    typer.echo(format_output(result, as_json=json_output))


@e2e_app.command("list-flows")
def e2e_list_flows(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    priority: str = typer.Option(
        None, "--priority", "-p", help="Filter by priority (high, medium, low)"
    ),
    tag: str = typer.Option(None, "--tag", "-t", help="Filter by tag"),
    limit: int = typer.Option(50, "--limit", "-l", help="Maximum number of flows to return"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """List available E2E test flows.

    Examples:
        dazzle e2e list-flows
        dazzle e2e list-flows --priority high
        dazzle e2e list-flows --tag crud --limit 10
        dazzle e2e list-flows --json
    """
    from dazzle.cli._output import format_output
    from dazzle.cli.common import resolve_project
    from dazzle.mcp.server.handlers.testing import list_e2e_flows_impl

    root = resolve_project(manifest)
    result = list_e2e_flows_impl(root, priority=priority, tag=tag, limit=limit)
    typer.echo(format_output(result, as_json=json_output))


@e2e_app.command("tier-guidance")
def e2e_tier_guidance(
    scenario: str = typer.Argument(..., help="Scenario description to get tier guidance for"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Provide guidance on which test tier to use for a scenario.

    Examples:
        dazzle e2e tier-guidance "visual layout regression"
        dazzle e2e tier-guidance "CRUD operations on tasks" --json
    """
    from dazzle.cli._output import format_output
    from dazzle.mcp.server.handlers.testing import get_test_tier_guidance_impl

    result = get_test_tier_guidance_impl(scenario)
    typer.echo(format_output(result, as_json=json_output))


@e2e_app.command("run-viewport")
def e2e_run_viewport(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    headless: bool = typer.Option(
        True, "--headless/--no-headless", help="Run browser in headless mode"
    ),
    viewports: str = typer.Option(
        None, "--viewports", help="Viewport names (comma-separated, e.g. mobile,tablet,desktop)"
    ),
    persona_id: str = typer.Option(None, "--persona", help="Persona ID to test as"),
    capture_screenshots: bool = typer.Option(
        False, "--screenshots", help="Capture screenshots during tests"
    ),
    update_baselines: bool = typer.Option(
        False, "--update-baselines", help="Update baseline screenshots"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Run viewport assertions against a running app.

    Examples:
        dazzle e2e run-viewport
        dazzle e2e run-viewport --viewports mobile,tablet
        dazzle e2e run-viewport --persona admin --screenshots
        dazzle e2e run-viewport --no-headless --json
    """
    from dazzle.cli._output import format_output
    from dazzle.cli.common import resolve_project
    from dazzle.mcp.server.handlers.viewport_testing import run_viewport_tests_impl

    root = resolve_project(manifest)
    viewport_list = [v.strip() for v in viewports.split(",")] if viewports else None
    raw = run_viewport_tests_impl(
        project_path=root,
        headless=headless,
        viewports=viewport_list,
        persona_id=persona_id,
        capture_screenshots=capture_screenshots,
        update_baselines=update_baselines,
    )
    result: dict = json.loads(raw)
    typer.echo(format_output(result, as_json=json_output))


@e2e_app.command("list-viewport-specs")
def e2e_list_viewport_specs(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """List custom viewport specs for the project.

    Examples:
        dazzle e2e list-viewport-specs
        dazzle e2e list-viewport-specs --json
    """
    from dazzle.cli._output import format_output
    from dazzle.cli.common import resolve_project
    from dazzle.mcp.server.handlers.viewport_testing import list_viewport_specs_impl

    root = resolve_project(manifest)
    result = list_viewport_specs_impl(root)
    typer.echo(format_output(result, as_json=json_output))


@e2e_app.command("save-viewport-specs")
def e2e_save_viewport_specs(
    specs_file: Path = typer.Argument(..., help="Path to JSON file containing viewport specs"),
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    to_dsl: bool = typer.Option(False, "--to-dsl", help="Save specs as DSL instead of JSON"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Save custom viewport specs from a JSON file.

    The JSON file should contain an array of viewport spec objects.

    Examples:
        dazzle e2e save-viewport-specs specs.json
        dazzle e2e save-viewport-specs specs.json --to-dsl
        dazzle e2e save-viewport-specs specs.json --json
    """
    from dazzle.cli._output import format_output
    from dazzle.cli.common import resolve_project
    from dazzle.mcp.server.handlers.viewport_testing import save_viewport_specs_impl

    root = resolve_project(manifest)

    if not specs_file.exists():
        typer.echo(f"Specs file not found: {specs_file}", err=True)
        raise typer.Exit(code=1)

    try:
        specs = json.loads(specs_file.read_text())
    except json.JSONDecodeError as e:
        typer.echo(f"Invalid JSON in specs file: {e}", err=True)
        raise typer.Exit(code=1)

    if not isinstance(specs, list):
        typer.echo("Specs file must contain a JSON array", err=True)
        raise typer.Exit(code=1)

    result = save_viewport_specs_impl(root, specs=specs, to_dsl=to_dsl)
    typer.echo(format_output(result, as_json=json_output))
