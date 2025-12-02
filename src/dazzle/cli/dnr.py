"""
DNR (Dazzle Native Runtime) CLI commands.

Commands for generating and serving runtime apps using DNR.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

import typer

from dazzle.core.errors import DazzleError, ParseError

if TYPE_CHECKING:
    from dazzle.core import ir
    from dazzle_dnr_back.specs import BackendSpec
    from dazzle_dnr_ui.specs import UISpec
from dazzle.core.fileset import discover_dsl_files
from dazzle.core.linker import build_appspec
from dazzle.core.lint import lint_appspec
from dazzle.core.manifest import load_manifest
from dazzle.core.parser import parse_modules

dnr_app = typer.Typer(
    help="Dazzle Native Runtime (DNR) commands for generating and serving runtime apps.",
    no_args_is_help=True,
)


@dnr_app.command("build-ui")
def dnr_build_ui(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    out: str = typer.Option("./dnr-ui", "--out", "-o", help="Output directory"),
    format: str = typer.Option(
        "vite",
        "--format",
        "-f",
        help="Output format: 'vite' (default), 'js' (split files), or 'html' (single file)",
    ),
) -> None:
    """
    Generate DNR UI artifacts from AppSpec.

    Converts AppSpec to UISpec and generates:
    - vite: Full Vite project with ES modules (production-ready)
    - js: Split HTML/JS files for development
    - html: Single HTML file with embedded runtime (quick preview)

    Examples:
        dazzle dnr build-ui                         # Vite project in ./dnr-ui
        dazzle dnr build-ui --format html -o out    # Single HTML file
        dazzle dnr build-ui --format js             # Split JS files
    """
    try:
        # Import DNR UI components
        from dazzle_dnr_ui.converters import convert_appspec_to_ui
        from dazzle_dnr_ui.runtime import (
            generate_js_app,
            generate_single_html,
            generate_vite_app,
        )
    except ImportError as e:
        typer.echo(f"DNR UI not available: {e}", err=True)
        typer.echo("Install with: pip install dazzle-dnr-ui", err=True)
        raise typer.Exit(code=1)

    # Load and build AppSpec
    manifest_path = Path(manifest).resolve()
    root = manifest_path.parent

    try:
        mf = load_manifest(manifest_path)
        dsl_files = discover_dsl_files(root, mf)
        modules = parse_modules(dsl_files)
        appspec = build_appspec(modules, mf.project_root)

        # Validate
        errors, warnings = lint_appspec(appspec)
        if errors:
            typer.echo("Cannot generate UI; spec has validation errors:", err=True)
            for err in errors:
                typer.echo(f"  ERROR: {err}", err=True)
            raise typer.Exit(code=1)

        for warn in warnings:
            typer.echo(f"WARNING: {warn}")

    except (ParseError, DazzleError) as e:
        typer.echo(f"Error loading spec: {e}", err=True)
        raise typer.Exit(code=1)

    # Convert to UISpec (pass shell config from manifest)
    typer.echo(f"Converting AppSpec '{appspec.name}' to UISpec...")
    ui_spec = convert_appspec_to_ui(appspec, shell_config=mf.shell)
    typer.echo(f"  • {len(ui_spec.workspaces)} workspace(s)")
    typer.echo(f"  • {len(ui_spec.components)} component(s)")
    typer.echo(f"  • {len(ui_spec.themes)} theme(s)")

    # Generate based on format
    output_dir = Path(out).resolve()

    if format == "vite":
        typer.echo(f"\nGenerating Vite project → {output_dir}")
        output_dir.mkdir(parents=True, exist_ok=True)
        files = generate_vite_app(ui_spec, str(output_dir))
        typer.echo(f"  ✓ Generated {len(files)} files")
        typer.echo("\nTo run:")
        typer.echo(f"  cd {output_dir}")
        typer.echo("  npm install")
        typer.echo("  npm run dev")

    elif format == "js":
        typer.echo(f"\nGenerating JS app → {output_dir}")
        output_dir.mkdir(parents=True, exist_ok=True)
        files = generate_js_app(ui_spec, str(output_dir))
        typer.echo(f"  ✓ Generated {len(files)} files")
        typer.echo("\nTo run:")
        typer.echo(f"  cd {output_dir}")
        typer.echo("  python -m http.server 8000")

    elif format == "html":
        output_file = output_dir / "index.html" if output_dir.suffix != ".html" else output_dir
        output_file.parent.mkdir(parents=True, exist_ok=True)
        typer.echo(f"\nGenerating single HTML → {output_file}")
        html = generate_single_html(ui_spec)
        output_file.write_text(html)
        typer.echo(f"  ✓ Generated {len(html)} bytes")
        typer.echo(f"\nOpen in browser: file://{output_file}")

    else:
        typer.echo(f"Unknown format: {format}", err=True)
        typer.echo("Use one of: vite, js, html", err=True)
        raise typer.Exit(code=1)


@dnr_app.command("build-api")
def dnr_build_api(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    out: str = typer.Option("./dnr-api", "--out", "-o", help="Output directory"),
    format: str = typer.Option(
        "json",
        "--format",
        "-f",
        help="Output format: 'json' (spec file) or 'python' (stub module)",
    ),
) -> None:
    """
    Generate DNR API spec from AppSpec.

    Converts AppSpec to BackendSpec suitable for FastAPI runtime.

    Examples:
        dazzle dnr build-api                        # JSON spec in ./dnr-api
        dazzle dnr build-api --format python        # Python module stub
    """
    try:
        from dazzle_dnr_back.converters import convert_appspec_to_backend
        from dazzle_dnr_back.specs import BackendSpec as _BackendSpec  # noqa: F401
    except ImportError as e:
        typer.echo(f"DNR Backend not available: {e}", err=True)
        typer.echo("Install with: pip install dazzle-dnr-back", err=True)
        raise typer.Exit(code=1)
    del _BackendSpec  # Used only to verify import availability

    # Load and build AppSpec
    manifest_path = Path(manifest).resolve()
    root = manifest_path.parent

    try:
        mf = load_manifest(manifest_path)
        dsl_files = discover_dsl_files(root, mf)
        modules = parse_modules(dsl_files)
        appspec = build_appspec(modules, mf.project_root)

        errors, warnings = lint_appspec(appspec)
        if errors:
            typer.echo("Cannot generate API; spec has validation errors:", err=True)
            for err in errors:
                typer.echo(f"  ERROR: {err}", err=True)
            raise typer.Exit(code=1)

        for warn in warnings:
            typer.echo(f"WARNING: {warn}")

    except (ParseError, DazzleError) as e:
        typer.echo(f"Error loading spec: {e}", err=True)
        raise typer.Exit(code=1)

    # Convert to BackendSpec
    typer.echo(f"Converting AppSpec '{appspec.name}' to BackendSpec...")
    backend_spec = convert_appspec_to_backend(appspec)
    typer.echo(f"  • {len(backend_spec.entities)} entities")
    typer.echo(f"  • {len(backend_spec.services)} services")
    typer.echo(f"  • {len(backend_spec.endpoints)} endpoints")

    # Output
    output_dir = Path(out).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if format == "json":
        spec_file = output_dir / "backend-spec.json"
        typer.echo(f"\nWriting BackendSpec → {spec_file}")
        spec_file.write_text(backend_spec.model_dump_json(indent=2))
        typer.echo(f"  ✓ Written {spec_file.stat().st_size} bytes")

    elif format == "python":
        stub_file = output_dir / "api_stub.py"
        typer.echo(f"\nWriting Python stub → {stub_file}")

        stub_content = f'''"""
