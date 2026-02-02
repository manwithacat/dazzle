"""Helper for creating GitHub issues via the `gh` CLI.

Supports three authentication methods:
1. Interactive: ``gh auth login`` (for human users)
2. Token env var: ``GITHUB_TOKEN`` or ``GH_TOKEN`` (for CI/agents)
3. Token pipe: ``echo $TOKEN | gh auth login --with-token`` (one-time setup)
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from typing import Any

logger = logging.getLogger(__name__)

REPO = "manwithacat/dazzle"


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


def create_github_issue(
    title: str,
    body: str,
    labels: list[str],
    repo: str = REPO,
) -> dict[str, Any]:
    """Create a GitHub issue via ``gh`` CLI.

    Returns ``{"url": "..."}`` on success or ``{"fallback": "..."}`` with
    a manual URL and the formatted body when ``gh`` is unavailable.
    """
    gh = _find_gh()
    if gh is None or not _gh_available():
        return _fallback(title, body, repo)

    cmd = [
        gh,
        "issue",
        "create",
        "--repo",
        repo,
        "--title",
        title,
        "--body",
        body,
    ]
    for label in labels:
        cmd.extend(["--label", label])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            url = result.stdout.strip()
            return {"url": url}
        logger.warning("gh issue create failed: %s", result.stderr)
        return _fallback(title, body, repo)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        logger.warning("gh issue create error: %s", exc)
        return _fallback(title, body, repo)


def _fallback(title: str, body: str, repo: str) -> dict[str, Any]:
    gh = _find_gh()
    manual_url = f"https://github.com/{repo}/issues/new"
    if gh is None:
        reason = (
            "GitHub CLI (`gh`) is not installed. "
            "Install it from https://cli.github.com/ then run `gh auth login`."
        )
    else:
        reason = (
            "GitHub CLI is installed but not authenticated. "
            "For interactive use, run `gh auth login`. "
            "For CI/agent environments, set the GITHUB_TOKEN environment variable "
            "or run: echo $YOUR_TOKEN | gh auth login --with-token"
        )
    return {
        "fallback": True,
        "manual_url": manual_url,
        "title": title,
        "body": body,
        "message": f"{reason}. Or create the issue manually at {manual_url}",
    }


def gh_auth_guidance() -> dict[str, Any]:
    """Return structured guidance for authenticating the GitHub CLI.

    Provides context-appropriate instructions: interactive auth for humans,
    token-based auth for CI/agent environments where interactive prompts
    are not available.
    """
    gh = _find_gh()
    installed = gh is not None
    has_token = _has_token_env()
    authenticated = has_token or (_gh_available() if installed else False)
    steps: list[str] = []

    if not installed:
        steps.append("Install the GitHub CLI: https://cli.github.com/")
    if not authenticated:
        steps.extend(
            [
                "Option A (interactive): Run `gh auth login` and follow the prompts.",
                (
                    "Option B (token/CI/agent): Set GITHUB_TOKEN as an environment "
                    "variable, or run: echo $YOUR_TOKEN | gh auth login --with-token"
                ),
            ]
        )
    steps.append(
        "Once authenticated, use `contribution(operation='create', type='bug_fix')` "
        "or `gh issue create --repo manwithacat/dazzle` to file issues."
    )
    return {
        "installed": installed,
        "authenticated": authenticated,
        "has_token_env": has_token,
        "steps": steps,
    }
