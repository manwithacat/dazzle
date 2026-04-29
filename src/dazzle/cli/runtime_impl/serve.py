"""
Dazzle serve command.

Start the development server with frontend and backend.

Port Allocation:
    By default, ports are deterministically assigned based on project name
    to prevent collisions when running multiple Dazzle instances. Each project
    gets a consistent port pair (UI + API) derived from its name hash.

    Override with --port and --api-port for explicit control.
"""

import atexit
import http.server
import os
import socketserver
import tempfile
from pathlib import Path
from typing import Any

import typer

from dazzle.cli.dotenv import load_project_dotenv as _load_dotenv
from dazzle.cli.utils import load_project_appspec
from dazzle.core.environment import (
    get_dazzle_env,
    should_enable_test_endpoints,
)
from dazzle.core.errors import DazzleError, ParseError
from dazzle.core.lint import lint_appspec
from dazzle.core.manifest import load_manifest
from dazzle.core.sitespec_loader import load_sitespec, sitespec_exists

from .ports import (
    PortAllocation,
    clear_runtime_file,
    find_available_ports,
    write_runtime_file,
)
from .production import configure_production_logging, validate_production_env


def _validate_infrastructure() -> tuple[str, str]:
    """Validate that required infrastructure env vars are set.

    Returns:
        (database_url, redis_url) tuple.

    Raises:
        SystemExit: If required env vars are missing and
            DAZZLE_SKIP_INFRA_CHECK is not set.
    """
    if os.environ.get("DAZZLE_SKIP_INFRA_CHECK") == "1":
        return os.environ.get("DATABASE_URL", ""), os.environ.get("REDIS_URL", "")

    missing: list[str] = []
    database_url = os.environ.get("DATABASE_URL", "")
    redis_url = os.environ.get("REDIS_URL", "")

    if not database_url:
        missing.append("DATABASE_URL")
    if not redis_url:
        missing.append("REDIS_URL")

    if missing:
        typer.echo("Dazzle requires PostgreSQL + Redis infrastructure.", err=True)
        typer.echo(f"Missing environment variables: {', '.join(missing)}", err=True)
        typer.echo("", err=True)
        typer.echo("Set them in .env (loaded automatically) or export before running:", err=True)
        typer.echo("  export DATABASE_URL=postgresql://localhost:5432/dazzle_dev", err=True)
        typer.echo("  export REDIS_URL=redis://localhost:6379/0", err=True)
        typer.echo("", err=True)
        typer.echo(
            "Skip this check with DAZZLE_SKIP_INFRA_CHECK=1 (tests only).",
            err=True,
        )
        raise typer.Exit(code=1)

    # Normalize postgres:// → postgresql://
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    return database_url, redis_url


def _print_infra_banner(
    database_url: str, redis_url: str, event_tier: str, process_backend: str
) -> None:
    """Print infrastructure status banner after validation passes."""
    typer.echo("Dazzle Infrastructure")
    typer.echo(f"  PostgreSQL: {database_url}")
    typer.echo(f"  Redis:      {redis_url}")
    typer.echo(f"  Event Bus:  {event_tier}")
    typer.echo(f"  Processes:  {process_backend}")
    typer.echo()


class _ServeContext:
    """Mutable bag of state threaded through serve_command helpers."""

    __slots__ = (
        "manifest_path",
        "project_root",
        "mf",
        "auth_enabled",
        "project_name",
        "dev_config_override_test",
        "production",
        "host",
        "port",
        "api_port",
        "database_url",
        "redis_url",
        "local",
        "watch",
        "watch_source",
        "enable_dev_mode",
        "enable_test_mode",
        "auto_mock",
        "env",
        "ui_only",
        "backend_only",
        "graphql",
        "workers",
        "local_assets",
        "bundle",
        "sitespec_data",
        "appspec",
    )

    def __init__(self) -> None:
        self.manifest_path: Path = Path(".")
        self.project_root: Path = Path(".")
        self.mf: Any = None
        self.auth_enabled: bool = False
        self.project_name: str = ""
        self.dev_config_override_test: bool | None = None
        self.production: bool = False
        self.host: str = "0.0.0.0"
        self.port: int = 3000
        self.api_port: int = 8000
        self.database_url: str = ""
        self.redis_url: str = ""
        self.local: bool = False
        self.watch: bool = False
        self.watch_source: bool = False
        self.enable_dev_mode: bool = False
        self.enable_test_mode: bool = False
        self.auto_mock: bool | None = False
        self.env: Any = None
        self.ui_only: bool = False
        self.backend_only: bool = False
        self.graphql: bool = False
        self.workers: int | None = 1
        self.local_assets: bool | None = False
        self.bundle: bool | None = None
        self.sitespec_data: dict[str, Any] | None = None
        self.appspec: Any = None


