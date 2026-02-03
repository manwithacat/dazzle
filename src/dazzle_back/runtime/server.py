"""
Runtime server - creates and runs a FastAPI application from BackendSpec.

This module provides the main entry point for running a DNR-Back application.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from dazzle_back.runtime.auth import AuthMiddleware, AuthStore, create_auth_routes
from dazzle_back.runtime.file_routes import create_file_routes, create_static_file_routes
from dazzle_back.runtime.file_storage import FileService, create_local_file_service
from dazzle_back.runtime.migrations import MigrationPlan, auto_migrate
from dazzle_back.runtime.model_generator import (
    generate_all_entity_models,
    generate_create_schema,
    generate_update_schema,
)
from dazzle_back.runtime.repository import DatabaseManager, RepositoryFactory
from dazzle_back.runtime.service_generator import CRUDService, ServiceFactory
from dazzle_back.runtime.service_loader import ServiceLoader
from dazzle_back.specs import BackendSpec

# FastAPI is optional - use TYPE_CHECKING for type hints
if TYPE_CHECKING:
    from fastapi import FastAPI


# =============================================================================
# Server Configuration
# =============================================================================


@dataclass
class ServerConfig:
    """
    Configuration for DNRBackendApp.

    Groups all initialization options into a single object for cleaner APIs.
    """

    # Database settings
    db_path: Path = field(default_factory=lambda: Path(".dazzle/data.db"))
    database_url: str | None = None  # PostgreSQL URL (e.g. postgresql://user:pass@host/db)
    use_database: bool = True

    # Authentication settings
    enable_auth: bool = False
    auth_db_path: Path = field(default_factory=lambda: Path(".dazzle/auth.db"))
    auth_config: Any = None  # AuthConfig from manifest (for OAuth providers)

    # File upload settings
    enable_files: bool = False
    files_path: Path = field(default_factory=lambda: Path(".dazzle/uploads"))
    files_db_path: Path = field(default_factory=lambda: Path(".dazzle/files.db"))

    # Development/testing settings
    enable_test_mode: bool = False
    services_dir: Path = field(default_factory=lambda: Path("services"))

    # Dazzle Bar control plane (v0.8.5)
    enable_dev_mode: bool = False
    feedback_dir: Path = field(default_factory=lambda: Path(".dazzle/feedback"))
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
    process_db_path: Path = field(default_factory=lambda: Path(".dazzle/processes.db"))

    # Fragment sources from DSL source= annotations (v0.25.1)
    fragment_sources: dict[str, dict[str, Any]] = field(default_factory=dict)

    # Founder Console (v0.26.0)
    enable_console: bool = True  # Enable /_console/ founder control plane


# Runtime import
try:
    from fastapi import FastAPI as _FastAPI
    from fastapi import Request
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse
    from pydantic import ValidationError

    from dazzle_back.runtime.invariant_evaluator import InvariantViolationError
    from dazzle_back.runtime.route_generator import RouteGenerator
    from dazzle_back.runtime.state_machine import TransitionError

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    _FastAPI = None  # type: ignore
    CORSMiddleware = None  # type: ignore
    RouteGenerator = None  # type: ignore
    Request = None  # type: ignore
    JSONResponse = None  # type: ignore
    TransitionError = Exception  # type: ignore
    InvariantViolationError = Exception  # type: ignore
    ValidationError = Exception  # type: ignore


# =============================================================================
# Application Builder
# =============================================================================


class DNRBackendApp:
    """
    DNR Backend Application.

    Creates a complete FastAPI application from a BackendSpec.
    """

    def __init__(
        self,
        spec: BackendSpec,
        config: ServerConfig | None = None,
        *,
        # Legacy parameters for backwards compatibility
        db_path: str | Path | None = None,
        use_database: bool | None = None,
        enable_auth: bool | None = None,
        auth_db_path: str | Path | None = None,
        auth_config: Any = None,  # AuthConfig from manifest (for OAuth providers)
        enable_files: bool | None = None,
        files_path: str | Path | None = None,
        files_db_path: str | Path | None = None,
        enable_test_mode: bool | None = None,
        services_dir: str | Path | None = None,
        # Dazzle Bar control plane (v0.8.5)
        enable_dev_mode: bool | None = None,
        feedback_dir: str | Path | None = None,
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

            Legacy parameters (use config instead):
            db_path: Path to SQLite database (default: .dazzle/data.db)
            use_database: Whether to use SQLite persistence (default: True)
            enable_auth: Whether to enable authentication (default: False)
            auth_db_path: Path to auth database (default: .dazzle/auth.db)
            enable_files: Whether to enable file uploads (default: False)
            files_path: Path for file storage (default: .dazzle/uploads)
            files_db_path: Path to file metadata database (default: .dazzle/files.db)
            enable_test_mode: Whether to enable /__test__/* endpoints (default: False)
            services_dir: Path to domain service stubs directory (default: services/)
            enable_dev_mode: Enable Dazzle Bar control plane (default: False)
            feedback_dir: Directory for feedback logs (default: .dazzle/feedback)
            personas: List of persona configurations for Dazzle Bar
            scenarios: List of scenario configurations for Dazzle Bar
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

        # Override config with any explicit legacy parameters
        self.spec = spec
        self._db_path = Path(db_path) if db_path else config.db_path
        self._database_url = config.database_url
        self._use_database = use_database if use_database is not None else config.use_database
        self._enable_auth = enable_auth if enable_auth is not None else config.enable_auth
        self._auth_db_path = Path(auth_db_path) if auth_db_path else config.auth_db_path
        self._auth_config = auth_config if auth_config is not None else config.auth_config
        self._enable_files = enable_files if enable_files is not None else config.enable_files
        self._files_path = Path(files_path) if files_path else config.files_path
        self._files_db_path = Path(files_db_path) if files_db_path else config.files_db_path
        self._enable_test_mode = (
            enable_test_mode if enable_test_mode is not None else config.enable_test_mode
        )
        self._services_dir = Path(services_dir) if services_dir else config.services_dir
        # Dazzle Bar control plane (v0.8.5)
        self._enable_dev_mode = (
            enable_dev_mode if enable_dev_mode is not None else config.enable_dev_mode
        )
        self._feedback_dir = Path(feedback_dir) if feedback_dir else config.feedback_dir
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
        self._db_manager: DatabaseManager | None = None
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
        self._channel_manager: Any | None = None  # ChannelManager type
        self._enable_channels = config.enable_channels
        # Security (v0.11.0)
        self._security_profile = config.security_profile
        self._cors_origins = config.cors_origins
        # Event system (v0.18.0)
        self._event_framework: Any | None = None  # EventFramework type
        # NOTE: _sitespec_data and _project_root are already set above (lines 201-203)
        # with proper parameter precedence over config defaults
        # Process/workflow support (v0.24.0)
        self._enable_processes = config.enable_processes
        self._process_db_path = config.process_db_path
        self._process_manager: Any | None = None  # ProcessManager type
        self._process_adapter: Any | None = None  # ProcessAdapter type
        # Fragment sources from DSL source= annotations (v0.25.1)
        self._fragment_sources: dict[str, dict[str, Any]] = config.fragment_sources
        # Founder Console (v0.26.0)
        self._enable_console = config.enable_console

    def _init_channel_manager(self) -> None:
        """Initialize the channel manager for messaging."""
        try:
            from dazzle.core.ir import ChannelKind
            from dazzle.core.ir import ChannelSpec as IRChannelSpec
            from dazzle_back.channels import create_channel_manager

            # Convert BackendSpec channels to IR ChannelSpecs
            ir_channels = []
            for channel in self.spec.channels:
                # Map string kind to ChannelKind enum
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

            # Create channel manager
            self._channel_manager = create_channel_manager(
                db_manager=self._db_manager,
                channel_specs=ir_channels,
                build_id=f"{self.spec.name}-{self.spec.version}",
            )

            # Add channel routes to the app
            self._add_channel_routes()

        except ImportError:
            # Channels module not available - skip
            pass
        except Exception as e:
            # Log but don't fail startup
            import logging

            logging.getLogger("dazzle.server").warning(f"Failed to init channels: {e}")

    def _add_channel_routes(self) -> None:
        """Add channel management routes to the FastAPI app."""
        if not self._channel_manager or not self._app:
            return

        channel_manager = self._channel_manager  # Capture for closures

        @self._app.on_event("startup")
        async def startup_channels() -> None:
            """Initialize channels on app startup."""
            await channel_manager.initialize()
            # Start background outbox processor
            await channel_manager.start_processor()

        @self._app.on_event("shutdown")
        async def shutdown_channels() -> None:
            """Cleanup channels on app shutdown."""
            await channel_manager.shutdown()

        @self._app.get("/_dazzle/channels", tags=["Channels"])
        async def list_channels() -> dict[str, Any]:
            """List all messaging channels and their status."""
            statuses = channel_manager.get_all_statuses()
            return {
                "channels": [s.to_dict() for s in statuses],
                "outbox_stats": channel_manager.get_outbox_stats(),
            }

        @self._app.get("/_dazzle/channels/{channel_name}", tags=["Channels"])
        async def get_channel_status(channel_name: str) -> dict[str, Any]:
            """Get status of a specific channel."""
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
            """Send a message through a channel (for testing)."""
            try:
                result = await channel_manager.send(
                    channel=channel_name,
                    operation=message.get("operation", "test"),
                    message_type=message.get("type", "TestMessage"),
                    payload=message.get("payload", {}),
                    recipient=message.get("recipient", "test@example.com"),
                    metadata=message.get("metadata"),
                )
                # Return message info
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
            """Run health checks on all channels."""
            results = await channel_manager.health_check_all()
            return {"health": results}

        @self._app.get("/_dazzle/channels/outbox/recent", tags=["Channels"])
        async def get_recent_outbox(limit: int = 20) -> dict[str, Any]:
            """Get recent outbox messages for the email panel."""
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

        # Create token store
        token_db_path = self._auth_db_path.parent / "tokens.db"
        self._token_store = TokenStore(
            db_path=token_db_path,
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
                db_path=str(self._db_path),
                auto_start_publisher=True,
                auto_start_consumers=True,
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

            # Create ops database for console (reuse path convention)
            ops_db = OpsDatabase(db_path=self._db_path.parent / "ops.db")
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
        """Initialize integration action executor (v0.20.0)."""
        if not self._app:
            return

        try:
            from dazzle_back.runtime.integration_executor import IntegrationExecutor

            # Check if any integrations have actions
            has_actions = False
            for integration in getattr(self.spec, "integrations", []):
                if getattr(integration, "actions", []):
                    has_actions = True
                    break

            if not has_actions:
                return

            self._integration_executor = IntegrationExecutor(
                app_spec=self.spec,
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

    def _init_workspace_routes(self) -> None:
        """Initialize workspace layout routes (v0.20.0)."""
        if not self._app:
            return

        workspaces = getattr(self.spec, "workspaces", [])
        if not workspaces:
            return

        try:
            from dazzle_ui.runtime.template_renderer import render_fragment
            from dazzle_ui.runtime.workspace_renderer import build_workspace_context

            app = self._app
            spec = self.spec
            repositories = self._repositories

            for workspace in workspaces:
                ws_ctx = build_workspace_context(workspace, spec)
                ws_name = workspace.name

                # Capture in closure
                _ws_ctx = ws_ctx

                @app.get(f"/workspaces/{ws_name}", tags=["Workspaces"])
                async def workspace_page(
                    request: Request,
                    _ctx: Any = _ws_ctx,
                ) -> Any:
                    """Render workspace page."""
                    from fastapi.responses import HTMLResponse

                    html = render_fragment(
                        "workspace/workspace.html",
                        workspace=_ctx,
                    )
                    return HTMLResponse(content=html)

                # Region data endpoints
                for region in ws_ctx.regions:
                    if not region.source:
                        continue

                    _region = region
                    _source = region.source

                    @app.get(
                        f"/api/workspaces/{ws_name}/regions/{region.name}",
                        tags=["Workspaces"],
                    )
                    async def workspace_region_data(
                        request: Request,
                        page: int = 1,
                        page_size: int = 20,
                        _r: Any = _region,
                        _s: str = _source,
                    ) -> Any:
                        """Return rendered HTML for a workspace region."""
                        from fastapi.responses import HTMLResponse

                        # Query the source entity
                        items: list[dict[str, Any]] = []
                        total = 0
                        columns: list[dict[str, str]] = []

                        repo = repositories.get(_s) if repositories else None
                        if repo:
                            try:
                                limit = _r.limit or page_size
                                result = await repo.list(page=page, page_size=limit)
                                if isinstance(result, dict):
                                    raw_items = result.get("items", [])
                                    total = result.get("total", 0)
                                    items = [
                                        i.model_dump() if hasattr(i, "model_dump") else dict(i)
                                        for i in raw_items
                                    ]
                                # Build columns from first item keys
                                if items:
                                    columns = [
                                        {"key": k, "label": k.replace("_", " ").title()}
                                        for k in items[0].keys()
                                        if k != "id"
                                    ]
                            except Exception:
                                pass

                        # Build aggregate metrics if configured
                        metrics: list[dict[str, Any]] = []
                        for metric_name, expr in _r.aggregates.items():
                            value: Any = 0
                            if expr == "count":
                                value = total
                            elif expr.startswith("sum:") and items:
                                field_name = expr.split(":", 1)[1]
                                value = sum(float(i.get(field_name, 0) or 0) for i in items)
                            metrics.append(
                                {
                                    "label": metric_name.replace("_", " ").title(),
                                    "value": value,
                                }
                            )

                        html = render_fragment(
                            _r.template,
                            title=_r.title,
                            items=items,
                            total=total,
                            columns=columns,
                            metrics=metrics,
                            empty_message=_r.empty_message,
                            display_key=columns[0]["key"] if columns else "name",
                            item=items[0] if items else None,
                        )
                        return HTMLResponse(content=html)

            import logging

            logging.getLogger("dazzle.server").info(
                f"Workspace routes initialized for {len(workspaces)} workspace(s)"
            )

        except ImportError as e:
            import logging

            logging.getLogger("dazzle.server").debug(f"Workspace renderer not available: {e}")
        except Exception as e:
            import logging

            logging.getLogger("dazzle.server").warning(f"Failed to init workspace routes: {e}")

    def _init_process_manager(self) -> None:
        """Initialize process manager for workflow execution (v0.24.0)."""
        if not self._app:
            return

        try:
            from dazzle.core.process import LiteProcessAdapter
            from dazzle_back.runtime.process_manager import ProcessManager
            from dazzle_back.runtime.task_routes import router as task_router
            from dazzle_back.runtime.task_routes import set_process_manager

            # Create the LiteProcessAdapter
            self._process_adapter = LiteProcessAdapter(db_path=str(self._process_db_path))

            # Create ProcessManager
            self._process_manager = ProcessManager(adapter=self._process_adapter)

            # Set process manager dependency for task routes
            set_process_manager(self._process_manager)

            # Include task router
            self._app.include_router(task_router, prefix="/api")

            # Wire entity lifecycle events to ProcessManager
            self._wire_entity_events_to_processes()

            # Capture for closures
            process_adapter = self._process_adapter

            @self._app.on_event("startup")
            async def startup_processes() -> None:
                """Initialize process adapter on app startup."""
                await process_adapter.initialize()
                # Scheduler is started automatically in initialize()

            @self._app.on_event("shutdown")
            async def shutdown_processes() -> None:
                """Cleanup process adapter on app shutdown."""
                await process_adapter.shutdown()

            import logging

            logging.getLogger("dazzle.server").info(
                f"Process manager initialized with DB: {self._process_db_path}"
            )

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

    def build(self) -> FastAPI:
        """
        Build the FastAPI application.

        Returns:
            FastAPI application instance
        """
        # Create FastAPI app
        self._app = _FastAPI(
            title=self.spec.name,
            description=self.spec.description or f"Dazzle Backend: {self.spec.name}",
            version=self.spec.version,
        )

        # Add security middleware based on profile (v0.11.0)
        from dazzle_back.runtime.security_middleware import apply_security_middleware

        apply_security_middleware(
            self._app,
            self._security_profile,
            cors_origins=self._cors_origins,
        )

        # Add exception handler for state machine transition errors
        @self._app.exception_handler(TransitionError)
        async def transition_error_handler(request: Request, exc: TransitionError) -> JSONResponse:
            """Convert state machine errors to 422 Unprocessable Entity."""
            return JSONResponse(
                status_code=422,
                content={"detail": str(exc), "type": "transition_error"},
            )

        # Add exception handler for invariant violations (v0.14.2)
        @self._app.exception_handler(InvariantViolationError)
        async def invariant_error_handler(
            request: Request, exc: InvariantViolationError
        ) -> JSONResponse:
            """Convert invariant violations to 422 Unprocessable Entity."""
            return JSONResponse(
                status_code=422,
                content={"detail": str(exc), "type": "invariant_violation"},
            )

        # Add exception handler for Pydantic validation errors (v0.14.2)
        @self._app.exception_handler(ValidationError)
        async def validation_error_handler(request: Request, exc: ValidationError) -> JSONResponse:
            """Convert validation errors to 422 Unprocessable Entity with field details."""
            return JSONResponse(
                status_code=422,
                content={"detail": exc.errors(), "type": "validation_error"},
            )

        # Generate models
        self._models = generate_all_entity_models(self.spec.entities)

        # Generate schemas (create/update)
        for entity in self.spec.entities:
            self._schemas[entity.name] = {
                "create": generate_create_schema(entity),
                "update": generate_update_schema(entity),
            }

        # Initialize database if enabled
        if self._use_database:
            if self._database_url:
                from dazzle_back.runtime.pg_backend import PostgresBackend

                self._db_manager = PostgresBackend(self._database_url)
            else:
                self._db_manager = DatabaseManager(self._db_path)

            # Auto-migrate: creates tables and applies schema changes
            self._last_migration = auto_migrate(
                self._db_manager,
                self.spec.entities,
                record_history=True,
            )

            repo_factory = RepositoryFactory(self._db_manager, self._models)
            self._repositories = repo_factory.create_all_repositories(self.spec.entities)

        # Extract state machines from entities
        state_machines = {
            entity.name: entity.state_machine
            for entity in self.spec.entities
            if entity.state_machine
        }

        # Build entity specs lookup for validation (v0.14.2)
        entity_specs = {entity.name: entity for entity in self.spec.entities}

        # Create services
        factory = ServiceFactory(self._models, state_machines, entity_specs)
        self._services = factory.create_all_services(
            self.spec.services,
            self._schemas,
        )

        # Wire up repositories to services
        # Match services to repositories by their target entity
        if self._use_database:
            for _service_name, service in self._services.items():
                if isinstance(service, CRUDService):
                    # Get the entity name from the service
                    entity_name = service.entity_name
                    repo = self._repositories.get(entity_name)
                    if repo:
                        service.set_repository(repo)

        # Initialize auth if enabled (needed before route generation)
        get_auth_context = None
        if self._enable_auth:
            self._auth_store = AuthStore(self._auth_db_path)
            self._auth_middleware = AuthMiddleware(self._auth_store)
            auth_router = create_auth_routes(self._auth_store)
            self._app.include_router(auth_router)
            # Create auth context getter for routes
            get_auth_context = self._auth_middleware.get_auth_context

            # Initialize social auth if OAuth providers configured
            self._init_social_auth()

        # Extract entity access specs from entity metadata
        entity_access_specs: dict[str, dict[str, Any]] = {}
        for entity in self.spec.entities:
            if entity.metadata and "access" in entity.metadata:
                entity_access_specs[entity.name] = entity.metadata["access"]

        # Generate routes
        # When auth is enabled, require authentication by default (deny-default)
        service_specs = {svc.name: svc for svc in self.spec.services}
        route_generator = RouteGenerator(
            services=self._services,
            models=self._models,
            schemas=self._schemas,
            entity_access_specs=entity_access_specs,
            get_auth_context=get_auth_context,
            require_auth_by_default=self._enable_auth and not self._enable_test_mode,
        )
        router = route_generator.generate_all_routes(
            self.spec.endpoints,
            service_specs,
        )

        # Include router
        self._app.include_router(router)

        # Initialize file uploads if enabled
        if self._enable_files:
            self._file_service = create_local_file_service(
                base_path=self._files_path,
                db_path=self._files_db_path,
                base_url="/files",
            )
            create_file_routes(self._app, self._file_service)
            create_static_file_routes(
                self._app,
                base_path=str(self._files_path),
                url_prefix="/files",
            )

        # Initialize test routes if enabled
        if self._enable_test_mode and self._use_database and self._db_manager:
            # Lazy import to avoid FastAPI dependency at module load
            from dazzle_back.runtime.test_routes import create_test_routes

            test_router = create_test_routes(
                db_manager=self._db_manager,
                repositories=self._repositories,
                entities=self.spec.entities,
            )
            self._app.include_router(test_router)

        # Initialize Dazzle Bar control plane if dev mode enabled (v0.8.5)
        if self._enable_dev_mode or self._enable_test_mode:
            from dazzle_back.runtime.control_plane import create_control_plane_routes

            control_plane_router = create_control_plane_routes(
                db_manager=self._db_manager,
                repositories=self._repositories if self._use_database else None,
                entities=self.spec.entities,
                personas=self._personas,
                scenarios=self._scenarios,
                feedback_dir=self._feedback_dir,
                auth_store=self._auth_store,  # v0.23.0: Enable persona login
            )
            self._app.include_router(control_plane_router)

        # Initialize event framework (v0.18.0)
        if self._use_database:
            self._init_event_framework()

        # Initialize debug routes (always available when database is enabled)
        if self._use_database and self._db_manager:
            from dazzle_back.runtime.debug_routes import create_debug_routes

            self._start_time = datetime.now()
            debug_router = create_debug_routes(
                spec=self.spec,
                db_manager=self._db_manager,
                entities=self.spec.entities,
                start_time=self._start_time,
            )
            self._app.include_router(debug_router)

            # Initialize event explorer routes (v0.18.0)
            from dazzle_back.runtime.event_explorer import create_event_explorer_routes

            event_explorer_router = create_event_explorer_routes(self._event_framework)
            self._app.include_router(event_explorer_router)

        # Initialize site routes (v0.16.0)
        if self._sitespec_data:
            from dazzle_back.runtime.site_routes import create_site_routes

            site_router = create_site_routes(
                sitespec_data=self._sitespec_data,
                project_root=self._project_root,
            )
            self._app.include_router(site_router)

        # Initialize messaging channels (v0.9)
        if self._enable_channels and self.spec.channels:
            self._init_channel_manager()

        # Initialize Founder Console (v0.26.0)
        if self._enable_console:
            self._init_console()

        # Initialize fragment routes (v0.25.0)
        self._init_fragment_routes()

        # Initialize integration executor (v0.20.0)
        self._init_integration_executor()

        # Initialize workspace routes (v0.20.0)
        self._init_workspace_routes()

        # Initialize process manager (v0.24.0)
        if self._enable_processes:
            self._init_process_manager()

        # Load domain service stubs
        self._service_loader = ServiceLoader(services_dir=self._services_dir)
        try:
            self._service_loader.load_services()
        except Exception:
            # Services are optional - log but don't fail startup
            pass

        # Add domain service routes if any services loaded
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

        # Add health check
        @self._app.get("/health", tags=["System"])
        async def health_check() -> dict[str, str]:
            return {"status": "healthy", "app": self.spec.name}

        # Add spec endpoint
        @self._app.get("/spec", tags=["System"])
        async def get_spec() -> dict[str, Any]:
            return self.spec.model_dump()

        # Add database info endpoint
        db_path = str(self._db_path) if self._use_database else None
        auth_db_path = str(self._auth_db_path) if self._enable_auth else None
        files_path = str(self._files_path) if self._enable_files else None
        files_db_path = str(self._files_db_path) if self._enable_files else None
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
                "database_enabled": self._use_database,
                "database_path": db_path,
                "tables": [e.name for e in self.spec.entities],
                "last_migration": migration_info,
                "auth_enabled": auth_enabled,
                "auth_database_path": auth_db_path,
                "files_enabled": files_enabled,
                "files_path": files_path,
                "files_database_path": files_db_path,
            }

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
        """Check if dev mode (Dazzle Bar) is enabled."""
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
        return self._channel_manager

    @property
    def channels_enabled(self) -> bool:
        """Check if messaging channels are enabled."""
        return self._enable_channels and self._channel_manager is not None

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
# Convenience Functions
# =============================================================================


def create_app(
    spec: BackendSpec,
    db_path: str | Path | None = None,
    use_database: bool = True,
    enable_auth: bool = False,
    auth_db_path: str | Path | None = None,
    enable_files: bool = False,
    files_path: str | Path | None = None,
    files_db_path: str | Path | None = None,
    enable_test_mode: bool = False,
    services_dir: str | Path | None = None,
    enable_dev_mode: bool = False,
    feedback_dir: str | Path | None = None,
    personas: list[dict[str, Any]] | None = None,
    scenarios: list[dict[str, Any]] | None = None,
) -> FastAPI:
    """
    Create a FastAPI application from a BackendSpec.

    This is the main entry point for creating a DNR-Back application.

    Args:
        spec: Backend specification
        db_path: Path to SQLite database (default: .dazzle/data.db)
        use_database: Whether to use SQLite persistence (default: True)
        enable_auth: Whether to enable authentication (default: False)
        auth_db_path: Path to auth database (default: .dazzle/auth.db)
        enable_files: Whether to enable file uploads (default: False)
        files_path: Path for file storage (default: .dazzle/uploads)
        files_db_path: Path to file metadata database (default: .dazzle/files.db)
        enable_test_mode: Whether to enable /__test__/* endpoints (default: False)
        services_dir: Path to domain service stubs directory (default: services/)
        enable_dev_mode: Enable Dazzle Bar control plane (default: False)
        feedback_dir: Directory for feedback logs (default: .dazzle/feedback)
        personas: List of persona configurations for Dazzle Bar
        scenarios: List of scenario configurations for Dazzle Bar

    Returns:
        FastAPI application

    Example:
        >>> from dazzle_back.specs import BackendSpec
        >>> spec = BackendSpec(name="my_app", ...)
        >>> app = create_app(spec)
        >>> # Run with uvicorn: uvicorn mymodule:app
    """
    builder = DNRBackendApp(
        spec,
        db_path=db_path,
        use_database=use_database,
        enable_auth=enable_auth,
        auth_db_path=auth_db_path,
        enable_files=enable_files,
        files_path=files_path,
        files_db_path=files_db_path,
        enable_test_mode=enable_test_mode,
        services_dir=services_dir,
        enable_dev_mode=enable_dev_mode,
        feedback_dir=feedback_dir,
        personas=personas,
        scenarios=scenarios,
    )
    return builder.build()


def run_app(
    spec: BackendSpec,
    host: str = "127.0.0.1",
    port: int = 8000,
    reload: bool = False,
    db_path: str | Path | None = None,
    use_database: bool = True,
    enable_auth: bool = False,
    auth_db_path: str | Path | None = None,
    enable_files: bool = False,
    files_path: str | Path | None = None,
    files_db_path: str | Path | None = None,
    enable_test_mode: bool = False,
    services_dir: str | Path | None = None,
    enable_dev_mode: bool = False,
    feedback_dir: str | Path | None = None,
    personas: list[dict[str, Any]] | None = None,
    scenarios: list[dict[str, Any]] | None = None,
) -> None:
    """
    Run a DNR-Back application.

    Args:
        spec: Backend specification
        host: Host to bind to
        port: Port to bind to
        reload: Enable auto-reload (for development)
        db_path: Path to SQLite database (default: .dazzle/data.db)
        use_database: Whether to use SQLite persistence (default: True)
        enable_auth: Whether to enable authentication (default: False)
        auth_db_path: Path to auth database (default: .dazzle/auth.db)
        enable_files: Whether to enable file uploads (default: False)
        files_path: Path for file storage (default: .dazzle/uploads)
        files_db_path: Path to file metadata database (default: .dazzle/files.db)
        enable_test_mode: Whether to enable /__test__/* endpoints (default: False)
        services_dir: Path to domain service stubs directory (default: services/)
        enable_dev_mode: Enable Dazzle Bar control plane (default: False)
        feedback_dir: Directory for feedback logs (default: .dazzle/feedback)
        personas: List of persona configurations for Dazzle Bar
        scenarios: List of scenario configurations for Dazzle Bar

    Example:
        >>> from dazzle_back.specs import BackendSpec
        >>> spec = BackendSpec(name="my_app", ...)
        >>> run_app(spec)  # Starts server on http://127.0.0.1:8000
    """
    try:
        import uvicorn
    except ImportError:
        raise RuntimeError("uvicorn is not installed. Install with: pip install uvicorn")

    app = create_app(
        spec,
        db_path=db_path,
        use_database=use_database,
        enable_auth=enable_auth,
        auth_db_path=auth_db_path,
        enable_files=enable_files,
        files_path=files_path,
        files_db_path=files_db_path,
        enable_test_mode=enable_test_mode,
        services_dir=services_dir,
        enable_dev_mode=enable_dev_mode,
        feedback_dir=feedback_dir,
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
    import json
    from pathlib import Path

    spec_dict = json.loads(Path(json_path).read_text())
    return create_app_from_dict(spec_dict)


# =============================================================================
# Production Factory (Heroku, etc.)
# =============================================================================


def create_app_factory() -> FastAPI:
    """
    ASGI factory for production deployment.

    Creates a FastAPI application by loading the DSL spec from the project
    directory and configuring from environment variables. Designed for use
    with Uvicorn's --factory flag.

    Environment Variables:
        DAZZLE_PROJECT_ROOT: Project root directory (default: current directory)
        DATABASE_URL: PostgreSQL connection URL (Heroku format supported)
        REDIS_URL: Redis connection URL (for sessions/cache)
        DAZZLE_ENV: Environment name (development/staging/production)
        DAZZLE_SECRET_KEY: Secret key for sessions/tokens

    Usage:
        uvicorn dazzle_back.runtime.server:create_app_factory --factory --host 0.0.0.0 --port $PORT

    Procfile example:
        web: uvicorn dazzle_back.runtime.server:create_app_factory --factory --host 0.0.0.0 --port $PORT

    Returns:
        FastAPI application configured for production
    """
    import logging
    import os
    from pathlib import Path

    logger = logging.getLogger(__name__)

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
        from dazzle.core.sitespec_loader import load_sitespec, sitespec_exists
        from dazzle_back.converters import convert_appspec_to_backend
    except ImportError as e:
        raise RuntimeError(
            f"Dazzle core modules not available: {e}. "
            "Ensure dazzle is installed: pip install dazzle"
        )

    # Load manifest
    logger.info(f"Loading Dazzle project from {project_root}")
    manifest = load_manifest(manifest_path)

    # Parse DATABASE_URL (convert Heroku's postgres:// to postgresql://)
    database_url = os.environ.get("DATABASE_URL", "")
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
        logger.info("Converted postgres:// to postgresql:// for SQLAlchemy compatibility")

    # Parse REDIS_URL (Heroku format: redis://h:password@host:port)
    redis_url = os.environ.get("REDIS_URL", "")
    if redis_url:
        logger.info("Redis URL configured")

    # Determine environment
    dazzle_env = os.environ.get("DAZZLE_ENV", "production")
    enable_dev_mode = dazzle_env == "development"
    enable_test_mode = dazzle_env in ("development", "test")

    # Parse DSL and build spec
    try:
        dsl_files = discover_dsl_files(project_root, manifest)
        modules = parse_modules(dsl_files)
        appspec = build_appspec(modules, manifest.project_root)
    except (ParseError, DazzleError) as e:
        raise RuntimeError(f"Failed to parse DSL: {e}")

    # Convert to backend spec
    backend_spec = convert_appspec_to_backend(appspec)

    # Load SiteSpec if available
    sitespec_data = None
    if sitespec_exists(project_root):
        try:
            sitespec = load_sitespec(project_root)
            sitespec_data = sitespec.model_dump()
            logger.info(f"Loaded SiteSpec with {len(sitespec.pages)} pages")
        except Exception as e:
            logger.warning(f"Failed to load sitespec.yaml: {e}")

    # Extract personas for Dazzle Bar (if enabled)
    personas = (
        [
            {
                "id": p.id,
                "label": p.label,
                "description": p.description,
                "goals": p.goals,
            }
            for p in appspec.personas
        ]
        if enable_dev_mode
        else []
    )

    # Build server config
    config = ServerConfig(
        database_url=database_url if database_url else None,
        db_path=project_root / ".dazzle" / "data.db",
        use_database=True,
        enable_auth=manifest.auth.enabled,
        auth_config=manifest.auth if manifest.auth.enabled else None,
        auth_db_path=project_root / ".dazzle" / "auth.db",
        enable_files=True,
        files_path=project_root / ".dazzle" / "uploads",
        files_db_path=project_root / ".dazzle" / "files.db",
        enable_test_mode=enable_test_mode,
        services_dir=project_root / "services",
        enable_dev_mode=enable_dev_mode,
        feedback_dir=project_root / ".dazzle" / "feedback",
        personas=personas,
        scenarios=[],
        sitespec_data=sitespec_data,
        project_root=project_root,
        enable_processes=True,
        process_db_path=project_root / ".dazzle" / "processes.db",
        enable_console=enable_dev_mode,
    )

    # Build and return the FastAPI app
    builder = DNRBackendApp(backend_spec, config=config)
    app = builder.build()

    # Log startup info
    logger.info(f"Dazzle app '{appspec.name}' ready")
    logger.info(f"  Entities: {len(backend_spec.entities)}")
    logger.info(f"  Endpoints: {len(backend_spec.endpoints)}")
    logger.info(f"  Environment: {dazzle_env}")
    logger.info(f"  Database: {'PostgreSQL' if database_url else 'SQLite'}")
    if enable_dev_mode:
        logger.info("  Dazzle Bar: enabled")

    return app
