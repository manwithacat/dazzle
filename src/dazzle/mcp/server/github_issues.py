"""Helper for creating GitHub issues via the `gh` CLI."""

from __future__ import annotations

import logging
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


def _gh_available() -> bool:
    """Check whether `gh` CLI is installed and authenticated.

    Not cached — a cached False would be permanently sticky if the first
    call runs before the user authenticates or in a restricted environment.
    """
    gh = _find_gh()
    if gh is None:
        logger.debug("gh CLI not found on PATH")
        return False
    try:
        result = subprocess.run(
            [gh, "auth", "status"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            logger.debug("gh auth status failed (rc=%d): %s", result.returncode, result.stderr)
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
            "Run `gh auth login` to authenticate, then retry."
        )
    return {
        "fallback": True,
        "manual_url": manual_url,
        "title": title,
        "body": body,
        "message": f"{reason} Or create the issue manually at {manual_url}",
    }


def gh_auth_guidance() -> dict[str, Any]:
    """Return structured guidance for authenticating the GitHub CLI.

    Intended for LLM agents to relay instructions to users.
    """
    gh = _find_gh()
    installed = gh is not None
    authenticated = _gh_available() if installed else False
    steps: list[str] = []
    if not installed:
        steps.append("Install the GitHub CLI: https://cli.github.com/")
    if not authenticated:
        steps.append("Run `gh auth login` and follow the prompts.")
    steps.append(
        "Once authenticated, use `contribution(operation='create', type='bug_fix')` "
        "or `gh issue create --repo manwithacat/dazzle` to file issues."
    )
    return {
        "installed": installed,
        "authenticated": authenticated,
        "steps": steps,
    }