def _load_manifest_and_dotenv(ctx: _ServeContext, manifest: str) -> None:
    """Resolve project root, load .env, and load manifest."""
    ctx.manifest_path = Path(manifest).resolve()
    ctx.project_root = ctx.manifest_path.parent

    _dotenv_loaded = _load_dotenv(ctx.project_root)
    if _dotenv_loaded:
        typer.echo(f"Loaded .env ({len(_dotenv_loaded)} vars): {', '.join(_dotenv_loaded)}")

    try:
        ctx.mf = load_manifest(ctx.manifest_path)
        from dazzle.core.manifest import check_framework_version

        try:
            if ctx.mf:
                check_framework_version(ctx.mf)
        except SystemExit:
            raise
        ctx.auth_enabled = ctx.mf.auth.enabled
        ctx.project_name = ctx.mf.name or ctx.project_root.name
        ctx.dev_config_override_test = ctx.mf.dev.test_endpoints
    except Exception:
        ctx.auth_enabled = False
        ctx.project_name = ctx.project_root.name


def _configure_production_mode(ctx: _ServeContext) -> None:
    """Apply production overrides: logging, env validation, migration check."""
    configure_production_logging()
    database_url_prod, redis_url_prod = validate_production_env()

    from dazzle.core.fileset import discover_dsl_files as _discover

    try:
        mf_check = load_manifest(ctx.manifest_path)
        dsl_files = _discover(ctx.project_root, mf_check)
    except Exception:
        dsl_files = []
    if not dsl_files:
        typer.echo(
            "No DSL files found in current directory. "
            "Run dazzle serve --production from your project root.",
            err=True,
        )
        raise typer.Exit(code=1)

    ctx.host = "0.0.0.0"
    port_env = os.environ.get("PORT")
    if port_env:
        try:
            ctx.port = int(port_env)
        except ValueError:
            pass
    ctx.database_url = database_url_prod
    ctx.redis_url = redis_url_prod or ""
    os.environ["DATABASE_URL"] = ctx.database_url
    if ctx.redis_url:
        os.environ["REDIS_URL"] = ctx.redis_url

    ctx.local = True
    ctx.watch = False
    ctx.watch_source = False
    ctx.enable_dev_mode = False
    ctx.enable_test_mode = False
    ctx.auto_mock = False

    # Refuse to start with pending migrations
    try:
        from alembic import command
        from alembic.config import Config as AlembicConfig
        from alembic.util.exc import CommandError

        from dazzle.cli.db import _get_framework_alembic_dir, _get_project_versions_dir

        framework_dir = _get_framework_alembic_dir()
        cfg = AlembicConfig(str(framework_dir / "alembic.ini"))
        cfg.set_main_option("script_location", str(framework_dir))
        cfg.set_main_option(
            "version_locations",
            f"{framework_dir / 'versions'} {_get_project_versions_dir()}",
        )
        cfg.set_main_option("sqlalchemy.url", ctx.database_url)

        try:
            command.check(cfg)
        except CommandError:
            typer.echo(
                "Cannot start in production mode: pending migrations detected. "
                "Run 'dazzle db migrate' first.",
                err=True,
            )
            raise typer.Exit(code=1)
    except ImportError:
        pass

    ctx.env = get_dazzle_env()


