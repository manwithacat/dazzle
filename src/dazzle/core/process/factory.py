"""
Process adapter factory for backend selection.

This module provides automatic backend selection based on configuration
and availability, allowing seamless switching between EventBus (Redis)
and Temporal backends.
"""

import logging
import os
import socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from .adapter import ProcessAdapter

logger = logging.getLogger(__name__)


BackendType = Literal["auto", "celery", "eventbus", "temporal"]


@dataclass
class EventBusConfig:
    """Configuration for EventBusProcessAdapter."""

    redis_url: str | None = None  # Defaults to REDIS_URL env var


@dataclass
class CeleryConfig:
    """Configuration for CeleryProcessAdapter."""

    redis_url: str | None = None  # Defaults to REDIS_URL env var


@dataclass
class TemporalConfig:
    """Configuration for TemporalAdapter."""

    host: str = "localhost"
    port: int = 7233
    namespace: str = "default"
    task_queue: str = "dazzle"
    connect_timeout_seconds: float = 5.0


@dataclass
class ProcessConfig:
    """
    Configuration for process execution backend.

    Examples:
        # Auto-detect mode
        config = ProcessConfig(backend="auto")
        adapter = create_adapter(config)

        # Production with Temporal
        config = ProcessConfig(
            backend="temporal",
            temporal=TemporalConfig(host="temporal.prod.internal")
        )
        adapter = create_adapter(config)
    """

    backend: BackendType = "auto"
    eventbus: EventBusConfig = field(default_factory=EventBusConfig)
    celery: CeleryConfig = field(default_factory=CeleryConfig)
    temporal: TemporalConfig = field(default_factory=TemporalConfig)

    # Project root for database paths
    project_root: Path | None = None


def create_adapter(config: ProcessConfig) -> ProcessAdapter:
    """
    Create the appropriate ProcessAdapter based on configuration.

    Selection logic:
    1. If backend is "temporal" or "eventbus", use that directly
    2. If backend is "auto":
       a. Check if Temporal SDK is installed and server is reachable
       b. Check if REDIS_URL is set -> EventBus
       c. Raise ValueError if no backend available

    Args:
        config: Process configuration

    Returns:
        ProcessAdapter instance (not yet initialized)

    Raises:
        ValueError: If requested backend is not available
    """
    backend = config.backend

    if backend == "auto":
        backend = _detect_backend(config)
        logger.info("Auto-detected process backend: %s", backend)

    if backend == "temporal":
        return _create_temporal_adapter(config)
    elif backend == "eventbus":
        return _create_eventbus_adapter(config)
    elif backend == "celery":
        return _create_celery_adapter(config)
    else:
        raise ValueError(f"Unknown process backend: {backend}")


def _detect_backend(config: ProcessConfig) -> BackendType:
    """
    Auto-detect the best available backend.

    Detection order:
    1. Temporal SDK installed + server reachable -> "temporal"
    2. REDIS_URL in environment -> "eventbus"
    3. No backend available -> raise ValueError
    """
    # Check if Temporal SDK is installed and server reachable
    try:
        import temporalio  # noqa: F401

        logger.debug("Temporal SDK is installed")
        if _temporal_available(config.temporal):
            logger.debug(
                "Temporal server reachable at %s:%s",
                config.temporal.host,
                config.temporal.port,
            )
            return "temporal"
        else:
            logger.debug("Temporal server not reachable")
    except ImportError:
        logger.debug("Temporal SDK not installed")

    # Check for Redis → EventBus (preferred over Celery)
    redis_url = config.eventbus.redis_url or config.celery.redis_url or os.environ.get("REDIS_URL")
    if redis_url:
        logger.debug("REDIS_URL set, using EventBus backend (native event-driven)")
        return "eventbus"

    raise ValueError(
        "No process backend available. Set REDIS_URL for EventBus "
        "or install temporalio for Temporal."
    )


def _temporal_available(config: TemporalConfig) -> bool:
    """
    Check if Temporal server is reachable.

    Args:
        config: Temporal configuration

    Returns:
        True if server responds to TCP connection
    """
    try:
        sock = socket.create_connection(
            (config.host, config.port),
            timeout=config.connect_timeout_seconds,
        )
        sock.close()
        return True
    except OSError as e:
        logger.debug("Temporal connection failed: %s", e)
        return False


def _create_temporal_adapter(config: ProcessConfig) -> ProcessAdapter:
    """Create TemporalAdapter with configuration."""
    try:
        from .temporal_adapter import TemporalAdapter
    except ImportError as e:
        raise ValueError(
            "Temporal backend requested but temporalio not installed. "
            "Install with: pip install dazzle[temporal]"
        ) from e

    if not _temporal_available(config.temporal):
        raise ValueError(
            f"Temporal server not reachable at {config.temporal.host}:{config.temporal.port}"
        )

    return TemporalAdapter(
        host=config.temporal.host,
        port=config.temporal.port,
        namespace=config.temporal.namespace,
        task_queue=config.temporal.task_queue,
    )


def _create_eventbus_adapter(config: ProcessConfig) -> ProcessAdapter:
    """Create EventBusProcessAdapter with configuration."""
    from .eventbus_adapter import EventBusProcessAdapter

    redis_url = config.eventbus.redis_url or config.celery.redis_url or os.environ.get("REDIS_URL")
    return EventBusProcessAdapter(redis_url=redis_url)


def _create_celery_adapter(config: ProcessConfig) -> ProcessAdapter:
    """Create CeleryProcessAdapter with configuration."""
    try:
        from .celery_adapter import CeleryProcessAdapter
    except ImportError as e:
        raise ValueError(
            "Celery backend requested but celery/redis not installed. "
            "Install with: pip install dazzle[celery]"
        ) from e

    redis_url = config.celery.redis_url or os.environ.get("REDIS_URL")
    return CeleryProcessAdapter(redis_url=redis_url)


def get_backend_info(config: ProcessConfig) -> dict[str, str | bool]:
    """
    Get information about available backends.

    Returns:
        Dictionary with backend availability and configuration info
    """
    info: dict[str, str | bool] = {
        "configured_backend": config.backend,
        "eventbus_available": bool(os.environ.get("REDIS_URL")),
        "celery_available": False,
        "redis_url_set": bool(os.environ.get("REDIS_URL")),
        "temporal_sdk_installed": False,
        "temporal_server_reachable": False,
    }

    try:
        import celery as _celery  # noqa: F401

        info["celery_available"] = True
    except ImportError:
        pass

    try:
        import temporalio  # noqa: F401

        info["temporal_sdk_installed"] = True
        info["temporal_sdk_version"] = getattr(temporalio, "__version__", "unknown")
    except ImportError:
        pass

    if info["temporal_sdk_installed"]:
        info["temporal_server_reachable"] = _temporal_available(config.temporal)
        info["temporal_host"] = f"{config.temporal.host}:{config.temporal.port}"

    return info