Auto-generated DNR API stub for {backend_spec.name}.

Usage:
    from dazzle_dnr_back.runtime import create_app_from_json
    app = create_app_from_json('backend-spec.json')

Or run directly:
    uvicorn api_stub:app --reload
"""

from pathlib import Path

try:
    from dazzle_dnr_back.runtime import create_app_from_json, FASTAPI_AVAILABLE
    if not FASTAPI_AVAILABLE:
        raise ImportError("FastAPI not installed")

    spec_path = Path(__file__).parent / "backend-spec.json"
    app = create_app_from_json(str(spec_path))

except ImportError as e:
    print(f"DNR runtime not available: {{e}}")
    print("Install with: pip install fastapi uvicorn")
    app = None
'''
        stub_file.write_text(stub_content)

        # Also write the JSON spec
        spec_file = output_dir / "backend-spec.json"
        spec_file.write_text(backend_spec.model_dump_json(indent=2))

        typer.echo("  ✓ Generated stub and spec")
        typer.echo("\nTo run:")
        typer.echo(f"  cd {output_dir}")
        typer.echo("  pip install fastapi uvicorn")
        typer.echo("  uvicorn api_stub:app --reload")

    else:
        typer.echo(f"Unknown format: {format}", err=True)
        typer.echo("Use one of: json, python", err=True)
        raise typer.Exit(code=1)


@dnr_app.command("serve")
def dnr_serve(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    port: int = typer.Option(3000, "--port", "-p", help="Frontend port"),
    api_port: int = typer.Option(8000, "--api-port", help="Backend API port"),
    host: str = typer.Option("127.0.0.1", "--host", help="Host to bind to"),
    ui_only: bool = typer.Option(False, "--ui-only", help="Serve UI only (static files)"),
    backend_only: bool = typer.Option(
        False,
        "--backend-only",
        help="Serve backend API only (no frontend UI)",
    ),
    db_path: str = typer.Option(".dazzle/data.db", "--db", help="SQLite database path"),
    test_mode: bool = typer.Option(
        False,
        "--test-mode",
        help="Enable test endpoints (/__test__/seed, /__test__/reset, etc.)",
    ),
    watch: bool = typer.Option(
        False,
        "--watch",
        "-w",
        help="Enable hot reload: watch DSL files and auto-refresh browser on changes",
    ),
    local: bool = typer.Option(
        False,
        "--local",
        help="Run locally without Docker (default is docker-first)",
    ),
    rebuild: bool = typer.Option(
        False,
        "--rebuild",
        help="Force rebuild of Docker image",
    ),
    attach: bool = typer.Option(
        False,
        "--attach",
        "-a",
        help="Run Docker container attached (stream logs to terminal)",
    ),
    single_container: bool = typer.Option(
        False,
        "--single-container",
        help="Use legacy single-container mode (combined frontend + backend)",
    ),
) -> None:
    """
    Serve DNR app (backend API + UI with live data).

    By default, runs frontend and backend in separate Docker containers.
    Use --single-container for legacy combined mode, --local to run without Docker.

    Runs:
    - FastAPI backend on api-port (default 8000) with SQLite persistence
    - Vite frontend dev server on port (default 3000)
    - Auto-migration for schema changes
    - Interactive API docs at http://host:api-port/docs

    Examples:
        dazzle dnr serve                    # Split containers (default)
        dazzle dnr serve --local --watch    # Local mode with hot reload
        dazzle dnr serve --attach           # Run Docker with log streaming
        dazzle dnr serve --local            # Run locally without Docker
        dazzle dnr serve --single-container # Legacy single-container mode
        dazzle dnr serve --backend-only     # API server only (for separate frontend)
        dazzle dnr serve --rebuild          # Force Docker image rebuild
        dazzle dnr serve --port 4000        # Frontend on 4000
        dazzle dnr serve --api-port 9000    # API on 9000
        dazzle dnr serve --ui-only          # Static UI only (no API)
        dazzle dnr serve --db ./my.db       # Custom database path
        dazzle dnr serve --test-mode        # Enable E2E test endpoints

    Hot reload (--watch):
        Watch DSL files for changes and auto-refresh browser.
        Currently only works in --local mode.

    Related commands:
        dazzle dnr stop                     # Stop the running container
        dazzle dnr rebuild                  # Rebuild and restart container
        dazzle dnr logs                     # View container logs
    """
    # Resolve project path from manifest
    manifest_path = Path(manifest).resolve()
    project_root = manifest_path.parent

    # Load manifest to get auth config and project name
    try:
        mf = load_manifest(manifest_path)
        auth_enabled = mf.auth.enabled
        project_name = mf.name
    except Exception:
        auth_enabled = False
        project_name = None

    # Warn if --watch is used without --local
    if watch and not local:
        typer.echo(
            "Note: --watch requires --local mode. Enabling local mode automatically.",
            err=True,
        )
        local = True

    # Docker-first: unless --local is specified, try Docker first
    if not local and not ui_only and not backend_only:
        try:
            from dazzle_dnr_ui.runtime import is_docker_available, run_in_docker

            if is_docker_available():
                detach = not attach  # Default to detached (no logs), --attach streams logs
                mode_desc = "single-container" if single_container else "split containers"
                auth_desc = " with auth" if auth_enabled else ""
                typer.echo(
                    f"Running in Docker mode ({mode_desc}{auth_desc}, use --local to run without Docker)"
                    if attach
                    else f"Starting Docker containers in background ({mode_desc}{auth_desc})..."
                )
                exit_code = run_in_docker(
                    project_path=project_root,
                    frontend_port=port,
                    api_port=api_port,
                    test_mode=test_mode,
                    auth_enabled=auth_enabled,
                    rebuild=rebuild,
                    detach=detach,
                    single_container=single_container,
                    project_name=project_name,
                )
                raise typer.Exit(code=exit_code)
            else:
                typer.echo("Docker not available, falling back to local mode")
                typer.echo("Install Docker for the recommended development experience")
                typer.echo()
        except ImportError:
            pass  # Docker runner not available, fall back to local

    # Local mode execution
    try:
        from dazzle_dnr_back.converters import convert_appspec_to_backend
        from dazzle_dnr_back.runtime import FASTAPI_AVAILABLE
        from dazzle_dnr_ui.converters import convert_appspec_to_ui
        from dazzle_dnr_ui.runtime import generate_single_html, run_combined_server
    except ImportError as e:
        typer.echo(f"DNR runtime not available: {e}", err=True)
        typer.echo("Install with: pip install dazzle-dnr-back dazzle-dnr-ui", err=True)
        raise typer.Exit(code=1)

    if not FASTAPI_AVAILABLE and not ui_only:
        typer.echo("FastAPI not installed. Use --ui-only or install:", err=True)
        typer.echo("  pip install fastapi uvicorn", err=True)
        raise typer.Exit(code=1)

    # Load AppSpec
    root = project_root

    try:
        mf = load_manifest(manifest_path)
        dsl_files = discover_dsl_files(root, mf)
        modules = parse_modules(dsl_files)
        appspec = build_appspec(modules, mf.project_root)

        errors, _ = lint_appspec(appspec)
        if errors:
            typer.echo("Cannot serve; spec has validation errors:", err=True)
            for err in errors:
                typer.echo(f"  ERROR: {err}", err=True)
            raise typer.Exit(code=1)

    except (ParseError, DazzleError) as e:
        typer.echo(f"Error loading spec: {e}", err=True)
        raise typer.Exit(code=1)

    if ui_only:
        # Serve UI only with simple HTTP server
        import http.server
        import socketserver
        import tempfile

        ui_spec = convert_appspec_to_ui(appspec, shell_config=mf.shell)
        html = generate_single_html(ui_spec)

        with tempfile.TemporaryDirectory() as tmpdir:
            html_path = Path(tmpdir) / "index.html"
            html_path.write_text(html)

            os.chdir(tmpdir)
            handler = http.server.SimpleHTTPRequestHandler
            typer.echo(f"\nServing DNR UI at http://{host}:{port}")
            typer.echo("Press Ctrl+C to stop\n")

            with socketserver.TCPServer((host, port), handler) as httpd:
                try:
                    httpd.serve_forever()
                except KeyboardInterrupt:
                    typer.echo("\nStopped.")
        return

    if backend_only:
        # Serve backend API only (no frontend UI)
        from dazzle_dnr_ui.runtime import run_backend_only

        backend_spec = convert_appspec_to_backend(appspec)

        typer.echo(f"Starting DNR backend for '{appspec.name}'...")
        typer.echo(f"  • {len(backend_spec.entities)} entities")
        typer.echo(f"  • {len(backend_spec.endpoints)} endpoints")
        typer.echo(f"  • Database: {db_path}")
        if test_mode:
            typer.echo("  • Test mode: ENABLED (/__test__/* endpoints available)")
        typer.echo()
        typer.echo(f"API: http://{host}:{api_port}")
        typer.echo(f"Docs: http://{host}:{api_port}/docs")
        typer.echo()

        db_file = Path(db_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)

        run_backend_only(
            backend_spec=backend_spec,
            port=api_port,
            db_path=db_file,
            enable_test_mode=test_mode,
            host=host,
        )
        return

    # Full combined server with API + UI
    typer.echo(f"Starting DNR server for '{appspec.name}'...")

    # Convert specs (pass shell config from manifest)
    backend_spec = convert_appspec_to_backend(appspec)
    ui_spec = convert_appspec_to_ui(appspec, shell_config=mf.shell)

    typer.echo(f"  • {len(backend_spec.entities)} entities")
    typer.echo(f"  • {len(backend_spec.endpoints)} endpoints")
    typer.echo(f"  • {len(ui_spec.workspaces)} workspaces")
    typer.echo(f"  • Database: {db_path}")
    typer.echo()

    # Ensure database directory exists
    db_file = Path(db_path)
    db_file.parent.mkdir(parents=True, exist_ok=True)

    # Run combined server
    # Show test mode status
    if test_mode:
        typer.echo("  • Test mode: ENABLED (/__test__/* endpoints available)")

    # Show hot reload status
    if watch:
        typer.echo("  • Hot reload: ENABLED (watching DSL files)")

    run_combined_server(
        backend_spec=backend_spec,
        ui_spec=ui_spec,
        backend_port=api_port,
        frontend_port=port,
        db_path=db_file,
        enable_test_mode=test_mode,
        enable_auth=auth_enabled,
        host=host,
        enable_watch=watch,
        project_root=project_root,
    )


@dnr_app.command("info")
def dnr_info() -> None:
    """
    Show DNR installation status and available features.
    """
    typer.echo("Dazzle Native Runtime (DNR) Status")
    typer.echo("=" * 50)

    # Check DNR Backend
    dnr_back_available = False
    fastapi_available = False
    try:
        import dazzle_dnr_back  # noqa: F401

        dnr_back_available = True
        from dazzle_dnr_back.runtime import FASTAPI_AVAILABLE

        fastapi_available = FASTAPI_AVAILABLE
    except ImportError:
        pass

    # Check DNR UI
    dnr_ui_available = False
    try:
        import dazzle_dnr_ui  # noqa: F401

        dnr_ui_available = True
    except ImportError:
        pass

    # Check uvicorn
    uvicorn_available = False
    try:
        import uvicorn  # noqa: F401

        uvicorn_available = True
    except ImportError:
        pass

    typer.echo(
        f"DNR Backend:   {'✓' if dnr_back_available else '✗'} {'installed' if dnr_back_available else 'not installed'}"
    )
    typer.echo(
        f"DNR UI:        {'✓' if dnr_ui_available else '✗'} {'installed' if dnr_ui_available else 'not installed'}"
    )
    typer.echo(
        f"FastAPI:       {'✓' if fastapi_available else '✗'} {'installed' if fastapi_available else 'not installed'}"
    )
    typer.echo(
        f"Uvicorn:       {'✓' if uvicorn_available else '✗'} {'installed' if uvicorn_available else 'not installed'}"
    )

    typer.echo("\nAvailable Commands:")
    if dnr_ui_available:
        typer.echo("  dazzle dnr build-ui   Generate UI (Vite/JS/HTML)")
    if dnr_back_available:
        typer.echo("  dazzle dnr build-api  Generate API spec")
    if dnr_back_available and fastapi_available and uvicorn_available:
        typer.echo("  dazzle dnr serve      Run development server")
    elif dnr_ui_available:
        typer.echo("  dazzle dnr serve --ui-only  Serve UI only")

    if not (dnr_back_available and dnr_ui_available):
        typer.echo("\nTo install DNR packages:")
        if not dnr_back_available:
            typer.echo("  pip install dazzle-dnr-back")
        if not dnr_ui_available:
            typer.echo("  pip install dazzle-dnr-ui")
        if not fastapi_available:
            typer.echo("  pip install fastapi")
        if not uvicorn_available:
            typer.echo("  pip install uvicorn")


def _get_container_name(project_root: Path, project_name: str | None = None) -> str:
    """Get the Docker container name for a project.

    Uses project_name from manifest if provided, otherwise falls back to directory name.
    """
    base_name = project_name or project_root.resolve().name
    return f"dazzle-{base_name}"


def _is_container_running(container_name: str) -> bool:
    """Check if a Docker container is running."""
    import subprocess

    try:
        result = subprocess.run(
            ["docker", "ps", "-q", "-f", f"name={container_name}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return bool(result.stdout.strip())
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


@dnr_app.command("stop")
def dnr_stop(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    remove: bool = typer.Option(
        True,
        "--remove/--no-remove",
        help="Remove the container after stopping",
    ),
) -> None:
    """
    Stop the running DNR Docker container.

    Stops and optionally removes the Docker container for this project.

    Examples:
        dazzle dnr stop              # Stop and remove container
        dazzle dnr stop --no-remove  # Stop but keep container
    """
    import subprocess

    manifest_path = Path(manifest).resolve()
    project_root = manifest_path.parent

    # Load manifest to get project name
    try:
        mf = load_manifest(manifest_path)
        project_name = mf.name
    except Exception:
        project_name = None

    container_name = _get_container_name(project_root, project_name)

    # Check if container is running
    if not _is_container_running(container_name):
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


@dnr_app.command("rebuild")
def dnr_rebuild(
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
        dazzle dnr rebuild              # Rebuild and restart (detached)
        dazzle dnr rebuild --attach     # Rebuild and restart with logs
        dazzle dnr rebuild --test-mode  # Rebuild with test endpoints
    """
    import subprocess

    manifest_path = Path(manifest).resolve()
    project_root = manifest_path.parent

    # Load manifest to get project name
    try:
        mf = load_manifest(manifest_path)
        project_name = mf.name
    except Exception:
        project_name = None

    container_name = _get_container_name(project_root, project_name)

    # Stop existing container if running
    if _is_container_running(container_name):
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
        from dazzle_dnr_ui.runtime import is_docker_available, run_in_docker

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
        typer.echo(f"DNR runtime not available: {e}", err=True)
        raise typer.Exit(code=1)


