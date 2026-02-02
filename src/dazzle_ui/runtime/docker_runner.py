"""
Docker runner for DNR applications.

Provides docker-first infrastructure for running DNR applications in containers.
This is the default way to run Dazzle apps in development.

Usage:
    from dazzle_ui.runtime.docker_runner import run_in_docker, is_docker_available

    if is_docker_available():
        run_in_docker(project_path, frontend_port=3000, api_port=8000)
    else:
        # Fall back to local execution
        run_local(...)

Note: This module re-exports from the docker subpackage for backward compatibility.
The implementation has been refactored into:
- docker/utils.py - Docker availability checks
- docker/templates.py - Dockerfile and compose templates
- docker/runner.py - DockerRunner class and convenience functions
"""

from __future__ import annotations

# Re-export everything from the docker subpackage for backward compatibility
from .docker import (
    # Templates
    DAZZLE_BACKEND_DOCKERFILE,
    DAZZLE_COMPOSE_TEMPLATE,
    DAZZLE_DOCKERIGNORE,
    DAZZLE_FRONTEND_DOCKERFILE,
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
    "DAZZLE_FRONTEND_DOCKERFILE",
    "DAZZLE_COMPOSE_TEMPLATE",
    "DAZZLE_DOCKERIGNORE",
    # Runner
    "DockerRunConfig",
    "DockerRunner",
    "run_in_docker",
    "stop_docker_container",
]
