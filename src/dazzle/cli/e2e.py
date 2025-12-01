"""
Docker-based E2E testing CLI commands.

Commands for running E2E tests with UX coverage tracking in Docker containers.
"""

import shutil
import subprocess
import sys
from pathlib import Path

import typer

e2e_app = typer.Typer(
    help="Docker-based E2E testing with UX coverage tracking.",
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
        typer.echo(
            f"Available examples: {', '.join(d.name for d in examples_dir.iterdir() if d.is_dir())}",
            err=True,
        )
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
