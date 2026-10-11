"""Locate the `gh` CLI and check that it can authenticate.

Recognises three authentication methods:
1. Interactive: ``gh auth login`` (for human users)
2. Token env var: ``GITHUB_TOKEN`` or ``GH_TOKEN`` (for CI/agents)
3. Token pipe: ``echo $TOKEN | gh auth login --with-token`` (one-time setup)
"""

import logging
import os
import shutil
import subprocess

logger = logging.getLogger(__name__)


def _find_gh() -> str | None:
    """Find the gh CLI binary, checking common Homebrew paths too."""
    found = shutil.which("gh")
    if found:
        return found
    # MCP servers may have a minimal PATH; check common install locations
    for path in ("/opt/homebrew/bin/gh", "/usr/local/bin/gh"):
        if shutil.which("gh", path=path):
            return path
    return None


def _has_token_env() -> bool:
    """Check if a GitHub token is available via environment variables.

    The ``gh`` CLI automatically uses ``GITHUB_TOKEN`` or ``GH_TOKEN``
    when present, so explicit ``gh auth login`` is not required.
    """
    return bool(os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN"))


def _gh_available() -> bool:
    """Check whether ``gh`` CLI is installed and authenticated.

    Checks in order:
    1. Token env vars (GITHUB_TOKEN / GH_TOKEN) — no subprocess needed
    2. ``gh auth status`` — validates interactive/stored auth

    Not cached — a cached False would be permanently sticky if the first
    call runs before the user authenticates or in a restricted environment.
    """
    gh = _find_gh()
    if gh is None:
        logger.debug("gh CLI not found on PATH")
        return False

    # Fast path: token env var means gh will authenticate automatically
    if _has_token_env():
        return True

    try:
        result = subprocess.run(
            [gh, "auth", "status"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            logger.debug(
                "gh auth status failed (rc=%d): %s",
                result.returncode,
                result.stderr,
            )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        logger.debug("gh auth status error: %s", exc)
        return False
