"""
Docker subpackage for DNR runtime.

This package provides Docker-first infrastructure for running DNR applications.
It contains:
- templates: Dockerfile and docker-compose templates for split container mode
- utils: Docker availability checks
- runner: DockerRunner class and convenience functions

Usage:
    from dazzle_ui.runtime.docker import (
        is_docker_available,
        get_docker_version,
        run_in_docker,
        stop_docker_container,
        DockerRunner,
        DockerRunConfig,
    )
"""

from __future__ import annotations

# Runner
from .runner import (
    DockerRunConfig,
    DockerRunner,
    run_in_docker,
    stop_docker_container,
)

# Templates
from .templates import (
    DAZZLE_BACKEND_DOCKERFILE,
    DAZZLE_COMPOSE_TEMPLATE,
    DAZZLE_DOCKERIGNORE,
    DAZZLE_FRONTEND_DOCKERFILE,
)

# Utilities
from .utils import get_docker_version, is_docker_available

__all__ = [
    # Utilities
    "is_docker_available",
    "get_docker_version",
    # Templates
    "DAZZLE_BACKEND_DOCKERFILE",
    "DAZZLE_FRONTEND_DOCKERFILE",
    "DAZZLE_COMPOSE_TEMPLATE",
    "DAZZLE_DOCKERIGNORE",
    # Runner
    "DockerRunConfig",
    "DockerRunner",
    "run_in_docker",
    "stop_docker_container",
]
