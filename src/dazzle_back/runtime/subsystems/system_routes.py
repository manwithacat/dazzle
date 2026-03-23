"""System routes subsystem.

Registers health, debug, system info, audit query, metadata, and static file routes.
Initializes optional features: audit logger, metadata store, file service.
Runs last so it can report on other subsystems' state.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

from dazzle_back.runtime.subsystems import SubsystemContext

if TYPE_CHECKING:
    pass

logger = logging.getLogger("dazzle.server")


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
        from dazzle_back.runtime.integration_manager import IntegrationManager
        from dazzle_back.runtime.workspace_route_builder import WorkspaceRouteBuilder

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
        )

        # Debug routes
        if ctx.db_manager:
            from dazzle_back.runtime.debug_routes import create_debug_routes

            self._start_time = datetime.now()
            debug_router = create_debug_routes(
                appspec=ctx.appspec,
                db_manager=ctx.db_manager,
                entities=ctx.entities,
                start_time=self._start_time,
            )
            ctx.app.include_router(debug_router)

            from dazzle_back.runtime.event_explorer import create_event_explorer_routes

            event_explorer_router = create_event_explorer_routes(ctx.event_framework)
            ctx.app.include_router(event_explorer_router)

        # Site routes (v0.16.0)
        if ctx.sitespec_data:
            from dazzle_back.runtime.site_routes import (
                create_site_page_routes,
                create_site_routes,
            )

            site_router = create_site_routes(
                sitespec_data=ctx.sitespec_data,
                project_root=ctx.project_root,
            )
            ctx.app.include_router(site_router)

            page_router = create_site_page_routes(
                sitespec_data=ctx.sitespec_data,
                project_root=ctx.project_root,
            )
            ctx.app.include_router(page_router)

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
            from dazzle_back.runtime.api_cache import ApiResponseCache
            from dazzle_back.runtime.fragment_routes import create_fragment_router

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

            _logging.getLogger("dazzle.server").warning("Failed to init fragment routes: %s", e)

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

            from dazzle_back.runtime.api_cache import ApiResponseCache
            from dazzle_back.runtime.event_bus import get_event_bus
            from dazzle_back.runtime.mapping_executor import MappingExecutor

            event_bus = get_event_bus()
            repositories = ctx.repositories

            async def update_entity(
                entity_name: str, entity_id: str, fields: dict[str, Any]
            ) -> None:
                repo = repositories.get(entity_name)
                if repo:
                    from uuid import UUID

                    await repo.update(UUID(entity_id), fields)

            cache = ApiResponseCache()  # auto-detects REDIS_URL
            executor = MappingExecutor(
                ctx.appspec, event_bus, update_entity=update_entity, cache=cache
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
        from dazzle_back.runtime.event_bus import EntityEventBus
        from dazzle_back.runtime.service_generator import CRUDService

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
        from dazzle.core.ir.integrations import MappingTriggerType
        from dazzle.core.strings import to_api_plural
        from dazzle_back.runtime._fastapi_compat import HTTPException, Request

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

        from dazzle.core.ir.process import StepEffect
        from dazzle_back.runtime.service_generator import CRUDService

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

        from dazzle_back.runtime.side_effect_executor import SideEffectExecutor
        from dazzle_back.runtime.transition_effects import TransitionEffectRunner

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
        from dazzle_back.runtime._fastapi_compat import HTTPException
        from dazzle_back.runtime.service_loader import ServiceLoader

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
                try:
                    result = service_loader.invoke(service_id, **(payload or {}))
                    return {"result": result}
                except Exception as e:
                    logger.error("Service invocation failed for %s: %s", service_id, e)
                    raise HTTPException(status_code=500, detail="Service invocation failed")

        appspec = ctx.appspec
        entities = ctx.entities

        @ctx.app.get("/health", tags=["System"])
        async def health_check() -> dict[str, str]:
            return {"status": "healthy", "app": appspec.name}

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

        # Configure project-level template overrides (v0.29.0)
        try:
            from dazzle_ui.runtime.template_renderer import (
                TEMPLATES_DIR,
                configure_project_templates,
                get_jinja_env,
            )

            if ctx.project_root:
                project_templates = ctx.project_root / "templates"
                if project_templates.is_dir():
                    configure_project_templates(project_templates)

                # CDN toggle from [ui] cdn in dazzle.toml
                manifest_path = ctx.project_root / "dazzle.toml"
                if manifest_path.exists():
                    from dazzle.core.manifest import load_manifest

                    mf = load_manifest(manifest_path)
                    get_jinja_env().globals["_use_cdn"] = mf.cdn
                    if mf.favicon:
                        get_jinja_env().globals["_favicon"] = mf.favicon

                    # Build override registry if project has declaration headers
                    try:
                        from dazzle import __version__ as dz_version
                        from dazzle_ui.runtime.override_registry import (
                            build_registry,
                            save_registry,
                        )

                        registry = build_registry(
                            project_templates,
                            TEMPLATES_DIR,
                            framework_version=dz_version,
                        )
                        if registry.get("template_overrides"):
                            from dazzle.core.paths import project_overrides_file

                            save_registry(
                                registry,
                                project_overrides_file(ctx.project_root),
                            )
                    except Exception:
                        logger.debug("Override registry build skipped", exc_info=True)
        except ImportError:
            pass  # dazzle_ui not installed

        # Mount static files from project dir + framework dir
        try:
            from pathlib import Path

            import dazzle_ui
            from dazzle_back.runtime.static_files import CombinedStaticFiles

            framework_static = Path(dazzle_ui.__file__).parent / "runtime" / "static"
            if framework_static.is_dir():
                dirs: list[Path] = []
                if ctx.project_root:
                    dirs.append(ctx.project_root / "static")
                dirs.append(framework_static)
                ctx.app.mount("/static", CombinedStaticFiles(directories=dirs), name="static")
        except ImportError:
            pass  # dazzle_ui not installed — static files served externally
        except Exception:
            logger.warning("Failed to mount static files", exc_info=True)

    def shutdown(self) -> None:
        pass
