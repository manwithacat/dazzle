"""Active environment profile for the CLI session.

Set by the ``--env`` global flag or ``DAZZLE_ENV`` environment variable.
Read by database-touching commands to select the right connection.
"""

import os

_active_env: str = ""


def resolve_env_name(cli_flag: str) -> str:
    """Resolve the active environment name.

    Priority:
        1. ``--env`` CLI flag (non-empty value)
        2. ``DAZZLE_ENV`` environment variable
        3. Empty string (no profile — existing behaviour)
    """
    if cli_flag:
        return cli_flag
    return os.environ.get("DAZZLE_ENV", "")


def set_active_env(name: str) -> None:
    """Store the active environment name for the CLI session."""
    global _active_env  # noqa: PLW0603
    _active_env = name


def get_active_env() -> str:
    """Get the active environment name."""
    return _active_env
