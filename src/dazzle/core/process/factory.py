"""
Process adapter factory for backend selection.

This module provides automatic backend selection based on configuration
and availability, allowing seamless switching between development
(LiteProcessAdapter) and production (TemporalAdapter) backends.
"""

from __future__ import annotations

import logging
import socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from .adapter import ProcessAdapter

logger = logging.getLogger(__name__)


BackendType = Literal["auto", "lite", "temporal"]


@dataclass
class LiteConfig:
    """Configuration for LiteProcessAdapter."""

    db_path: str = ".dazzle/processes.db"
    poll_interval_seconds: float = 1.0
    scheduler_interval_seconds: float = 60.0


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
        # Development mode (automatic)
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
    lite: LiteConfig = field(default_factory=LiteConfig)
    temporal: TemporalConfig = field(default_factory=TemporalConfig)

    # Project root for database paths
    project_root: Path | None = None


def create_adapter(config: ProcessConfig) -> ProcessAdapter:
    """
    Create the appropriate ProcessAdapter based on configuration.

    Selection logic:
    1. If backend is "lite" or "temporal", use that directly
    2. If backend is "auto":
       a. Check if Temporal SDK is installed
       b. Check if Temporal server is reachable
       c. Fall back to LiteProcessAdapter if not

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
        logger.info(f"Auto-detected process backend: {backend}")

    if backend == "temporal":
        return _create_temporal_adapter(config)
    elif backend == "lite":
        return _create_lite_adapter(config)
    else:
        raise ValueError(f"Unknown process backend: {backend}")


def _detect_backend(config: ProcessConfig) -> BackendType:
    """
    Auto-detect the best available backend.

    Returns "temporal" if SDK is installed and server is reachable,
    otherwise returns "lite".
    """
    # Check if Temporal SDK is installed
    try:
        import temporalio  # noqa: F401

        logger.debug("Temporal SDK is installed")
    except ImportError:
        logger.debug("Temporal SDK not installed, using lite backend")
        return "lite"

    # Check if Temporal server is reachable
    if _temporal_available(config.temporal):
        logger.debug(f"Temporal server reachable at {config.temporal.host}:{config.temporal.port}")
        return "temporal"
    else:
        logger.debug("Temporal server not reachable, using lite backend")
        return "lite"


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
        logger.debug(f"Temporal connection failed: {e}")
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


def _create_lite_adapter(config: ProcessConfig) -> ProcessAdapter:
    """Create LiteProcessAdapter with configuration."""
    from .lite_adapter import LiteProcessAdapter

    # Resolve database path relative to project root
    db_path = config.lite.db_path
    if config.project_root and not Path(db_path).is_absolute():
        db_path = str(config.project_root / db_path)

    return LiteProcessAdapter(
        db_path=db_path,
        poll_interval=config.lite.poll_interval_seconds,
        scheduler_interval=config.lite.scheduler_interval_seconds,
    )


def get_backend_info(config: ProcessConfig) -> dict[str, str | bool]:
    """
    Get information about available backends.

    Returns:
        Dictionary with backend availability and configuration info
    """
    info: dict[str, str | bool] = {
        "configured_backend": config.backend,
        "lite_available": True,  # Always available
        "temporal_sdk_installed": False,
        "temporal_server_reachable": False,
    }

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
