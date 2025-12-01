"""
Docker subpackage for DNR runtime.

This package provides Docker-first infrastructure for running DNR applications.
It contains:
- templates: Dockerfile, docker-compose, and entrypoint templates
- utils: Docker availability checks
- entrypoint: Self-contained FastAPI server script for containers
- runner: DockerRunner class and convenience functions

Usage:
    from dazzle_dnr_ui.runtime.docker import (
        is_docker_available,
        get_docker_version,
        run_in_docker,
        stop_docker_container,
        DockerRunner,
        DockerRunConfig,
    )
"""

from __future__ import annotations

# Entrypoint
from .entrypoint import DNR_ENTRYPOINT_TEMPLATE

# Runner
from .runner import (
    DockerRunConfig,
    DockerRunner,
    run_in_docker,
    stop_docker_container,
)

# Templates
from .templates import (
    DNR_BACKEND_DOCKERFILE,
    DNR_COMPOSE_TEMPLATE,
    DNR_DOCKERFILE_TEMPLATE,
    DNR_DOCKERIGNORE,
    DNR_FRONTEND_DOCKERFILE,
    generate_dockerfile,
)

# Utilities
from .utils import get_docker_version, is_docker_available

__all__ = [
    # Utilities
    "is_docker_available",
    "get_docker_version",
    # Templates
    "DNR_DOCKERFILE_TEMPLATE",
    "DNR_BACKEND_DOCKERFILE",
    "DNR_FRONTEND_DOCKERFILE",
    "DNR_COMPOSE_TEMPLATE",
    "DNR_DOCKERIGNORE",
    "generate_dockerfile",
    # Entrypoint
    "DNR_ENTRYPOINT_TEMPLATE",
    # Runner
    "DockerRunConfig",
    "DockerRunner",
    "run_in_docker",
    "stop_docker_container",
]