def _configure_dev_mode(
    ctx: _ServeContext,
    dev_mode: bool | None,
    test_mode: bool | None,
) -> None:
    """Resolve dev/test mode flags and database URL for non-production runs."""
    ctx.env = get_dazzle_env()

    if dev_mode is None:
        ctx.enable_dev_mode = ctx.env.value == "development"
    else:
        ctx.enable_dev_mode = dev_mode

    if test_mode is None:
        ctx.enable_test_mode = should_enable_test_endpoints(ctx.dev_config_override_test)
    else:
        ctx.enable_test_mode = test_mode

    from dazzle.core.manifest import resolve_database_url

    ctx.database_url = resolve_database_url(ctx.mf, explicit_url=ctx.database_url)
    ctx.redis_url = os.environ.get("REDIS_URL", "")


def _allocate_ports_and_runtime(ctx: _ServeContext) -> None:
    """Allocate ports, write runtime file, register cleanup."""
    allocation = find_available_ports(
        project_name=ctx.project_name,
        ui_port=ctx.port,
        api_port=ctx.api_port,
        host=ctx.host,
    )
    ctx.port = allocation.ui_port
    ctx.api_port = allocation.api_port

    if allocation.ui_port != 3000 or allocation.api_port != 8000:
        typer.echo(f"Port allocation for '{ctx.project_name}':")
        typer.echo(f"  UI:  {allocation.ui_port}")
        typer.echo(f"  API: {allocation.api_port}")
        typer.echo()

    # In unified mode the API is served on the UI port — collapse for runtime.json
    if not ctx.backend_only and not ctx.ui_only:
        allocation = PortAllocation(
            ui_port=allocation.ui_port,
            api_port=allocation.ui_port,
            project_name=allocation.project_name,
        )

    # In test mode, generate/read a shared secret and publish it so
    # `dazzle test create-sessions` can authenticate without the caller
    # setting DAZZLE_TEST_SECRET in their own env (#790).
    test_secret: str | None = None
    if ctx.enable_test_mode:
        test_secret = os.environ.get("DAZZLE_TEST_SECRET", "")
        if not test_secret:
            import secrets

            test_secret = secrets.token_urlsafe(24)
            os.environ["DAZZLE_TEST_SECRET"] = test_secret

    write_runtime_file(ctx.project_root, allocation, test_secret=test_secret)

    def cleanup_runtime() -> None:
        clear_runtime_file(ctx.project_root)

    atexit.register(cleanup_runtime)

    if ctx.watch_source:
        ctx.watch = True


def _start_docker_infrastructure(ctx: _ServeContext) -> None:
    """Start Postgres + Redis in Docker if available, mutating ctx URLs."""
    if ctx.local or ctx.ui_only or ctx.backend_only:
        return

    try:
        from dazzle_ui.runtime.docker.utils import is_docker_available

        if is_docker_available():
            from dazzle.cli.runtime_impl.docker import (
                start_dev_infrastructure,
                stop_dev_infrastructure,
            )

            typer.echo("Starting dev infrastructure (Postgres + Redis) in Docker...")
            try:
                infra_db_url, infra_redis_url = start_dev_infrastructure(
                    project_root=ctx.project_root,
                    project_name=ctx.project_name,
                )
                os.environ["DATABASE_URL"] = infra_db_url
                os.environ["REDIS_URL"] = infra_redis_url
                ctx.database_url = infra_db_url
                ctx.redis_url = infra_redis_url

                typer.echo("  PostgreSQL: ready")
                typer.echo("  Redis:      ready")
                typer.echo()

                def _stop_infra() -> None:
                    typer.echo("Stopping dev infrastructure...")
                    stop_dev_infrastructure(ctx.project_root)

                atexit.register(_stop_infra)

            except RuntimeError as exc:
                typer.echo(f"Docker infrastructure failed: {exc}", err=True)
                typer.echo("Falling back to local mode (ensure DATABASE_URL and REDIS_URL are set)")
                typer.echo()
        else:
            typer.echo("Docker not available, falling back to local mode")
            typer.echo("Install Docker for automatic Postgres + Redis setup")
            typer.echo()
    except ImportError:
        pass


