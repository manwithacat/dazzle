"""
DNR serve command.

Start the DNR development server with frontend and backend.
"""

from __future__ import annotations

import http.server
import os
import socketserver
import tempfile
from pathlib import Path

import typer

from dazzle.core.errors import DazzleError, ParseError
from dazzle.core.fileset import discover_dsl_files
from dazzle.core.linker import build_appspec
from dazzle.core.lint import lint_appspec
from dazzle.core.manifest import load_manifest
from dazzle.core.parser import parse_modules


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
    graphql: bool = typer.Option(
        False,
        "--graphql",
        help="Enable GraphQL endpoint at /graphql (requires strawberry-graphql)",
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
        dazzle dnr serve --graphql          # Enable GraphQL at /graphql

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
        if graphql:
            typer.echo("  • GraphQL: ENABLED (/graphql endpoint)")
        typer.echo()
        typer.echo(f"API: http://{host}:{api_port}")
        typer.echo(f"Docs: http://{host}:{api_port}/docs")
        if graphql:
            typer.echo(f"GraphQL: http://{host}:{api_port}/graphql")
        typer.echo()

        db_file = Path(db_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)

        run_backend_only(
            backend_spec=backend_spec,
            port=api_port,
            db_path=db_file,
            enable_test_mode=test_mode,
            enable_graphql=graphql,
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
