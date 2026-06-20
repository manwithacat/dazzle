"""
Docker subpackage for Dazzle runtime.

Provides Docker availability checks for dev infrastructure.
"""

from .utils import get_docker_version, is_docker_available

__all__ = [
    "is_docker_available",
    "get_docker_version",
]
