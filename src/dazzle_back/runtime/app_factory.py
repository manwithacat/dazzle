"""App factory functions extracted from server.py.

Convenience functions for creating and running Dazzle backend applications,
including the production ASGI factory for deployment.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dazzle.core.ir import AppSpec

if TYPE_CHECKING:
    from fastapi import FastAPI

    from dazzle.core.ir import EntitySpec, SurfaceSpec, ViewSpec
    from dazzle_back.runtime.server import DazzleBackendApp, ServerConfig

logger = logging.getLogger(__name__)


def create_app(
    appspec: AppSpec,
    database_url: str | None = None,
    enable_auth: bool = False,
    enable_files: bool = False,
    files_path: str | Path | None = None,
    enable_test_mode: bool = False,
    services_dir: str | Path | None = None,
    enable_dev_mode: bool = False,
    personas: list[dict[str, Any]] | None = None,
    scenarios: list[dict[str, Any]] | None = None,
) -> FastAPI:
    """
    Create a FastAPI application from an AppSpec.

    This is the main entry point for creating a Dazzle backend application.

    Args:
        appspec: Dazzle AppSpec (parsed IR)
        database_url: PostgreSQL connection URL (or set DATABASE_URL env var)
        enable_auth: Whether to enable authentication (default: False)
        enable_files: Whether to enable file uploads (default: False)
        files_path: Path for file storage (default: .dazzle/uploads)
        enable_test_mode: Whether to enable /__test__/* endpoints (default: False)
        services_dir: Path to domain service stubs directory (default: services/)
        enable_dev_mode: Enable dev control plane (default: False)
        personas: List of persona configurations for dev mode
        scenarios: List of scenario configurations for dev mode

    Returns:
        FastAPI application

    Example:
        >>> from dazzle.core.linker import build_appspec
        >>> appspec = build_appspec(modules, project_root)
        >>> app = create_app(appspec, database_url="postgresql://...")
        >>> # Run with uvicorn: uvicorn mymodule:app
    """
    from dazzle_back.runtime.server import DazzleBackendApp

    builder = DazzleBackendApp(
        appspec,
        database_url=database_url,
        enable_auth=enable_auth,
        enable_files=enable_files,
        files_path=files_path,
        enable_test_mode=enable_test_mode,
        services_dir=services_dir,
        enable_dev_mode=enable_dev_mode,
        personas=personas,
        scenarios=scenarios,
    )
    return builder.build()


def run_app(
    appspec: AppSpec,
    host: str = "127.0.0.1",
    port: int = 8000,
    reload: bool = False,
    database_url: str | None = None,
    enable_auth: bool = False,
    enable_files: bool = False,
    files_path: str | Path | None = None,
    enable_test_mode: bool = False,
    services_dir: str | Path | None = None,
    enable_dev_mode: bool = False,
    personas: list[dict[str, Any]] | None = None,
    scenarios: list[dict[str, Any]] | None = None,
) -> None:
    """
    Run a Dazzle backend application.

    Args:
        appspec: Dazzle AppSpec (parsed IR)
        host: Host to bind to
        port: Port to bind to
        reload: Enable auto-reload (for development)
        database_url: PostgreSQL connection URL (or set DATABASE_URL env var)
        enable_auth: Whether to enable authentication (default: False)
        enable_files: Whether to enable file uploads (default: False)
        files_path: Path for file storage (default: .dazzle/uploads)
        enable_test_mode: Whether to enable /__test__/* endpoints (default: False)
        services_dir: Path to domain service stubs directory (default: services/)
        enable_dev_mode: Enable dev control plane (default: False)
        personas: List of persona configurations for dev mode
        scenarios: List of scenario configurations for dev mode
    """
    try:
        import uvicorn
    except ImportError:
        raise RuntimeError("uvicorn is not installed. Install with: pip install uvicorn")

    app = create_app(
        appspec,
        database_url=database_url,
        enable_auth=enable_auth,
        enable_files=enable_files,
        files_path=files_path,
        enable_test_mode=enable_test_mode,
        services_dir=services_dir,
        enable_dev_mode=enable_dev_mode,
        personas=personas,
        scenarios=scenarios,
    )
    uvicorn.run(app, host=host, port=port, reload=reload)


# =============================================================================
# View-based list projections
# =============================================================================


def _expand_money_field(fname: str) -> list[str]:
    """Expand a money field name to its database column pair."""
    return [f"{fname}_minor", f"{fname}_currency"]


def build_entity_list_projections(
    entities: list[EntitySpec],
    surfaces: list[SurfaceSpec],
    views: list[ViewSpec],
) -> dict[str, list[str]]:
    """Pre-plan column projections for list surfaces (query pre-planning).

    Determines the minimal SELECT field set for each entity's list endpoint
    at startup, eliminating per-request field derivation.

    Projection sources (in priority order):
    1. View-backed surfaces (``view_ref``) — explicit field list from the view
    2. Surface sections — fields declared in ``section.elements[].field_name``
    3. Fallback — no projection (SELECT * via repository default)

    Money fields are expanded to ``_minor``/``_currency`` column pairs.
    Required fields are always included (Pydantic model validation needs them).

    Returns a mapping of ``{entity_name: [column_names]}``.
    """
    views_by_name = {v.name: v for v in views}
    # Build per-entity field metadata: type kind + required status
    entity_fields_meta: dict[str, dict[str, tuple[str, bool]]] = {}
    for entity in entities:
        entity_fields_meta[entity.name] = {
            f.name: (f.type.kind, f.is_required) for f in entity.fields
        }

    projections: dict[str, list[str]] = {}
    for surface in surfaces:
        if not surface.entity_ref:
            continue
        entity_ref = surface.entity_ref

        # Already have a projection for this entity — keep the wider one
        if entity_ref in projections:
            continue

        fields_meta = entity_fields_meta.get(entity_ref, {})

        # Source 1: View-backed projection
        if surface.view_ref:
            view = views_by_name.get(surface.view_ref)
            if view and view.fields:
                view_field_names = {f.name for f in view.fields}
                columns: list[str] = []
                # Required fields not in view (Pydantic needs them)
                for fname, (fkind, freq) in fields_meta.items():
                    if freq and fname not in view_field_names and fname != "id":
                        columns.extend(_expand_money_field(fname) if fkind == "money" else [fname])
                # View's explicit fields
                for f in view.fields:
                    kind = fields_meta.get(f.name, ("scalar", False))[0]
                    columns.extend(_expand_money_field(f.name) if kind == "money" else [f.name])
                if "id" not in columns:
                    columns.insert(0, "id")
                projections[entity_ref] = columns
                continue

        # Source 2: Surface section fields (list mode)
        if surface.mode == "list" and surface.sections:
            surface_field_names: set[str] = set()
            for section in surface.sections:
                for element in section.elements:
                    surface_field_names.add(element.field_name)
            if surface_field_names:
                columns = []
                # Required fields not explicitly listed
                for fname, (fkind, freq) in fields_meta.items():
                    if freq and fname not in surface_field_names and fname != "id":
                        columns.extend(_expand_money_field(fname) if fkind == "money" else [fname])
                # Surface's declared fields
                for fname in surface_field_names:
                    kind = fields_meta.get(fname, ("scalar", False))[0]
                    columns.extend(_expand_money_field(fname) if kind == "money" else [fname])
                if "id" not in columns:
                    columns.insert(0, "id")
                projections[entity_ref] = columns

    return projections


def build_entity_search_fields(
    surfaces: list[SurfaceSpec],
) -> dict[str, list[str]]:
    """Pre-plan search fields for each entity from surface declarations.

    Extracts ``search_fields`` from list-mode surfaces. When a surface
    declares explicit search fields, those are used for LIKE-based search
    on the entity's list endpoint.

    Returns a mapping of ``{entity_name: [field_names]}``.
    """
    result: dict[str, list[str]] = {}
    for surface in surfaces:
        entity_ref = surface.entity_ref
        if not entity_ref or entity_ref in result:
            continue
        sf = surface.search_fields
        if sf:
            result[entity_ref] = list(sf)
    return result


# =============================================================================
# Shared startup helpers
# =============================================================================


def build_fragment_sources(appspec: AppSpec) -> dict[str, dict[str, Any]]:
    """Extract fragment sources from DSL ``source=`` annotations on surface elements.

    Scans all surfaces for elements with ``options.source`` references like
    ``"pack_name.operation_name"`` and loads the corresponding API pack fragment.

    Returns ``{pack_name: fragment_data}``.
    """
    frag_sources: dict[str, dict[str, Any]] = {}
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
    return frag_sources


def build_server_config(
    appspec: AppSpec,
    *,
    database_url: str | None = None,
    enable_auth: bool = False,
    auth_config: Any = None,
    enable_files: bool = False,
    files_path: Path | None = None,
    enable_test_mode: bool = False,
    enable_dev_mode: bool = False,
    services_dir: Path | None = None,
    enable_console: bool = False,
    enable_processes: bool = True,
    process_adapter_class: type | None = None,
    personas: list[dict[str, Any]] | None = None,
    scenarios: list[dict[str, Any]] | None = None,
    sitespec_data: dict[str, Any] | None = None,
    project_root: Path | None = None,
    fragment_sources: dict[str, dict[str, Any]] | None = None,
) -> ServerConfig:
    """Build a fully-populated ``ServerConfig`` from an AppSpec.

    Computes derived config (projections, search fields, auto-includes,
    process specs, schedules, fragment sources) that both
    ``create_app_factory()`` and ``run_unified_server()`` need.

    Process adapter resolution is left to the caller (env-var-driven,
    deployment-specific).
    """
    from dazzle_back.runtime.server import ServerConfig

    # Compute view-based list projections from DSL surfaces
    entity_list_projections = build_entity_list_projections(
        entities=appspec.domain.entities,
        surfaces=appspec.surfaces,
        views=appspec.views,
    )

    # Extract search fields from surface declarations
    entity_search_fields = build_entity_search_fields(surfaces=appspec.surfaces)

    # Auto-detect ref/belongs_to fields for eager loading (prevents N+1 queries).
    # Use relation names (strip _id suffix) to match relation_loader conventions.
    entity_auto_includes: dict[str, list[str]] = {}
    for entity in appspec.domain.entities:
        rel_names = [
            f.name[:-3] if f.name.endswith("_id") else f.name
            for f in entity.fields
            if f.type.kind in ("ref", "belongs_to") and f.type.ref_entity
        ]
        if rel_names:
            entity_auto_includes[entity.name] = rel_names

    # Extract entity status fields for process trigger status transition detection
    entity_status_fields: dict[str, str] = {}
    if appspec.domain:
        for ent in appspec.domain.entities:
            sm = getattr(ent, "state_machine", None)
            if sm:
                entity_status_fields[ent.name] = getattr(sm, "status_field", "status")

    # Merge DSL-parsed processes with persisted processes
    all_processes = list(appspec.processes)
    if project_root is not None:
        try:
            from dazzle.core.process_persistence import load_processes

            persisted = load_processes(project_root)
            dsl_names = {p.name for p in all_processes}
            merged = all_processes + [p for p in persisted if p.name not in dsl_names]
            if persisted:
                logger.info(
                    "Loaded %d persisted process(es), %d total (%d from DSL)",
                    len(persisted),
                    len(merged),
                    len(all_processes),
                )
            all_processes = merged
        except Exception:
            logger.debug("Could not load persisted processes", exc_info=True)

    # Build fragment sources if not provided by caller
    if fragment_sources is None:
        fragment_sources = build_fragment_sources(appspec)

    return ServerConfig(
        database_url=database_url,
        enable_auth=enable_auth,
        auth_config=auth_config,
        enable_files=enable_files,
        files_path=files_path or Path(".dazzle/uploads"),
        enable_test_mode=enable_test_mode,
        services_dir=services_dir or Path("services"),
        enable_dev_mode=enable_dev_mode,
        personas=personas or [],
        scenarios=scenarios or [],
        sitespec_data=sitespec_data,
        project_root=project_root,
        enable_processes=enable_processes,
        process_adapter_class=process_adapter_class,
        enable_console=enable_console,
        entity_list_projections=entity_list_projections,
        entity_search_fields=entity_search_fields,
        entity_auto_includes=entity_auto_includes,
        process_specs=all_processes,
        schedule_specs=list(appspec.schedules),
        entity_status_fields=entity_status_fields,
        fragment_sources=fragment_sources,
    )


def assemble_post_build_routes(
    app: FastAPI,
    appspec: AppSpec,
    builder: DazzleBackendApp,
    *,
    project_root: Path | None = None,
    sitespec_data: dict[str, Any] | None = None,
    theme_css: str = "",
    backend_url: str = "http://127.0.0.1:8000",
    bundled_css: str = "",
) -> None:
    """Mount all post-build routes on a FastAPI app in the correct order.

    Called by both ``create_app_factory()`` and ``run_unified_server()``
    to ensure identical route assembly.

    Order:
    1. Site page routes (if sitespec)
    2. Auth page routes (if sitespec, always with ``project_root``)
    3. App page routes (``/app/*``, always with ``app_prefix="/app"``)
    4. Experience routes (``/app/experiences/*``, if experiences exist)
    5. Bundled CSS route (``/static/css/dazzle-bundle.css``, if ``bundled_css``)
    6. Island API routes (``/api/islands``, if islands exist)
    7. Schedule sync to process adapter (if adapter + schedules)
    8. 404 handler (if sitespec)
    9. Route validation via ``validate_routes()``
    """
    # ---- 1. Site page routes ----
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
            logger.info("  Site pages: landing, /site.js, /styles/dazzle.css")

            # ---- 2. Auth page routes ----
            auth_page_router = create_auth_page_routes(sitespec_data, project_root=project_root)
            app.include_router(auth_page_router)
            logger.info("  Auth pages: /login, /signup")
        except ImportError:
            pass

    # ---- 3. App page routes (/app/*) ----
    try:
        from dazzle_ui.runtime.page_routes import create_page_routes

        get_auth_context = None
        if builder.auth_middleware:
            get_auth_context = builder.auth_middleware.get_auth_context

        page_router = create_page_routes(
            appspec,
            backend_url=backend_url,
            theme_css=theme_css,
            get_auth_context=get_auth_context,
            app_prefix="/app",
        )
        app.include_router(page_router, prefix="/app")
        logger.info("  App pages: %s workspaces mounted at /app", len(appspec.workspaces))

        # ---- 4. Experience routes (/app/experiences/*) ----
        if appspec.experiences:
            try:
                from dazzle_ui.runtime.experience_routes import create_experience_routes

                experience_router = create_experience_routes(
                    appspec,
                    backend_url=backend_url,
                    theme_css=theme_css,
                    get_auth_context=get_auth_context,
                    app_prefix="/app",
                    project_root=project_root,
                )
                app.include_router(experience_router, prefix="/app")
                logger.info(
                    "  Experiences: %s mounted at /app/experiences",
                    len(appspec.experiences),
                )
            except ImportError as e:
                logger.warning("Experience routes not available: %s", e)
    except ImportError as e:
        logger.warning("Page routes not available: %s", e)

    # ---- 5. Bundled CSS route ----
    if bundled_css:
        try:
            from starlette.responses import Response as StarletteResponse

            _css_content = bundled_css

            @app.get("/static/css/dazzle-bundle.css", include_in_schema=False)
            async def serve_bundled_css() -> StarletteResponse:
                return StarletteResponse(
                    content=_css_content,
                    media_type="text/css",
                    headers={"Cache-Control": "public, max-age=3600"},
                )

        except ImportError:
            pass

    # ---- 6. Island API routes ----
    if getattr(appspec, "islands", None):
        try:
            from dazzle_back.runtime.island_routes import create_island_routes

            _island_auth_dep = None
            _island_opt_dep = None
            if builder.auth_store:
                from dazzle_back.runtime.auth import (
                    create_auth_dependency,
                    create_optional_auth_dependency,
                )

                _island_auth_dep = create_auth_dependency(builder.auth_store)
                _island_opt_dep = create_optional_auth_dependency(builder.auth_store)

            island_router = create_island_routes(
                islands=appspec.islands,
                services=builder.services,
                auth_dep=_island_auth_dep,
                optional_auth_dep=_island_opt_dep,
            )
            app.include_router(island_router)
            logger.info("  Islands: %s mounted at /api/islands", len(appspec.islands))
        except ImportError as e:
            logger.warning("Island routes not available: %s", e)

    # ---- 7. Schedule sync to process adapter ----
    if builder.process_adapter is not None and appspec.schedules:
        if hasattr(builder.process_adapter, "sync_schedules_from_appspec"):
            count = builder.process_adapter.sync_schedules_from_appspec(appspec)
            if count:
                adapter_name = type(builder.process_adapter).__name__
                logger.info("Synced %s DSL schedule(s) to %s", count, adapter_name)

    # ---- 8. 404 handler ----
    if sitespec_data:
        try:
            from dazzle_back.runtime.exception_handlers import register_site_404_handler

            register_site_404_handler(app, sitespec_data, project_root=project_root)
        except ImportError:
            pass

    # ---- 9. Route validation ----
    try:
        from dazzle_back.runtime.route_validator import validate_routes

        validate_routes(app)
    except ImportError:
        pass


# =============================================================================
# Production Factory (Heroku, etc.)
# =============================================================================


def create_app_factory(
    process_adapter_class: type | None = None,
) -> FastAPI:
    """
    ASGI factory for production deployment.

    Creates a FastAPI application by loading the DSL spec from the project
    directory and configuring from environment variables. Designed for use
    with Uvicorn's --factory flag.

    Args:
        process_adapter_class: Custom ProcessAdapter class.
            Can also be set via DAZZLE_PROCESS_ADAPTER env var:
            - "eventbus" -> EventBusProcessAdapter (recommended with REDIS_URL)
            - "celery" or "redis" -> CeleryProcessAdapter (legacy)

    Environment Variables:
        DAZZLE_PROJECT_ROOT: Project root directory (default: current directory)
        DATABASE_URL: PostgreSQL connection URL (Heroku format supported)
        AUTH_DATABASE_URL: PostgreSQL URL for auth DB (defaults to DATABASE_URL)
        REDIS_URL: Redis connection URL (for sessions/cache)
        DAZZLE_ENV: Environment name (development/staging/production)
        DAZZLE_SECRET_KEY: Secret key for sessions/tokens
        DAZZLE_ENABLE_PROCESSES: Enable/disable process workflows (default: "true")
        DAZZLE_PROCESS_ADAPTER: Process adapter type ("eventbus", "celery", "temporal")

    Usage:
        uvicorn dazzle_back.runtime.app_factory:create_app_factory --factory --host 0.0.0.0 --port $PORT

    Multi-worker (production):
        uvicorn dazzle_back.runtime.app_factory:create_app_factory --factory --host 0.0.0.0 --port $PORT --workers 4

    Procfile example:
        web: uvicorn dazzle_back.runtime.app_factory:create_app_factory --factory --host 0.0.0.0 --port $PORT --workers ${WEB_CONCURRENCY:-4}

    Returns:
        FastAPI application configured for production
    """
    from dazzle_back.runtime.server import DazzleBackendApp

    # Determine project root
    project_root = Path(os.environ.get("DAZZLE_PROJECT_ROOT", ".")).resolve()
    manifest_path = project_root / "dazzle.toml"

    if not manifest_path.exists():
        raise RuntimeError(
            f"dazzle.toml not found at {manifest_path}. "
            "Set DAZZLE_PROJECT_ROOT to the project directory."
        )

    # Import Dazzle core modules (deferred to avoid circular imports)
    try:
        from dazzle.core.errors import DazzleError, ParseError
        from dazzle.core.fileset import discover_dsl_files
        from dazzle.core.linker import build_appspec
        from dazzle.core.manifest import load_manifest
        from dazzle.core.parser import parse_modules
        from dazzle.core.sitespec_loader import load_sitespec_with_copy, sitespec_exists
    except ImportError as e:
        raise RuntimeError(
            f"Dazzle core modules not available: {e}. "
            "Ensure dazzle is installed: pip install dazzle"
        )

    # Load manifest
    logger.info("Loading Dazzle project from %s", project_root)
    manifest = load_manifest(manifest_path)

    # Resolve DATABASE_URL: env → dazzle.toml [database] → default
    from dazzle.core.manifest import resolve_database_url

    database_url = resolve_database_url(manifest)
    logger.info("Database URL resolved (%s chars)", len(database_url))

    # Parse REDIS_URL (Heroku format: redis://h:password@host:port)
    redis_url = os.environ.get("REDIS_URL", "")
    if redis_url:
        logger.info("Redis URL configured")

    # Determine environment
    dazzle_env = os.environ.get("DAZZLE_ENV", "production")
    enable_dev_mode = dazzle_env == "development"
    enable_test_mode = dazzle_env in ("development", "test")

    # Process workflow support (can be disabled via env var)
    enable_processes = os.environ.get("DAZZLE_ENABLE_PROCESSES", "true").lower() == "true"

    # Parse DSL and build spec
    try:
        dsl_files = discover_dsl_files(project_root, manifest)
        modules = parse_modules(dsl_files)
        appspec = build_appspec(modules, manifest.project_root)
    except (ParseError, DazzleError) as e:
        raise RuntimeError(f"Failed to parse DSL: {e}")

    # Load SiteSpec if available (merges copy.md content if present)
    sitespec_data = None
    if sitespec_exists(project_root):
        try:
            sitespec = load_sitespec_with_copy(project_root)
            sitespec_data = sitespec.model_dump()
            logger.info("Loaded SiteSpec with %s pages", len(sitespec.pages))
        except Exception as e:
            logger.warning("Failed to load sitespec.yaml: %s", e)

    # Extract personas with default routes for auth redirect (#255)
    from dazzle_ui.converters.workspace_converter import compute_persona_default_routes

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

    # Resolve process adapter class from parameter or environment
    resolved_adapter_class = process_adapter_class
    if resolved_adapter_class is None:
        adapter_env = os.environ.get("DAZZLE_PROCESS_ADAPTER", "").lower()
        if adapter_env == "eventbus":
            try:
                from dazzle.core.process import EventBusProcessAdapter

                resolved_adapter_class = EventBusProcessAdapter
                logger.info("Using EventBusProcessAdapter (DAZZLE_PROCESS_ADAPTER=eventbus)")
            except ImportError:
                logger.warning("EventBusProcessAdapter requested but not available (install redis)")
        elif adapter_env in ("celery", "redis"):
            try:
                from dazzle.core.process import CeleryProcessAdapter

                resolved_adapter_class = CeleryProcessAdapter
                logger.info("Using CeleryProcessAdapter (DAZZLE_PROCESS_ADAPTER=celery)")
            except ImportError:
                logger.warning(
                    "CeleryProcessAdapter requested but not available (install celery+redis)"
                )
        elif adapter_env == "temporal":
            try:
                from dazzle.core.process import TemporalAdapter

                resolved_adapter_class = TemporalAdapter
                logger.info("Using TemporalAdapter (DAZZLE_PROCESS_ADAPTER=temporal)")
            except ImportError:
                logger.warning("TemporalAdapter requested but not available (install temporalio)")
        # Default: None means auto-detect (requires REDIS_URL for EventBus)

    # Build unified server config
    config = build_server_config(
        appspec,
        database_url=database_url if database_url else None,
        enable_auth=manifest.auth.enabled,
        auth_config=manifest.auth if manifest.auth.enabled else None,
        enable_files=True,
        files_path=project_root / ".dazzle" / "uploads",
        enable_test_mode=enable_test_mode,
        services_dir=project_root / "services",
        enable_dev_mode=enable_dev_mode,
        enable_console=enable_dev_mode,
        enable_processes=enable_processes,
        process_adapter_class=resolved_adapter_class,
        personas=personas,
        scenarios=[],
        sitespec_data=sitespec_data,
        project_root=project_root,
    )

    # Build and return the FastAPI app
    builder = DazzleBackendApp(appspec, config=config)
    app = builder.build()

    # Get theme CSS for page routes
    theme_css = ""
    try:
        from dazzle_ui.runtime.css_loader import get_bundled_css

        theme_css = get_bundled_css()
    except Exception:
        logger.debug("Failed to load bundled theme CSS", exc_info=True)

    assemble_post_build_routes(
        app,
        appspec,
        builder,
        project_root=project_root,
        sitespec_data=sitespec_data,
        theme_css=theme_css,
        backend_url=os.environ.get("BACKEND_URL", "http://127.0.0.1:8000"),
    )

    # Log startup info
    logger.info("Dazzle app '%s' ready", appspec.name)
    logger.info("  Entities: %s", len(appspec.domain.entities))
    logger.info("  Surfaces: %s", len(appspec.surfaces))
    logger.info("  Environment: %s", dazzle_env)
    logger.info("  Database: PostgreSQL")
    if enable_dev_mode:
        logger.info("  Dev mode: enabled")

    return app
