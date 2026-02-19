"""
Runtime server - creates and runs a FastAPI application from BackendSpec.

This module provides the main entry point for running a Dazzle backend application.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from dazzle_back.runtime.auth import AuthMiddleware, AuthStore, create_auth_routes
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
    _compute_aggregate_metrics,
    _fetch_count_metric,
    _fetch_region_json,
    _field_kind_to_col_type,
    _parse_simple_where,
    _workspace_batch_handler,
    _workspace_region_handler,
)
from dazzle_back.specs import BackendSpec

# FastAPI is optional - use TYPE_CHECKING for type hints
if TYPE_CHECKING:
    from fastapi import FastAPI

    from dazzle_back.runtime.pg_backend import PostgresBackend

logger = logging.getLogger(__name__)

# =============================================================================
# Extracted delegate classes
# =============================================================================


class IntegrationManager:
    """Manages integration executor and messaging channels for DazzleBackendApp."""

    def __init__(
        self,
        *,
        app: FastAPI,
        spec: BackendSpec,
        db_manager: PostgresBackend | None,
        fragment_sources: dict[str, dict[str, Any]],
    ) -> None:
        self._app = app
        self._spec = spec
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
            for channel in self._spec.channels:
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
                build_id=f"{self._spec.name}-{self._spec.version}",
            )

            self._add_channel_routes()

        except ImportError:
            pass
        except Exception as e:
            import logging

            logging.getLogger("dazzle.server").warning(f"Failed to init channels: {e}")

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
                return {"error": f"Channel '{channel_name}' not found"}
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
                return {"error": str(e)}

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
            for integration in getattr(self._spec, "integrations", []):
                if getattr(integration, "actions", []):
                    has_actions = True
                    break

            if not has_actions:
                return

            self.integration_executor = IntegrationExecutor(
                app_spec=self._spec,
                fragment_sources=self._fragment_sources,
            )

            import logging

            logging.getLogger("dazzle.server").info("Integration executor initialized")

        except ImportError as e:
            import logging

            logging.getLogger("dazzle.server").debug(f"Integration executor not available: {e}")
        except Exception as e:
            import logging

            logging.getLogger("dazzle.server").warning(f"Failed to init integration executor: {e}")


class WorkspaceRouteBuilder:
    """Registers workspace region and entity redirect routes for DazzleBackendApp."""

    def __init__(
        self,
        *,
        app: FastAPI,
        spec: BackendSpec,
        repositories: dict[str, Any],
        auth_middleware: AuthMiddleware | None,
        enable_auth: bool,
        enable_test_mode: bool,
    ) -> None:
        self._app = app
        self._spec = spec
        self._repositories = repositories
        self._auth_middleware = auth_middleware
        self._enable_auth = enable_auth
        self._enable_test_mode = enable_test_mode

    def init_workspace_routes(self) -> None:
        """Initialize workspace layout routes (v0.20.0)."""
        if not self._app:
            return

        workspaces = getattr(self._spec, "workspaces", [])
        if not workspaces:
            import logging

            logging.getLogger("dazzle.server").debug(
                "No workspaces in spec — skipping workspace routes"
            )
            return

        try:
            from dazzle_ui.runtime.workspace_renderer import build_workspace_context

            app = self._app
            spec = self._spec
            repositories = self._repositories
            auth_middleware = self._auth_middleware

            require_auth = self._enable_auth and not self._enable_test_mode

            for workspace in workspaces:
                ws_ctx = build_workspace_context(workspace, spec)
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
                            _entities = getattr(spec, "entities", [])
                            for _e in _entities:
                                if _e.name == _src_name:
                                    _src_entity_spec = _e
                                    break

                            # Build a synthetic single-source IR region for this tab
                            _src_filter = source_filters_ir.get(
                                _src_name, getattr(ir_region, "filter", None)
                            )

                            _src_region_ctx = WorkspaceRegionContext(
                                ctx_region=ctx_region,
                                ir_region=ir_region,
                                source=_src_name,
                                entity_spec=_src_entity_spec,
                                attention_signals=[],
                                ws_access=_ws_access,
                                repositories=repositories,
                                require_auth=require_auth,
                                auth_middleware=auth_middleware,
                                precomputed_columns=_build_entity_columns(_src_entity_spec),
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
                    _entities = getattr(spec, "entities", [])
                    for _e in _entities:
                        if _e.name == _source:
                            _entity_spec = _e
                            break

                    _attention_signals: list[Any] = []
                    if spec and hasattr(spec, "surfaces"):
                        for _surf in spec.surfaces:
                            if getattr(_surf, "entity_ref", None) == _source:
                                ux = getattr(_surf, "ux", None)
                                if ux and getattr(ux, "attention_signals", None):
                                    _attention_signals = list(ux.attention_signals)
                                    break

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
                        precomputed_columns=_build_entity_columns(_entity_spec),
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

                self._init_workspace_entity_routes(workspaces, app)

            import logging

            logging.getLogger("dazzle.server").info(
                f"Workspace routes initialized for {len(workspaces)} workspace(s)"
            )

        except ImportError as e:
            import logging

            logging.getLogger("dazzle.server").debug(f"Workspace renderer not available: {e}")
        except Exception as e:
            import logging
            import traceback

            logging.getLogger("dazzle.server").error(
                f"Failed to init workspace routes: {e}\n{traceback.format_exc()}"
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
    process_adapter_class: type | None = None  # Custom ProcessAdapter (default: LiteProcessAdapter)
    process_specs: list[Any] = field(default_factory=list)  # ProcessSpec list from AppSpec
    schedule_specs: list[Any] = field(default_factory=list)  # ScheduleSpec list from AppSpec
    entity_status_fields: dict[str, str] = field(default_factory=dict)  # entity_name → status field

    # Fragment sources from DSL source= annotations (v0.25.1)
    fragment_sources: dict[str, dict[str, Any]] = field(default_factory=dict)

    # Founder Console (v0.26.0)
    enable_console: bool = True  # Enable /_console/ founder control plane

    # View-based list projections (v0.26.0) — entity_name -> [field_names]
    entity_list_projections: dict[str, list[str]] = field(default_factory=dict)
    # Auto-eager-load ref relations (v0.26.0) — entity_name -> [relation_names]
    entity_auto_includes: dict[str, list[str]] = field(default_factory=dict)


# Runtime import
try:
    from fastapi import FastAPI as _FastAPI
    from fastapi import Request
    from fastapi.middleware.cors import CORSMiddleware

    from dazzle_back.runtime.route_generator import RouteGenerator

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    _FastAPI = None  # type: ignore
    CORSMiddleware = None  # type: ignore
    RouteGenerator = None  # type: ignore
    Request = None  # type: ignore


# =============================================================================
# Application Builder
# =============================================================================


class DazzleBackendApp:
    """
    Dazzle Backend Application.

    Creates a complete FastAPI application from a BackendSpec.
    """

    def __init__(
        self,
        spec: BackendSpec,
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
            spec: Backend specification
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

        # Override config with any explicit parameters
        self.spec = spec
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
        # Social auth (OAuth2)
        self._jwt_service: Any | None = None  # JWTService type
        self._token_store: Any | None = None  # TokenStore type
        self._social_auth_service: Any | None = None  # SocialAuthService type
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
        # Fragment sources from DSL source= annotations (v0.25.1)
        self._fragment_sources: dict[str, dict[str, Any]] = config.fragment_sources
        # Founder Console (v0.26.0)
        self._enable_console = config.enable_console
        # View-based list projections (v0.26.0)
        self._entity_list_projections: dict[str, list[str]] = config.entity_list_projections
        # Auto-eager-load ref relations (v0.26.0)
        self._entity_auto_includes: dict[str, list[str]] = config.entity_auto_includes

    def _init_channel_manager(self) -> None:
        """Initialize the channel manager for messaging (delegates to IntegrationManager)."""
        if self._integration_mgr:
            self._integration_mgr.init_channel_manager()

    def _add_channel_routes(self) -> None:
        """Add channel management routes (delegates to IntegrationManager)."""
        if self._integration_mgr:
            self._integration_mgr._add_channel_routes()

    def _init_social_auth(self) -> None:
        """Initialize social auth (OAuth2) if providers are configured."""
        if not self._auth_config or not self._app or not self._auth_store:
            return

        # Check if OAuth providers are configured
        oauth_providers = getattr(self._auth_config, "oauth_providers", None)
        if not oauth_providers:
            return

        import logging
        import os

        logger = logging.getLogger(__name__)

        try:
            from dazzle_back.runtime.jwt_auth import JWTConfig, JWTService
            from dazzle_back.runtime.social_auth import (
                SocialAuthService,
                create_social_auth_routes,
            )
            from dazzle_back.runtime.token_store import TokenStore
        except ImportError as e:
            logger.warning(f"Social auth dependencies not available: {e}")
            return

        # Get JWT config from auth_config
        jwt_cfg = getattr(self._auth_config, "jwt", None)
        access_minutes = getattr(jwt_cfg, "access_token_minutes", 15) if jwt_cfg else 15
        refresh_days = getattr(jwt_cfg, "refresh_token_days", 7) if jwt_cfg else 7

        # Create JWT service
        jwt_secret = os.getenv("JWT_SECRET")
        jwt_config_kwargs: dict[str, Any] = {
            "access_token_expire_minutes": access_minutes,
            "refresh_token_expire_days": refresh_days,
        }
        if jwt_secret:
            jwt_config_kwargs["secret_key"] = jwt_secret
        self._jwt_service = JWTService(JWTConfig(**jwt_config_kwargs))

        # Create token store (PostgreSQL-only)
        if not self._database_url:
            logger.warning("Social auth requires DATABASE_URL for token storage")
            return
        self._token_store = TokenStore(
            database_url=self._database_url,
            token_lifetime_days=refresh_days,
        )

        # Build social auth config from manifest + environment
        social_config = self._build_social_auth_config(oauth_providers)
        if not social_config:
            logger.info("No OAuth providers configured with valid credentials")
            return

        # Create social auth service
        self._social_auth_service = SocialAuthService(
            auth_store=self._auth_store,
            jwt_service=self._jwt_service,
            token_store=self._token_store,
            config=social_config,
        )

        # Register social auth routes
        social_router = create_social_auth_routes(self._social_auth_service)
        self._app.include_router(social_router)

        # Log enabled providers
        enabled = []
        if social_config.google_client_id:
            enabled.append("google")
        if social_config.github_client_id:
            enabled.append("github")
        if social_config.apple_team_id:
            enabled.append("apple")

        if enabled:
            logger.info(f"Social auth enabled: {', '.join(enabled)}")

    def _build_social_auth_config(self, oauth_providers: list[Any]) -> Any | None:
        """
        Build SocialAuthConfig from manifest oauth_providers.

        Reads credentials from environment variables specified in manifest.
        """
        import logging
        import os

        from dazzle_back.runtime.social_auth import SocialAuthConfig

        logger = logging.getLogger(__name__)
        config = SocialAuthConfig()
        any_configured = False

        for provider_cfg in oauth_providers:
            provider = provider_cfg.provider.lower()

            if provider == "google":
                client_id = os.getenv(provider_cfg.client_id_env)
                if client_id:
                    config.google_client_id = client_id
                    any_configured = True
                else:
                    logger.warning(f"Google OAuth: {provider_cfg.client_id_env} not set")

            elif provider == "github":
                client_id = os.getenv(provider_cfg.client_id_env)
                client_secret = os.getenv(provider_cfg.client_secret_env)
                if client_id and client_secret:
                    config.github_client_id = client_id
                    config.github_client_secret = client_secret
                    any_configured = True
                else:
                    missing = []
                    if not client_id:
                        missing.append(provider_cfg.client_id_env)
                    if not client_secret:
                        missing.append(provider_cfg.client_secret_env)
                    logger.warning(f"GitHub OAuth: {', '.join(missing)} not set")

            elif provider == "apple":
                # Apple requires team_id, key_id, private_key, bundle_id
                # These would need extended manifest schema
                logger.warning(
                    "Apple OAuth: requires extended configuration "
                    "(team_id, key_id, private_key, bundle_id)"
                )

            else:
                logger.warning(f"Unknown OAuth provider: {provider}")

        return config if any_configured else None

    def _init_event_framework(self) -> None:
        """Initialize the event framework for event-driven features (v0.18.0)."""
        if not self._app:
            return

        try:
            from dazzle_back.events.framework import EventFramework, EventFrameworkConfig

            # Create event framework with same database as app
            config = EventFrameworkConfig(
                auto_start_publisher=True,
                auto_start_consumers=True,
                database_url=self._database_url,
            )
            self._event_framework = EventFramework(config)

            # Capture for closures
            event_framework = self._event_framework

            @self._app.on_event("startup")
            async def startup_events() -> None:
                """Start event framework on app startup."""
                await event_framework.start()

            @self._app.on_event("shutdown")
            async def shutdown_events() -> None:
                """Stop event framework on app shutdown."""
                await event_framework.stop()

        except ImportError:
            # Events module not available - skip
            pass
        except Exception as e:
            # Log but don't fail startup
            import logging

            logging.getLogger("dazzle.server").warning(f"Failed to init event framework: {e}")

    def _init_console(self) -> None:
        """Initialize the Founder Console (v0.26.0)."""
        if not self._app or not self._enable_console:
            return

        try:
            from dazzle_back.runtime.console_routes import create_console_routes
            from dazzle_back.runtime.deploy_history import DeployHistoryStore
            from dazzle_back.runtime.deploy_routes import create_deploy_routes
            from dazzle_back.runtime.ops_database import OpsDatabase
            from dazzle_back.runtime.rollback_manager import RollbackManager
            from dazzle_back.runtime.spec_versioning import SpecVersionStore

            # Create ops database for console (PostgreSQL)
            if not self._database_url:
                import logging as _log

                _log.getLogger("dazzle.server").info("Console requires DATABASE_URL — skipping")
                return
            ops_db = OpsDatabase(
                database_url=self._database_url,
            )
            spec_version_store = SpecVersionStore(ops_db)
            deploy_history_store = DeployHistoryStore(ops_db)

            # Save current spec version
            spec_version_store.save_version(self.spec)

            # Rollback manager
            rollback_manager = RollbackManager(
                spec_version_store=spec_version_store,
                deploy_history_store=deploy_history_store,
            )

            console_router = create_console_routes(
                ops_db=ops_db,
                appspec=self.spec,
                spec_version_store=spec_version_store,
                deploy_history_store=deploy_history_store,
            )
            self._app.include_router(console_router)

            deploy_router = create_deploy_routes(
                deploy_history_store=deploy_history_store,
                spec_version_store=spec_version_store,
                rollback_manager=rollback_manager,
                appspec=self.spec,
            )
            self._app.include_router(deploy_router)

            import logging

            logging.getLogger("dazzle.server").info("Founder Console initialized at /_console/")

        except ImportError as e:
            import logging

            logging.getLogger("dazzle.server").debug(f"Console not available: {e}")
        except Exception as e:
            import logging

            logging.getLogger("dazzle.server").warning(f"Failed to init console: {e}")

    def _init_fragment_routes(self) -> None:
        """Initialize fragment routes for composable HTMX fragments (v0.25.0)."""
        if not self._app:
            return

        try:
            from dazzle_back.runtime.fragment_routes import create_fragment_router

            # Build fragment sources from integration specs if available
            fragment_sources: dict[str, dict[str, Any]] = {}
            for integration in getattr(self.spec, "integrations", []):
                if hasattr(integration, "base_url") and integration.base_url:
                    fragment_sources[integration.name] = {
                        "url": integration.base_url,
                        "display_key": "name",
                        "value_key": "id",
                        "headers": getattr(integration, "headers", {}),
                    }

            # Merge fragment sources from DSL source= annotations (v0.25.1)
            fragment_sources.update(self._fragment_sources)

            fragment_router = create_fragment_router(fragment_sources)
            self._app.include_router(fragment_router)
        except Exception as e:
            import logging

            logging.getLogger("dazzle.server").debug(f"Fragment routes not available: {e}")

    def _init_integration_executor(self) -> None:
        """Initialize integration action executor (delegates to IntegrationManager)."""
        if self._integration_mgr:
            self._integration_mgr.init_integration_executor()

    def _init_mapping_executor(self) -> None:
        """Initialize declarative integration mapping executor (v0.30.0).

        Scans integrations for ``IntegrationMapping`` blocks and registers
        handlers on the global entity event bus to fire HTTP requests on
        entity lifecycle events.
        """
        try:
            # Check if any integrations have mappings
            has_mappings = False
            for integration in getattr(self.spec, "integrations", []):
                if getattr(integration, "mappings", []):
                    has_mappings = True
                    break

            if not has_mappings:
                return

            from dazzle_back.runtime.event_bus import get_event_bus
            from dazzle_back.runtime.mapping_executor import MappingExecutor

            event_bus = get_event_bus()
            repositories = self._repositories

            async def update_entity(
                entity_name: str, entity_id: str, fields: dict[str, Any]
            ) -> None:
                repo = repositories.get(entity_name)
                if repo:
                    from uuid import UUID

                    await repo.update(UUID(entity_id), fields)

            executor = MappingExecutor(self.spec, event_bus, update_entity=update_entity)
            executor.register_all()

        except Exception as e:
            import logging

            logging.getLogger("dazzle.server").warning(f"Failed to init mapping executor: {e}")

    def _init_workspace_routes(self) -> None:
        """Initialize workspace layout routes (delegates to WorkspaceRouteBuilder)."""
        if self._workspace_builder:
            self._workspace_builder.init_workspace_routes()

    def _init_workspace_entity_routes(self, workspaces: list[Any], app: Any) -> None:
        """Register workspace-prefixed entity routes (delegates to WorkspaceRouteBuilder)."""
        if self._workspace_builder:
            self._workspace_builder._init_workspace_entity_routes(workspaces, app)

    def _init_process_manager(self) -> None:
        """Initialize process manager for workflow execution (v0.24.0)."""
        if not self._app:
            return

        try:
            import os

            from dazzle.core.process import LiteProcessAdapter
            from dazzle_back.runtime.process_manager import ProcessManager
            from dazzle_back.runtime.task_routes import router as task_router
            from dazzle_back.runtime.task_routes import set_process_manager

            # Create the ProcessAdapter - use custom class if configured
            # Auto-detect Celery when REDIS_URL is set and no explicit class
            adapter_cls: type | None = self._process_adapter_class
            if adapter_cls is None:
                redis_url = os.environ.get("REDIS_URL")
                if redis_url:
                    try:
                        from dazzle.core.process import CeleryProcessAdapter

                        self._process_adapter = CeleryProcessAdapter(redis_url=redis_url)
                    except ImportError:
                        self._process_adapter = LiteProcessAdapter(database_url=self._database_url)
                else:
                    self._process_adapter = LiteProcessAdapter(database_url=self._database_url)
            else:
                self._process_adapter = adapter_cls(database_url=self._database_url)

            # Create ProcessManager with process/schedule specs so triggers are registered
            self._process_manager = ProcessManager(
                adapter=self._process_adapter,
                process_specs=self._process_specs or None,
                schedule_specs=self._schedule_specs or None,
            )
            # Pass entity status field mapping for transition detection
            self._process_manager._entity_status_fields = self._entity_status_fields

            # Set process manager dependency for task routes
            set_process_manager(self._process_manager)

            # Include task router
            self._app.include_router(task_router, prefix="/api")

            # Wire entity lifecycle events to ProcessManager
            self._wire_entity_events_to_processes()

            # Wire SideEffectExecutor for step effects (v0.33.0)
            if hasattr(self._process_adapter, "set_side_effect_executor"):
                from dazzle_back.runtime.side_effect_executor import SideEffectExecutor

                side_effect_executor = SideEffectExecutor(
                    services=self._services,
                    repositories=self._repositories,
                )
                self._process_adapter.set_side_effect_executor(side_effect_executor)

            # Capture for closures
            process_adapter = self._process_adapter
            process_manager = self._process_manager

            @self._app.on_event("startup")
            async def startup_processes() -> None:
                """Initialize process adapter and register triggers."""
                await process_adapter.initialize()
                await process_manager.initialize()

            @self._app.on_event("shutdown")
            async def shutdown_processes() -> None:
                """Cleanup process manager and adapter on app shutdown."""
                await process_manager.shutdown()

            import logging

            logging.getLogger("dazzle.server").info("Process manager initialized")

        except ImportError as e:
            # Process module not available - skip
            import logging

            logging.getLogger("dazzle.server").debug(f"Process module not available: {e}")
        except Exception as e:
            # Log but don't fail startup
            import logging

            logging.getLogger("dazzle.server").warning(f"Failed to init process manager: {e}")

    def _wire_entity_events_to_processes(self) -> None:
        """Wire entity lifecycle events from CRUD services to ProcessManager.

        This enables automatic process triggering when entities are created,
        updated, or deleted.
        """
        if not self._process_manager:
            return

        process_manager = self._process_manager

        # Create callback functions that delegate to ProcessManager
        async def on_created_callback(
            entity_name: str,
            entity_id: str,
            entity_data: dict[str, Any],
            _old_data: dict[str, Any] | None,
        ) -> Any:
            """Callback for entity creation events."""
            return await process_manager.on_entity_created(entity_name, entity_id, entity_data)

        async def on_updated_callback(
            entity_name: str,
            entity_id: str,
            entity_data: dict[str, Any],
            old_data: dict[str, Any] | None,
        ) -> Any:
            """Callback for entity update events."""
            return await process_manager.on_entity_updated(
                entity_name, entity_id, entity_data, old_data
            )

        async def on_deleted_callback(
            entity_name: str,
            entity_id: str,
            entity_data: dict[str, Any],
            _old_data: dict[str, Any] | None,
        ) -> Any:
            """Callback for entity deletion events."""
            return await process_manager.on_entity_deleted(entity_name, entity_id, entity_data)

        # Register callbacks with all CRUD services
        wired_count = 0
        for _service_name, service in self._services.items():
            if isinstance(service, CRUDService):
                service.on_created(on_created_callback)
                service.on_updated(on_updated_callback)
                service.on_deleted(on_deleted_callback)
                wired_count += 1

        import logging

        logging.getLogger("dazzle.server").debug(
            f"Wired entity events to ProcessManager for {wired_count} services"
        )

    def _wire_send_handler_to_channels(self) -> None:
        """Connect process adapter's SEND step to ChannelManager.

        When a process step has ``kind: send``, the adapter calls the
        send handler.  This wires it to ChannelManager.send() so that
        process workflows can dispatch email/queue/stream messages.
        """
        channel_mgr = self.channel_manager
        if not channel_mgr or not self._process_adapter:
            return

        # Only LiteProcessAdapter exposes set_send_handler
        if not hasattr(self._process_adapter, "set_send_handler"):
            return

        async def _send_via_channel(
            channel: str, message_type: str, payload: dict[str, Any]
        ) -> None:
            await channel_mgr.send(
                channel=channel,
                operation="process_send",
                message_type=message_type,
                payload=payload,
                recipient=payload.get("to", payload.get("recipient", "")),
            )

        self._process_adapter.set_send_handler(_send_via_channel)

        logger.info("Wired process SEND steps to ChannelManager")

    def _wire_entity_events_to_channels(self) -> None:
        """Wire entity lifecycle events to channel send operations.

        Scans channel send operations in the BackendSpec for entity_event
        triggers (stored in channel metadata by the converter) and registers
        callbacks on the corresponding CRUDService.
        """
        channel_mgr = self.channel_manager
        if not channel_mgr or not self._services:
            return

        # Build trigger map: (entity_name, event_type) → [(channel, op, message)]
        trigger_map: dict[tuple[str, str], list[tuple[str, str, str]]] = {}

        for channel in self.spec.channels:
            trigger_meta = channel.metadata.get("send_triggers", {})
            for send_op in channel.send_operations:
                op_trigger = trigger_meta.get(send_op.name)
                if not op_trigger:
                    continue
                entity_name = op_trigger.get("entity_name")
                event_type = op_trigger.get("event")
                if entity_name and event_type:
                    key = (entity_name, event_type)
                    trigger_map.setdefault(key, []).append(
                        (channel.name, send_op.name, send_op.message)
                    )

        if not trigger_map:
            return

        def _make_callback(
            event_type: str,
        ) -> Any:
            """Create an event-specific callback for channel dispatch."""

            async def _dispatch(
                entity_name: str,
                entity_id: str,
                entity_data: dict[str, Any],
                _old_data: dict[str, Any] | None,
            ) -> None:
                operations = trigger_map.get((entity_name, event_type), [])
                for channel_name, op_name, message_type in operations:
                    try:
                        await channel_mgr.send(
                            channel=channel_name,
                            operation=op_name,
                            message_type=message_type,
                            payload={
                                "entity_id": entity_id,
                                "entity_name": entity_name,
                                "event_type": event_type,
                                **entity_data,
                            },
                            recipient=entity_data.get("email", entity_data.get("to", "")),
                        )
                    except Exception:
                        logger.warning(
                            "Channel send failed for %s.%s on %s %s",
                            channel_name,
                            op_name,
                            entity_name,
                            event_type,
                        )

            return _dispatch

        on_created_cb = _make_callback("created")
        on_updated_cb = _make_callback("updated")
        on_deleted_cb = _make_callback("deleted")

        # Register callbacks with CRUD services for entities that have triggers
        triggered_entities = {ename for (ename, _) in trigger_map}
        wired = 0
        for _svc_name, service in self._services.items():
            if isinstance(service, CRUDService):
                if service.entity_name in triggered_entities:
                    service.on_created(on_created_cb)
                    service.on_updated(on_updated_cb)
                    service.on_deleted(on_deleted_cb)
                    wired += 1

        if wired:
            logger.info("Wired entity events to channel sends for %d entities", wired)

    # ------------------------------------------------------------------
    # Build phases — called in order by build()
    # ------------------------------------------------------------------

    def _create_app(self) -> None:
        """Create the FastAPI app instance and apply middleware."""
        self._app = _FastAPI(
            title=self.spec.name,
            description=self.spec.description or f"Dazzle Backend: {self.spec.name}",
            version=self.spec.version,
        )

        # Security middleware (v0.11.0)
        from dazzle_back.runtime.security_middleware import apply_security_middleware

        apply_security_middleware(
            self._app,
            self._security_profile,
            cors_origins=self._cors_origins,
        )

        # GZip compression (v0.33.0) — must be added before other middleware
        from starlette.middleware.gzip import GZipMiddleware

        self._app.add_middleware(GZipMiddleware, minimum_size=500)

        # Metrics middleware (v0.27.0)
        try:
            from dazzle_back.runtime.metrics import add_metrics_middleware

            add_metrics_middleware(self._app)
        except ImportError:
            pass

        # Exception handlers (v0.28.0)
        from dazzle_back.runtime.exception_handlers import register_exception_handlers

        register_exception_handlers(self._app)

    def _setup_models(self) -> None:
        """Generate Pydantic models and create/update schemas from the spec."""
        self._models = generate_all_entity_models(self.spec.entities)
        for entity in self.spec.entities:
            self._schemas[entity.name] = {
                "create": generate_create_schema(entity),
                "update": generate_update_schema(entity),
            }

    def _setup_database(self) -> None:
        """Initialize database backend, run migrations, create repositories."""
        if not self._database_url:
            raise ValueError(
                "database_url is required. Set DATABASE_URL environment variable "
                "or pass database_url to ServerConfig/DazzleBackendApp."
            )

        from dazzle_back.runtime.pg_backend import PostgresBackend

        self._db_manager = PostgresBackend(self._database_url)
        self._last_migration = auto_migrate(
            self._db_manager,
            self.spec.entities,
            record_history=True,
        )

        # Build relation loader for nested ref resolution (#272)
        from dazzle_back.runtime.relation_loader import RelationLoader, RelationRegistry

        relation_registry = RelationRegistry.from_entities(self.spec.entities)
        relation_loader = RelationLoader(
            registry=relation_registry,
            entities=self.spec.entities,
            conn_factory=self._db_manager.get_persistent_connection,
        )

        repo_factory = RepositoryFactory(
            self._db_manager,
            self._models,
            relation_loader=relation_loader,
        )
        self._repositories = repo_factory.create_all_repositories(self.spec.entities)

    def _setup_services(self) -> None:
        """Create CRUD services and wire them to repositories."""
        state_machines = {
            entity.name: entity.state_machine
            for entity in self.spec.entities
            if entity.state_machine
        }
        entity_specs = {entity.name: entity for entity in self.spec.entities}

        factory = ServiceFactory(self._models, state_machines, entity_specs)
        self._services = factory.create_all_services(
            self.spec.services,
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

    def _setup_auth(self) -> tuple[Any, Any]:
        """Initialize auth store, middleware, and social auth.

        Returns (auth_dep, optional_auth_dep) for route generation.
        """
        auth_dep = None
        optional_auth_dep = None
        if not self._enable_auth:
            return auth_dep, optional_auth_dep

        assert self._database_url is not None  # guaranteed by _setup_database()
        self._auth_store = AuthStore(database_url=self._database_url)
        self._auth_middleware = AuthMiddleware(self._auth_store)

        # Build persona -> default_route mapping for post-login redirect
        _persona_routes: dict[str, str] = {}
        for p in self._personas:
            route = p.get("default_route")
            if route:
                _persona_routes[p["id"]] = route
        # Default signup role: first persona ID (public-facing persona by convention)
        _default_signup_roles = [self._personas[0]["id"]] if self._personas else None
        auth_router = create_auth_routes(
            self._auth_store,
            persona_routes=_persona_routes or None,
            default_signup_roles=_default_signup_roles,
        )
        assert self._app is not None
        self._app.include_router(auth_router)

        from dazzle_back.runtime.auth import (
            create_auth_dependency,
            create_optional_auth_dependency,
        )

        auth_dep = create_auth_dependency(self._auth_store)
        optional_auth_dep = create_optional_auth_dependency(self._auth_store)

        # Social auth (OAuth providers)
        self._init_social_auth()

        return auth_dep, optional_auth_dep

    def _setup_routes(self, auth_dep: Any, optional_auth_dep: Any) -> None:
        """Generate entity CRUD routes, audit routes, file routes, and dev routes."""
        assert self._app is not None

        # Extract access specs
        entity_access_specs: dict[str, dict[str, Any]] = {}
        for entity in self.spec.entities:
            if entity.metadata and "access" in entity.metadata:
                entity_access_specs[entity.name] = entity.metadata["access"]

        cedar_access_specs: dict[str, Any] = {}
        for entity in self.spec.entities:
            if entity.access:
                cedar_access_specs[entity.name] = entity.access

        # Audit logger
        audit_logger = None
        _has_auditable_entities = any(
            (entity.metadata and "access" in entity.metadata)
            or getattr(entity, "audit", None)
            or entity.access
            for entity in self.spec.entities
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
        service_specs = {svc.name: svc for svc in self.spec.services}

        # Pre-compute HTMX metadata per entity so list API endpoints can
        # render table row fragments with correct column definitions.
        entity_htmx_meta: dict[str, dict[str, Any]] = {}
        app_prefix = "/app"
        for entity in self.spec.entities:
            entity_slug = entity.name.lower().replace("_", "-")
            entity_htmx_meta[entity.name] = {
                "columns": _build_entity_columns(entity),
                "detail_url": f"{app_prefix}/{entity_slug}/{{id}}",
                "entity_name": entity.name,
            }

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
            entity_auto_includes=self._entity_auto_includes,
            entity_htmx_meta=entity_htmx_meta,
        )
        router = route_generator.generate_all_routes(
            self.spec.endpoints,
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
            create_file_routes(self._app, self._file_service)
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
                entities=self.spec.entities,
                auth_store=self._auth_store,
            )
            self._app.include_router(test_router)

        # Dev control plane
        if self._enable_dev_mode or self._enable_test_mode:
            from dazzle_back.runtime.control_plane import create_control_plane_routes

            control_plane_router = create_control_plane_routes(
                db_manager=self._db_manager,
                repositories=self._repositories if self._db_manager else None,
                entities=self.spec.entities,
                personas=self._personas,
                scenarios=self._scenarios,
                auth_store=self._auth_store,
            )
            self._app.include_router(control_plane_router)

    def _setup_optional_features(self) -> None:
        """Initialize optional features: events, debug, site, channels, etc."""
        assert self._app is not None

        # Create delegate instances
        self._integration_mgr = IntegrationManager(
            app=self._app,
            spec=self.spec,
            db_manager=self._db_manager,
            fragment_sources=self._fragment_sources,
        )
        self._workspace_builder = WorkspaceRouteBuilder(
            app=self._app,
            spec=self.spec,
            repositories=self._repositories,
            auth_middleware=self._auth_middleware,
            enable_auth=self._enable_auth,
            enable_test_mode=self._enable_test_mode,
        )

        # Event framework (v0.18.0)
        self._init_event_framework()

        # Debug routes
        if self._db_manager:
            from dazzle_back.runtime.debug_routes import create_debug_routes

            self._start_time = datetime.now()
            debug_router = create_debug_routes(
                spec=self.spec,
                db_manager=self._db_manager,
                entities=self.spec.entities,
                start_time=self._start_time,
            )
            self._app.include_router(debug_router)

            from dazzle_back.runtime.event_explorer import create_event_explorer_routes

            event_explorer_router = create_event_explorer_routes(self._event_framework)
            self._app.include_router(event_explorer_router)

        # Site routes (v0.16.0)
        if self._sitespec_data:
            from dazzle_back.runtime.site_routes import (
                create_site_page_routes,
                create_site_routes,
            )

            site_router = create_site_routes(
                sitespec_data=self._sitespec_data,
                project_root=self._project_root,
            )
            self._app.include_router(site_router)

            page_router = create_site_page_routes(
                sitespec_data=self._sitespec_data,
                project_root=self._project_root,
            )
            self._app.include_router(page_router)

        # Messaging channels (v0.9)
        if self._enable_channels and self.spec.channels:
            self._init_channel_manager()

        # Founder Console (v0.26.0)
        if self._enable_console:
            self._init_console()

        # Fragment routes (v0.25.0)
        self._init_fragment_routes()

        # Integration executor (v0.20.0)
        self._init_integration_executor()

        # Mapping executor (v0.30.0)
        self._init_mapping_executor()

        # Workspace routes (v0.20.0)
        self._init_workspace_routes()

        # Process manager (v0.24.0)
        if self._enable_processes:
            self._init_process_manager()

        # Wire process SEND steps to channel manager (v0.33.0)
        self._wire_send_handler_to_channels()

        # Wire entity event triggers from channel send operations (v0.33.0)
        self._wire_entity_events_to_channels()

    def _setup_system_routes(self) -> None:
        """Register domain service stubs, health check, spec, and db-info routes."""
        assert self._app is not None

        # Load domain service stubs
        self._service_loader = ServiceLoader(services_dir=self._services_dir)
        try:
            self._service_loader.load_services()
        except Exception:
            logger.warning("Failed to load domain services", exc_info=True)

        if self._service_loader and self._service_loader.services:
            service_loader = self._service_loader  # Capture for closure

            @self._app.get("/_dazzle/services", tags=["System"])
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

            @self._app.post("/_dazzle/services/{service_id}/invoke", tags=["System"])
            async def invoke_domain_service(
                service_id: str, payload: dict[str, Any] | None = None
            ) -> dict[str, Any]:
                """Invoke a domain service stub."""
                if not service_loader.has_service(service_id):
                    return {"error": f"Service not found: {service_id}"}
                try:
                    result = service_loader.invoke(service_id, **(payload or {}))
                    return {"result": result}
                except Exception as e:
                    return {"error": str(e)}

        @self._app.get("/health", tags=["System"])
        async def health_check() -> dict[str, str]:
            return {"status": "healthy", "app": self.spec.name}

        @self._app.get("/spec", tags=["System"])
        async def get_spec() -> dict[str, Any]:
            return self.spec.model_dump()

        def _mask_database_url(url: str | None) -> str | None:
            """Mask password in database URL for safe display."""
            if not url:
                return None
            import re as _re

            return _re.sub(r"://([^:]+):([^@]+)@", r"://\1:***@", url)

        masked_db_url = _mask_database_url(self._database_url)
        files_path_str = str(self._files_path) if self._enable_files else None
        last_migration = self._last_migration
        auth_enabled = self._enable_auth
        files_enabled = self._enable_files

        @self._app.get("/db-info", tags=["System"])
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
                "tables": [e.name for e in self.spec.entities],
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
            )

            if self._project_root:
                project_templates = self._project_root / "templates"
                if project_templates.is_dir():
                    configure_project_templates(project_templates)

                    # Build override registry if project has declaration headers
                    try:
                        from dazzle import __version__ as dz_version
                        from dazzle_ui.runtime.override_registry import (
                            build_registry,
                            save_registry,
                        )

                        registry = build_registry(
                            project_templates, TEMPLATES_DIR, framework_version=dz_version
                        )
                        if registry.get("template_overrides"):
                            from dazzle.mcp.server.paths import project_overrides_file

                            save_registry(registry, project_overrides_file(self._project_root))
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
                if self._project_root:
                    dirs.append(self._project_root / "static")
                dirs.append(framework_static)
                self._app.mount("/static", CombinedStaticFiles(directories=dirs), name="static")
        except ImportError:
            pass  # dazzle_ui not installed — static files served externally
        except Exception:
            logger.warning("Failed to mount static files", exc_info=True)

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
        self._setup_optional_features()
        self._setup_system_routes()

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
# Backward-compat re-exports (moved to app_factory.py)
# =============================================================================

from dazzle_back.runtime.app_factory import (  # noqa: E402, F401
    build_entity_list_projections,
    create_app,
    create_app_factory,
    create_app_from_dict,
    create_app_from_json,
    run_app,
)

# Backward compatibility alias (deprecated as of v0.28.0)
DNRBackendApp = DazzleBackendApp

__all__ = [
    "DazzleBackendApp",
    "DNRBackendApp",
    "ServerConfig",
    "create_app",
    "create_app_factory",
    "create_app_from_dict",
    "create_app_from_json",
    "run_app",
    "build_entity_list_projections",
]
