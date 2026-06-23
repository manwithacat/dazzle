"""System routes subsystem.

Registers health, debug, system info, audit query, metadata, and static file routes.
Initializes optional features: audit logger, metadata store, file service.
Runs last so it can report on other subsystems' state.
"""

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

from fastapi import Depends, HTTPException, Request

from dazzle.core.ir.integrations import MappingTriggerType
from dazzle.core.ir.process import StepEffect
from dazzle.core.manifest import load_manifest
from dazzle.core.strings import to_api_plural
from dazzle.http.runtime.subsystems import SubsystemContext

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


def _mount_static_files(
    app: Any,
    *,
    project_root: Any = None,
    extra_static_dirs: Any = None,
) -> None:
    """Mount the framework + project static file routes on ``app``.

    Registration order is load-bearing (#1330): Starlette matches mounts in
    registration order and stops at the first prefix match. The MORE-SPECIFIC
    ``/static/themes`` mount (project-local ``<project>/themes/``) MUST be
    registered BEFORE the catch-all ``/static`` mount — otherwise ``/static``
    swallows ``/static/themes/*.css`` into ``CombinedStaticFiles`` (which looks
    under ``<project>/static`` + framework_static, not ``<project>/themes/``) and
    every project theme stylesheet 404s.

    Extracted from ``SystemRoutesSubsystem._setup_system_routes`` so the mount
    ordering is unit-testable in isolation.
    """
    from pathlib import Path

    from dazzle import page as dazzle_page
    from dazzle.http.runtime.static_files import CombinedStaticFiles

    framework_static = Path(dazzle_page.__file__).parent / "runtime" / "static"
    if not framework_static.is_dir():
        return

    dirs: list[Path] = []
    # Consumer-supplied static dirs win (issue #793). Keeps consumer assets from
    # being shadowed by framework assets of the same name.
    if extra_static_dirs:
        dirs.extend(Path(d) for d in extra_static_dirs)
    if project_root:
        dirs.append(Path(project_root) / "static")
    dirs.append(framework_static)

    # v0.61.41 (Phase B Patch 5): mount project-local themes under /static/themes/
    # so `<project>/themes/<name>.css` is served without nesting under
    # `/static/css/themes/`. Theme authors get a clean discoverable location at
    # the project root; the URL split keeps framework + project themes distinct.
    #
    # #1330: register this specific mount BEFORE the catch-all /static below
    # (see the docstring) — order is the whole fix.
    if project_root:
        project_themes_dir = Path(project_root) / "themes"
        if project_themes_dir.is_dir():
            from starlette.staticfiles import StaticFiles

            app.mount(
                "/static/themes",
                StaticFiles(directory=str(project_themes_dir)),
                name="project_themes",
            )

    app.mount("/static", CombinedStaticFiles(directories=dirs), name="static")


