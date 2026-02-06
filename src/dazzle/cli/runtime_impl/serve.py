"""
Dazzle serve command.

Start the development server with frontend and backend.

Port Allocation:
    By default, ports are deterministically assigned based on project name
    to prevent collisions when running multiple Dazzle instances. Each project
    gets a consistent port pair (UI + API) derived from its name hash.

    Override with --port and --api-port for explicit control.
"""

from __future__ import annotations

import atexit
import http.server
import os
import socketserver
import tempfile
from pathlib import Path
from typing import Any

import typer

from dazzle.core.environment import (
    get_dazzle_env,
    should_enable_test_endpoints,
)
from dazzle.core.errors import DazzleError, ParseError
from dazzle.core.fileset import discover_dsl_files
from dazzle.core.linker import build_appspec
from dazzle.core.lint import lint_appspec
from dazzle.core.manifest import load_manifest
from dazzle.core.parser import parse_modules
from dazzle.core.sitespec_loader import load_sitespec, sitespec_exists

from .ports import (
    clear_runtime_file,
    find_available_ports,
    write_runtime_file,
)


def serve_command(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    port: int = typer.Option(None, "--port", "-p", help="Frontend port (auto-assigned if not set)"),
    api_port: int = typer.Option(
        None, "--api-port", help="Backend API port (auto-assigned if not set)"
    ),
    host: str = typer.Option("127.0.0.1", "--host", help="Host to bind to"),
    ui_only: bool = typer.Option(False, "--ui-only", help="Serve UI only (static files)"),
    backend_only: bool = typer.Option(
        False,
        "--backend-only",
        help="Serve backend API only (no frontend UI)",
    ),
    db_path: str = typer.Option(".dazzle/data.db", "--db", help="SQLite database path"),
    test_mode: bool | None = typer.Option(
        None,
        "--test-mode/--no-test-mode",
        help="Enable test endpoints. Default based on DAZZLE_ENV (enabled in development/test).",
    ),
    dev_mode: bool | None = typer.Option(
        None,
        "--dev-mode/--no-dev-mode",
        help="Enable Dazzle Bar. Default based on DAZZLE_ENV (enabled in development only).",
    ),
    watch: bool = typer.Option(
        False,
        "--watch",
        "-w",
        help="Enable hot reload: watch DSL files and auto-refresh browser on changes",
    ),
    watch_source: bool = typer.Option(
        False,
        "--watch-source",
        "-W",
        help="Also watch framework source files (Python, CSS, JS). Implies --watch.",
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
    graphql: bool = typer.Option(
        False,
        "--graphql",
        help="Enable GraphQL endpoint at /graphql (requires strawberry-graphql)",
    ),
    database_url: str = typer.Option(
        "",
        "--database-url",
        help="PostgreSQL URL. Also reads DATABASE_URL env var.",
    ),
) -> None:
    """
    Serve Dazzle app (backend API + UI with live data).

    By default, runs frontend and backend in separate Docker containers.
    Use --local to run without Docker.

    Runs:
    - FastAPI backend on api-port (default 8000) with SQLite persistence
    - Jinja2/HTMX frontend on port (default 3000)
    - Auto-migration for schema changes
    - Interactive API docs at http://host:api-port/docs

    Examples:
        dazzle serve                    # Docker mode (default)
        dazzle serve --local --watch    # Local mode with hot reload
        dazzle serve --attach           # Run Docker with log streaming
        dazzle serve --local            # Run locally without Docker
        dazzle serve --backend-only     # API server only (for separate frontend)
        dazzle serve --rebuild          # Force Docker image rebuild
        dazzle serve --port 4000        # Frontend on 4000
        dazzle serve --api-port 9000    # API on 9000
        dazzle serve --ui-only          # Static UI only (no API)
        dazzle serve --db ./my.db       # Custom database path
        dazzle serve --no-test-mode     # Disable E2E test endpoints
        dazzle serve --graphql          # Enable GraphQL at /graphql

    Hot reload (--watch):
        Watch DSL files for changes and auto-refresh browser.
        Currently only works in --local mode.

    Related commands:
        dazzle stop                     # Stop the running container
        dazzle rebuild                  # Rebuild and restart container
        dazzle logs                     # View container logs
    """
    # Resolve project path from manifest
    manifest_path = Path(manifest).resolve()
    project_root = manifest_path.parent

    # Load manifest to get auth config and project name
    dev_config_override_test: bool | None = None
    try:
        mf = load_manifest(manifest_path)
        auth_enabled = mf.auth.enabled
        project_name = mf.name or project_root.name
        # Get manifest dev config overrides (v0.24.0)
        dev_config_override_test = mf.dev.test_endpoints
    except Exception:
        auth_enabled = False
        project_name = project_root.name

    # Resolve dev_mode and test_mode based on:
    # 1. CLI option (if explicitly set)
    # 2. Manifest [dev] section (if set)
    # 3. Environment defaults (based on DAZZLE_ENV)
    # (v0.24.0 - environment-aware dev features)
    env = get_dazzle_env()

    if dev_mode is None:
        # CLI not set - enable in development env
        enable_dev_mode = env.value == "development"
    else:
        # CLI explicitly set - honor it
        enable_dev_mode = dev_mode

    if test_mode is None:
        # CLI not set - use manifest or environment default
        enable_test_mode = should_enable_test_endpoints(dev_config_override_test)
    else:
        # CLI explicitly set - honor it
        enable_test_mode = test_mode

    # Resolve DATABASE_URL from CLI flag or environment
    if not database_url:
        database_url = os.environ.get("DATABASE_URL", "")
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    # Ensure env var is set for subcomponents that read it
    if database_url:
        os.environ["DATABASE_URL"] = database_url

    # Allocate ports based on project name (deterministic hashing)
    # This prevents collisions when running multiple Dazzle instances
    allocation = find_available_ports(
        project_name=project_name,
        ui_port=port,
        api_port=api_port,
        host=host,
    )
    port = allocation.ui_port
    api_port = allocation.api_port

    # Show port allocation info if auto-assigned
    if allocation.ui_port != 3000 or allocation.api_port != 8000:
        typer.echo(f"Port allocation for '{project_name}':")
        typer.echo(f"  UI:  {allocation.ui_port}")
        typer.echo(f"  API: {allocation.api_port}")
        typer.echo()

    # Write runtime file for port discovery by E2E tests
    write_runtime_file(project_root, allocation)

    # Clean up runtime file on exit
    def cleanup_runtime() -> None:
        clear_runtime_file(project_root)

    atexit.register(cleanup_runtime)

    # --watch-source implies --watch
    if watch_source:
        watch = True

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
            from dazzle_ui.runtime import is_docker_available, run_in_docker

            if is_docker_available():
                detach = not attach  # Default to detached (no logs), --attach streams logs
                auth_desc = " with auth" if auth_enabled else ""
                typer.echo(
                    f"Running in Docker mode{auth_desc} (use --local to run without Docker)"
                    if attach
                    else f"Starting Docker containers in background{auth_desc}..."
                )
                exit_code = run_in_docker(
                    project_path=project_root,
                    frontend_port=port,
                    api_port=api_port,
                    test_mode=enable_test_mode,
                    auth_enabled=auth_enabled,
                    rebuild=rebuild,
                    detach=detach,
                    project_name=project_name,
                    dev_mode=enable_dev_mode,
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
        from dazzle_back.converters import convert_appspec_to_backend
        from dazzle_back.runtime import FASTAPI_AVAILABLE
        from dazzle_ui.converters import compute_persona_default_routes, convert_appspec_to_ui
        from dazzle_ui.runtime import run_combined_server
    except ImportError as e:
        typer.echo(f"Dazzle runtime not available: {e}", err=True)
        typer.echo("Install with: pip install dazzle-app-back dazzle-app-ui", err=True)
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

    # Load SiteSpec if available (v0.16.0)
    sitespec_data = None
    if sitespec_exists(project_root):
        try:
            sitespec = load_sitespec(project_root)
            sitespec_data = sitespec.model_dump()
            typer.echo(f"  • SiteSpec: loaded ({len(sitespec.pages)} pages)")
        except Exception as e:
            typer.echo(f"Warning: Failed to load sitespec.yaml: {e}", err=True)
            # Continue without SiteSpec - it's optional

    if ui_only:
        # Serve UI only with static preview files
        from dazzle_ui.runtime.static_preview import generate_preview_files

        with tempfile.TemporaryDirectory() as tmpdir:
            preview_files = generate_preview_files(appspec, tmpdir)
            # Create an index.html that links to all previews
            if preview_files:
                # Copy the first list file as index.html
                first = preview_files[0]
                (Path(tmpdir) / "index.html").write_text(first.read_text())

            os.chdir(tmpdir)
            handler = http.server.SimpleHTTPRequestHandler
            typer.echo(f"\nServing Dazzle UI preview at http://{host}:{port}")
            typer.echo(f"  {len(preview_files)} preview files generated")
            typer.echo("Press Ctrl+C to stop\n")

            with socketserver.TCPServer((host, port), handler) as httpd:
                try:
                    httpd.serve_forever()
                except KeyboardInterrupt:
                    typer.echo("\nStopped.")
        return

    if backend_only:
        # Serve backend API only (no frontend UI)
        from dazzle_ui.runtime import run_backend_only

        backend_spec = convert_appspec_to_backend(appspec)

        typer.echo(f"Starting Dazzle backend for '{appspec.name}'...")
        typer.echo(f"  • {len(backend_spec.entities)} entities")
        typer.echo(f"  • {len(backend_spec.endpoints)} endpoints")
        if database_url:
            typer.echo("  • Database: PostgreSQL (DATABASE_URL)")
        else:
            typer.echo(f"  • Database: {db_path}")
        if enable_test_mode:
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
            enable_test_mode=enable_test_mode,
            enable_dev_mode=enable_dev_mode,
            enable_graphql=graphql,
            host=host,
            sitespec_data=sitespec_data,
            project_root=project_root,
        )
        return

    # Full combined server with API + UI
    typer.echo(f"Starting Dazzle server for '{appspec.name}'...")

    # Convert specs (pass shell config from manifest)
    backend_spec = convert_appspec_to_backend(appspec)
    ui_spec = convert_appspec_to_ui(appspec, shell_config=mf.shell)

    typer.echo(f"  • {len(backend_spec.entities)} entities")
    typer.echo(f"  • {len(backend_spec.endpoints)} endpoints")
    typer.echo(f"  • {len(ui_spec.workspaces)} workspaces")
    if database_url:
        typer.echo("  • Database: PostgreSQL (DATABASE_URL)")
    else:
        typer.echo(f"  • Database: {db_path}")

    # Extract personas and scenarios for Dazzle Bar (v0.8.5)
    # Compute default routes from workspace access rules (v0.23.0)
    persona_routes = compute_persona_default_routes(appspec.personas, appspec.workspaces)
    personas = [
        {
            "id": p.id,
            "label": p.label,
            "description": p.description,
            "goals": p.goals,
            "default_route": persona_routes.get(p.id),
        }
        for p in appspec.personas
    ]
    scenarios = [
        {
            "id": s.id,
            "name": s.name,
            "description": s.description,
            "demo_fixtures": [{"entity": f.entity, "records": f.records} for f in s.demo_fixtures],
            "seed_data_path": s.seed_data_path,
            "persona_entries": [
                {
                    "persona_id": e.persona_id,
                    "start_route": e.start_route,
                    "seed_script": e.seed_script,
                }
                for e in s.persona_entries
            ],
        }
        for s in appspec.scenarios
    ]

    if personas:
        typer.echo(f"  • {len(personas)} personas (Dazzle Bar)")
    if scenarios:
        typer.echo(f"  • {len(scenarios)} scenarios (Dazzle Bar)")

    typer.echo()

    # Ensure database directory exists
    db_file = Path(db_path)
    db_file.parent.mkdir(parents=True, exist_ok=True)

    # Run combined server
    # Show environment and mode status (v0.24.0)
    typer.echo(f"  • Environment: {env.value.upper()}")
    if enable_dev_mode:
        typer.echo(
            "  • Dazzle Bar: ENABLED (use --no-dev-mode or DAZZLE_ENV=production to disable)"
        )
    if enable_test_mode:
        typer.echo("  • Test mode: ENABLED (/__test__/* endpoints available)")

    # Show hot reload status
    if watch:
        typer.echo("  • Hot reload: ENABLED (watching DSL files)")

    # Build theme overrides from manifest (v0.16.0)
    theme_overrides: dict[str, Any] = {}
    if mf.theme.colors:
        theme_overrides["colors"] = mf.theme.colors
    if mf.theme.shadows:
        theme_overrides["shadows"] = mf.theme.shadows
    if mf.theme.spacing:
        theme_overrides["spacing"] = mf.theme.spacing
    if mf.theme.radii:
        theme_overrides["radii"] = mf.theme.radii
    if mf.theme.custom:
        theme_overrides["custom"] = mf.theme.custom

    run_combined_server(
        backend_spec=backend_spec,
        ui_spec=ui_spec,
        backend_port=api_port,
        frontend_port=port,
        db_path=db_file,
        enable_test_mode=enable_test_mode,
        enable_dev_mode=enable_dev_mode,
        enable_auth=auth_enabled,
        auth_config=mf.auth if auth_enabled else None,
        host=host,
        enable_watch=watch,
        watch_source=watch_source,
        project_root=project_root,
        personas=personas,
        scenarios=scenarios,
        sitespec_data=sitespec_data,
        theme_preset=mf.theme.preset,
        theme_overrides=theme_overrides if theme_overrides else None,
        appspec=appspec,
    )
