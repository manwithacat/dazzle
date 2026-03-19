"""
Runtime server - creates and runs a FastAPI application from AppSpec.

This module provides the main entry point for running a Dazzle backend application.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from dazzle.core.ir import AppSpec
from dazzle_back.runtime._fastapi_compat import (
    FASTAPI_AVAILABLE,
    HTTPException,
    Request,
)
from dazzle_back.runtime._fastapi_compat import FastAPI as _FastAPI
from dazzle_back.runtime.auth import (
    AuthMiddleware,
    AuthStore,
)
from dazzle_back.runtime.file_routes import create_file_routes, create_static_file_routes
from dazzle_back.runtime.file_storage import FileService
from dazzle_back.runtime.migrations import MigrationPlan, auto_migrate
from dazzle_back.runtime.model_generator import (
    generate_all_entity_models,
    generate_create_schema,
    generate_update_schema,
)
from dazzle_back.runtime.repository import RepositoryFactory
from dazzle_back.runtime.service_generator import CRUDService, ServiceFactory
from dazzle_back.runtime.service_loader import ServiceLoader
from dazzle_back.runtime.workspace_rendering import (  # noqa: F401
    _AGGREGATE_RE,
    WorkspaceRegionContext,
    _build_entity_columns,
    _build_surface_columns,
    _compute_aggregate_metrics,
    _fetch_count_metric,
    _fetch_region_json,
    _field_kind_to_col_type,
    _parse_simple_where,
    _workspace_batch_handler,
    _workspace_region_handler,
)

if FASTAPI_AVAILABLE:
    from dazzle_back.runtime.route_generator import RouteGenerator
else:
    RouteGenerator = None  # type: ignore[assignment,misc]

# FastAPI is optional - use TYPE_CHECKING for type hints
if TYPE_CHECKING:
    from fastapi import FastAPI

    from dazzle_back.runtime.pg_backend import PostgresBackend

logger = logging.getLogger(__name__)


# =============================================================================
# Channel conversion (moved from dazzle_back.converters)
# =============================================================================


def _convert_channels(ir_channels: list[Any]) -> list[Any]:
    """Convert IR ChannelSpecs to backend ChannelSpecs.

    Trigger info from IR send operations is serialized into channel
    metadata under ``send_triggers`` so the runtime can wire entity
    lifecycle events to channel dispatches.
    """
    from dazzle_back.specs.channel import ChannelSpec, SendOperationSpec

    result: list[ChannelSpec] = []
    for ch in ir_channels:
        send_ops: list[SendOperationSpec] = []
        send_triggers: dict[str, dict[str, Any]] = {}

        for op in ch.send_operations:
            send_ops.append(
                SendOperationSpec(
                    name=op.name,
                    message=op.message_name,
                    template=op.options.get("template"),
                    subject_template=op.options.get("subject_template"),
                )
            )
            if op.trigger:
                trigger_data: dict[str, Any] = {"kind": str(op.trigger.kind)}
                if op.trigger.entity_name:
                    trigger_data["entity_name"] = op.trigger.entity_name
                if op.trigger.event:
                    trigger_data["event"] = str(op.trigger.event)
                if op.trigger.field_name:
                    trigger_data["field_name"] = op.trigger.field_name
                if op.trigger.field_value:
                    trigger_data["field_value"] = op.trigger.field_value
                if op.trigger.from_state:
                    trigger_data["from_state"] = op.trigger.from_state
                if op.trigger.to_state:
                    trigger_data["to_state"] = op.trigger.to_state
                send_triggers[op.name] = trigger_data

        metadata: dict[str, Any] = {}
        if send_triggers:
            metadata["send_triggers"] = send_triggers

        result.append(
            ChannelSpec(
                name=ch.name,
                kind=ch.kind.value,
                provider=ch.provider,
                send_operations=send_ops,
                metadata=metadata,
            )
        )
    return result


# =============================================================================
# Extracted delegate classes
# =============================================================================


class IntegrationManager:
    """Manages integration executor and messaging channels for DazzleBackendApp."""

    def __init__(
        self,
        *,
        app: FastAPI,
        appspec: AppSpec,
        channels: list[Any],
        db_manager: PostgresBackend | None,
        fragment_sources: dict[str, dict[str, Any]],
    ) -> None:
        self._app = app
        self._appspec = appspec
        self._channels = channels
        self._db_manager = db_manager
        self._fragment_sources = fragment_sources
        self.channel_manager: Any | None = None
        self.integration_executor: Any | None = None

    def init_channel_manager(self) -> None:
        """Initialize the channel manager for messaging."""
        try:
            from dazzle.core.ir import ChannelKind
            from dazzle.core.ir import ChannelSpec as IRChannelSpec
            from dazzle_back.channels import create_channel_manager

            ir_channels = []
            for channel in self._channels:
                kind_map = {
                    "email": ChannelKind.EMAIL,
                    "queue": ChannelKind.QUEUE,
                    "stream": ChannelKind.STREAM,
                }
                ir_channel = IRChannelSpec(
                    name=channel.name,
                    kind=kind_map.get(channel.kind, ChannelKind.EMAIL),
                    provider=channel.provider,
                )
                ir_channels.append(ir_channel)

            self.channel_manager = create_channel_manager(
                db_manager=self._db_manager,
                channel_specs=ir_channels,
                build_id=f"{self._appspec.name}-{self._appspec.version}",
            )

            self._add_channel_routes()

        except ImportError:
            pass
        except Exception as e:
            import logging

            logging.getLogger("dazzle.server").warning("Failed to init channels: %s", e)

    def _add_channel_routes(self) -> None:
        """Add channel management routes to the FastAPI app."""
        if not self.channel_manager or not self._app:
            return

        channel_manager = self.channel_manager  # Capture for closures

        @self._app.on_event("startup")
        async def startup_channels() -> None:
            await channel_manager.initialize()
            await channel_manager.start_processor()

        @self._app.on_event("shutdown")
        async def shutdown_channels() -> None:
            await channel_manager.shutdown()

        @self._app.get("/_dazzle/channels", tags=["Channels"])
        async def list_channels() -> dict[str, Any]:
            statuses = channel_manager.get_all_statuses()
            return {
                "channels": [s.to_dict() for s in statuses],
                "outbox_stats": channel_manager.get_outbox_stats(),
            }

        @self._app.get("/_dazzle/channels/{channel_name}", tags=["Channels"])
        async def get_channel_status(channel_name: str) -> dict[str, Any]:
            status = channel_manager.get_channel_status(channel_name)
            if not status:
                raise HTTPException(status_code=404, detail=f"Channel '{channel_name}' not found")
            result: dict[str, Any] = status.to_dict()
            return result

        @self._app.post("/_dazzle/channels/{channel_name}/send", tags=["Channels"])
        async def send_message(
            channel_name: str,
            message: dict[str, Any],
        ) -> dict[str, Any]:
            try:
                result = await channel_manager.send(
                    channel=channel_name,
                    operation=message.get("operation", "test"),
                    message_type=message.get("type", "TestMessage"),
                    payload=message.get("payload", {}),
                    recipient=message.get("recipient", "test@example.com"),
                    metadata=message.get("metadata"),
                )
                if hasattr(result, "to_dict"):
                    return {"status": "queued", "message": result.to_dict()}
                elif hasattr(result, "is_success"):
                    return {
                        "status": "sent" if result.is_success else "failed",
                        "error": result.error,
                    }
                return {"status": "queued"}
            except Exception as e:
                logger.error("Channel test message failed: %s", e)
                raise HTTPException(status_code=500, detail="Failed to send test message")

        @self._app.post("/_dazzle/channels/health", tags=["Channels"])
        async def check_channel_health() -> dict[str, Any]:
            results = await channel_manager.health_check_all()
            return {"health": results}

        @self._app.get("/_dazzle/channels/outbox/recent", tags=["Channels"])
        async def get_recent_outbox(limit: int = 20) -> dict[str, Any]:
            messages = channel_manager.get_recent_messages(limit)
            return {
                "messages": [
                    {
                        "id": m.id,
                        "channel": m.channel_name,
                        "recipient": m.recipient,
                        "subject": m.payload.get("subject", m.message_type),
                        "status": m.status.value,
                        "created_at": m.created_at.isoformat(),
                        "last_error": m.last_error,
                    }
                    for m in messages
                ],
                "stats": channel_manager.get_outbox_stats(),
            }

    def init_integration_executor(self) -> None:
        """Initialize integration action executor (v0.20.0)."""
        if not self._app:
            return

        try:
            from dazzle_back.runtime.integration_executor import IntegrationExecutor

            has_actions = False
            for integration in self._appspec.integrations:
                if getattr(integration, "actions", []):
                    has_actions = True
                    break

            if not has_actions:
                return

            self.integration_executor = IntegrationExecutor(
                app_spec=self._appspec,
                fragment_sources=self._fragment_sources,
            )

            import logging

            logging.getLogger("dazzle.server").info("Integration executor initialized")

        except ImportError as e:
            import logging

            logging.getLogger("dazzle.server").debug("Integration executor not available: %s", e)

        except Exception as e:
            import logging

            logging.getLogger("dazzle.server").warning("Failed to init integration executor: %s", e)


class WorkspaceRouteBuilder:
    """Registers workspace region and entity redirect routes for DazzleBackendApp."""

    def __init__(
        self,
        *,
        app: FastAPI,
        appspec: AppSpec,
        entities: list[Any],
        repositories: dict[str, Any],
        auth_middleware: AuthMiddleware | None,
        enable_auth: bool,
        enable_test_mode: bool,
        entity_auto_includes: dict[str, list[str]] | None = None,
    ) -> None:
        self._app = app
        self._appspec = appspec
        self._entities = entities
        self._repositories = repositories
        self._auth_middleware = auth_middleware
        self._enable_auth = enable_auth
        self._enable_test_mode = enable_test_mode
        self._entity_auto_includes = entity_auto_includes or {}

    def init_workspace_routes(self) -> None:
        """Initialize workspace layout routes (v0.20.0)."""
        if not self._app:
            return

        workspaces = self._appspec.workspaces
        if not workspaces:
            import logging

            logging.getLogger("dazzle.server").debug(
                "No workspaces in spec — skipping workspace routes"
            )
            return

        try:
            from dazzle_ui.runtime.workspace_renderer import build_workspace_context

            app = self._app
            appspec = self._appspec
            entities = self._entities
            repositories = self._repositories
            auth_middleware = self._auth_middleware
            entity_auto_includes = self._entity_auto_includes

            require_auth = self._enable_auth and not self._enable_test_mode

            # Build entity → list surface lookup for column projection (#357, #359)
            _entity_list_surfaces: dict[str, Any] = {}
            for _surf in appspec.surfaces:
                _eref = _surf.entity_ref
                _mode = str(_surf.mode or "").lower()
                if _eref and _mode == "list" and _eref not in _entity_list_surfaces:
                    _entity_list_surfaces[_eref] = _surf

            def _columns_for_entity(entity_spec: Any, entity_name: str) -> list[dict[str, Any]]:
                """Build columns using list surface projection if available."""
                _ls = _entity_list_surfaces.get(entity_name)
                if _ls and entity_spec:
                    return _build_surface_columns(entity_spec, _ls)
                return _build_entity_columns(entity_spec)

            for workspace in workspaces:
                ws_ctx = build_workspace_context(workspace, appspec)
                ws_name = workspace.name

                _ws_access = workspace.access
                _ws_region_ctxs: list[WorkspaceRegionContext] = []

                for ir_region, ctx_region in zip(workspace.regions, ws_ctx.regions, strict=False):
                    # Multi-source regions: register per-source sub-endpoints
                    if ctx_region.sources:
                        source_filters_ir = dict(getattr(ir_region, "source_filters", {}) or {})
                        for src_tab in ctx_region.source_tabs:
                            _src_name = src_tab.entity_name
                            _src_entity_spec = None
                            for _e in entities:
                                if _e.name == _src_name:
                                    _src_entity_spec = _e
                                    break

                            # Build a synthetic single-source IR region for this tab
                            _src_filter = source_filters_ir.get(
                                _src_name, getattr(ir_region, "filter", None)
                            )

                            # Per-source tab uses tab_data.html (not tabbed_list.html)
                            # to avoid infinite HTMX loop (#328)
                            _tab_endpoint = (
                                f"/api/workspaces/{ws_name}/regions/{ctx_region.name}/{_src_name}"
                            )
                            _src_ctx_region = ctx_region.model_copy(
                                update={
                                    "template": "workspace/regions/tab_data.html",
                                    "endpoint": _tab_endpoint,
                                    "source_tabs": [],
                                }
                            )
                            _src_region_ctx = WorkspaceRegionContext(
                                ctx_region=_src_ctx_region,
                                ir_region=ir_region,
                                source=_src_name,
                                entity_spec=_src_entity_spec,
                                attention_signals=[],
                                ws_access=_ws_access,
                                repositories=repositories,
                                require_auth=require_auth,
                                auth_middleware=auth_middleware,
                                precomputed_columns=_columns_for_entity(
                                    _src_entity_spec, _src_name
                                ),
                                auto_include=entity_auto_includes.get(_src_name, []),
                            )
                            # Override the IR filter for this source
                            _src_region_ctx._source_filter = _src_filter  # type: ignore[attr-defined]
                            _ws_region_ctxs.append(_src_region_ctx)

                            def _make_src_route(
                                rctx: WorkspaceRegionContext,
                                src_filter: Any = _src_filter,
                            ) -> Any:
                                async def workspace_src_data(
                                    request: Request,
                                    page: int = 1,
                                    page_size: int = 20,
                                    sort: str | None = None,
                                    dir: str = "asc",
                                ) -> Any:
                                    return await _workspace_region_handler(
                                        request,
                                        page,
                                        page_size,
                                        sort,
                                        dir,
                                        ctx=rctx,
                                    )

                                return workspace_src_data

                            app.get(
                                f"/api/workspaces/{ws_name}/regions/{ctx_region.name}/{_src_name}",
                                tags=["Workspaces"],
                            )(_make_src_route(_src_region_ctx))
                        continue

                    if not ctx_region.source:
                        continue

                    _ir_region = ir_region
                    _ctx_region = ctx_region
                    _source = ctx_region.source

                    _entity_spec = None
                    for _e in entities:
                        if _e.name == _source:
                            _entity_spec = _e
                            break

                    _attention_signals: list[Any] = []
                    _surface_default_sort: list[Any] = []
                    _surface_empty_message = ""
                    for _surf in appspec.surfaces:
                        if _surf.entity_ref == _source:
                            ux = getattr(_surf, "ux", None)
                            if ux:
                                if getattr(ux, "attention_signals", None):
                                    _attention_signals = list(ux.attention_signals)
                                if getattr(ux, "sort", None):
                                    _surface_default_sort = list(ux.sort)
                                if getattr(ux, "empty_message", None):
                                    _surface_empty_message = ux.empty_message

                    _columns = _columns_for_entity(_entity_spec, _source)

                    _region_ctx = WorkspaceRegionContext(
                        ctx_region=ctx_region,
                        ir_region=ir_region,
                        source=_source,
                        entity_spec=_entity_spec,
                        attention_signals=_attention_signals,
                        ws_access=_ws_access,
                        repositories=repositories,
                        require_auth=require_auth,
                        auth_middleware=auth_middleware,
                        precomputed_columns=_columns,
                        auto_include=entity_auto_includes.get(_source, []),
                        surface_default_sort=_surface_default_sort,
                        surface_empty_message=_surface_empty_message,
                    )
                    _ws_region_ctxs.append(_region_ctx)

                    # Use a factory to bind each region context via closure
                    # instead of a default parameter — FastAPI deepcopies
                    # defaults, which fails on non-picklable PGconn objects (#290).
                    def _make_region_route(rctx: WorkspaceRegionContext) -> Any:
                        async def workspace_region_data(
                            request: Request,
                            page: int = 1,
                            page_size: int = 20,
                            sort: str | None = None,
                            dir: str = "asc",
                        ) -> Any:
                            return await _workspace_region_handler(
                                request,
                                page,
                                page_size,
                                sort,
                                dir,
                                ctx=rctx,
                            )

                        return workspace_region_data

                    app.get(
                        f"/api/workspaces/{ws_name}/regions/{ctx_region.name}",
                        tags=["Workspaces"],
                    )(_make_region_route(_region_ctx))

                # Batch endpoint: collect all region contexts (already built above)
                _batch_ctxs = list(_ws_region_ctxs)

                def _make_batch_route(
                    ctxs: list[WorkspaceRegionContext],
                ) -> Any:
                    async def workspace_batch(
                        request: Request,
                        page: int = 1,
                        page_size: int = 20,
                    ) -> Any:
                        return await _workspace_batch_handler(request, page, page_size, ctxs)

                    return workspace_batch

                app.get(
                    f"/api/workspaces/{ws_name}/batch",
                    tags=["Workspaces"],
                )(_make_batch_route(_batch_ctxs))

                # Context selector options endpoint (v0.38.0)
                _ctx_sel = workspace.context_selector
                if _ctx_sel and repositories.get(_ctx_sel.entity):
                    _sel_repo = repositories[_ctx_sel.entity]
                    _sel_display = _ctx_sel.display_field

                    def _make_context_options_route(
                        sel_repo: Any,
                        display: str,
                    ) -> Any:
                        async def context_options(request: Request) -> Any:
                            from fastapi.responses import JSONResponse

                            result = await sel_repo.list(page=1, page_size=500)
                            items = result.get("items", []) if isinstance(result, dict) else result
                            options = []
                            for row in items:
                                r = row if isinstance(row, dict) else row.model_dump()
                                options.append(
                                    {
                                        "id": str(r.get("id", "")),
                                        "label": str(r.get(display, r.get("name", ""))),
                                    }
                                )
                            return JSONResponse(content={"options": options})

                        return context_options

                    app.get(
                        f"/api/workspaces/{ws_name}/context-options",
                        tags=["Workspaces"],
                    )(_make_context_options_route(_sel_repo, _sel_display))

                self._init_workspace_entity_routes(workspaces, app)

            import logging

            logging.getLogger("dazzle.server").info(
                "Workspace routes initialized for %s workspace(s)",
                len(workspaces),
            )

        except ImportError as e:
            import logging

            logging.getLogger("dazzle.server").debug("Workspace renderer not available: %s", e)

        except Exception:
            import logging

            logging.getLogger("dazzle.server").error(
                "Failed to init workspace routes",
                exc_info=True,
            )

    def _init_workspace_entity_routes(self, workspaces: list[Any], app: Any) -> None:
        """Register workspace-prefixed entity routes (v0.20.1)."""
        from starlette.responses import RedirectResponse

        from dazzle.core.strings import to_api_plural

        seen: set[str] = set()

        for workspace in workspaces:
            ws_name = workspace.name
            for region in workspace.regions:
                source: str | None = region.source
                if not source:
                    continue

                entity_plural = to_api_plural(source)
                route_key = f"{ws_name}/{entity_plural}"
                if route_key in seen:
                    continue
                seen.add(route_key)

                _entity_plural = entity_plural

                @app.api_route(  # type: ignore[misc, untyped-decorator, unused-ignore]
                    f"/{ws_name}/{entity_plural}",
                    methods=["GET", "POST"],
                    tags=["Workspaces"],
                    include_in_schema=False,
                )
                async def ws_entity_collection(
                    request: Request,
                    _ep: str = _entity_plural,
                ) -> RedirectResponse:
                    qs = str(request.query_params)
                    target = f"/{_ep}?{qs}" if qs else f"/{_ep}"
                    return RedirectResponse(url=target, status_code=307)

                @app.api_route(  # type: ignore[misc, untyped-decorator, unused-ignore]
                    f"/{ws_name}/{entity_plural}/{{id}}",
                    methods=["GET", "PUT", "PATCH", "DELETE"],
                    tags=["Workspaces"],
                    include_in_schema=False,
                )
                async def ws_entity_item(
                    request: Request,
                    id: str,
                    _ep: str = _entity_plural,
                ) -> RedirectResponse:
                    qs = str(request.query_params)
                    target = f"/{_ep}/{id}?{qs}" if qs else f"/{_ep}/{id}"
                    return RedirectResponse(url=target, status_code=307)


# =============================================================================
# Server Configuration
# =============================================================================


@dataclass
class ServerConfig:
    """
    Configuration for DazzleBackendApp.

    Groups all initialization options into a single object for cleaner APIs.
    """

    # Database settings
    database_url: str | None = None  # PostgreSQL URL (e.g. postgresql://user:pass@host/db)

    # Authentication settings
    enable_auth: bool = False
    auth_config: Any = None  # AuthConfig from manifest (for OAuth providers)

    # File upload settings
    enable_files: bool = False
    files_path: Path = field(default_factory=lambda: Path(".dazzle/uploads"))

    # Development/testing settings
    enable_test_mode: bool = False
    services_dir: Path = field(default_factory=lambda: Path("services"))

    # Dev control plane
    enable_dev_mode: bool = False
    personas: list[dict[str, Any]] = field(default_factory=list)
    scenarios: list[dict[str, Any]] = field(default_factory=list)

    # Messaging channels (v0.9)
    enable_channels: bool = True  # Auto-enabled if channels defined in spec

    # Security (v0.11.0)
    security_profile: str = "basic"  # basic | standard | strict
    cors_origins: list[str] | None = None  # Custom CORS origins

    # SiteSpec (v0.16.0) - Public site shell
    sitespec_data: dict[str, Any] | None = None  # SiteSpec as dict
    project_root: Path | None = None  # For content file loading

    # Process/workflow support (v0.24.0)
    enable_processes: bool = True  # Enable process workflow execution
    process_adapter_class: type | None = None  # Custom ProcessAdapter class
    process_specs: list[Any] = field(default_factory=list)  # ProcessSpec list from AppSpec
    schedule_specs: list[Any] = field(default_factory=list)  # ScheduleSpec list from AppSpec
    entity_status_fields: dict[str, str] = field(default_factory=dict)  # entity_name → status field

    # Tenant isolation (v0.43.0)
    tenant_config: Any = None  # TenantConfig from manifest

    # Fragment sources from DSL source= annotations (v0.25.1)
    fragment_sources: dict[str, dict[str, Any]] = field(default_factory=dict)

    # Founder Console (v0.26.0)
    enable_console: bool = True  # Enable /_console/ founder control plane

    # View-based list projections (v0.26.0) — entity_name -> [field_names]
    entity_list_projections: dict[str, list[str]] = field(default_factory=dict)
    # Surface search fields (v0.34.2) — entity_name -> [field_names]
    entity_search_fields: dict[str, list[str]] = field(default_factory=dict)
    # Auto-eager-load ref relations (v0.26.0) — entity_name -> [relation_names]
    entity_auto_includes: dict[str, list[str]] = field(default_factory=dict)


# =============================================================================
# Application Builder
# =============================================================================


class DazzleBackendApp:
    """
    Dazzle Backend Application.

    Creates a complete FastAPI application from an AppSpec.
    """

    def __init__(
        self,
        appspec: AppSpec,
        config: ServerConfig | None = None,
        *,
        database_url: str | None = None,
        enable_auth: bool | None = None,
        auth_config: Any = None,  # AuthConfig from manifest (for OAuth providers)
        enable_files: bool | None = None,
        files_path: str | Path | None = None,
        enable_test_mode: bool | None = None,
        services_dir: str | Path | None = None,
        # Dev control plane
        enable_dev_mode: bool | None = None,
        personas: list[dict[str, Any]] | None = None,
        scenarios: list[dict[str, Any]] | None = None,
        # SiteSpec (v0.16.0)
        sitespec_data: dict[str, Any] | None = None,
        project_root: str | Path | None = None,
    ):
        """
        Initialize the backend application.

        Args:
            appspec: Dazzle AppSpec (parsed IR)
            config: Server configuration object (preferred)
            database_url: PostgreSQL connection URL (or set DATABASE_URL env var)
            enable_auth: Whether to enable authentication (default: False)
            enable_files: Whether to enable file uploads (default: False)
            files_path: Path for file storage (default: .dazzle/uploads)
            enable_test_mode: Whether to enable /__test__/* endpoints (default: False)
            services_dir: Path to domain service stubs directory (default: services/)
            enable_dev_mode: Enable dev control plane (default: False)
            personas: List of persona configurations for dev mode
            scenarios: List of scenario configurations for dev mode
            sitespec_data: SiteSpec as dict for public site shell (v0.16.0)
            project_root: Project root for content file loading (v0.16.0)
        """
        if not FASTAPI_AVAILABLE:
            raise RuntimeError(
                "FastAPI is not installed. Install with: pip install fastapi uvicorn"
            )

        # Use config if provided, otherwise build from legacy parameters
        if config is None:
            config = ServerConfig()

        import os

        # Convert AppSpec to runtime-ready specs
        from dazzle_back.converters.entity_converter import convert_entities
        from dazzle_back.converters.surface_converter import convert_surfaces_to_services

        self._appspec = appspec
        self._entities = convert_entities(appspec.domain.entities)
        self._service_specs, self._endpoint_specs = convert_surfaces_to_services(
            appspec.surfaces, appspec.domain
        )
        self._channels = _convert_channels(appspec.channels)
        self._database_url = database_url or config.database_url or os.environ.get("DATABASE_URL")
        self._enable_auth = enable_auth if enable_auth is not None else config.enable_auth
        self._auth_config = auth_config if auth_config is not None else config.auth_config
        self._enable_files = enable_files if enable_files is not None else config.enable_files
        self._files_path = Path(files_path) if files_path else config.files_path
        self._enable_test_mode = (
            enable_test_mode if enable_test_mode is not None else config.enable_test_mode
        )
        self._services_dir = Path(services_dir) if services_dir else config.services_dir
        # Dev control plane
        self._enable_dev_mode = (
            enable_dev_mode if enable_dev_mode is not None else config.enable_dev_mode
        )
        self._personas = personas if personas is not None else config.personas
        self._scenarios = scenarios if scenarios is not None else config.scenarios
        # SiteSpec (v0.16.0)
        self._sitespec_data = sitespec_data if sitespec_data is not None else config.sitespec_data
        self._project_root = Path(project_root) if project_root else config.project_root
        self._app: FastAPI | None = None
        self._models: dict[str, type[BaseModel]] = {}
        self._schemas: dict[str, dict[str, type[BaseModel]]] = {}
        self._services: dict[str, Any] = {}
        self._repositories: dict[str, Any] = {}
        self._db_manager: PostgresBackend | None = None
        self._auth_store: AuthStore | None = None
        self._auth_middleware: AuthMiddleware | None = None
        self._file_service: FileService | None = None
        self._last_migration: MigrationPlan | None = None
        self._start_time: datetime | None = None
        self._service_loader: ServiceLoader | None = None
        # Messaging channels (v0.9)
        self._enable_channels = config.enable_channels
        # Delegate instances (created lazily in _setup_optional_features)
        self._integration_mgr: IntegrationManager | None = None
        self._workspace_builder: WorkspaceRouteBuilder | None = None
        # Security (v0.11.0)
        self._security_profile = config.security_profile
        self._cors_origins = config.cors_origins
        # Event system (v0.18.0)
        self._event_framework: Any | None = None  # EventFramework type
        # NOTE: _sitespec_data and _project_root are already set above (lines 201-203)
        # with proper parameter precedence over config defaults
        # Process/workflow support (v0.24.0)
        self._enable_processes = config.enable_processes
        self._process_adapter_class = config.process_adapter_class  # Custom adapter class
        self._process_specs: list[Any] = config.process_specs  # ProcessSpec list from AppSpec
        self._schedule_specs: list[Any] = config.schedule_specs  # ScheduleSpec list from AppSpec
        self._entity_status_fields: dict[str, str] = config.entity_status_fields
        self._process_manager: Any | None = None  # ProcessManager type
        self._process_adapter: Any | None = None  # ProcessAdapter type
        self._sla_manager: Any | None = None  # SLAManager type
        # Tenant isolation (v0.43.0)
        self._tenant_config = config.tenant_config
        # Fragment sources from DSL source= annotations (v0.25.1)
        self._fragment_sources: dict[str, dict[str, Any]] = config.fragment_sources
        # Founder Console (v0.26.0)
        self._enable_console = config.enable_console
        # View-based list projections (v0.26.0)
        self._entity_list_projections: dict[str, list[str]] = config.entity_list_projections
        # Surface search fields (v0.34.2)
        self._entity_search_fields: dict[str, list[str]] = config.entity_search_fields
        # Auto-eager-load ref relations (v0.26.0)
        self._entity_auto_includes: dict[str, list[str]] = config.entity_auto_includes
        # Keep full config for subsystem context
        self._config: ServerConfig = config
        # Subsystem plugin infrastructure (v0.42.0)
        self._subsystem_ctx: Any | None = (
            None  # SubsystemContext, set in build() after _setup_optional_features
        )
        self._subsystems: list[Any] = self._build_default_subsystems()

    # ------------------------------------------------------------------
    # Subsystem plugin infrastructure
    # ------------------------------------------------------------------

    def _build_default_subsystems(self) -> list[Any]:
        """Create the ordered list of default subsystem plugins."""
        from dazzle_back.runtime.subsystems.auth import AuthSubsystem
        from dazzle_back.runtime.subsystems.channels import ChannelsSubsystem
        from dazzle_back.runtime.subsystems.console import ConsoleSubsystem
        from dazzle_back.runtime.subsystems.events import EventsSubsystem
        from dazzle_back.runtime.subsystems.llm_queue import LLMQueueSubsystem
        from dazzle_back.runtime.subsystems.process import ProcessSubsystem
        from dazzle_back.runtime.subsystems.seed import SeedSubsystem
        from dazzle_back.runtime.subsystems.sla import SLASubsystem
        from dazzle_back.runtime.subsystems.system_routes import SystemRoutesSubsystem

        return [
            AuthSubsystem(),
            EventsSubsystem(),
            ChannelsSubsystem(),
            ConsoleSubsystem(),
            ProcessSubsystem(),
            SLASubsystem(),
            LLMQueueSubsystem(),
            SeedSubsystem(),
            SystemRoutesSubsystem(),
        ]

    def _build_subsystem_context(self, auth_dep: Any = None, optional_auth_dep: Any = None) -> Any:
        """Build SubsystemContext from current DazzleBackendApp state."""
        from dazzle_back.runtime.subsystems import SubsystemContext

        assert self._app is not None
        return SubsystemContext(
            app=self._app,
            appspec=self._appspec,
            config=self._config,
            services=self._services,
            repositories=self._repositories,
            entities=self._entities,
            channels=self._channels,
            db_manager=self._db_manager,
            auth_middleware=self._auth_middleware,
            enable_auth=self._enable_auth,
            enable_test_mode=self._enable_test_mode,
            auth_store=self._auth_store,
            auth_dep=auth_dep,
            optional_auth_dep=optional_auth_dep,
            auth_config=self._auth_config,
            database_url=self._database_url or "",
            security_profile=self._security_profile,
            project_root=self._project_root,
            last_migration=self._last_migration,
            # Resolved instance vars (may differ from config when passed as constructor kwargs)
            sitespec_data=self._sitespec_data,
            enable_files=self._enable_files,
            files_path=self._files_path,
            services_dir=self._services_dir,
        )

    def _run_subsystems(self) -> None:
        """Call startup() on each registered subsystem plugin in order."""
        assert self._subsystem_ctx is not None
        for plugin in self._subsystems:
            try:
                plugin.startup(self._subsystem_ctx)
            except Exception as exc:  # pragma: no cover
                logging.getLogger("dazzle.server").warning(
                    "Subsystem '%s' startup failed: %s", getattr(plugin, "name", "?"), exc
                )
        # Sync mutable outputs back to DazzleBackendApp attributes so existing
        # properties (channel_manager, process_manager, etc.) still work.
        ctx = self._subsystem_ctx
        if ctx.event_framework is not None:
            self._event_framework = ctx.event_framework
        if ctx.process_manager is not None:
            self._process_manager = ctx.process_manager
        if ctx.process_adapter is not None:
            self._process_adapter = ctx.process_adapter
        if ctx.sla_manager is not None:
            self._sla_manager = ctx.sla_manager

    # ------------------------------------------------------------------
    # Build phases — called in order by build()
    # ------------------------------------------------------------------

    def _create_app(self) -> None:
        """Create the FastAPI app instance and apply middleware."""
        self._app = _FastAPI(
            title=self._appspec.name,
            description=self._appspec.title or f"Dazzle Backend: {self._appspec.name}",
            version=self._appspec.version,
        )

        # Security middleware (v0.11.0)
        from dazzle_back.runtime.security_middleware import apply_security_middleware

        apply_security_middleware(
            self._app,
            self._security_profile,
            cors_origins=self._cors_origins,
        )

        # Rate limiting (v1.0.0)
        from dazzle_back.runtime.rate_limit import apply_rate_limiting

        apply_rate_limiting(self._app, self._security_profile)

        # CSRF protection (v1.0.0)
        from dazzle_back.runtime.csrf import apply_csrf_protection

        apply_csrf_protection(self._app, self._security_profile)

        # GZip compression (v0.33.0) — must be added before other middleware
        from starlette.middleware.gzip import GZipMiddleware

        self._app.add_middleware(GZipMiddleware, minimum_size=500)

        # Metrics middleware (v0.27.0)
        try:
            from dazzle_back.runtime.metrics import add_metrics_middleware

            add_metrics_middleware(self._app)
        except ImportError:
            pass

        # Tenant isolation middleware (schema-per-tenant)
        tenant_config = self._tenant_config
        if tenant_config and tenant_config.isolation == "schema":
            from dazzle.tenant.registry import TenantRegistry
            from dazzle_back.runtime.tenant_middleware import (
                TenantMiddleware,
                build_resolver,
            )

            resolver = build_resolver(tenant_config)
            assert self._database_url is not None, "database_url required for tenant isolation"
            registry = TenantRegistry(self._database_url)
            registry.ensure_table()
            self._app.add_middleware(
                TenantMiddleware,
                resolver=resolver,
                registry=registry,
            )

        # Exception handlers (v0.28.0)
        from dazzle_back.runtime.exception_handlers import register_exception_handlers

        register_exception_handlers(self._app)

    def _setup_models(self) -> None:
        """Generate Pydantic models and create/update schemas from the spec."""
        self._models = generate_all_entity_models(self._entities)
        for entity in self._entities:
            self._schemas[entity.name] = {
                "create": generate_create_schema(entity),
                "update": generate_update_schema(entity),
            }

    def _setup_database(self) -> None:
        """Initialize database backend, run migrations, create repositories."""
        import os

        if not self._database_url:
            raise ValueError(
                "database_url is required. Set DATABASE_URL environment variable "
                "or pass database_url to ServerConfig/DazzleBackendApp."
            )

        from dazzle_back.runtime.pg_backend import PostgresBackend

        self._db_manager = PostgresBackend(self._database_url)
        self._last_migration = auto_migrate(
            self._db_manager,
            self._entities,
            record_history=True,
        )

        # Open connection pool and register lifecycle events (#438)
        pool_min = int(os.environ.get("DAZZLE_DB_POOL_MIN", "2"))
        pool_max = int(os.environ.get("DAZZLE_DB_POOL_MAX", "10"))
        db_manager = self._db_manager

        assert self._app is not None
        app = self._app

        @app.on_event("startup")
        async def _open_db_pool() -> None:
            db_manager.open_pool(min_size=pool_min, max_size=pool_max)

        @app.on_event("shutdown")
        async def _close_db_pool() -> None:
            db_manager.close_pool()

        # Build relation loader for nested ref resolution (#272)
        from dazzle_back.runtime.relation_loader import RelationLoader, RelationRegistry

        relation_registry = RelationRegistry.from_entities(self._entities)
        relation_loader = RelationLoader(
            registry=relation_registry,
            entities=self._entities,
            conn_factory=self._db_manager.get_persistent_connection,
        )

        repo_factory = RepositoryFactory(
            self._db_manager,
            self._models,
            relation_loader=relation_loader,
        )
        self._repositories = repo_factory.create_all_repositories(self._entities)

    def _setup_services(self) -> None:
        """Create CRUD services and wire them to repositories."""
        state_machines = {
            entity.name: entity.state_machine for entity in self._entities if entity.state_machine
        }
        entity_specs = {entity.name: entity for entity in self._entities}

        factory = ServiceFactory(self._models, state_machines, entity_specs)
        self._services = factory.create_all_services(
            self._service_specs,
            self._schemas,
        )

        if self._db_manager:
            for _service_name, service in self._services.items():
                if isinstance(service, CRUDService):
                    entity_name = service.entity_name
                    repo = self._repositories.get(entity_name)
                    if repo:
                        service.set_repository(repo)

        # Wire project-level service hooks (v0.29.0)
        self._wire_service_hooks()

    def _wire_service_hooks(self) -> None:
        """Discover and register project-level service hooks."""
        if not self._project_root:
            return
        hooks_dir = self._project_root / "hooks"
        if not hooks_dir.is_dir():
            return

        try:
            from dazzle_back.runtime.hook_registry import build_registry
        except ImportError:
            return

        registry = build_registry(hooks_dir)
        if registry.count == 0:
            return

        logger.info("Registered %d service hook(s): %s", registry.count, registry.summary())

        # Wire hooks to CRUD services
        for _service_name, service in self._services.items():
            if not isinstance(service, CRUDService):
                continue
            entity_name = service.entity_name

            for h in registry.get_hooks("entity.pre_create", entity_name):
                service.add_pre_create_hook(h.function)
            for h in registry.get_hooks("entity.pre_update", entity_name):
                service.add_pre_update_hook(h.function)
            for h in registry.get_hooks("entity.pre_delete", entity_name):
                service.add_pre_delete_hook(h.function)
            for h in registry.get_hooks("entity.post_create", entity_name):
                service.on_created(h.function)
            for h in registry.get_hooks("entity.post_update", entity_name):
                service.on_updated(h.function)
            for h in registry.get_hooks("entity.post_delete", entity_name):
                service.on_deleted(h.function)

        # Wire post_upload hooks to file upload callbacks (v0.39.0, #437)
        if hasattr(self, "_upload_callbacks"):
            for _service_name, service in self._services.items():
                if not isinstance(service, CRUDService):
                    continue
                _ename = service.entity_name
                for h in registry.get_hooks("entity.post_upload", _ename):
                    _hook_fn = h.function

                    async def _upload_hook(
                        entity_name: str,
                        entity_id: str,
                        field_name: str,
                        file_meta: dict[str, Any],
                        fn: Any = _hook_fn,
                    ) -> None:
                        await fn(entity_name, entity_id, file_meta)

                    self._upload_callbacks.append(_upload_hook)

    def _setup_auth(self) -> tuple[Any, Any]:
        """Initialize auth store, middleware, and social auth.

        Returns (auth_dep, optional_auth_dep) for route generation.
        """
        auth_dep = None
        optional_auth_dep = None
        if not self._enable_auth:
            return auth_dep, optional_auth_dep

        assert self._database_url is not None  # guaranteed by _setup_database()
        # Pass the DSL user entity name so auth can load domain attributes
        # (e.g. school, department) into preferences for scope rules (#532).
        _user_entity = (
            getattr(self._auth_config, "user_entity", "User") if self._auth_config else "User"
        )
        self._auth_store = AuthStore(
            database_url=self._database_url,
            user_entity_table=_user_entity,
        )
        self._auth_middleware = AuthMiddleware(self._auth_store)

        from dazzle_back.runtime.auth import (
            create_auth_dependency,
            create_optional_auth_dependency,
        )

        auth_dep = create_auth_dependency(self._auth_store)
        optional_auth_dep = create_optional_auth_dependency(self._auth_store)

        return auth_dep, optional_auth_dep

    def _setup_routes(self, auth_dep: Any, optional_auth_dep: Any) -> None:
        """Generate entity CRUD routes, audit routes, file routes, and dev routes."""
        assert self._app is not None

        # Extract access specs
        entity_access_specs: dict[str, dict[str, Any]] = {}
        for entity in self._entities:
            if entity.metadata and "access" in entity.metadata:
                entity_access_specs[entity.name] = entity.metadata["access"]

        cedar_access_specs: dict[str, Any] = {}
        for entity in self._entities:
            if entity.access:
                cedar_access_specs[entity.name] = entity.access

        # Audit logger
        audit_logger = None
        _has_auditable_entities = any(
            (entity.metadata and "access" in entity.metadata)
            or getattr(entity, "audit", None)
            or entity.access
            for entity in self._entities
        )
        if _has_auditable_entities and self._database_url:
            from dazzle_back.runtime.audit_log import AuditLogger

            audit_logger = AuditLogger(database_url=self._database_url)
            audit_logger.start()

        # Project route overrides — registered first for priority (v0.29.0)
        if self._project_root:
            try:
                from dazzle_back.runtime.route_overrides import build_override_router

                override_router = build_override_router(self._project_root / "routes")
                if override_router is not None:
                    self._app.include_router(override_router)
            except Exception:
                logger.debug("Route override discovery skipped", exc_info=True)

        # Entity CRUD routes
        service_specs = {svc.name: svc for svc in self._service_specs}

        # Pre-compute HTMX metadata per entity so list API endpoints can
        # render table row fragments with correct column definitions.
        # Use surface field projection when a list surface exists (#405).
        _entity_list_surfaces: dict[str, Any] = {}
        for _surf in self._appspec.surfaces:
            _eref = _surf.entity_ref
            _mode = str(_surf.mode or "").lower()
            if _eref and _mode == "list" and _eref not in _entity_list_surfaces:
                _entity_list_surfaces[_eref] = _surf

        entity_htmx_meta: dict[str, dict[str, Any]] = {}
        app_prefix = "/app"
        for entity in self._entities:
            entity_slug = entity.name.lower().replace("_", "-")
            _ls = _entity_list_surfaces.get(entity.name)
            cols = _build_surface_columns(entity, _ls) if _ls else _build_entity_columns(entity)
            entity_htmx_meta[entity.name] = {
                "columns": cols,
                "detail_url": f"{app_prefix}/{entity_slug}/{{id}}",
                "entity_name": entity.name,
            }

        # Build per-entity audit config mapping.
        # When audit_trail is True (app-level switch), all entities get audit
        # logging by default. Entities can still opt out with audit: false.
        entity_audit_configs: dict[str, Any] = {}
        _global_audit = self._appspec.audit_trail
        for entity in self._entities:
            _ac = getattr(entity, "audit", None)
            if _ac is not None:
                entity_audit_configs[entity.name] = _ac
            elif _global_audit:
                # Default to audit: all when audit_trail is globally enabled
                from dazzle.core.ir.domain import AuditConfig

                entity_audit_configs[entity.name] = AuditConfig(enabled=True)

        route_generator = RouteGenerator(
            services=self._services,
            models=self._models,
            schemas=self._schemas,
            entity_access_specs=entity_access_specs,
            auth_dep=auth_dep,
            optional_auth_dep=optional_auth_dep,
            require_auth_by_default=self._enable_auth and not self._enable_test_mode,
            auth_store=self._auth_store,
            audit_logger=audit_logger,
            cedar_access_specs=cedar_access_specs,
            entity_list_projections=self._entity_list_projections,
            entity_search_fields=self._entity_search_fields,
            entity_auto_includes=self._entity_auto_includes,
            entity_htmx_meta=entity_htmx_meta,
            entity_audit_configs=entity_audit_configs,
        )
        router = route_generator.generate_all_routes(
            self._endpoint_specs,
            service_specs,
        )
        self._app.include_router(router)

        # Audit query routes
        if audit_logger:
            from dazzle_back.runtime.audit_routes import create_audit_routes

            audit_router = create_audit_routes(
                audit_logger=audit_logger,
                auth_dep=auth_dep,
            )
            self._app.include_router(audit_router)

        # File uploads
        if self._enable_files:
            from dazzle_back.runtime.file_storage import (
                FileMetadataStore,
                FileValidator,
                LocalStorageBackend,
            )

            storage = LocalStorageBackend(self._files_path, "/files")
            metadata_store = FileMetadataStore(database_url=self._database_url)
            validator = FileValidator()
            self._file_service = FileService(storage, metadata_store, validator)

            # Profile-based upload size limits (v1.0.0)
            _upload_limits = {"basic": 50, "standard": 10, "strict": 5}
            _max_mb = _upload_limits.get(self._security_profile, 10)

            # Per-entity/field size overrides from DSL (v0.39.0, #436)
            _field_size_overrides: dict[tuple[str, str], int] = {}
            if self._appspec:
                from dazzle.core.ir.fields import FieldTypeKind

                for _ent in self._appspec.domain.entities:
                    for _f in _ent.fields:
                        if _f.type.kind == FieldTypeKind.FILE and _f.type.max_size:
                            _field_size_overrides[(_ent.name, _f.name)] = _f.type.max_size

            # Post-upload callbacks: event bus + hook registry (v0.39.0, #437)
            # Stored on self so hook registry wiring can append later.
            self._upload_callbacks: list[Any] = []
            _upload_callbacks = self._upload_callbacks

            from dazzle_back.runtime.event_bus import get_event_bus

            _upload_bus = get_event_bus()

            async def _on_file_uploaded(
                entity_name: str,
                entity_id: str,
                field_name: str,
                file_meta: dict[str, Any],
                bus: Any = _upload_bus,
            ) -> None:
                data = {"field_name": field_name, **file_meta}
                await bus.emit_file_uploaded(entity_name, entity_id, data)

            _upload_callbacks.append(_on_file_uploaded)

            create_file_routes(
                self._app,
                self._file_service,
                max_upload_size=_max_mb * 1024 * 1024,
                field_size_overrides=_field_size_overrides,
                on_upload_callbacks=_upload_callbacks,
            )
            create_static_file_routes(
                self._app,
                base_path=str(self._files_path),
                url_prefix="/files",
            )

        # Test routes
        if self._enable_test_mode and self._db_manager:
            from dazzle_back.runtime.test_routes import create_test_routes

            test_router = create_test_routes(
                db_manager=self._db_manager,
                repositories=self._repositories,
                entities=self._entities,
                auth_store=self._auth_store,
                personas=self._personas,
            )
            self._app.include_router(test_router)

        # Dev control plane
        if self._enable_dev_mode or self._enable_test_mode:
            from dazzle_back.runtime.control_plane import create_control_plane_routes

            control_plane_router = create_control_plane_routes(
                db_manager=self._db_manager,
                repositories=self._repositories if self._db_manager else None,
                entities=self._entities,
                personas=self._personas,
                scenarios=self._scenarios,
                auth_store=self._auth_store,
            )
            self._app.include_router(control_plane_router)

    # ------------------------------------------------------------------
    # Public build orchestrator
    # ------------------------------------------------------------------

    def build(self) -> FastAPI:
        """
        Build the FastAPI application.

        Returns:
            FastAPI application instance
        """
        self._create_app()
        self._setup_models()
        self._setup_database()
        self._setup_services()
        auth_dep, optional_auth_dep = self._setup_auth()
        self._setup_routes(auth_dep, optional_auth_dep)
        # Build subsystem context with auth deps, then run subsystems.
        # SystemRoutesSubsystem (last) handles _setup_optional_features and
        # _setup_system_routes.
        self._subsystem_ctx = self._build_subsystem_context(auth_dep, optional_auth_dep)
        self._run_subsystems()
        # Sync integration_mgr and workspace_builder back from subsystem context
        if self._subsystem_ctx.integration_mgr is not None:
            self._integration_mgr = self._subsystem_ctx.integration_mgr
        if self._subsystem_ctx.workspace_builder is not None:
            self._workspace_builder = self._subsystem_ctx.workspace_builder
        # Sync channel_manager back so IntegrationManager-based properties work
        if self._subsystem_ctx.channel_manager is not None:
            if self._integration_mgr is not None:
                self._integration_mgr.channel_manager = self._subsystem_ctx.channel_manager

        # Validate routes for conflicts
        from dazzle_back.runtime.route_validator import validate_routes

        assert self._app is not None
        validate_routes(self._app)

        return self._app

    @property
    def app(self) -> FastAPI | None:
        """Get the FastAPI application (None if not built)."""
        return self._app

    @property
    def models(self) -> dict[str, type[BaseModel]]:
        """Get generated Pydantic models."""
        return self._models

    @property
    def services(self) -> dict[str, Any]:
        """Get service instances."""
        return self._services

    def get_service(self, name: str) -> Any | None:
        """Get a service by name."""
        return self._services.get(name)

    @property
    def auth_store(self) -> AuthStore | None:
        """Get the auth store (None if auth not enabled)."""
        return self._auth_store

    @property
    def auth_middleware(self) -> AuthMiddleware | None:
        """Get the auth middleware (None if auth not enabled)."""
        return self._auth_middleware

    @property
    def auth_enabled(self) -> bool:
        """Check if authentication is enabled."""
        return self._enable_auth

    @property
    def file_service(self) -> FileService | None:
        """Get the file service (None if files not enabled)."""
        return self._file_service

    @property
    def files_enabled(self) -> bool:
        """Check if file uploads are enabled."""
        return self._enable_files

    @property
    def test_mode_enabled(self) -> bool:
        """Check if test mode is enabled."""
        return self._enable_test_mode

    @property
    def dev_mode_enabled(self) -> bool:
        """Check if dev mode is enabled."""
        return self._enable_dev_mode

    @property
    def repositories(self) -> dict[str, Any]:
        """Get repository instances."""
        return self._repositories

    @property
    def service_loader(self) -> ServiceLoader | None:
        """Get the domain service loader (None if not initialized)."""
        return self._service_loader

    @property
    def channel_manager(self) -> Any | None:
        """Get the channel manager (None if channels not enabled)."""
        return self._integration_mgr.channel_manager if self._integration_mgr else None

    @property
    def channels_enabled(self) -> bool:
        """Check if messaging channels are enabled."""
        return self._enable_channels and self.channel_manager is not None

    @property
    def process_manager(self) -> Any | None:
        """Get the process manager (None if processes not enabled)."""
        return self._process_manager

    @property
    def process_adapter(self) -> Any | None:
        """Get the process adapter (None if processes not enabled)."""
        return self._process_adapter

    @property
    def processes_enabled(self) -> bool:
        """Check if process workflows are enabled."""
        return self._enable_processes and self._process_manager is not None


# =============================================================================
# Re-exports (moved to app_factory.py)
# =============================================================================

from dazzle_back.runtime.app_factory import (  # noqa: E402, F401
    assemble_post_build_routes,
    build_entity_list_projections,
    build_entity_search_fields,
    build_server_config,
    create_app,
    create_app_factory,
    run_app,
)

__all__ = [
    "DazzleBackendApp",
    "ServerConfig",
    "assemble_post_build_routes",
    "build_entity_list_projections",
    "build_entity_search_fields",
    "build_server_config",
    "create_app",
    "create_app_factory",
    "run_app",
]