def _validate_and_finalize_infra(ctx: _ServeContext) -> None:
    """Ensure DATABASE_URL env var is set and validate infrastructure."""
    if ctx.database_url:
        os.environ["DATABASE_URL"] = ctx.database_url

    validated_db_url, validated_redis_url = _validate_infrastructure()
    if not ctx.database_url and validated_db_url:
        ctx.database_url = validated_db_url
        os.environ["DATABASE_URL"] = ctx.database_url
    if not ctx.redis_url and validated_redis_url:
        ctx.redis_url = validated_redis_url


def _load_appspec_and_subsystems(ctx: _ServeContext) -> None:
    """Import runtime, load AppSpec, start vendor mocks, load SiteSpec."""
    try:
        from dazzle_back.runtime import FASTAPI_AVAILABLE
    except ImportError as e:
        typer.echo(f"Dazzle runtime not available: {e}", err=True)
        typer.echo("Install with: pip install dazzle-dsl[serve]", err=True)
        raise typer.Exit(code=1)

    if not FASTAPI_AVAILABLE and not ctx.ui_only:
        typer.echo("FastAPI not installed. Use --ui-only or install:", err=True)
        typer.echo("  pip install fastapi uvicorn", err=True)
        raise typer.Exit(code=1)

    try:
        ctx.appspec = load_project_appspec(ctx.project_root)

        errors, _, _relevance = lint_appspec(ctx.appspec)
        if errors:
            typer.echo("Cannot serve; spec has validation errors:", err=True)
            for err in errors:
                typer.echo(f"  ERROR: {err}", err=True)
            raise typer.Exit(code=1)

    except (ParseError, DazzleError) as e:
        typer.echo(f"Error loading spec: {e}", err=True)
        raise typer.Exit(code=1)

    # Auto-start vendor mocks (v0.32.0)
    should_mock = ctx.auto_mock if ctx.auto_mock is not None else ctx.local
    if should_mock and not ctx.ui_only:
        _start_vendor_mocks(ctx)

    # Load SiteSpec (v0.16.0)
    if sitespec_exists(ctx.project_root):
        try:
            sitespec = load_sitespec(ctx.project_root)
            ctx.sitespec_data = sitespec.model_dump()
            typer.echo(f"  • SiteSpec: loaded ({len(sitespec.pages)} pages)")
        except Exception as e:
            typer.echo(f"Warning: Failed to load sitespec.yaml: {e}", err=True)


def _start_vendor_mocks(ctx: _ServeContext) -> None:
    """Auto-start vendor mocks for API packs without credentials."""
    try:
        from dazzle.testing.vendor_mock.orchestrator import (
            MockOrchestrator,
            discover_packs_from_appspec,
        )

        packs = discover_packs_from_appspec(ctx.appspec)
        if packs:
            mock_orch = MockOrchestrator.from_appspec(
                ctx.appspec, base_port=9001, project_root=ctx.project_root
            )
            mock_orch.start()
            for _name, mock in mock_orch.vendors.items():
                typer.echo(f"  • Mock: {mock.provider} on :{mock.port} ({mock.env_var})")
            try:
                from dazzle.mcp.server.state import set_mock_orchestrator

                set_mock_orchestrator(mock_orch)
            except Exception:
                pass
    except Exception as e:
        typer.echo(f"  Warning: Vendor mock setup failed: {e}", err=True)


def _serve_ui_only(ctx: _ServeContext) -> None:
    """Serve UI-only static preview files."""
    from dazzle_ui.runtime.static_preview import generate_preview_files

    with tempfile.TemporaryDirectory() as tmpdir:
        preview_files = generate_preview_files(ctx.appspec, tmpdir)
        if preview_files:
            first = preview_files[0]
            (Path(tmpdir) / "index.html").write_text(first.read_text())

        os.chdir(tmpdir)
        handler = http.server.SimpleHTTPRequestHandler
        typer.echo(f"\nServing Dazzle UI preview at http://{ctx.host}:{ctx.port}")
        typer.echo(f"  {len(preview_files)} preview files generated")
        typer.echo("Press Ctrl+C to stop\n")

        with socketserver.TCPServer((ctx.host, ctx.port), handler) as httpd:
            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                typer.echo("\nStopped.")


