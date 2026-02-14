"""GitHub issue scanning via the ``gh`` CLI."""

from __future__ import annotations

import json
import logging
import re
import subprocess
from datetime import UTC, datetime, timedelta

from dazzle.docs_update.models import ClosedIssue

logger = logging.getLogger(__name__)

# Labels that indicate non-actionable closures
SKIP_LABELS = {"wontfix", "duplicate", "invalid"}

# Max body length sent to the LLM
BODY_TRUNCATE = 2000

# Regex to strip image markdown
_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")


def _find_gh() -> str | None:
    """Locate the ``gh`` binary (reuses logic from github_issues)."""
    from dazzle.mcp.server.github_issues import _find_gh as _upstream_find_gh

    return _upstream_find_gh()


def _gh_available() -> bool:
    from dazzle.mcp.server.github_issues import _gh_available as _upstream_gh_available

    return _upstream_gh_available()


def _run_gh(args: list[str], *, timeout: int = 30) -> str:
    """Run a ``gh`` subcommand and return stdout."""
    gh = _find_gh()
    if gh is None:
        raise RuntimeError("gh CLI not found. Install from https://cli.github.com/")

    cmd = [gh, *args]
    logger.debug("Running: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(f"gh command failed (rc={result.returncode}): {result.stderr.strip()}")
    return result.stdout


def resolve_since(since: str | None, repo: str) -> str:
    """Resolve *since* into an ISO date string (YYYY-MM-DD).

    Accepted formats:
    - ``None`` → date of the latest release / tag
    - Tag name (e.g. ``v0.25.0``) → published date of that release
    - Relative (e.g. ``"14 days"``, ``"30 days"``) → computed from now
    - Date string (e.g. ``"2026-02-01"``) → used as-is
    """
    if since is None:
        return _latest_release_date(repo)

    # Relative: "N days"
    m = re.match(r"^(\d+)\s*days?$", since.strip(), re.IGNORECASE)
    if m:
        days = int(m.group(1))
        dt = datetime.now(tz=UTC) - timedelta(days=days)
        return dt.strftime("%Y-%m-%d")

    # Tag name: starts with 'v' or contains '.'
    if since.startswith("v") or re.match(r"^\d+\.\d+", since):
        return _tag_date(since, repo)

    # Assume date string
    return since.strip()


def _latest_release_date(repo: str) -> str:
    """Get the published date of the latest release."""
    raw = _run_gh(
        ["release", "list", "--repo", repo, "--limit", "1", "--json", "publishedAt"],
        timeout=15,
    )
    data = json.loads(raw)
    if not data:
        # No releases — fall back to 30 days ago
        dt = datetime.now(tz=UTC) - timedelta(days=30)
        return dt.strftime("%Y-%m-%d")
    result: str = data[0]["publishedAt"][:10]
    return result


def _tag_date(tag: str, repo: str) -> str:
    """Get the published date of a specific release/tag."""
    raw = _run_gh(
        ["release", "view", tag, "--repo", repo, "--json", "publishedAt"],
        timeout=15,
    )
    data = json.loads(raw)
    result: str = data["publishedAt"][:10]
    return result


def _clean_body(body: str) -> str:
    """Truncate and strip images from issue body."""
    if not body:
        return ""
    body = _IMAGE_RE.sub("", body)
    if len(body) > BODY_TRUNCATE:
        body = body[:BODY_TRUNCATE] + "\n…[truncated]"
    return body.strip()


def scan_closed_issues(
    since: str,
    repo: str,
    *,
    limit: int = 100,
) -> list[ClosedIssue]:
    """Fetch closed issues from GitHub since a given date.

    Args:
        since: ISO date string (YYYY-MM-DD) — issues closed after this date.
        repo: GitHub ``owner/repo`` identifier.
        limit: Maximum number of issues to fetch.

    Returns:
        List of :class:`ClosedIssue` with body cleaned and skip-labels filtered.
    """
    if not _gh_available():
        raise RuntimeError("gh CLI is not authenticated. Run `gh auth login` or set GITHUB_TOKEN.")

    fields = "number,title,body,labels,closedAt,url"
    raw = _run_gh(
        [
            "issue",
            "list",
            "--repo",
            repo,
            "--state",
            "closed",
            "--json",
            fields,
            "--limit",
            str(limit),
            "--search",
            f"closed:>{since}",
        ],
        timeout=30,
    )

    items = json.loads(raw)
    issues: list[ClosedIssue] = []

    for item in items:
        labels = [lbl["name"] if isinstance(lbl, dict) else lbl for lbl in item.get("labels", [])]

        # Skip wontfix / duplicate / invalid
        if SKIP_LABELS & {lbl.lower() for lbl in labels}:
            continue

        issues.append(
            ClosedIssue(
                number=item["number"],
                title=item["title"],
                body=_clean_body(item.get("body", "")),
                labels=labels,
                closed_at=item.get("closedAt", ""),
                url=item.get("url", ""),
            )
        )

    logger.info(
        "Scanned %d closed issues (since %s), %d after filtering", len(items), since, len(issues)
    )
    return issues
