"""
Docker utility functions.

Provides Docker availability checks and version detection.
"""

from __future__ import annotations

import subprocess


def is_docker_available() -> bool:
    """
    Check if Docker is available on the system.

    Returns:
        True if Docker is installed and the daemon is running
    """
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (subprocess.SubprocessError, FileNotFoundError, subprocess.TimeoutExpired):
        return False


def get_docker_version() -> str | None:
    """
    Get the Docker version string.

    Returns:
        Docker version string or None if not available
    """
    try:
        result = subprocess.run(
            ["docker", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except (subprocess.SubprocessError, FileNotFoundError, subprocess.TimeoutExpired):
        return None
