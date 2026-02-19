"""App factory functions extracted from server.py.

Convenience functions for creating and running Dazzle backend applications,
including the production ASGI factory for deployment.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dazzle_back.specs import BackendSpec

if TYPE_CHECKING:
    from fastapi import FastAPI

    from dazzle.core.ir import EntitySpec, SurfaceSpec, ViewSpec

logger = logging.getLogger(__name__)


def create_app(
    spec: BackendSpec,
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
    Create a FastAPI application from a BackendSpec.

    This is the main entry point for creating a Dazzle backend application.

    Args:
        spec: Backend specification
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
        >>> from dazzle_back.specs import BackendSpec
        >>> spec = BackendSpec(name="my_app", ...)
        >>> app = create_app(spec, database_url="postgresql://...")
        >>> # Run with uvicorn: uvicorn mymodule:app
    """
    from dazzle_back.runtime.server import DazzleBackendApp

    builder = DazzleBackendApp(
        spec,
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
    spec: BackendSpec,
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
        spec: Backend specification
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

    Example:
        >>> from dazzle_back.specs import BackendSpec
        >>> spec = BackendSpec(name="my_app", ...)
        >>> run_app(spec, database_url="postgresql://...")
    """
    try:
        import uvicorn
    except ImportError:
        raise RuntimeError("uvicorn is not installed. Install with: pip install uvicorn")

    app = create_app(
        spec,
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
# App from JSON/Dict
# =============================================================================


def create_app_from_dict(spec_dict: dict[str, Any]) -> FastAPI:
    """
    Create a FastAPI application from a dictionary specification.

    Useful for loading specs from JSON files or API responses.

    Args:
        spec_dict: Dictionary representation of BackendSpec

    Returns:
        FastAPI application
    """
    spec = BackendSpec.model_validate(spec_dict)
    return create_app(spec)


def create_app_from_json(json_path: str) -> FastAPI:
    """
    Create a FastAPI application from a JSON file.

    Args:
        json_path: Path to JSON file containing BackendSpec

    Returns:
        FastAPI application
    """
    spec_dict = json.loads(Path(json_path).read_text())
    return create_app_from_dict(spec_dict)


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
        process_adapter_class: Custom ProcessAdapter class (default: LiteProcessAdapter).
            Use CeleryProcessAdapter for Heroku/Redis deployments.
            Can also be set via DAZZLE_PROCESS_ADAPTER env var:
            - "lite" or "sqlite" -> LiteProcessAdapter (default)
            - "celery" or "redis" -> CeleryProcessAdapter

    Environment Variables:
        DAZZLE_PROJECT_ROOT: Project root directory (default: current directory)
        DATABASE_URL: PostgreSQL connection URL (Heroku format supported)
        AUTH_DATABASE_URL: PostgreSQL URL for auth DB (defaults to DATABASE_URL)
        REDIS_URL: Redis connection URL (for sessions/cache)
        DAZZLE_ENV: Environment name (development/staging/production)
        DAZZLE_SECRET_KEY: Secret key for sessions/tokens
        DAZZLE_ENABLE_PROCESSES: Enable/disable process workflows (default: "true")
        DAZZLE_PROCESS_ADAPTER: Process adapter type ("lite", "celery", "temporal")

    Usage:
        uvicorn dazzle_back.runtime.app_factory:create_app_factory --factory --host 0.0.0.0 --port $PORT

    Procfile example:
        web: uvicorn dazzle_back.runtime.app_factory:create_app_factory --factory --host 0.0.0.0 --port $PORT

    Returns:
        FastAPI application configured for production
    """
    from dazzle_back.runtime.server import DazzleBackendApp, ServerConfig

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
        from dazzle_back.converters import convert_appspec_to_backend
    except ImportError as e:
        raise RuntimeError(
            f"Dazzle core modules not available: {e}. "
            "Ensure dazzle is installed: pip install dazzle"
        )

    # Load manifest
    logger.info(f"Loading Dazzle project from {project_root}")
    manifest = load_manifest(manifest_path)

    # Resolve DATABASE_URL: env → dazzle.toml [database] → default
    from dazzle.core.manifest import resolve_database_url

    database_url = resolve_database_url(manifest)
    logger.info(f"Database URL resolved ({len(database_url)} chars)")

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

    # Convert to backend spec
    backend_spec = convert_appspec_to_backend(appspec)

    # Load SiteSpec if available (merges copy.md content if present)
    sitespec_data = None
    if sitespec_exists(project_root):
        try:
            sitespec = load_sitespec_with_copy(project_root)
            sitespec_data = sitespec.model_dump()
            logger.info(f"Loaded SiteSpec with {len(sitespec.pages)} pages")
        except Exception as e:
            logger.warning(f"Failed to load sitespec.yaml: {e}")

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
        if adapter_env in ("celery", "redis"):
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
        # Default: None means LiteProcessAdapter will be used

    # Compute view-based list projections from DSL surfaces
    entity_list_projections = build_entity_list_projections(
        entities=appspec.domain.entities,
        surfaces=appspec.surfaces,
        views=appspec.views,
    )

    # Auto-detect ref fields for eager loading (prevents N+1 queries)
    entity_auto_includes: dict[str, list[str]] = {}
    for entity in backend_spec.entities:
        ref_names = [f.name for f in entity.fields if f.type.kind == "ref" and f.type.ref_entity]
        if ref_names:
            entity_auto_includes[entity.name] = ref_names

    # Extract entity status fields for process trigger status transition detection
    entity_status_fields: dict[str, str] = {}
    if appspec.domain:
        for ent in appspec.domain.entities:
            sm = getattr(ent, "state_machine", None)
            if sm:
                entity_status_fields[ent.name] = getattr(sm, "status_field", "status")

    # Build server config
    config = ServerConfig(
        database_url=database_url if database_url else None,
        enable_auth=manifest.auth.enabled,
        auth_config=manifest.auth if manifest.auth.enabled else None,
        enable_files=True,
        files_path=project_root / ".dazzle" / "uploads",
        enable_test_mode=enable_test_mode,
        services_dir=project_root / "services",
        enable_dev_mode=enable_dev_mode,
        personas=personas,
        scenarios=[],
        sitespec_data=sitespec_data,
        project_root=project_root,
        enable_processes=enable_processes,
        process_adapter_class=resolved_adapter_class,
        enable_console=enable_dev_mode,
        entity_list_projections=entity_list_projections,
        entity_auto_includes=entity_auto_includes,
        process_specs=list(appspec.processes),
        schedule_specs=list(appspec.schedules),
        entity_status_fields=entity_status_fields,
    )

    # Build and return the FastAPI app
    builder = DazzleBackendApp(backend_spec, config=config)
    app = builder.build()

    # Sync DSL schedules to Celery Beat if using CeleryProcessAdapter
    if builder._process_adapter is not None:
        try:
            from dazzle.core.process.celery_adapter import CeleryProcessAdapter as _CPA

            if isinstance(builder._process_adapter, _CPA) and appspec.schedules:
                count = builder._process_adapter.sync_schedules_from_appspec(appspec)
                if count:
                    logger.info(f"Synced {count} DSL schedules to Celery Beat")
        except ImportError:
            pass

    # Add site page routes if sitespec exists (landing pages, /site.js)
    if sitespec_data:
        from dazzle_back.runtime.site_routes import (
            create_auth_page_routes,
            create_site_page_routes,
        )

        # Landing pages (/, /features, /pricing, etc.) and /site.js
        site_page_router = create_site_page_routes(
            sitespec_data=sitespec_data,
            project_root=project_root,
        )
        app.include_router(site_page_router)
        logger.info("  Site pages: landing, /site.js, /styles/dazzle.css")

        # Auth pages (/login, /signup)
        auth_page_router = create_auth_page_routes(sitespec_data, project_root=project_root)
        app.include_router(auth_page_router)
        logger.info("  Auth pages: /login, /signup")

    # Add app page routes (/app/*)
    try:
        from dazzle_ui.runtime.page_routes import create_page_routes

        # Get theme CSS if available
        theme_css = ""
        try:
            from dazzle_ui.runtime.css_loader import get_bundled_css

            theme_css = get_bundled_css()
        except Exception:
            logger.debug("Failed to load bundled theme CSS", exc_info=True)

        # Get auth context getter from builder if auth is enabled
        _page_get_auth_context = None
        if builder.auth_middleware:
            _page_get_auth_context = builder.auth_middleware.get_auth_context

        page_router = create_page_routes(
            appspec,
            backend_url=os.environ.get("BACKEND_URL", "http://127.0.0.1:8000"),
            theme_css=theme_css,
            get_auth_context=_page_get_auth_context,
            app_prefix="/app",
        )
        app.include_router(page_router, prefix="/app")
        logger.info(f"  App pages: {len(appspec.workspaces)} workspaces mounted at /app")
    except ImportError as e:
        logger.warning(f"Page routes not available: {e}")

    # Add island API routes (/api/islands)
    if getattr(appspec, "islands", None):
        try:
            from dazzle_back.runtime.island_routes import create_island_routes

            _island_auth_dep = None
            _island_opt_dep = None
            if builder._auth_store:
                from dazzle_back.runtime.auth import (
                    create_auth_dependency,
                    create_optional_auth_dependency,
                )

                _island_auth_dep = create_auth_dependency(builder._auth_store)
                _island_opt_dep = create_optional_auth_dependency(builder._auth_store)

            island_router = create_island_routes(
                islands=appspec.islands,
                services=builder.services,
                auth_dep=_island_auth_dep,
                optional_auth_dep=_island_opt_dep,
            )
            app.include_router(island_router)
            logger.info(f"  Islands: {len(appspec.islands)} mounted at /api/islands")
        except ImportError as e:
            logger.warning(f"Island routes not available: {e}")

    # Log startup info
    logger.info(f"Dazzle app '{appspec.name}' ready")
    logger.info(f"  Entities: {len(backend_spec.entities)}")
    logger.info(f"  Endpoints: {len(backend_spec.endpoints)}")
    logger.info(f"  Environment: {dazzle_env}")
    logger.info("  Database: PostgreSQL")
    if enable_dev_mode:
        logger.info("  Dev mode: enabled")

    # Add custom 404 handler for site pages (v0.28.0 - extracted to exception_handlers.py)
    if sitespec_data:
        from dazzle_back.runtime.exception_handlers import register_site_404_handler

        register_site_404_handler(app, sitespec_data, project_root=project_root)

    return app
