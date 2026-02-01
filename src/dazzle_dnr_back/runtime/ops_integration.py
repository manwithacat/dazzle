"""
Operations Platform Integration.

Wires together all ops components:
- OpsDatabase (separate from app db)
- HealthAggregator (system health monitoring)
- SSEStreamManager (real-time streaming)
- AnalyticsCollector (tenant-scoped analytics)

Provides a single function to mount all ops routes on a FastAPI app.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from dazzle_dnr_back.runtime.analytics_collector import (
    AnalyticsCollector,
    AnalyticsConfig,
    create_analytics_routes,
)
from dazzle_dnr_back.runtime.api_middleware import (
    ApiTrackingMiddleware,
    create_tracked_client,
)
from dazzle_dnr_back.runtime.api_tracker import (
    ApiTracker,
    configure_anthropic_tracking,
    configure_openai_tracking,
)
from dazzle_dnr_back.runtime.console_routes import create_console_routes
from dazzle_dnr_back.runtime.email_templates import (
    BrandConfig,
    EmailTemplateEngine,
    create_email_tracking_routes,
)
from dazzle_dnr_back.runtime.health_aggregator import (
    HealthAggregator,
    create_database_check,
    create_event_bus_check,
    create_websocket_check,
)
from dazzle_dnr_back.runtime.ops_database import (
    ComponentType,
    OpsDatabase,
    RetentionConfig,
)
from dazzle_dnr_back.runtime.ops_routes import create_ops_routes
from dazzle_dnr_back.runtime.ops_simulator import OpsSimulator
from dazzle_dnr_back.runtime.sse_stream import SSEStreamManager, create_sse_routes

if TYPE_CHECKING:
    from fastapi import FastAPI

    from dazzle_dnr_back.events.bus import EventBus
    from dazzle_dnr_back.runtime.websocket_manager import WebSocketManager


class OpsConfig:
    """Configuration for the Operations Platform."""

    def __init__(
        self,
        ops_db_path: Path | None = None,
        require_auth: bool = True,
        retention: RetentionConfig | None = None,
        analytics_enabled: bool = True,
        health_check_interval: float = 30.0,
        sse_heartbeat_interval: float = 30.0,
        brand_config: BrandConfig | None = None,
        tracking_base_url: str | None = None,
    ):
        """
        Initialize ops configuration.

        Args:
            ops_db_path: Path to ops database. Defaults to .dazzle/ops.db
            require_auth: Whether to require authentication for ops routes
            retention: Data retention configuration
            analytics_enabled: Whether to collect analytics
            health_check_interval: Seconds between health checks
            sse_heartbeat_interval: Seconds between SSE heartbeats
            brand_config: Brand configuration for email templates
            tracking_base_url: Base URL for email tracking (e.g., https://app.example.com)
        """
        self.ops_db_path = ops_db_path or Path(".dazzle/ops.db")
        self.require_auth = require_auth
        self.retention = retention or RetentionConfig()
        self.analytics_enabled = analytics_enabled
        self.health_check_interval = health_check_interval
        self.sse_heartbeat_interval = sse_heartbeat_interval
        self.brand_config = brand_config
        self.tracking_base_url = tracking_base_url
        self.enable_console = True


class OpsPlatform:
    """
    Operations Platform manager.

    Provides centralized access to all ops components and handles
    lifecycle management.
    """

    def __init__(self, config: OpsConfig | None = None):
        """Initialize the ops platform."""
        self.config = config or OpsConfig()

        # Core components
        self.ops_db = OpsDatabase(
            db_path=self.config.ops_db_path,
            retention=self.config.retention,
        )

        # Will be set when event_bus is provided
        self.health_aggregator: HealthAggregator | None = None
        self.sse_manager: SSEStreamManager | None = None
        self.analytics_collector: AnalyticsCollector | None = None
        self.api_tracker: ApiTracker | None = None
        self.email_engine: EmailTemplateEngine | None = None
        self.simulator: OpsSimulator | None = None
        self.appspec: Any = None
        self.spec_version_store: Any = None
        self.deploy_history_store: Any = None
        self.rollback_manager: Any = None

    def configure(
        self,
        event_bus: EventBus | None = None,
        ws_manager: WebSocketManager | None = None,
        app_db_path: str | None = None,
    ) -> None:
        """
        Configure platform with runtime dependencies.

        Args:
            event_bus: Event bus for SSE streaming
            ws_manager: WebSocket manager for health checks
            app_db_path: Path to app database for health checks
        """
        # Health aggregator
        self.health_aggregator = HealthAggregator(
            ops_db=self.ops_db,
            event_bus=event_bus,
            check_interval_seconds=self.config.health_check_interval,
        )

        # Register built-in health checks
        if app_db_path:
            self.health_aggregator.register(
                name="app_database",
                component_type=ComponentType.DATABASE,
                check_fn=create_database_check(app_db_path),
            )

        # Ops database health check
        self.health_aggregator.register(
            name="ops_database",
            component_type=ComponentType.DATABASE,
            check_fn=create_database_check(str(self.config.ops_db_path)),
        )

        if event_bus:
            self.health_aggregator.register(
                name="event_bus",
                component_type=ComponentType.EVENT_BUS,
                check_fn=create_event_bus_check(event_bus),
            )

            # SSE manager
            self.sse_manager = SSEStreamManager(
                event_bus=event_bus,
                heartbeat_interval=self.config.sse_heartbeat_interval,
            )

        if ws_manager:
            self.health_aggregator.register(
                name="websocket",
                component_type=ComponentType.WEBSOCKET,
                check_fn=create_websocket_check(ws_manager),
            )

        # Analytics collector
        if self.config.analytics_enabled:
            self.analytics_collector = AnalyticsCollector(
                ops_db=self.ops_db,
                event_bus=event_bus,
                config=AnalyticsConfig(enabled=True),
            )

        # API tracker for external call instrumentation
        self.api_tracker = ApiTracker(
            ops_db=self.ops_db,
            event_bus=event_bus,
        )
        # Pre-configure cost tracking for common LLM providers
        configure_openai_tracking(self.api_tracker)
        configure_anthropic_tracking(self.api_tracker)

        # Email template engine with tracking
        self.email_engine = EmailTemplateEngine(
            ops_db=self.ops_db,
            tracking_base_url=self.config.tracking_base_url,
            brand_config=self.config.brand_config,
        )

        # Simulator for dashboard demo
        self.simulator = OpsSimulator(
            ops_db=self.ops_db,
            event_bus=event_bus,
        )

    async def start(self) -> None:
        """Start all ops services."""
        if self.health_aggregator:
            await self.health_aggregator.start_periodic_checks()

        if self.sse_manager:
            await self.sse_manager.start()

        if self.analytics_collector:
            await self.analytics_collector.start()

    async def stop(self) -> None:
        """Stop all ops services."""
        if self.simulator and self.simulator.running:
            await self.simulator.stop()

        if self.health_aggregator:
            await self.health_aggregator.stop_periodic_checks()

        if self.sse_manager:
            await self.sse_manager.stop()

        if self.analytics_collector:
            await self.analytics_collector.stop()

    def set_appspec(self, appspec: Any) -> None:
        """Set the AppSpec for console features (versioning, app map, etc.)."""
        self.appspec = appspec

        # Initialize spec versioning
        try:
            from dazzle_dnr_back.runtime.spec_versioning import SpecVersionStore

            self.spec_version_store = SpecVersionStore(self.ops_db)
            self.spec_version_store.save_version(appspec)
        except Exception:
            import logging

            logging.getLogger("dazzle.ops").debug("Spec versioning not available")

        # Initialize deploy history
        try:
            from dazzle_dnr_back.runtime.deploy_history import DeployHistoryStore

            self.deploy_history_store = DeployHistoryStore(self.ops_db)
        except Exception:
            pass

        # Initialize rollback manager
        try:
            from dazzle_dnr_back.runtime.rollback_manager import RollbackManager

            if self.spec_version_store:
                self.rollback_manager = RollbackManager(
                    spec_version_store=self.spec_version_store,
                    deploy_history_store=self.deploy_history_store,
                )
        except Exception:
            pass

    def create_routes(self) -> list[Any]:
        """
        Create all ops routes.

        Returns:
            List of FastAPI routers to mount
        """
        routers = []

        # Main ops routes
        routers.append(
            create_ops_routes(
                ops_db=self.ops_db,
                health_aggregator=self.health_aggregator,
                sse_manager=self.sse_manager,
                simulator=self.simulator,
                require_auth=self.config.require_auth,
            )
        )

        # SSE routes
        if self.sse_manager:
            routers.append(create_sse_routes(self.sse_manager))

        # Analytics routes
        if self.analytics_collector:
            routers.append(create_analytics_routes(self.analytics_collector))

        # Email tracking routes
        if self.email_engine:
            routers.append(create_email_tracking_routes(self.email_engine))

        # Founder Console routes
        if self.config.enable_console:
            try:
                console_router = create_console_routes(
                    ops_db=self.ops_db,
                    health_aggregator=self.health_aggregator,
                    appspec=self.appspec,
                    spec_version_store=self.spec_version_store,
                    deploy_history_store=self.deploy_history_store,
                    require_auth=self.config.require_auth,
                )
                routers.append(console_router)

                # Deploy routes
                from dazzle_dnr_back.runtime.deploy_routes import create_deploy_routes

                deploy_router = create_deploy_routes(
                    deploy_history_store=self.deploy_history_store,
                    spec_version_store=self.spec_version_store,
                    rollback_manager=self.rollback_manager,
                    appspec=self.appspec,
                )
                routers.append(deploy_router)
            except Exception:
                import logging

                logging.getLogger("dazzle.ops").debug("Console routes not available")

        return routers

    def create_http_client(
        self,
        service_name: str,
        base_url: str = "",
        **httpx_kwargs: Any,
    ) -> Any:
        """
        Create a tracked HTTP client for external API calls.

        The client automatically tracks latency, errors, and costs.

        Args:
            service_name: Name of the external service (e.g., "stripe", "openai")
            base_url: Base URL for the service
            **httpx_kwargs: Additional kwargs for httpx.AsyncClient

        Returns:
            TrackedHttpxClient with automatic tracking

        Example:
            ```python
            client = ops_platform.create_http_client("stripe", "https://api.stripe.com")
            response = await client.post("/v1/charges", json=charge_data)
            # Latency, status, and cost automatically tracked
            ```
        """
        if not self.api_tracker:
            raise RuntimeError("API tracker not configured. Call configure() first.")

        return create_tracked_client(
            tracker=self.api_tracker,
            service_name=service_name,
            base_url=base_url,
            **httpx_kwargs,
        )

    def render_email(
        self,
        template_name: str,
        recipient: str,
        context: dict[str, Any] | None = None,
        track: bool = True,
    ) -> Any:
        """
        Render an email using the template engine.

        This is a convenience method for sending tracked emails.

        Args:
            template_name: Name of the template (e.g., "welcome", "notification")
            recipient: Email recipient address
            context: Variables to substitute in template
            track: Whether to enable open/click tracking

        Returns:
            RenderedEmail object ready for sending

        Example:
            ```python
            email = ops_platform.render_email(
                template_name="welcome",
                recipient="user@example.com",
                context={
                    "user_name": "John",
                    "action_url": "https://app.example.com/start",
                    "action_text": "Get Started",
                },
            )
            # email.subject, email.body_html, email.body_text ready for SMTP
            ```
        """
        if not self.email_engine:
            raise RuntimeError("Email engine not configured. Call configure() first.")

        return self.email_engine.render(
            template_name=template_name,
            context=context or {},
            recipient=recipient,
            track_opens=track,
            track_clicks=track,
        )

    def record_event(
        self,
        event_type: str,
        entity_name: str | None = None,
        entity_id: str | None = None,
        payload: dict[str, Any] | None = None,
        tenant_id: str | None = None,
        user_id: str | None = None,
        correlation_id: str | None = None,
    ) -> str:
        """
        Record an event to the ops event log.

        Args:
            event_type: Type of event
            entity_name: Optional entity name
            entity_id: Optional entity ID
            payload: Event payload
            tenant_id: Tenant ID for scoping
            user_id: User who triggered the event
            correlation_id: Correlation ID for tracing

        Returns:
            Event ID
        """
        return self.ops_db.record_event(
            event_type=event_type,
            entity_name=entity_name,
            entity_id=entity_id,
            payload=payload,
            tenant_id=tenant_id,
            user_id=user_id,
            correlation_id=correlation_id,
        )


def mount_ops_platform(
    app: FastAPI,
    config: OpsConfig | None = None,
    event_bus: EventBus | None = None,
    ws_manager: WebSocketManager | None = None,
    app_db_path: str | None = None,
    appspec: Any = None,
) -> OpsPlatform:
    """
    Mount the Operations Platform on a FastAPI app.

    This is the main entry point for integrating ops into a DNR app.

    Args:
        app: FastAPI application
        config: Ops configuration
        event_bus: Event bus for real-time features
        ws_manager: WebSocket manager
        app_db_path: Path to application database

    Returns:
        OpsPlatform instance for further configuration

    Example:
        ```python
        from fastapi import FastAPI
        from dazzle_dnr_back.runtime.ops_integration import mount_ops_platform

        app = FastAPI()
        ops = mount_ops_platform(app, event_bus=my_event_bus)

        @app.on_event("startup")
        async def startup():
            await ops.start()

        @app.on_event("shutdown")
        async def shutdown():
            await ops.stop()
        ```
    """
    platform = OpsPlatform(config)
    platform.configure(
        event_bus=event_bus,
        ws_manager=ws_manager,
        app_db_path=app_db_path,
    )

    # Set AppSpec for console features
    if appspec:
        platform.set_appspec(appspec)

    # Add API tracking middleware for request correlation
    if platform.api_tracker:
        app.add_middleware(ApiTrackingMiddleware, tracker=platform.api_tracker)

    # Mount all routes
    for router in platform.create_routes():
        app.include_router(router)

    # Mount static files for ops UI
    try:
        from fastapi.staticfiles import StaticFiles

        # Find the ops UI directory
        import dazzle_dnr_ui

        ui_path = Path(dazzle_dnr_ui.__file__).parent / "runtime" / "static" / "ops"
        if ui_path.exists():
            app.mount(
                "/_ops/ui",
                StaticFiles(directory=str(ui_path), html=True),
                name="ops_ui",
            )
    except Exception:
        pass  # UI mounting is optional

    return platform