@dnr_app.command("logs")
def dnr_logs(
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
    View logs from the running DNR Docker container.

    Shows the most recent logs from the container. Use --follow to stream
    new logs as they are generated.

    Examples:
        dazzle dnr logs              # Show last 100 lines
        dazzle dnr logs -f           # Follow/stream logs
        dazzle dnr logs -n 50        # Show last 50 lines
        dazzle dnr logs -f -n 10     # Follow starting from last 10 lines
    """
    import subprocess

    manifest_path = Path(manifest).resolve()
    project_root = manifest_path.parent

    # Load manifest to get project name
    try:
        mf = load_manifest(manifest_path)
        project_name = mf.name
    except Exception:
        project_name = None

    container_name = _get_container_name(project_root, project_name)

    # Check if container exists
    if not _is_container_running(container_name):
        typer.echo(f"Container '{container_name}' is not running")
        typer.echo("Start it with: dazzle dnr serve")
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


@dnr_app.command("status")
def dnr_status(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
) -> None:
    """
    Show the status of the DNR Docker container.

    Displays whether the container is running, its ports, and resource usage.

    Examples:
        dazzle dnr status
    """
    import subprocess

    manifest_path = Path(manifest).resolve()
    project_root = manifest_path.parent

    # Load manifest to get project name
    try:
        mf = load_manifest(manifest_path)
        project_name = mf.name
    except Exception:
        project_name = None

    container_name = _get_container_name(project_root, project_name)

    typer.echo(f"DNR Container Status: {container_name}")
    typer.echo("=" * 50)

    # Check if container is running
    if not _is_container_running(container_name):
        typer.echo("Status: NOT RUNNING")
        typer.echo("\nStart with: dazzle dnr serve")
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
    typer.echo("  dazzle dnr logs     - View container logs")
    typer.echo("  dazzle dnr stop     - Stop the container")
    typer.echo("  dazzle dnr rebuild  - Rebuild and restart")


@dnr_app.command("inspect")
def dnr_inspect(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    format_output: str = typer.Option(
        "tree",
        "--format",
        "-f",
        help="Output format: tree, json, summary",
    ),
    entity: str | None = typer.Option(
        None,
        "--entity",
        "-e",
        help="Inspect a specific entity by name",
    ),
    surface: str | None = typer.Option(
        None,
        "--surface",
        "-s",
        help="Inspect a specific surface by name",
    ),
    workspace: str | None = typer.Option(
        None,
        "--workspace",
        "-w",
        help="Inspect a specific workspace by name",
    ),
    endpoints: bool = typer.Option(
        False,
        "--endpoints",
        help="Show generated API endpoints",
    ),
    components: bool = typer.Option(
        False,
        "--components",
        help="Show generated UI components",
    ),
    live: bool = typer.Option(
        False,
        "--live",
        "-l",
        help="Query a running DNR server for runtime state (entity counts, uptime, etc.)",
    ),
    api_url: str = typer.Option(
        "http://localhost:8000",
        "--api-url",
        help="URL of running DNR API server (for --live mode)",
    ),
) -> None:
    """
    Inspect the DNR app structure and generated artifacts.

    Shows detailed information about entities, surfaces, workspaces,
    API endpoints, and UI components generated from the DSL.

    Use --live to query a running server for runtime statistics like
    entity counts, uptime, and database state.

    Examples:
        dazzle dnr inspect                    # Full tree view
        dazzle dnr inspect --format json      # JSON output
        dazzle dnr inspect --format summary   # Brief summary
        dazzle dnr inspect --entity Task      # Inspect Task entity
        dazzle dnr inspect --surface task_list  # Inspect surface
        dazzle dnr inspect --endpoints        # Show API endpoints
        dazzle dnr inspect --components       # Show UI components
        dazzle dnr inspect --live             # Query running server
        dazzle dnr inspect --live --entity Task  # Live entity details
    """
    import json as json_module

    # Handle live mode - query running server
    if live:
        _inspect_live(api_url, format_output, entity)
        return

    manifest_path = Path(manifest).resolve()
    project_root = manifest_path.parent

    # Load and parse the project
    try:
        mf = load_manifest(manifest_path)
        dsl_files = discover_dsl_files(project_root, mf)
        modules = parse_modules(dsl_files)
        appspec = build_appspec(modules, mf.project_root)
    except Exception as e:
        typer.echo(f"Error loading project: {e}", err=True)
        raise typer.Exit(code=1)

    # Import converters
    try:
        from dazzle_dnr_back.converters import convert_appspec_to_backend
        from dazzle_dnr_ui.converters import convert_appspec_to_ui

        backend_spec = convert_appspec_to_backend(appspec)
        ui_spec = convert_appspec_to_ui(appspec, shell_config=mf.shell)
    except ImportError as e:
        typer.echo(f"DNR runtime not available: {e}", err=True)
        raise typer.Exit(code=1)

    # Handle specific item inspection
    if entity:
        _inspect_entity(appspec, backend_spec, entity, format_output)
        return

    if surface:
        _inspect_surface(appspec, ui_spec, surface, format_output)
        return

    if workspace:
        _inspect_workspace(appspec, ui_spec, workspace, format_output)
        return

    if endpoints:
        _inspect_endpoints(backend_spec, format_output)
        return

    if components:
        _inspect_components(ui_spec, format_output)
        return

    # Get entities from domain
    entities = appspec.domain.entities

    # Full inspection
    if format_output == "json":
        output = {
            "app": appspec.name,
            "entities": [e.name for e in entities],
            "surfaces": [s.name for s in appspec.surfaces],
            "workspaces": [w.name for w in appspec.workspaces],
            "endpoints": len(backend_spec.endpoints),
            "components": len(ui_spec.components),
        }
        typer.echo(json_module.dumps(output, indent=2))
    elif format_output == "summary":
        typer.echo(f"App: {appspec.name}")
        typer.echo(f"  Entities:   {len(entities)}")
        typer.echo(f"  Surfaces:   {len(appspec.surfaces)}")
        typer.echo(f"  Workspaces: {len(appspec.workspaces)}")
        typer.echo(f"  Endpoints:  {len(backend_spec.endpoints)}")
        typer.echo(f"  Components: {len(ui_spec.components)}")
    else:  # tree format
        typer.echo(f"📦 {appspec.name}")
        typer.echo("│")

        # Entities
        if entities:
            typer.echo("├── 📊 Entities")
            for i, ent in enumerate(entities):
                prefix = "│   └──" if i == len(entities) - 1 else "│   ├──"
                field_count = len(ent.fields)
                typer.echo(f"{prefix} {ent.name} ({field_count} fields)")

        # Surfaces
        if appspec.surfaces:
            typer.echo("│")
            typer.echo("├── 🖥️  Surfaces")
            for i, s in enumerate(appspec.surfaces):
                prefix = "│   └──" if i == len(appspec.surfaces) - 1 else "│   ├──"
                entity_ref = s.entity_ref or "no entity"
                typer.echo(f"{prefix} {s.name} ({s.mode}, {entity_ref})")

        # Workspaces
        if appspec.workspaces:
            typer.echo("│")
            typer.echo("├── 📁 Workspaces")
            for i, w in enumerate(appspec.workspaces):
                prefix = "│   └──" if i == len(appspec.workspaces) - 1 else "│   ├──"
                region_count = len(w.regions)
                typer.echo(f"{prefix} {w.name} ({region_count} regions)")

        # Backend summary
        typer.echo("│")
        typer.echo(f"├── 🔧 Backend: {len(backend_spec.endpoints)} endpoints")

        # UI summary
        typer.echo("│")
        typer.echo(f"└── 🎨 UI: {len(ui_spec.components)} components")


def _inspect_entity(
    appspec: ir.AppSpec,
    backend_spec: BackendSpec,
    entity_name: str,
    format_output: str,
) -> None:
    """Inspect a specific entity."""
    import json as json_module

    entities = appspec.domain.entities

    # Find entity
    entity = next((e for e in entities if e.name == entity_name), None)
    if not entity:
        typer.echo(f"Entity '{entity_name}' not found", err=True)
        typer.echo(f"Available: {', '.join(e.name for e in entities)}")
        raise typer.Exit(code=1)

    # Find related endpoints
    related_endpoints = [
        ep for ep in backend_spec.endpoints if entity_name.lower() in ep.path.lower()
    ]

    if format_output == "json":
        output = {
            "name": entity.name,
            "title": entity.title,
            "fields": [
                {
                    "name": f.name,
                    "type": str(f.type),
                    "required": f.is_required,
                    "primary_key": f.is_primary_key,
                }
                for f in entity.fields
            ],
            "endpoints": [{"method": str(ep.method), "path": ep.path} for ep in related_endpoints],
        }
        typer.echo(json_module.dumps(output, indent=2))
    else:
        typer.echo(f"📊 Entity: {entity.name}")
        if entity.title:
            typer.echo(f"   Title: {entity.title}")
        typer.echo()
        typer.echo("   Fields:")
        for f in entity.fields:
            pk = " [PK]" if f.is_primary_key else ""
            req = " (required)" if f.is_required else ""
            typer.echo(f"   • {f.name}: {f.type}{pk}{req}")

        if related_endpoints:
            typer.echo()
            typer.echo("   Endpoints:")
            for ep in related_endpoints:
                typer.echo(f"   • {ep.method:6} {ep.path}")


def _inspect_surface(
    appspec: ir.AppSpec,
    ui_spec: UISpec,
    surface_name: str,
    format_output: str,
) -> None:
    """Inspect a specific surface."""
    import json as json_module

    # Find surface
    surface = next((s for s in appspec.surfaces if s.name == surface_name), None)
    if not surface:
        typer.echo(f"Surface '{surface_name}' not found", err=True)
        typer.echo(f"Available: {', '.join(s.name for s in appspec.surfaces)}")
        raise typer.Exit(code=1)

    if format_output == "json":
        output = {
            "name": surface.name,
            "title": surface.title,
            "mode": str(surface.mode),
            "entity_ref": surface.entity_ref,
            "sections": [
                {"name": sec.name, "elements": len(sec.elements)} for sec in surface.sections
            ],
        }
        typer.echo(json_module.dumps(output, indent=2))
    else:
        typer.echo(f"🖥️  Surface: {surface.name}")
        if surface.title:
            typer.echo(f"   Title: {surface.title}")
        typer.echo(f"   Mode: {surface.mode}")
        if surface.entity_ref:
            typer.echo(f"   Entity: {surface.entity_ref}")
        typer.echo()
        typer.echo("   Sections:")
        for sec in surface.sections:
            typer.echo(f"   • {sec.name}: {len(sec.elements)} elements")


def _inspect_workspace(
    appspec: ir.AppSpec,
    ui_spec: UISpec,
    workspace_name: str,
    format_output: str,
) -> None:
    """Inspect a specific workspace."""
    import json as json_module

    # Find workspace
    workspace = next((w for w in appspec.workspaces if w.name == workspace_name), None)
    if not workspace:
        typer.echo(f"Workspace '{workspace_name}' not found", err=True)
        typer.echo(f"Available: {', '.join(w.name for w in appspec.workspaces)}")
        raise typer.Exit(code=1)

    if format_output == "json":
        output = {
            "name": workspace.name,
            "title": workspace.title,
            "purpose": workspace.purpose,
            "regions": [{"name": r.name, "source": r.source} for r in workspace.regions],
        }
        typer.echo(json_module.dumps(output, indent=2))
    else:
        typer.echo(f"📁 Workspace: {workspace.name}")
        if workspace.title:
            typer.echo(f"   Title: {workspace.title}")
        if workspace.purpose:
            typer.echo(f"   Purpose: {workspace.purpose}")
        typer.echo()
        typer.echo("   Regions:")
        for r in workspace.regions:
            typer.echo(f"   • {r.name}: {r.source}")


def _inspect_endpoints(backend_spec: BackendSpec, format_output: str) -> None:
    """Inspect API endpoints."""
    import json as json_module

    if format_output == "json":
        output = [
            {"method": str(ep.method), "path": ep.path, "name": ep.name}
            for ep in backend_spec.endpoints
        ]
        typer.echo(json_module.dumps(output, indent=2))
    else:
        typer.echo("🔧 API Endpoints")
        typer.echo()
        # Group by entity/path prefix
        for ep in sorted(backend_spec.endpoints, key=lambda e: (e.path, str(e.method))):
            typer.echo(f"   {str(ep.method):6} {ep.path}")


def _inspect_components(ui_spec: UISpec, format_output: str) -> None:
    """Inspect UI components."""
    import json as json_module

    if format_output == "json":
        output = [{"name": c.name, "category": c.category} for c in ui_spec.components]
        typer.echo(json_module.dumps(output, indent=2))
    else:
        typer.echo("🎨 UI Components")
        typer.echo()
        for c in ui_spec.components:
            typer.echo(f"   • {c.name} ({c.category})")


def _inspect_live(api_url: str, format_output: str, entity_name: str | None = None) -> None:
    """Query running DNR server for runtime state."""
    import json as json_module
    import urllib.error
    import urllib.request

    def fetch_json(endpoint: str) -> dict[str, Any] | None:
        """Fetch JSON from API endpoint."""
        url = f"{api_url.rstrip('/')}{endpoint}"
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                result: dict[str, Any] = json_module.loads(response.read().decode())
                return result
        except urllib.error.URLError as e:
            typer.echo(f"Error connecting to {url}: {e}", err=True)
            return None
        except Exception as e:
            typer.echo(f"Error fetching {endpoint}: {e}", err=True)
            return None

    # If entity specified, get entity details
    if entity_name:
        data = fetch_json(f"/_dnr/entity/{entity_name}")
        if not data:
            raise typer.Exit(code=1)

        if "error" in data:
            typer.echo(f"Error: {data['error']}", err=True)
            raise typer.Exit(code=1)

        if format_output == "json":
            typer.echo(json_module.dumps(data, indent=2, default=str))
        else:
            typer.echo(f"📊 Entity: {data['name']} (live)")
            if data.get("label"):
                typer.echo(f"   Label: {data['label']}")
            if data.get("description"):
                typer.echo(f"   Description: {data['description']}")
            typer.echo(f"   Records: {data.get('count', 0)}")
            typer.echo()
            typer.echo("   Fields:")
            for f in data.get("fields", []):
                req = " (required)" if f.get("required") else ""
                unique = " [unique]" if f.get("unique") else ""
                indexed = " [indexed]" if f.get("indexed") else ""
                typer.echo(f"   • {f['name']}: {f['type']}{req}{unique}{indexed}")

            if data.get("sample"):
                typer.echo()
                typer.echo(f"   Sample data ({len(data['sample'])} records):")
                for row in data["sample"][:3]:  # Show max 3
                    # Show a compact view of the row
                    preview = ", ".join(f"{k}={v!r}" for k, v in list(row.items())[:4])
                    if len(row) > 4:
                        preview += ", ..."
                    typer.echo(f"   • {preview}")
        return

    # Get overall stats
    stats = fetch_json("/_dnr/stats")
    health = fetch_json("/_dnr/health")
    spec = fetch_json("/_dnr/spec")

    if not stats:
        typer.echo("Could not connect to DNR server", err=True)
        typer.echo(f"Tried: {api_url}/_dnr/stats")
        typer.echo()
        typer.echo("Make sure the server is running:")
        typer.echo("  dazzle dnr serve")
        raise typer.Exit(code=1)

    if format_output == "json":
        output = {
            "stats": stats,
            "health": health,
            "spec": spec,
        }
        typer.echo(json_module.dumps(output, indent=2, default=str))
    elif format_output == "summary":
        typer.echo(f"App: {stats.get('app_name', 'Unknown')}")
        typer.echo(f"  Status:       {health.get('status', 'unknown') if health else 'unknown'}")
        typer.echo(f"  Uptime:       {_format_uptime(stats.get('uptime_seconds', 0))}")
        typer.echo(f"  Total records: {stats.get('total_records', 0)}")
        typer.echo(f"  Entities:     {len(stats.get('entities', []))}")
    else:  # tree format
        status_emoji = "✅" if health and health.get("status") == "ok" else "⚠️"
        typer.echo(f"📦 {stats.get('app_name', 'Unknown')} (live)")
        typer.echo(f"│  {status_emoji} Status: {health.get('status', 'unknown') if health else 'unknown'}")
        typer.echo(f"│  ⏱️  Uptime: {_format_uptime(stats.get('uptime_seconds', 0))}")
        typer.echo("│")

        # Show entities with record counts
        entities = stats.get("entities", [])
        if entities:
            typer.echo("├── 📊 Entities (with record counts)")
            for i, ent in enumerate(entities):
                prefix = "│   └──" if i == len(entities) - 1 else "│   ├──"
                fts_badge = " 🔍" if ent.get("has_fts") else ""
                typer.echo(f"{prefix} {ent['name']}: {ent['count']} records{fts_badge}")

        # Show database info
        typer.echo("│")
        typer.echo(f"└── 💾 Total records: {stats.get('total_records', 0)}")


def _format_uptime(seconds: float) -> str:
    """Format uptime seconds into a human-readable string."""
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins}m {secs}s"
    else:
        hours = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        return f"{hours}h {mins}m"
