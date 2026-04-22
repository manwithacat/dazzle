"""
Dazzle Unified Server — runs a single FastAPI app with both API and UI.

Provides:
1. run_unified_server()  — full app: FastAPI backend + page routes + site pages on one port
2. run_backend_only()    — backend API only (for --backend-only flag)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from dazzle.core.ir import AppSpec


@dataclass
class UnifiedServerConfig:
    """Configuration for run_unified_server(), replacing 19 individual parameters."""

    appspec: AppSpec
    ui_spec: Any = None
    port: int = 3000
    enable_test_mode: bool = False
    enable_dev_mode: bool = True
    enable_auth: bool = True
    auth_config: Any = None
    host: str = "127.0.0.1"
    enable_watch: bool = False
    watch_source: bool = False
    project_root: Path | None = None
    personas: list[dict[str, Any]] | None = None
    scenarios: list[dict[str, Any]] | None = None
    sitespec_data: dict[str, Any] | None = None
    theme_preset: str = "saas-default"
    theme_overrides: dict[str, Any] | None = None
    redis_url: str = ""
    tenant_config: Any = None


# =============================================================================
# Terminal Utilities
# =============================================================================


def _supports_hyperlinks() -> bool:
    """
    Check if the terminal likely supports OSC 8 hyperlinks.

    We check for:
    1. NO_COLOR not set (respect user preference)
    2. TERM is set (indicates a terminal environment)
    3. Not running in dumb terminal
    """
    if os.environ.get("NO_COLOR"):
        return False

    term = os.environ.get("TERM", "")
    if not term or term == "dumb":
        return False

    # Most modern terminals support OSC 8: iTerm2, Terminal.app, VS Code, etc.
    return True


def _clickable_url(url: str, label: str | None = None) -> str:
    """
    Create a clickable hyperlink for terminal emulators that support OSC 8.

    Uses the OSC 8 escape sequence format:
    \\e]8;;URL\\e\\\\LABEL\\e]8;;\\e\\\\

    Falls back to plain text if NO_COLOR is set or TERM is not set.
    """
    if not _supports_hyperlinks():
        return label or url

    # OSC 8 hyperlink format
    # \x1b]8;; starts the hyperlink, \x1b\\ (or \x07) ends parameters
    # Then the visible text, then \x1b]8;;\x1b\\ to close
    display = label or url
    return f"\x1b]8;;{url}\x1b\\{display}\x1b]8;;\x1b\\"


def _set_factory_env(
    project_root: Path | None,
    enable_dev_mode: bool,
    enable_test_mode: bool,
) -> None:
    """Set environment variables for create_app_factory in multi-worker mode.

    When workers > 1, uvicorn forks and re-imports the app in each child.
    The factory reads config from env vars, so we set them here before fork.
    """
    if project_root is not None:
        os.environ.setdefault("DAZZLE_PROJECT_ROOT", str(project_root))
    if enable_dev_mode:
        os.environ["DAZZLE_ENV"] = "development"
    elif enable_test_mode:
        os.environ["DAZZLE_ENV"] = "test"


# =============================================================================
# Unified Server (single-port FastAPI)
# =============================================================================


def run_unified_server(
    appspec: AppSpec | None = None,
    ui_spec: Any = None,
    port: int = 3000,
    enable_test_mode: bool = False,
    enable_dev_mode: bool = True,
    enable_auth: bool = True,
    auth_config: Any = None,
    host: str = "127.0.0.1",
    enable_watch: bool = False,
    watch_source: bool = False,
    project_root: Path | None = None,
    personas: list[dict[str, Any]] | None = None,
    scenarios: list[dict[str, Any]] | None = None,
    sitespec_data: dict[str, Any] | None = None,
    theme_preset: str = "saas-default",
    theme_overrides: dict[str, Any] | None = None,
    redis_url: str = "",
    workers: int | None = None,
    tenant_config: Any = None,
    local_assets: bool = False,
    *,
    config: UnifiedServerConfig | None = None,
) -> None:
    """
    Run a unified Dazzle server on a single port.

    Accepts either individual parameters (backward compat) or a UnifiedServerConfig.

    Args:
        appspec: Dazzle AppSpec (parsed IR).
        config: UnifiedServerConfig with all options (preferred).
            When provided, individual parameters are ignored.
    """
    # If config provided, unpack it — otherwise use individual params
    enable_watch = False
    watch_source = False
    if config is not None:
        appspec = config.appspec
        ui_spec = config.ui_spec
        port = config.port
        enable_test_mode = config.enable_test_mode
        enable_dev_mode = config.enable_dev_mode
        enable_auth = config.enable_auth
        auth_config = config.auth_config
        host = config.host
        enable_watch = config.enable_watch
        watch_source = config.watch_source
        project_root = config.project_root
        personas = config.personas
        scenarios = config.scenarios
        sitespec_data = config.sitespec_data
        theme_preset = config.theme_preset
        theme_overrides = config.theme_overrides
        redis_url = config.redis_url
        tenant_config = config.tenant_config
    try:
        import uvicorn

        from dazzle_back.runtime.app_factory import (
            assemble_post_build_routes,
            build_server_config,
        )
        from dazzle_back.runtime.server import DazzleBackendApp
    except ImportError as e:
        print(f"[Dazzle] Error: Required dependencies not available: {e}")
        print("[Dazzle] Install with: pip install dazzle-dsl[serve]")
        return

    project_root = project_root or Path.cwd()

    # Initialize logging
    try:
        from dazzle_back.runtime.logging import setup_logging

        log_dir = Path(".dazzle") / "logs"
        setup_logging(log_dir=log_dir)
    except ImportError:
        pass

    print("\n" + "=" * 60)
    print("  DAZZLE NATIVE RUNTIME (DNR)")
    print("=" * 60)
    print()

    # Check for PostgreSQL DATABASE_URL
    database_url = os.environ.get("DATABASE_URL", "")
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    # Set REDIS_URL in env for subcomponents that read it
    if redis_url:
        os.environ.setdefault("REDIS_URL", redis_url)

    if appspec is None:
        print("[Dazzle] Error: appspec is required")
        return

    server_config = build_server_config(
        appspec,
        database_url=database_url or None,
        enable_test_mode=enable_test_mode,
        enable_auth=enable_auth,
        auth_config=auth_config,
        enable_dev_mode=enable_dev_mode,
        tenant_config=tenant_config,
        personas=personas or [],
        scenarios=scenarios or [],
        sitespec_data=sitespec_data,
        project_root=project_root,
    )
    builder = DazzleBackendApp(appspec, config=server_config)
    app = builder.build()

    # #768 — QA mode setup: provision dev personas and mount dev-gated routes
    if (
        os.environ.get("DAZZLE_QA_MODE") == "1"
        and getattr(app.state, "auth_store", None) is not None
    ):
        from dazzle.cli.runtime_impl.dev_personas import provision_dev_personas

        try:
            provisioned = provision_dev_personas(appspec, app.state.auth_store)
        except Exception as err:
            provisioned = []
            print(f"[Dazzle] Warning: dev persona provisioning failed: {err}")

        if provisioned:
            # Stash on app.state for the landing page renderer
            app.state.qa_personas = provisioned

            # Dynamically mount the dev-gated qa_router
            try:
                from dazzle_back.runtime.qa_routes import create_qa_routes

                app.include_router(create_qa_routes())
            except Exception as err:
                print(f"[Dazzle] Warning: failed to mount QA routes: {err}")

            # Print startup banner
            print()
            print("WARNING: QA MODE ACTIVE")
            print("  Dev-only endpoint /qa/magic-link is mounted.")
            print("  Any request can create a session for any provisioned persona.")
            print("  This mode is ONLY intended for local QA testing.")
            print("  Never expose this server to untrusted networks.")
            print()
            print(f"Dev Personas ({len(provisioned)})")
            for p in provisioned:
                print(f"  {p.display_name:<20} -> {p.email}")
            print()

    # Build theme CSS (unique to unified server path)
    theme_css = ""
    try:
        from dazzle_ui.runtime.css_loader import get_bundled_css
        from dazzle_ui.themes import generate_theme_css, resolve_theme

        theme = resolve_theme(
            preset_name=theme_preset,
            manifest_overrides=theme_overrides or {},
        )
        theme_css = get_bundled_css(theme_css=generate_theme_css(theme))
    except Exception:
        logger.debug("Failed to load themed CSS, trying default", exc_info=True)
        try:
            from dazzle_ui.runtime.css_loader import get_bundled_css

            theme_css = get_bundled_css()
        except Exception:
            logger.debug("Failed to load bundled CSS", exc_info=True)

    # Build Tailwind+DaisyUI CSS via standalone CLI (#377)
    tailwind_css = ""
    try:
        from dazzle_ui.build_css import build_css

        tw_output = build_css(project_root=project_root)
        if tw_output and tw_output.exists():
            tailwind_css = tw_output.read_text(encoding="utf-8")
            print(f"[Dazzle] CSS bundle built: {tw_output.stat().st_size / 1024:.0f} KB")
    except Exception:
        logger.debug("Tailwind CSS build skipped (CLI not available)", exc_info=True)

    # Combine CSS parts into a single bundle string
    _bundle_parts = [p for p in [tailwind_css, theme_css] if p]
    bundled_css = "\n".join(_bundle_parts) if _bundle_parts else ""

    assemble_post_build_routes(
        app,
        appspec,
        builder,
        project_root=project_root,
        sitespec_data=sitespec_data,
        theme_css=theme_css,
        backend_url=f"http://{host}:{port}",
        bundled_css=bundled_css,
    )

    # Apply --local-assets / --cdn-assets toggle (#637)
    if local_assets:
        try:
            from dazzle_ui.runtime.template_renderer import get_jinja_env

            get_jinja_env().globals["_use_cdn"] = False
        except Exception:
            pass

    # ---- Print startup info ----
    base_url = f"http://{host}:{port}"
    docs_url = f"{base_url}/docs"
    print(f"[Dazzle] Server:   {_clickable_url(base_url)}")
    print(f"[Dazzle] App:      {_clickable_url(base_url + '/app')}")
    print(f"[Dazzle] API Docs: {_clickable_url(docs_url)}")
    print(
        f"[Dazzle] Database: PostgreSQL ({database_url[:40] + '...' if len(database_url) > 40 else database_url or 'not configured'})"
    )
    print(f"[Dazzle] Assets:   {'local (static/)' if local_assets else 'CDN (jsdelivr)'}")
    if enable_test_mode:
        print("[Dazzle] Test endpoints: /__test__/* (enabled)")
    if enable_auth:
        print("[Dazzle] Authentication: ENABLED (/auth/* endpoints available)")
    if sitespec_data:
        pages = sitespec_data.get("pages", [])
        routes = sorted(p.get("route", "") for p in pages if p.get("route"))
        if routes:
            print(f"[Dazzle] Site pages: {', '.join(routes)}")
    print()
    print("Press Ctrl+C to stop")
    print("-" * 60)
    print()

    # ---- Hot reload (single-worker only — multi-worker fork conflicts with watchers) ----
    hot_reload_manager = None
    if enable_watch and (workers is None or workers == 1) and project_root is not None:
        try:
            from dazzle_ui.runtime.hot_reload import HotReloadManager, create_reload_callback

            hot_reload_manager = HotReloadManager(
                project_root=project_root,
                on_reload=create_reload_callback(project_root),
                watch_source=watch_source,
            )
            if appspec is not None and ui_spec is not None:
                hot_reload_manager.set_specs(appspec, ui_spec)
            hot_reload_manager.start()
            app.state.hot_reload_manager = hot_reload_manager
        except Exception:
            logger.debug("Hot reload manager failed to start", exc_info=True)
            hot_reload_manager = None
    elif enable_watch and workers and workers > 1:
        print("[Dazzle] Warning: --watch is ignored when --workers > 1 (multi-process)")

    uvicorn_kwargs: dict[str, Any] = {
        "host": host,
        "port": port,
        "log_level": "info",
    }
    if workers is not None:
        uvicorn_kwargs["workers"] = workers

    try:
        if workers is not None and workers > 1:
            # Multi-worker requires an import string so uvicorn can fork and
            # re-import the app in each child process.
            _set_factory_env(project_root, enable_dev_mode, enable_test_mode)
            uvicorn.run(
                "dazzle_back.runtime.app_factory:create_app_factory",
                factory=True,
                **uvicorn_kwargs,
            )
        else:
            uvicorn.run(app, **uvicorn_kwargs)
    except KeyboardInterrupt:
        print("\n[Dazzle] Shutting down...")
    except OSError as e:
        if e.errno == 48 or "address already in use" in str(e).lower():
            print(f"\n[Dazzle] ERROR: Port {port} is already in use.")
            print("[Dazzle] Stop the other process or use --port to specify a different port.")
            print(f"[Dazzle] Hint: lsof -i :{port} | grep LISTEN")
        else:
            raise
    finally:
        if hot_reload_manager is not None:
            hot_reload_manager.stop()


# =============================================================================
# Backend-Only Server
# =============================================================================


def run_backend_only(
    appspec: AppSpec,
    host: str = "127.0.0.1",
    port: int = 8000,
    enable_test_mode: bool = False,
    enable_dev_mode: bool = True,
    enable_graphql: bool = False,
    sitespec_data: dict[str, Any] | None = None,
    project_root: Path | None = None,
    redis_url: str = "",
    workers: int | None = None,
) -> None:
    """
    Run only the FastAPI backend server.

    Args:
        appspec: Dazzle AppSpec (parsed IR)
        host: Host to bind to
        port: Port to bind to
        enable_test_mode: Enable test endpoints (/__test__/*)
        enable_dev_mode: Enable dev control plane
        enable_graphql: Enable GraphQL endpoint at /graphql
        sitespec_data: SiteSpec data as dict for public site shell
        project_root: Project root directory for content file loading
    """
    try:
        import uvicorn

        from dazzle_back.runtime.app_factory import build_server_config
        from dazzle_back.runtime.server import DazzleBackendApp
    except ImportError as e:
        print(f"[Dazzle] Error: Required dependencies not available: {e}")
        print("[Dazzle] Install with: pip install dazzle-dsl[serve]")
        return

    print("\n" + "=" * 60)
    print("  DAZZLE NATIVE RUNTIME (DNR) - Backend Only")
    print("=" * 60)
    print()

    # Set REDIS_URL in env for subcomponents that read it
    if redis_url:
        os.environ.setdefault("REDIS_URL", redis_url)

    database_url = os.environ.get("DATABASE_URL", "")
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    config = build_server_config(
        appspec,
        database_url=database_url or None,
        enable_test_mode=enable_test_mode,
        enable_dev_mode=enable_dev_mode,
        sitespec_data=sitespec_data,
        project_root=project_root,
    )
    app_builder = DazzleBackendApp(appspec, config=config)
    app = app_builder.build()

    # Mount GraphQL if enabled
    if enable_graphql:
        try:
            from dazzle_back import convert_appspec_to_backend
            from dazzle_back.graphql import mount_graphql

            # mount_graphql expects a BackendSpec (not AppSpec) — the
            # function reads `spec.entities` directly, whereas AppSpec
            # exposes entities at `appspec.domain.entities`. Without
            # the conversion this path would raise AttributeError the
            # moment GraphQL is enabled (the bug stayed latent because
            # --graphql defaults to off). Match the pattern already
            # used by dazzle.mcp.runtime_tools.handlers.
            backend_spec = convert_appspec_to_backend(appspec)
            mount_graphql(
                app,
                backend_spec,
                services=app_builder.services,
                repositories=app_builder.repositories,
            )
            graphql_url = f"http://{host}:{port}/graphql"
            print(f"[Dazzle] GraphQL: {_clickable_url(graphql_url)}")
        except ImportError:
            print("[Dazzle] Warning: GraphQL not available (install strawberry-graphql)")

    backend_url = f"http://{host}:{port}"
    docs_url = f"{backend_url}/docs"
    print(f"[Dazzle] Backend:  {_clickable_url(backend_url)}")
    print(f"[Dazzle] API Docs: {_clickable_url(docs_url)}")
    print(
        f"[Dazzle] Database: PostgreSQL ({database_url[:40] + '...' if len(database_url) > 40 else database_url or 'not configured'})"
    )
    if enable_test_mode:
        print("[Dazzle] Test endpoints: /__test__/* (enabled)")
    print()
    print("Press Ctrl+C to stop")
    print("-" * 60)
    print()

    uvicorn_kwargs: dict[str, Any] = {
        "host": host,
        "port": port,
        "log_level": "info",
    }
    if workers is not None:
        uvicorn_kwargs["workers"] = workers

    try:
        if workers is not None and workers > 1:
            _set_factory_env(project_root, enable_dev_mode, enable_test_mode)
            uvicorn.run(
                "dazzle_back.runtime.app_factory:create_app_factory",
                factory=True,
                **uvicorn_kwargs,
            )
        else:
            uvicorn.run(app, **uvicorn_kwargs)
    except KeyboardInterrupt:
        print("\n[Dazzle] Shutting down...")
    except OSError as e:
        if e.errno == 48 or "address already in use" in str(e).lower():
            print(f"\n[Dazzle] ERROR: Port {port} is already in use.")
            print("[Dazzle] Stop the other process or use --api-port to specify a different port.")
            print(f"[Dazzle] Hint: lsof -i :{port} | grep LISTEN")
        else:
            raise
