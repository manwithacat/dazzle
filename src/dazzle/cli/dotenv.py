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

For **managed** servers (qa trial, interaction verify, e2e), also call
:func:`apply_project_infra_urls` so a shell ``DATABASE_URL`` left over
from another example app cannot pin the managed process to the wrong
Postgres (support_tickets trial against invoice_ops → missing columns).
"""

from __future__ import annotations

import os
from pathlib import Path

# Infra keys that must track the project under test for managed subprocesses.
_PROJECT_INFRA_KEYS = frozenset({"DATABASE_URL", "REDIS_URL"})


def _parse_env_file(env_file: Path) -> dict[str, str]:
    """Parse a dotenv file into key→value (empty if missing/unreadable)."""
    if not env_file.exists():
        return {}
    try:
        content = env_file.read_text(encoding="utf-8")
    except OSError:
        return {}

    parsed: dict[str, str] = {}
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
        if key:
            parsed[key] = value
    return parsed


def load_project_dotenv(project_root: Path) -> list[str]:
    """Load environment variables from ``<project_root>/.env`` if present.

    Existing shell exports take precedence — we only set variables that
    aren't already in ``os.environ``. Returns the list of variables that
    were actually loaded (so callers can log what happened).

    For managed multi-app hosts that must bind to the *project* database
    even when the shell still holds another app's ``DATABASE_URL``, call
    :func:`apply_project_infra_urls` after this (or instead of relying
    on shell precedence for infra keys alone).
    """
    env_file = project_root / ".env"
    parsed = _parse_env_file(env_file)
    if not parsed:
        return []

    loaded: list[str] = []
    for key, value in parsed.items():
        if key not in os.environ:
            os.environ[key] = value
            loaded.append(key)

    return loaded


def project_infra_env(project_root: Path) -> dict[str, str]:
    """Return ``DATABASE_URL`` / ``REDIS_URL`` from the project ``.env`` only."""
    parsed = _parse_env_file(project_root / ".env")
    return {k: parsed[k] for k in _PROJECT_INFRA_KEYS if k in parsed}


def apply_project_infra_urls(project_root: Path) -> list[str]:
    """Force ``DATABASE_URL`` / ``REDIS_URL`` from the project ``.env``.

    Shell-export precedence is correct for interactive ``dazzle serve``
    (operator may intentionally point at a remote DB). Managed servers
    (qa trial, contract verify, e2e) must always use the project under
    test — otherwise a host that previously exported another example's
    URL seeds against the wrong schema (e.g. support_tickets trial
    inserting ``User.role`` into invoice_ops).

    Returns the keys that were applied from the project file.
    """
    infra = project_infra_env(project_root)
    for key, value in infra.items():
        os.environ[key] = value
    return list(infra.keys())