def _serve_backend_only(ctx: _ServeContext) -> None:
    """Serve backend API only (no frontend UI)."""
    from dazzle_ui.runtime import run_backend_only

    typer.echo(f"Starting Dazzle backend for '{ctx.appspec.name}'...")
    typer.echo(f"  • {len(ctx.appspec.domain.entities)} entities")
    typer.echo(f"  • {len(ctx.appspec.surfaces)} surfaces")
    typer.echo("  • Database: PostgreSQL (DATABASE_URL)")
    if ctx.enable_test_mode:
        typer.echo("  • Test mode: ENABLED (/__test__/* endpoints available)")
    if ctx.graphql:
        typer.echo("  • GraphQL: ENABLED (/graphql endpoint)")
    typer.echo()
    typer.echo(f"API: http://{ctx.host}:{ctx.api_port}")
    typer.echo(f"Docs: http://{ctx.host}:{ctx.api_port}/docs")
    if ctx.graphql:
        typer.echo(f"GraphQL: http://{ctx.host}:{ctx.api_port}/graphql")
    typer.echo()

    run_backend_only(
        appspec=ctx.appspec,
        port=ctx.api_port,
        enable_test_mode=ctx.enable_test_mode,
        enable_dev_mode=ctx.enable_dev_mode,
        enable_graphql=ctx.graphql,
        host=ctx.host,
        sitespec_data=ctx.sitespec_data,
        project_root=ctx.project_root,
        redis_url=ctx.redis_url,
        workers=ctx.workers,
        storage_defs=getattr(ctx.mf, "storage_defs", None) if ctx.mf else None,
    )


