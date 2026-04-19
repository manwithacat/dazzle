"""Tiny stdlib-only ``.env`` loader shared across CLI commands.

``dazzle serve`` has always auto-loaded ``<project_root>/.env`` so users
can set ``DATABASE_URL`` / ``REDIS_URL`` per-project without exporting
them in the shell. Before this module existed, only ``serve`` did that —
every other CLI command (``dazzle db reset``, ``dazzle qa trial`` and so
on) inherited only the shell environment, which meant DB commands
silently connected to whichever default the manifest picked (often the
wrong database), producing mysterious "relation does not exist" errors
(#814).

Usage: call :func:`load_project_dotenv` from any CLI command that
depends on ``DATABASE_URL`` / ``REDIS_URL`` / other project env vars
before resolving them.
"""

from __future__ import annotations

import os
from pathlib import Path


def load_project_dotenv(project_root: Path) -> list[str]:
    """Load environment variables from ``<project_root>/.env`` if present.

    Existing shell exports take precedence — we only set variables that
    aren't already in ``os.environ``. Returns the list of variables that
    were actually loaded (so callers can log what happened).
    """
    env_file = project_root / ".env"
    if not env_file.exists():
        return []

    try:
        content = env_file.read_text()
    except OSError:
        return []

    loaded: list[str] = []
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value
            loaded.append(key)

    return loaded
