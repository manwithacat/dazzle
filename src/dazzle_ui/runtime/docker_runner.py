"""
Docker runner for Dazzle applications.

Provides docker-first infrastructure for running Dazzle applications in containers.

Note: This module re-exports from the docker subpackage for backward compatibility.
The implementation lives in:
- docker/utils.py - Docker availability checks
- docker/templates.py - Dockerfile and compose templates
- docker/runner.py - DockerRunner class and convenience functions
"""

from __future__ import annotations

# Re-export everything from the docker subpackage for backward compatibility
from .docker import (
    # Templates
    DAZZLE_BACKEND_DOCKERFILE,
    DAZZLE_DOCKERIGNORE,
    DAZZLE_SINGLE_COMPOSE_TEMPLATE,
    # Runner
    DockerRunConfig,
    DockerRunner,
    # Utilities
    get_docker_version,
    is_docker_available,
    run_in_docker,
    stop_docker_container,
)

__all__ = [
    # Utilities
    "is_docker_available",
    "get_docker_version",
    # Templates
    "DAZZLE_BACKEND_DOCKERFILE",
    "DAZZLE_SINGLE_COMPOSE_TEMPLATE",
    "DAZZLE_DOCKERIGNORE",
    # Runner
    "DockerRunConfig",
    "DockerRunner",
    "run_in_docker",
    "stop_docker_container",
]