class SystemRoutesSubsystem:
    name = "system_routes"

    def __init__(self) -> None:
        self._start_time: datetime | None = None
        self._file_service: Any | None = None
        self._service_loader: Any | None = None
        self._upload_callbacks: list[Any] = []

    def startup(self, ctx: SubsystemContext) -> None:
        self._setup_optional_features(ctx)
        self._setup_system_routes(ctx)

    def _setup_optional_features(self, ctx: SubsystemContext) -> None:
        """Initialize optional features: integration manager, workspace builder,
        debug routes, site routes, fragments, integration executor, workspace routes,
        and transition effects."""
        from dazzle.http.runtime.integration_manager import IntegrationManager
        from dazzle.http.runtime.workspace_route_builder import WorkspaceRouteBuilder

        # Create delegate instances for workspace and integration features
        ctx.integration_mgr = IntegrationManager(
            app=ctx.app,
            appspec=ctx.appspec,
            channels=ctx.channels,
            db_manager=ctx.db_manager,
            fragment_sources=ctx.config.fragment_sources,
        )
        # Derive user entity name from auth config so workspace region
        # filters using current_user resolve against the correct entity (#588).
        _user_entity_name = "User"
        if ctx.auth_config:
            _ue_name = getattr(ctx.auth_config, "user_entity_name", None)
            if _ue_name:
                _user_entity_name = _ue_name
        ctx.workspace_builder = WorkspaceRouteBuilder(
            app=ctx.app,
            appspec=ctx.appspec,
            entities=ctx.entities,
            repositories=ctx.repositories,
            auth_middleware=ctx.auth_middleware,
            enable_auth=ctx.enable_auth,
            enable_test_mode=ctx.enable_test_mode,
            entity_auto_includes=ctx.config.entity_auto_includes,
            user_entity_name=_user_entity_name,
            # #1232 — thread the entity → {fk_field: target_entity} map so
            # task_inbox sources can resolve dotted-path filters via
            # subquery JOINs (mirrors the entity_card #1225 fix shape).
            entity_ref_targets=ctx.config.entity_ref_targets,
        )

        # Debug routes
        if ctx.db_manager:
            from dazzle.http.runtime.debug_routes import create_debug_routes

            self._start_time = datetime.now()
            debug_router = create_debug_routes(
                appspec=ctx.appspec,
                db_manager=ctx.db_manager,
                entities=ctx.entities,
                start_time=self._start_time,
            )
            ctx.app.include_router(debug_router)

            from dazzle.http.runtime.event_explorer import create_event_explorer_routes

            event_explorer_router = create_event_explorer_routes(ctx.event_framework)
            ctx.app.include_router(event_explorer_router)

            # Prometheus scrape endpoint (#1192 slice 1) — pull-side
            # observability over the SystemMetricsCollector snapshot.
            # The collector lives on ``app.state.services.system_collector``
            # and may be ``None`` when telemetry is off; the route serves
            # an empty Prometheus document in that case (never 500s).
            from dazzle.http.runtime.metrics_routes import create_metrics_routes

            _system_collector = getattr(
                getattr(ctx.app.state, "services", None), "system_collector", None
            )
            metrics_router = create_metrics_routes(_system_collector)
            ctx.app.include_router(metrics_router)

            # Job explorer (#1193) — /_dazzle/jobs/* inspection endpoints,
            # the job-system analogue of the event explorer above. Only
            # registered when `job` blocks are declared (the JobRun system
            # entity + its CRUD service exist only then). Resolves the
            # JobRun service from `ctx.services` (keyed by service name)
            # the same way `services_by_entity()` does.
            if ctx.appspec.jobs:
                from dazzle.http.runtime.job_explorer import create_job_explorer_routes

                job_run_service = next(
                    (
                        svc
                        for svc in ctx.services.values()
                        if getattr(svc, "entity_name", None) == "JobRun"
                    ),
                    None,
                )
                job_explorer_router = create_job_explorer_routes(
                    job_run_service,
                    jobs_declared=len(ctx.appspec.jobs),
                )
                ctx.app.include_router(job_explorer_router)

            # Approvals explorer (#1194) — /_dazzle/approvals/pending.
            # Only registered when `approval` blocks are declared. Reads
            # the per-entity CRUD services from `ctx.services`, keyed by
            # ``service.entity_name`` (mirrors `services_by_entity()`).
            if ctx.appspec.approvals:
                from dazzle.http.runtime.approvals_explorer import create_approvals_routes

                services_by_entity = {
                    entity_name: svc
                    for svc in ctx.services.values()
                    if (entity_name := getattr(svc, "entity_name", None))
                }
                approvals_router = create_approvals_routes(
                    services_by_entity,
                    list(ctx.appspec.approvals),
                )
                ctx.app.include_router(approvals_router)

            # Integration retries explorer (#1194) —
            # /_dazzle/integrations/{name}/retries. Only registered when
            # `integration` blocks are declared. Reads from the
            # process-wide RetryAccumulator singleton that MappingExecutor
            # also writes to. The accumulator is IN-PROCESS and resets
            # on restart — see retry_accumulator.py module docstring +
            # the CHANGELOG entry for #1194.
            if ctx.appspec.integrations:
                from dazzle.http.runtime.integrations_retries import (
                    create_integrations_retries_routes,
                )
                from dazzle.http.runtime.retry_accumulator import app_retry_accumulator

                integrations_retries_router = create_integrations_retries_routes(
                    app_retry_accumulator(ctx.app),
                    list(ctx.appspec.integrations),
                )
                ctx.app.include_router(integrations_retries_router)

        # Site API routes (v0.16.0). The page-router (`/`, `/site.js`,
        # `/styles/dazzle.css`) is registered by app_factory.py with the
        # full auth/persona/analytics wiring. Calling
        # `create_site_page_routes` here too would re-register the same
        # paths and produce duplicate-route warnings on every boot
        # (caught by the cycle 4 fuzz sweep against contact_manager,
        # support_tickets, ops_dashboard).
        if ctx.sitespec_data:
            from dazzle.http.runtime.site_routes import create_site_routes

            site_router = create_site_routes(
                sitespec_data=ctx.sitespec_data,
                project_root=ctx.project_root,
            )
            ctx.app.include_router(site_router)

        # Fragment routes (v0.25.0)
        self._init_fragment_routes(ctx)

        # Integration executor (v0.20.0)
        self._init_integration_executor(ctx)

        # Mapping executor (v0.30.0)
        self._init_mapping_executor(ctx)

        # Workspace routes (v0.20.0)
        self._init_workspace_routes(ctx)

        # Transition side effects (v0.39.0, #435)
        self._init_transition_effects(ctx)

    def _init_fragment_routes(self, ctx: SubsystemContext) -> None:
        """Initialize fragment routes for composable HTMX fragments (v0.25.0)."""
        try:
            from dazzle.http.runtime.api_cache import ApiResponseCache
            from dazzle.http.runtime.fragment_routes import create_fragment_router

            # Build fragment sources from integration specs if available
            fragment_sources: dict[str, dict[str, Any]] = {}
            for integration in ctx.appspec.integrations:
                if hasattr(integration, "base_url") and integration.base_url:
                    fragment_sources[integration.name] = {
                        "url": integration.base_url,
                        "display_key": "name",
                        "value_key": "id",
                        "headers": getattr(integration, "headers", {}),
                    }

            # Merge fragment sources from DSL source= annotations (v0.25.1)
            fragment_sources.update(ctx.config.fragment_sources)

            fragment_cache = ApiResponseCache()  # auto-detects REDIS_URL
            fragment_router = create_fragment_router(fragment_sources, cache=fragment_cache)
            ctx.app.include_router(fragment_router)
        except Exception as e:
            import logging as _logging

            _logging.getLogger(__name__).warning("Failed to init fragment routes: %s", e)

    def _init_integration_executor(self, ctx: SubsystemContext) -> None:
        """Initialize integration action executor (delegates to IntegrationManager)."""
        if ctx.integration_mgr:
            ctx.integration_mgr.init_integration_executor()

    def _init_mapping_executor(self, ctx: SubsystemContext) -> None:
        """Initialize declarative integration mapping executor (v0.30.0)."""
        try:
            integrations = getattr(ctx.appspec, "integrations", []) if ctx.appspec else []

            has_mappings = False
            for integration in integrations:
                if getattr(integration, "mappings", []):
                    has_mappings = True
                    break

            if not has_mappings:
                return

            from dazzle.http.runtime.api_cache import ApiResponseCache
            from dazzle.http.runtime.mapping_executor import MappingExecutor

            event_bus = ctx.app.state.services.event_bus
            repositories = ctx.repositories

            async def update_entity(
                entity_name: str, entity_id: str, fields: dict[str, Any]
            ) -> None:
                repo = repositories.get(entity_name)
                if repo:
                    from uuid import UUID

                    await repo.update(UUID(entity_id), fields)

            cache = ApiResponseCache()  # auto-detects REDIS_URL
            from dazzle.http.runtime.retry_accumulator import app_retry_accumulator

            executor = MappingExecutor(
                ctx.appspec,
                event_bus,
                update_entity=update_entity,
                cache=cache,
                # #1445: share the per-app accumulator with the retries route reader.
                retry_accumulator=app_retry_accumulator(ctx.app),
            )
            executor.register_all()

            # Wire entity lifecycle events to the event bus
            self._wire_entity_events_to_bus(ctx, event_bus)

            # Register manual trigger endpoint for each entity with manual mappings
            self._register_manual_trigger_routes(ctx, executor)

        except Exception as e:
            logger.warning("Failed to init mapping executor: %s", e)

    def _wire_entity_events_to_bus(self, ctx: SubsystemContext, event_bus: Any) -> None:
        """Wire CRUD service lifecycle callbacks to the EntityEventBus."""
        from dazzle.http.runtime.event_bus import EntityEventBus
        from dazzle.http.runtime.service_generator import CRUDService

        bus: EntityEventBus = event_bus

        async def _on_created(
            entity_name: str,
            entity_id: str,
            entity_data: dict[str, Any],
            _old_data: dict[str, Any] | None,
        ) -> None:
            await bus.emit_created(entity_name, entity_id, entity_data)

        async def _on_updated(
            entity_name: str,
            entity_id: str,
            entity_data: dict[str, Any],
            old_data: dict[str, Any] | None,
        ) -> None:
            data = dict(entity_data)
            if old_data:
                for key in ("status", "state"):
                    if key in old_data and old_data[key] != entity_data.get(key):
                        data["_previous_state"] = old_data[key]
                        break
            await bus.emit_updated(entity_name, entity_id, data)

        async def _on_deleted(
            entity_name: str,
            entity_id: str,
            entity_data: dict[str, Any],
            _old_data: dict[str, Any] | None,
        ) -> None:
            await bus.emit_deleted(entity_name, entity_id)

        wired = 0
        for service in ctx.services.values():
            if isinstance(service, CRUDService):
                service.on_created(_on_created)
                service.on_updated(_on_updated)
                service.on_deleted(_on_deleted)
                wired += 1

        if wired:
            logger.debug("Wired entity events to EntityEventBus for %d services", wired)

    def _register_manual_trigger_routes(self, ctx: SubsystemContext, executor: Any) -> None:
        """Register POST endpoints for manual integration triggers."""

        def _make_handler(
            _executor: Any,
            _int_name: str,
            _map_name: str,
            _entity_name: str,
            _repositories: Any,
            _slug: str,
        ) -> Any:
            async def _handler(entity_id: str, request: Request) -> Any:
                from uuid import UUID

                from starlette.responses import Response

                repo = _repositories.get(_entity_name)
                if not repo:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Entity {_entity_name} not found",
                    )
                entity_data = await repo.read(UUID(entity_id))
                if not entity_data:
                    raise HTTPException(status_code=404, detail="Record not found")
                data = (
                    dict(entity_data)
                    if isinstance(entity_data, dict)
                    else (entity_data.__dict__ if hasattr(entity_data, "__dict__") else {})
                )
                force_refresh = request.query_params.get("force") == "1"
                result = await _executor.execute_manual(
                    _int_name,
                    _map_name,
                    data,
                    entity_name=_entity_name,
                    entity_id=entity_id,
                    force_refresh=force_refresh,
                )

                is_htmx = request.headers.get("HX-Request") == "true"
                if is_htmx:
                    detail_url = f"/{_slug}/{entity_id}"
                    return Response(
                        status_code=200,
                        headers={"HX-Redirect": detail_url},
                    )

                return {
                    "success": result.success,
                    "message": result.message if hasattr(result, "message") else "",
                    "mapped_fields": result.mapped_fields or {},
                    "cache_hit": result.cache_hit,
                }

            return _handler

        for integration in getattr(ctx.appspec, "integrations", []):
            for mapping in integration.mappings:
                has_manual = any(
                    t.trigger_type == MappingTriggerType.MANUAL for t in mapping.triggers
                )
                if not has_manual:
                    continue

                entity_name = mapping.entity_ref
                slug = to_api_plural(entity_name)
                int_name = integration.name
                map_name = mapping.name

                handler = _make_handler(
                    executor,
                    int_name,
                    map_name,
                    entity_name,
                    ctx.repositories,
                    slug,
                )

                ctx.app.post(
                    f"/{slug}/{{entity_id}}/integrations/{int_name}/{map_name}",
                    tags=[entity_name],
                )(handler)

    def _init_workspace_routes(self, ctx: SubsystemContext) -> None:
        """Initialize workspace layout routes (delegates to WorkspaceRouteBuilder)."""
        if ctx.workspace_builder:
            ctx.workspace_builder.init_workspace_routes()

    def _init_transition_effects(self, ctx: SubsystemContext) -> None:
        """Wire on_transition side effects into entity update callbacks (#435)."""
        if not ctx.appspec:
            return

        from dazzle.http.runtime.service_generator import CRUDService

        entity_transitions: dict[str, list[tuple[str, str, list[StepEffect]]]] = {}
        for entity in ctx.appspec.domain.entities:
            if not entity.state_machine:
                continue
            for t in entity.state_machine.transitions:
                if t.effects:
                    entity_transitions.setdefault(entity.name, []).append(
                        (t.from_state, t.to_state, list(t.effects))
                    )

        if not entity_transitions:
            return

        from dazzle.http.runtime.side_effect_executor import SideEffectExecutor
        from dazzle.http.runtime.transition_effects import TransitionEffectRunner

        executor = SideEffectExecutor(services=ctx.services)
        runner = TransitionEffectRunner(
            executor=executor,
            entity_transitions=entity_transitions,
            status_fields=ctx.config.entity_status_fields,
        )

        wired = 0
        for entity_name in entity_transitions:
            service = ctx.services.get(entity_name)
            if service and isinstance(service, CRUDService):
                service.on_updated(runner.on_entity_updated)
                wired += 1

        if wired:
            logger.info("Transition effects wired for %d entity/entities", wired)

    def _setup_system_routes(self, ctx: SubsystemContext) -> None:
        """Register domain service stubs, health check, spec, and db-info routes."""
        from dazzle.http.runtime.service_loader import (
            ServiceInputCoercionError,
            ServiceLoader,
            coerce_service_inputs,
        )

        # Load domain service stubs
        assert ctx.services_dir is not None, (
            "services_dir must be set before SystemRoutesSubsystem starts"
        )
        self._service_loader = ServiceLoader(services_dir=ctx.services_dir)
        try:
            self._service_loader.load_services()
        except Exception:
            logger.warning("Failed to load domain services", exc_info=True)

        if self._service_loader and self._service_loader.services:
            service_loader = self._service_loader  # Capture for closure

            @ctx.app.get("/_dazzle/services", tags=["System"])
            async def list_domain_services() -> dict[str, Any]:
                """List loaded domain service stubs."""
                services = []
                for service_id, loaded in service_loader.services.items():
                    services.append(
                        {
                            "id": service_id,
                            "module_path": str(loaded.module_path),
                            "has_result_type": loaded.result_type is not None,
                        }
                    )
                return {"services": services, "count": len(services)}

            @ctx.app.post("/_dazzle/services/{service_id}/invoke", tags=["System"])
            async def invoke_domain_service(
                service_id: str, payload: dict[str, Any] | None = None
            ) -> dict[str, Any]:
                """Invoke a domain service stub."""
                if not service_loader.has_service(service_id):
                    raise HTTPException(status_code=404, detail=f"Service not found: {service_id}")
                # Coerce the raw JSON body into the service's declared input types
                # (date/datetime/Decimal/Money) so the stub receives the types its
                # generated signature declares, not raw JSON scalars (#1323).
                kwargs = payload or {}
                spec = ctx.appspec.get_domain_service(service_id)
                if spec is not None:
                    try:
                        kwargs = coerce_service_inputs(spec.inputs, kwargs)
                    except ServiceInputCoercionError as e:
                        raise HTTPException(status_code=400, detail=str(e)) from e
                try:
                    result = service_loader.invoke(service_id, **kwargs)
                    return {"result": result}
                except Exception as e:
                    logger.error("Service invocation failed for %s: %s", service_id, e)
                    raise HTTPException(status_code=500, detail="Service invocation failed")

        appspec = ctx.appspec
        entities = ctx.entities

        # Compute DSL hash and capture startup time for /health
        import hashlib
        import time

        try:
            _spec_bytes = appspec.model_dump_json().encode()
        except Exception:
            # ParamRef or other non-serializable IR nodes — fall back to repr
            _spec_bytes = repr(appspec.model_dump(mode="python")).encode()
        _dsl_hash = hashlib.sha256(_spec_bytes).hexdigest()[:8]
        _start_time = time.monotonic()

        try:
            from dazzle import __version__ as _dz_version
        except ImportError:
            _dz_version = "unknown"

        @ctx.app.get("/health", tags=["System"])
        async def health_check() -> dict[str, Any]:
            return {
                "status": "healthy",
                "app": appspec.name,
                "version": _dz_version,
                "dsl_hash": _dsl_hash,
                "uptime_seconds": round(time.monotonic() - _start_time, 1),
            }

        @ctx.app.get("/spec", tags=["System"])
        async def get_spec() -> dict[str, Any]:
            return appspec.model_dump()

        def _mask_database_url(url: str | None) -> str | None:
            """Mask password in database URL for safe display."""
            if not url:
                return None
            import re as _re

            return _re.sub(r"://([^:]+):([^@]+)@", r"://\1:***@", url)

        masked_db_url = _mask_database_url(ctx.database_url or None)
        files_path_str = str(ctx.files_path) if ctx.enable_files else None
        last_migration = ctx.last_migration
        auth_enabled = ctx.enable_auth
        files_enabled = ctx.enable_files

        @ctx.app.get("/db-info", tags=["System"])
        async def db_info() -> dict[str, Any]:
            migration_info = None
            if last_migration:
                migration_info = {
                    "steps_executed": len(last_migration.safe_steps),
                    "warnings": last_migration.warnings,
                    "has_pending_destructive": last_migration.has_destructive,
                }
            return {
                "database_url": masked_db_url,
                "database_backend": "postgresql",
                "tables": [e.name for e in entities],
                "last_migration": migration_info,
                "auth_enabled": auth_enabled,
                "files_enabled": files_enabled,
                "files_path": files_path_str,
            }

        # Authenticated diagnostics endpoint
        if ctx.auth_dep:

            @ctx.app.get("/_diagnostics", tags=["System"])
            async def diagnostics(
                auth_context: Any = Depends(ctx.auth_dep),
            ) -> dict[str, Any]:
                user_roles = {
                    r if isinstance(r, str) else getattr(r, "name", str(r))
                    for r in getattr(getattr(auth_context, "user", None), "roles", [])
                }
                admin_roles = {"super_admin", "trust_admin", "admin"}
                if not user_roles.intersection(admin_roles):
                    raise HTTPException(status_code=403, detail="Admin role required")

                surfaces = getattr(appspec, "surfaces", []) or []
                workspaces = getattr(appspec, "workspaces", []) or []
                features = {
                    "auth": auth_enabled,
                    "files": files_enabled,
                    "feedback_widget": bool(
                        appspec.feedback_widget and appspec.feedback_widget.enabled
                    )
                    if getattr(appspec, "feedback_widget", None)
                    else False,
                }
                migration_pending = 0
                if last_migration and last_migration.has_destructive:
                    migration_pending = len(list(getattr(last_migration, "destructive_steps", [])))
                return {
                    "entities": len(entities),
                    "surfaces": len(surfaces),
                    "workspaces": len(workspaces),
                    "features": features,
                    "database": {
                        "connected": True,
                        "pending_migrations": migration_pending,
                    },
                    "dsl_hash": _dsl_hash,
                    "version": _dz_version,
                }

        # Theme + chrome resolution (#1042 follow-up, v0.67.93). The
        # typed-Page primitive substrate consumes the same theme /
        # favicon / feedback-widget config the legacy Jinja env did,
        # but via `AppChrome` stashed on app.state. Page-render call
        # sites read `app.state.fragment_chrome` and thread the
        # css_links / js_scripts / theme / font_preconnect kwargs into
        # `dispatch_render_page`.
        try:
            from pathlib import Path

            from dazzle.page.runtime.app_chrome import resolve_app_chrome

            mf = None
            if ctx.project_root:
                manifest_path = Path(ctx.project_root) / "dazzle.toml"
                if manifest_path.exists():
                    mf = load_manifest(manifest_path)

            chrome = resolve_app_chrome(
                appspec,
                project_root=Path(ctx.project_root) if ctx.project_root else None,
                manifest=mf,
            )
            ctx.app.state.fragment_chrome = chrome
            # Back-compat slots — existing readers (page_routes,
            # experience_routes, route_generator, exception_handlers,
            # site_routes) read these direct attributes via getattr().
            ctx.app.state.fragment_chrome_css_links = chrome.css_links
            ctx.app.state.fragment_chrome_js_scripts = chrome.js_scripts
            ctx.app.state.fragment_chrome_theme = chrome.theme
            ctx.app.state.fragment_chrome_font_preconnect = chrome.font_preconnect
            ctx.app.state.fragment_chrome_favicon = chrome.favicon
            ctx.app.state.fragment_chrome_feedback_widget_enabled = chrome.feedback_widget_enabled
        except ImportError:
            pass  # dazzle_page not installed (CLI-only context)

        # Mount static files from project dir + framework dir. Mount ordering
        # is load-bearing (#1330) — see `_mount_static_files`.
        try:
            _mount_static_files(
                ctx.app,
                project_root=ctx.project_root,
                extra_static_dirs=ctx.extra_static_dirs,
            )
        except ImportError:
            pass  # dazzle_page not installed — static files served externally
        except Exception:
            logger.warning("Failed to mount static files", exc_info=True)

    def shutdown(self) -> None:
        pass
