"""
Control Plane FastAPI Application.

Provides the dashboard and API endpoints for observability.
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application lifecycle."""
    import redis

    from .log_store import LogStore
    from .metrics_collector import MetricsCollector
    from .process_monitor import ProcessMonitor

    # Initialize Redis connection
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")

    # Handle Heroku/AWS Redis SSL
    ssl_cert_reqs = None if "amazonaws.com" in redis_url else "required"
    redis_client: redis.Redis[Any] = redis.from_url(
        redis_url,
        decode_responses=True,
        ssl_cert_reqs=ssl_cert_reqs,
    )

    # Initialize components
    app.state.log_store = LogStore(redis_client)
    app.state.process_monitor = ProcessMonitor(redis_client)

    # Start metrics collector background task
    collector = MetricsCollector.from_env()
    app.state.metrics_collector = collector
    collector_task = asyncio.create_task(collector.run())

    logger.info("Control plane started")
    yield

    # Shutdown
    collector.stop()
    collector_task.cancel()
    try:
        await collector_task
    except asyncio.CancelledError:
        pass
    logger.info("Control plane stopped")


def create_app() -> FastAPI:
    """Create the control plane FastAPI application."""
    app = FastAPI(
        title="Dazzle Control Plane",
        description="Observability and monitoring for Dazzle applications",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Register routes
    from .api import router as api_router
    from .dashboard import router as dashboard_router

    app.include_router(dashboard_router)
    app.include_router(api_router, prefix="/api")

    # Health check
    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "healthy", "service": "control-plane"}

    return app


def create_app_factory() -> FastAPI:
    """ASGI factory for production deployment."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    return create_app()
