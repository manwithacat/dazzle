"""Helper for creating GitHub issues via the `gh` CLI."""

from __future__ import annotations

import functools
import logging
import subprocess
from typing import Any

logger = logging.getLogger(__name__)

REPO = "manwithacat/dazzle"


@functools.lru_cache(maxsize=1)
def _gh_available() -> bool:
    """Check whether `gh` CLI is installed and authenticated."""
    try:
        result = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
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
    if not _gh_available():
        return _fallback(title, body, repo)

    cmd = [
        "gh",
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
    manual_url = f"https://github.com/{repo}/issues/new"
    return {
        "fallback": True,
        "manual_url": manual_url,
        "title": title,
        "body": body,
        "message": (
            "GitHub CLI not available or not authenticated. "
            f"Create the issue manually at {manual_url}"
        ),
    }