def _serve_combined(ctx: _ServeContext) -> None:
    """Serve full combined API + UI server."""
    from dazzle_ui.converters import compute_persona_default_routes, convert_appspec_to_ui
    from dazzle_ui.runtime import run_unified_server

    appspec = ctx.appspec
    mf = ctx.mf
    typer.echo(f"Starting Dazzle server for '{appspec.name}'...")

    assert mf is not None, "Manifest must be loaded for combined server mode"

    # #938 — wire `[ui] dark_mode_toggle` into the theme module so
    # both layouts (app shell + marketing) gate the toggle button on
    # the same flag, and a stale `dz_theme=dark` cookie can't trap a
    # newly opted-out project's users in dark-mode.
    from dazzle_ui.runtime.theme import configure_dark_mode_toggle

    configure_dark_mode_toggle(mf.dark_mode_toggle)

    ui_spec = convert_appspec_to_ui(appspec, shell_config=mf.shell)

    typer.echo(f"  • {len(appspec.domain.entities)} entities")
    typer.echo(f"  • {len(appspec.surfaces)} surfaces")
    typer.echo(f"  • {len(ui_spec.workspaces)} workspaces")
    typer.echo("  • Database: PostgreSQL (DATABASE_URL)")

    # Extract personas and scenarios for dev control plane
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
        typer.echo(f"  • {len(personas)} personas")
    if scenarios:
        typer.echo(f"  • {len(scenarios)} scenarios")

    typer.echo()

    # Show environment and mode status
    typer.echo(f"  • Environment: {ctx.env.value.upper()}")
    if ctx.enable_dev_mode:
        typer.echo("  • Dev mode: ENABLED (use --no-dev-mode or DAZZLE_ENV=production to disable)")
    if ctx.enable_test_mode:
        typer.echo("  • Test mode: ENABLED (/__test__/* endpoints available)")
    if ctx.watch:
        typer.echo("  • Hot reload: ENABLED (watching DSL files)")

    # Infrastructure banner
    if ctx.redis_url:
        event_tier = "Redis Streams"
        process_backend = "Celery + Beat"
    elif ctx.database_url:
        event_tier = "PostgreSQL"
        process_backend = "EventBus (PostgreSQL)"
    else:
        event_tier = "Memory"
        process_backend = "None (set REDIS_URL or DATABASE_URL)"
    _print_infra_banner(ctx.database_url, ctx.redis_url, event_tier, process_backend)

    # Theme overrides from manifest
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

    # Phase C Patch 4: when the active app theme declares a `[site]`
    # section, blend its preset + overrides onto the legacy `[theme]`
    # baseline so a single theme file can configure both layers.
    # Precedence: env DAZZLE_OVERRIDE_THEME > DSL `app: theme:` >
    # `[ui] app_theme` in dazzle.toml. The site config from the matched
    # theme overlays the manifest-supplied baseline (preset is replaced;
    # token categories are merged shallowly).
    _env_override_theme = os.environ.get("DAZZLE_OVERRIDE_THEME") or None
    _dsl_theme = (
        getattr(appspec.app_config, "theme", None)
        if getattr(appspec, "app_config", None) is not None
        else None
    )
    _active_theme = _env_override_theme or _dsl_theme or mf.app_theme
    _theme_preset = mf.theme.preset
    if _active_theme:
        from dazzle_ui.themes.app_theme_registry import resolve_site_config

        _site_preset, _site_overrides = resolve_site_config(
            _active_theme, project_root=ctx.project_root
        )
        if _site_preset is not None:
            _theme_preset = _site_preset
        for _category, _values in _site_overrides.items():
            existing = theme_overrides.setdefault(_category, {})
            existing.update(_values)

    # Resolve local_assets
    if ctx.local_assets is None:
        env_val = os.environ.get("DAZZLE_LOCAL_ASSETS")
        if env_val is not None:
            use_local_assets = env_val == "1"
        else:
            use_local_assets = not ctx.production
    else:
        use_local_assets = ctx.local_assets

    # QA mode for local non-production runs
    if ctx.local and not ctx.production:
        os.environ["DAZZLE_QA_MODE"] = "1"
        os.environ.setdefault("DAZZLE_ENV", "development")

    run_unified_server(
        appspec=appspec,
        ui_spec=ui_spec,
        port=ctx.port,
        enable_test_mode=ctx.enable_test_mode,
        enable_dev_mode=ctx.enable_dev_mode,
        enable_auth=ctx.auth_enabled,
        auth_config=mf.auth if ctx.auth_enabled else None,
        host=ctx.host,
        enable_watch=ctx.watch,
        watch_source=ctx.watch_source,
        project_root=ctx.project_root,
        personas=personas,
        scenarios=scenarios,
        sitespec_data=ctx.sitespec_data,
        theme_preset=_theme_preset,
        theme_overrides=theme_overrides if theme_overrides else None,
        redis_url=ctx.redis_url,
        workers=ctx.workers,
        tenant_config=mf.tenant if mf.tenant.isolation != "none" else None,
        local_assets=use_local_assets,
        storage_defs=getattr(mf, "storage_defs", None),
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
    test_mode: bool | None = typer.Option(
        None,
        "--test-mode/--no-test-mode",
        help="Enable test endpoints. Default based on DAZZLE_ENV (enabled in development/test).",
    ),
    dev_mode: bool | None = typer.Option(
        None,
        "--dev-mode/--no-dev-mode",
        help="Enable dev control plane. Default based on DAZZLE_ENV (enabled in development only).",
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
        help="Skip Docker infrastructure; require DATABASE_URL and REDIS_URL to be set manually",
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
    auto_mock: bool | None = typer.Option(
        None,
        "--mock/--no-mock",
        help="Auto-start vendor mocks for API packs without credentials. Default: enabled in local mode.",
    ),
    workers: int | None = typer.Option(
        None,
        "--workers",
        help="Number of uvicorn workers (default: 1).",
    ),
    local_assets: bool | None = typer.Option(
        None,
        "--local-assets/--cdn-assets",
        help="Serve JS/CSS from local installation instead of CDN. Default: local in dev, CDN in --production.",
    ),
    bundle: bool | None = typer.Option(
        None,
        "--bundle/--no-bundle",
        help=(
            "Asset bundling override. --bundle loads dist/dazzle.min.{js,css}; "
            "--no-bundle loads individual scripts (live-reload friendly). "
            "Default: resolved from `[ui] assets` in dazzle.toml + DAZZLE_ENV "
            "('auto' bundles in production, individual in dev)."
        ),
    ),
    production: bool = typer.Option(
        False,
        "--production",
        help="Production mode: bind 0.0.0.0, require DATABASE_URL, JSON logging, no dev features.",
    ),
) -> None:
    """
    Serve Dazzle app (backend API + UI with live data).

    By default, starts Postgres + Redis in Docker and runs the app locally.
    Use --local to skip Docker infrastructure (you must set DATABASE_URL
    and REDIS_URL yourself).

    Runs:
    - FastAPI backend on api-port (default 8000) with PostgreSQL persistence
    - Jinja2/HTMX frontend on port (default 3000)
    - Auto-migration for schema changes
    - Interactive API docs at http://host:api-port/docs

    Examples:
        dazzle serve                    # Start infra in Docker, run app locally
        dazzle serve --local            # No Docker; bring your own Postgres + Redis
        dazzle serve --watch            # With hot reload (DSL file watching)
        dazzle serve --backend-only     # API server only (for separate frontend)
        dazzle serve --port 4000        # Frontend on 4000
        dazzle serve --api-port 9000    # API on 9000
        dazzle serve --ui-only          # Static UI only (no API)
        dazzle serve --no-test-mode     # Disable E2E test endpoints
        dazzle serve --graphql          # Enable GraphQL at /graphql

    Hot reload (--watch):
        Watch DSL files for changes and auto-refresh browser.

    Related commands:
        dazzle stop                     # Stop dev infrastructure
        dazzle logs                     # View container logs
    """
    # Build context from CLI args
    ctx = _ServeContext()
    ctx.production = production
    ctx.host = host
    ctx.port = port
    ctx.api_port = api_port
    ctx.database_url = database_url
    ctx.local = local
    ctx.watch = watch
    ctx.watch_source = watch_source
    ctx.auto_mock = auto_mock
    ctx.ui_only = ui_only
    ctx.backend_only = backend_only
    ctx.graphql = graphql
    ctx.workers = workers
    ctx.local_assets = local_assets
    ctx.bundle = bundle

    # Phase 1: Load project manifest and .env
    _load_manifest_and_dotenv(ctx, manifest)

    # Resolve asset bundling decision and propagate via environment
    # variable so the template renderer's Jinja env globals pick it up
    # at engine init. Resolver order: CLI flag > [ui] assets in
    # dazzle.toml > DAZZLE_ENV. Set production-mode default to bundle.
    import os as _os

    from dazzle_ui.runtime.asset_bundle import should_bundle_assets

    _assets_mode = getattr(ctx.mf, "assets", "auto") if ctx.mf is not None else "auto"
    _cli_override: str | None
    if ctx.bundle is True:
        _cli_override = "bundle"
    elif ctx.bundle is False:
        _cli_override = "no-bundle"
    else:
        _cli_override = None
    # When --production is set without an explicit DAZZLE_ENV, treat as production
    # for the bundle decision so `dazzle serve --production` bundles by default.
    _resolved_env = _os.environ.get("DAZZLE_ENV") or ("production" if production else "")
    _bundle_decision = should_bundle_assets(
        _assets_mode,  # type: ignore[arg-type]
        env=_resolved_env,
        cli_override=_cli_override,  # type: ignore[arg-type]
    )
    _os.environ["DAZZLE_BUNDLE_ASSETS"] = "1" if _bundle_decision else "0"

    # Phase 2: Configure mode (production vs development)
    if production:
        _configure_production_mode(ctx)
    else:
        _configure_dev_mode(ctx, dev_mode, test_mode)

    # Phase 3: Port allocation and runtime file
    _allocate_ports_and_runtime(ctx)

    # Phase 4: Docker infrastructure (if applicable)
    _start_docker_infrastructure(ctx)

    # Phase 5: Validate infrastructure
    _validate_and_finalize_infra(ctx)

    # Phase 6: Load AppSpec, mocks, SiteSpec
    _load_appspec_and_subsystems(ctx)

    # Phase 7: Dispatch to the appropriate server mode
    if ctx.ui_only:
        _serve_ui_only(ctx)
    elif ctx.backend_only:
        _serve_backend_only(ctx)
    else:
        _serve_combined(ctx)
