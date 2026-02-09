"""
Dazzle Unified Server — runs a single FastAPI app with both API and UI.

Provides:
1. run_unified_server()  — full app: FastAPI backend + page routes + site pages on one port
2. run_backend_only()    — backend API only (for --backend-only flag)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dazzle_back.specs import BackendSpec


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


# =============================================================================
# Unified Server (single-port FastAPI)
# =============================================================================


def run_unified_server(
    backend_spec: BackendSpec,
    ui_spec: Any = None,
    port: int = 3000,
    db_path: str | Path | None = None,
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
    appspec: Any = None,
    redis_url: str = "",
) -> None:
    """
    Run a unified Dazzle server on a single port.

    Builds a FastAPI app with:
    - Backend API routes (entities, auth, files, etc.)
    - Server-rendered app pages (/app/*)
    - Site pages (/, /about, /pricing, etc.) if sitespec exists
    - Static file serving (/static/*)

    Args:
        backend_spec: Backend specification
        ui_spec: UI specification (unused, kept for backward compat)
        port: Port to bind to
        db_path: Path to SQLite database
        enable_test_mode: Enable test endpoints (/__test__/*)
        enable_dev_mode: Enable dev control plane
        enable_auth: Enable authentication endpoints (/auth/*)
        auth_config: Full auth configuration from manifest
        host: Host to bind to
        enable_watch: Enable hot reload file watching (currently unused)
        watch_source: Also watch framework source files (currently unused)
        project_root: Project root directory
        personas: List of persona configurations
        scenarios: List of scenario configurations
        sitespec_data: SiteSpec data as dict for public site pages
        theme_preset: Theme preset name
        theme_overrides: Custom theme token overrides
        appspec: AppSpec for template-based page rendering
    """
    try:
        import uvicorn

        from dazzle_back.runtime.server import DNRBackendApp, ServerConfig
    except ImportError as e:
        print(f"[Dazzle] Error: Required dependencies not available: {e}")
        print("[Dazzle] Install with: pip install fastapi uvicorn dazzle-app-back")
        return

    project_root = project_root or Path.cwd()
    db_file = Path(db_path) if db_path else Path(".dazzle/data.db")

    # Initialize logging
    try:
        from dazzle_back.runtime.logging import setup_logging

        log_dir = db_file.parent / "logs"
        setup_logging(log_dir=log_dir)
    except ImportError:
        pass

    print("\n" + "=" * 60)
    print("  DAZZLE NATIVE RUNTIME (DNR)")
    print("=" * 60)
    print()

    # Build fragment sources from DSL source= annotations
    frag_sources: dict[str, dict[str, Any]] = {}
    if appspec:
        try:
            from dazzle.api_kb import load_pack

            for surface in appspec.surfaces:
                for section in getattr(surface, "sections", []):
                    for element in getattr(section, "elements", []):
                        src_ref = getattr(element, "options", {}).get("source")
                        if src_ref and "." in src_ref:
                            pname, opname = src_ref.rsplit(".", 1)
                            if pname not in frag_sources:
                                pack = load_pack(pname)
                                if pack:
                                    try:
                                        frag_sources[pname] = pack.generate_fragment_source(opname)
                                    except ValueError:
                                        pass
        except ImportError:
            pass

    # Check for PostgreSQL DATABASE_URL
    database_url = os.environ.get("DATABASE_URL", "")
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    # Set REDIS_URL in env for subcomponents that read it
    if redis_url:
        os.environ.setdefault("REDIS_URL", redis_url)

    config = ServerConfig(
        database_url=database_url or None,
        enable_test_mode=enable_test_mode,
        enable_auth=enable_auth,
        auth_config=auth_config,
        enable_dev_mode=enable_dev_mode,
        personas=personas or [],
        scenarios=scenarios or [],
        sitespec_data=sitespec_data,
        project_root=project_root,
        fragment_sources=frag_sources,
    )
    builder = DNRBackendApp(backend_spec, config=config)
    app = builder.build()

    # ---- Mount site page routes (landing pages, /site.js, /styles/dazzle.css) ----
    if sitespec_data:
        try:
            from dazzle_back.runtime.site_routes import (
                create_auth_page_routes,
                create_site_page_routes,
            )

            site_page_router = create_site_page_routes(
                sitespec_data=sitespec_data,
                project_root=project_root,
            )
            app.include_router(site_page_router)

            auth_page_router = create_auth_page_routes(sitespec_data)
            app.include_router(auth_page_router)
        except ImportError:
            pass

    # ---- Mount app page routes (/app/*) ----
    if appspec:
        try:
            from dazzle_ui.runtime.page_routes import create_page_routes

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
                try:
                    from dazzle_ui.runtime.css_loader import get_bundled_css

                    theme_css = get_bundled_css()
                except Exception:
                    pass

            get_auth_context = None
            if builder.auth_middleware:
                get_auth_context = builder.auth_middleware.get_auth_context

            page_router = create_page_routes(
                appspec,
                backend_url=f"http://{host}:{port}",
                theme_css=theme_css,
                get_auth_context=get_auth_context,
            )
            app.include_router(page_router, prefix="/app")
            print("[Dazzle] App pages: mounted at /app")
        except ImportError as e:
            print(f"[Dazzle] Warning: Page routes not available: {e}")

    # ---- Print startup info ----
    base_url = f"http://{host}:{port}"
    docs_url = f"{base_url}/docs"
    print(f"[Dazzle] Server:   {_clickable_url(base_url)}")
    print(f"[Dazzle] App:      {_clickable_url(base_url + '/app')}")
    print(f"[Dazzle] API Docs: {_clickable_url(docs_url)}")
    print(f"[Dazzle] Database: {db_file}")
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

    try:
        uvicorn.run(app, host=host, port=port, log_level="info")
    except KeyboardInterrupt:
        print("\n[Dazzle] Shutting down...")
    except OSError as e:
        if e.errno == 48 or "address already in use" in str(e).lower():
            print(f"\n[Dazzle] ERROR: Port {port} is already in use.")
            print("[Dazzle] Stop the other process or use --port to specify a different port.")
            print(f"[Dazzle] Hint: lsof -i :{port} | grep LISTEN")
        else:
            raise


# =============================================================================
# Backend-Only Server
# =============================================================================


def run_backend_only(
    backend_spec: BackendSpec,
    host: str = "127.0.0.1",
    port: int = 8000,
    db_path: str | Path | None = None,
    enable_test_mode: bool = False,
    enable_dev_mode: bool = True,
    enable_graphql: bool = False,
    sitespec_data: dict[str, Any] | None = None,
    project_root: Path | None = None,
    redis_url: str = "",
) -> None:
    """
    Run only the FastAPI backend server.

    Args:
        backend_spec: Backend specification
        host: Host to bind to
        port: Port to bind to
        db_path: Path to SQLite database
        enable_test_mode: Enable test endpoints (/__test__/*)
        enable_dev_mode: Enable dev control plane
        enable_graphql: Enable GraphQL endpoint at /graphql
        sitespec_data: SiteSpec data as dict for public site shell
        project_root: Project root directory for content file loading
    """
    try:
        import uvicorn

        from dazzle_back.runtime.server import DNRBackendApp
    except ImportError as e:
        print(f"[Dazzle] Error: Required dependencies not available: {e}")
        print("[Dazzle] Install with: pip install fastapi uvicorn dazzle-app-back")
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

    app_builder = DNRBackendApp(
        backend_spec,
        database_url=database_url or None,
        enable_test_mode=enable_test_mode,
        enable_dev_mode=enable_dev_mode,
        sitespec_data=sitespec_data,
        project_root=project_root,
    )
    app = app_builder.build()

    # Mount GraphQL if enabled
    if enable_graphql:
        try:
            from dazzle_back.graphql import mount_graphql

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
    print(f"[Dazzle] Database: {db_path}")
    if enable_test_mode:
        print("[Dazzle] Test endpoints: /__test__/* (enabled)")
    print()
    print("Press Ctrl+C to stop")
    print("-" * 60)
    print()

    try:
        uvicorn.run(app, host=host, port=port, log_level="info")
    except KeyboardInterrupt:
        print("\n[Dazzle] Shutting down...")
    except OSError as e:
        if e.errno == 48 or "address already in use" in str(e).lower():
            print(f"\n[Dazzle] ERROR: Port {port} is already in use.")
            print("[Dazzle] Stop the other process or use --api-port to specify a different port.")
            print(f"[Dazzle] Hint: lsof -i :{port} | grep LISTEN")
        else:
            raise
