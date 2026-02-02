"""
Dazzle lifecycle commands.

Commands for managing running Dazzle Docker containers: stop, rebuild, logs, status.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import typer

from dazzle.core.manifest import load_manifest

from .docker import get_container_name, is_container_running


def stop_command(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    remove: bool = typer.Option(
        True,
        "--remove/--no-remove",
        help="Remove the container after stopping",
    ),
) -> None:
    """
    Stop the running Dazzle Docker container.

    Stops and optionally removes the Docker container for this project.

    Examples:
        dazzle stop              # Stop and remove container
        dazzle stop --no-remove  # Stop but keep container
    """
    manifest_path = Path(manifest).resolve()
    project_root = manifest_path.parent

    # Load manifest to get project name
    try:
        mf = load_manifest(manifest_path)
        project_name = mf.name
    except Exception:
        project_name = None

    container_name = get_container_name(project_root, project_name)

    # Check if container is running
    if not is_container_running(container_name):
        typer.echo(f"Container '{container_name}' is not running")
        raise typer.Exit(code=0)

    typer.echo(f"Stopping container: {container_name}")

    try:
        # Stop the container
        result = subprocess.run(
            ["docker", "stop", container_name],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            typer.echo(f"Failed to stop container: {result.stderr}", err=True)
            raise typer.Exit(code=1)

        typer.echo("Container stopped")

        # Remove if requested
        if remove:
            result = subprocess.run(
                ["docker", "rm", container_name],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                typer.echo("Container removed")

    except subprocess.TimeoutExpired:
        typer.echo("Timeout stopping container", err=True)
        raise typer.Exit(code=1)
    except FileNotFoundError:
        typer.echo("Docker not found", err=True)
        raise typer.Exit(code=1)


def rebuild_command(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    port: int = typer.Option(3000, "--port", "-p", help="Frontend port"),
    api_port: int = typer.Option(8000, "--api-port", help="Backend API port"),
    test_mode: bool = typer.Option(
        False,
        "--test-mode",
        help="Enable test endpoints (/__test__/seed, /__test__/reset, etc.)",
    ),
    attach: bool = typer.Option(
        False,
        "--attach",
        "-a",
        help="Run Docker container attached (stream logs to terminal)",
    ),
) -> None:
    """
    Rebuild the Docker image and restart the container.

    Stops any running container, rebuilds the Docker image from the current
    DSL files, and starts a fresh container.

    Examples:
        dazzle rebuild              # Rebuild and restart (detached)
        dazzle rebuild --attach     # Rebuild and restart with logs
        dazzle rebuild --test-mode  # Rebuild with test endpoints
    """
    manifest_path = Path(manifest).resolve()
    project_root = manifest_path.parent

    # Load manifest to get project name
    try:
        mf = load_manifest(manifest_path)
        project_name = mf.name
    except Exception:
        project_name = None

    container_name = get_container_name(project_root, project_name)

    # Stop existing container if running
    if is_container_running(container_name):
        typer.echo(f"Stopping existing container: {container_name}")
        subprocess.run(
            ["docker", "stop", container_name],
            capture_output=True,
            timeout=30,
        )
        subprocess.run(
            ["docker", "rm", container_name],
            capture_output=True,
            timeout=10,
        )
        typer.echo("Stopped existing container")

    # Now start with rebuild flag
    typer.echo("Rebuilding Docker image from DSL...")

    try:
        from dazzle_ui.runtime import is_docker_available, run_in_docker

        if not is_docker_available():
            typer.echo("Docker is not available", err=True)
            raise typer.Exit(code=1)

        detach = not attach
        exit_code = run_in_docker(
            project_path=project_root,
            frontend_port=port,
            api_port=api_port,
            test_mode=test_mode,
            rebuild=True,  # Force rebuild
            detach=detach,
        )
        raise typer.Exit(code=exit_code)

    except ImportError as e:
        typer.echo(f"Dazzle runtime not available: {e}", err=True)
        raise typer.Exit(code=1)


def logs_command(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    follow: bool = typer.Option(
        False,
        "--follow",
        "-f",
        help="Follow log output (stream new logs)",
    ),
    tail: int = typer.Option(
        100,
        "--tail",
        "-n",
        help="Number of lines to show from end of logs",
    ),
) -> None:
    """
    View logs from the running Dazzle Docker container.

    Shows the most recent logs from the container. Use --follow to stream
    new logs as they are generated.

    Examples:
        dazzle logs              # Show last 100 lines
        dazzle logs -f           # Follow/stream logs
        dazzle logs -n 50        # Show last 50 lines
        dazzle logs -f -n 10     # Follow starting from last 10 lines
    """
    manifest_path = Path(manifest).resolve()
    project_root = manifest_path.parent

    # Load manifest to get project name
    try:
        mf = load_manifest(manifest_path)
        project_name = mf.name
    except Exception:
        project_name = None

    container_name = get_container_name(project_root, project_name)

    # Check if container exists
    if not is_container_running(container_name):
        typer.echo(f"Container '{container_name}' is not running")
        typer.echo("Start it with: dazzle serve")
        raise typer.Exit(code=1)

    # Build docker logs command
    cmd = ["docker", "logs"]

    if follow:
        cmd.append("-f")

    cmd.extend(["--tail", str(tail)])
    cmd.append(container_name)

    typer.echo(f"Logs from container: {container_name}")
    typer.echo("-" * 50)

    try:
        # Run docker logs, passing output directly to terminal
        subprocess.run(cmd)
    except KeyboardInterrupt:
        typer.echo("\nStopped following logs")
    except FileNotFoundError:
        typer.echo("Docker not found", err=True)
        raise typer.Exit(code=1)


def status_command(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
) -> None:
    """
    Show the status of the Dazzle Docker container.

    Displays whether the container is running, its ports, and resource usage.

    Examples:
        dazzle status
    """
    manifest_path = Path(manifest).resolve()
    project_root = manifest_path.parent

    # Load manifest to get project name
    try:
        mf = load_manifest(manifest_path)
        project_name = mf.name
    except Exception:
        project_name = None

    container_name = get_container_name(project_root, project_name)

    typer.echo(f"Dazzle Container Status: {container_name}")
    typer.echo("=" * 50)

    # Check if container is running
    if not is_container_running(container_name):
        typer.echo("Status: NOT RUNNING")
        typer.echo("\nStart with: dazzle serve")
        return

    typer.echo("Status: RUNNING")

    # Get container details
    try:
        result = subprocess.run(
            [
                "docker",
                "inspect",
                "--format",
                "{{range .NetworkSettings.Ports}}{{.}}{{end}}",
                container_name,
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            typer.echo(f"Ports: {result.stdout.strip()}")

        # Get container stats (CPU, memory)
        result = subprocess.run(
            [
                "docker",
                "stats",
                "--no-stream",
                "--format",
                "CPU: {{.CPUPerc}}, Memory: {{.MemUsage}}",
                container_name,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            typer.echo(result.stdout.strip())

        # Health check
        result = subprocess.run(
            [
                "docker",
                "inspect",
                "--format",
                "{{.State.Health.Status}}",
                container_name,
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            health = result.stdout.strip()
            typer.echo(f"Health: {health}")

    except (subprocess.SubprocessError, FileNotFoundError):
        pass

    typer.echo("\nCommands:")
    typer.echo("  dazzle logs     - View container logs")
    typer.echo("  dazzle stop     - Stop the container")
    typer.echo("  dazzle rebuild  - Rebuild and restart")
