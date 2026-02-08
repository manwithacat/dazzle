"""Session/auth bridge for viewport testing.

Loads persona session cookies from the SessionManager store and converts
them to Playwright-compatible cookie format for ``context.add_cookies()``.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger("dazzle.testing.viewport_auth")


def load_persona_cookies(
    project_path: Path,
    persona_id: str,
    base_url: str,
) -> list[dict[str, Any]]:
    """Load session cookies in Playwright format for ``context.add_cookies()``.

    Reads the stored session from ``.dazzle/test_sessions/{persona_id}.json``
    and converts the ``session_token`` to a Playwright cookie dict.

    Parameters
    ----------
    project_path:
        Root directory of the project.
    persona_id:
        Persona identifier (e.g. ``"admin"``).
    base_url:
        Base URL of the running app (used to derive cookie domain).

    Returns
    -------
    list[dict[str, Any]]
        Playwright-format cookies, or empty list if no session found.
    """
    session_file = project_path / ".dazzle" / "test_sessions" / f"{persona_id}.json"
    if not session_file.exists():
        logger.debug("No session file for persona '%s'", persona_id)
        return []

    try:
        data = json.loads(session_file.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not read session for '%s': %s", persona_id, exc)
        return []

    token = data.get("session_token")
    if not token:
        logger.debug("No session_token in session file for '%s'", persona_id)
        return []

    parsed = urlparse(base_url)
    domain = parsed.hostname or "localhost"

    return [
        {
            "name": "dazzle_session",
            "value": token,
            "domain": domain,
            "path": "/",
        }
    ]


def ensure_session_exists(
    project_path: Path,
    persona_id: str,
    base_url: str,
) -> bool:
    """Check if a session exists for the persona.

    Parameters
    ----------
    project_path:
        Root directory of the project.
    persona_id:
        Persona identifier.
    base_url:
        Base URL (unused, kept for API symmetry).

    Returns
    -------
    bool
        True if a session file with a token exists.
    """
    session_file = project_path / ".dazzle" / "test_sessions" / f"{persona_id}.json"
    if not session_file.exists():
        return False
    try:
        data = json.loads(session_file.read_text())
        return bool(data.get("session_token"))
    except (json.JSONDecodeError, OSError):
        return False
