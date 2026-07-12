#!/usr/bin/env python3
"""Cross-repo gate: hatchi-maxchi standalone CI must be green.

Dazzle monorepo CI runs the *non-browser* HM package suite in-tree, but the
standalone repo (github.com/manwithacat/hatchi-maxchi) owns behaviour /
visual / WCAG / Nu validity. Until those go green after a subtree sync,
shipping Dazzle "green" while HM is red is a false sense of security.

This script queries the public Actions API for the standalone ``CI``
workflow on ``main`` and exits non-zero when the latest relevant run is
not successful — so Dazzle CI can fail transitively.

Usage (from monorepo root)::

    python scripts/hm_standalone_ci_status.py
    python scripts/hm_standalone_ci_status.py --wait 900
    python scripts/hm_standalone_ci_status.py --json
    python scripts/hm_standalone_ci_status.py --sha <full_or_prefix>

Exit codes: 0 green; 1 red/unknown; 2 usage/API error.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any

REPO = "manwithacat/hatchi-maxchi"
WORKFLOW = "ci.yml"  # path under .github/workflows
API = f"https://api.github.com/repos/{REPO}/actions/workflows/{WORKFLOW}/runs"


def _headers() -> dict[str, str]:
    h = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "dazzle-hm-standalone-ci-status",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _get(url: str) -> dict[str, Any]:
    req = urllib.request.Request(url, headers=_headers())
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"GitHub API {e.code} for {url}: {body}") from e


def latest_runs(*, branch: str = "main", per_page: int = 5) -> list[dict[str, Any]]:
    url = f"{API}?branch={branch}&per_page={per_page}&event=push"
    data = _get(url)
    return list(data.get("workflow_runs") or [])


def pick_run(
    runs: list[dict[str, Any]],
    *,
    sha: str | None,
    prefer_completed: bool,
) -> dict[str, Any] | None:
    if not runs:
        return None
    if sha:
        sha = sha.lower()
        for r in runs:
            head = (r.get("head_sha") or "").lower()
            if head == sha or head.startswith(sha) or sha.startswith(head[: len(sha)]):
                return r
        return None
    if prefer_completed:
        # Mirror mode: ignore an in-flight tip so a new sync does not
        # fail every concurrent Dazzle CI while HM is still running.
        for r in runs:
            if r.get("status") == "completed":
                return r
    return runs[0]


def format_run(run: dict[str, Any]) -> str:
    return (
        f"run={run.get('id')} status={run.get('status')} "
        f"conclusion={run.get('conclusion')} "
        f"sha={(run.get('head_sha') or '')[:8]} "
        f"url={run.get('html_url')}"
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--wait",
        type=int,
        default=0,
        metavar="SEC",
        help="poll until the selected run completes (0 = no wait)",
    )
    p.add_argument(
        "--poll",
        type=int,
        default=20,
        help="seconds between polls when --wait is set (default 20)",
    )
    p.add_argument(
        "--sha",
        default=None,
        help="require this head SHA (or unique prefix); default = latest main run",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="print the selected run as JSON",
    )
    p.add_argument(
        "--allow-in-progress",
        action="store_true",
        help="exit 0 if latest run is still queued/in_progress (default: fail)",
    )
    p.add_argument(
        "--prefer-completed",
        action="store_true",
        help=(
            "select the newest *completed* main run (skip in-flight tips). "
            "Default for Dazzle CI mirror so concurrent HM syncs do not flake."
        ),
    )
    args = p.parse_args(argv)

    deadline = time.monotonic() + max(0, args.wait)
    run: dict[str, Any] | None = None
    prefer_completed = bool(args.prefer_completed) and not args.sha

    while True:
        try:
            runs = latest_runs()
        except RuntimeError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        run = pick_run(runs, sha=args.sha, prefer_completed=prefer_completed)
        if run is None:
            msg = f"no CI run found for {REPO} workflow={WORKFLOW}" + (
                f" sha={args.sha}" if args.sha else " branch=main"
            )
            if args.wait and time.monotonic() < deadline:
                print(f"waiting: {msg}", flush=True)
                time.sleep(max(5, args.poll))
                continue
            print(f"FAIL: {msg}", file=sys.stderr)
            return 1

        status = run.get("status")
        conclusion = run.get("conclusion")
        if args.json:
            print(json.dumps(run, indent=2))
        else:
            print(format_run(run), flush=True)

        if status == "completed":
            if conclusion == "success":
                print("OK: hatchi-maxchi standalone CI is green")
                return 0
            print(
                f"FAIL: hatchi-maxchi standalone CI conclusion={conclusion!r} "
                f"(Dazzle must not treat main as green while HM is red)",
                file=sys.stderr,
            )
            print(f"  {run.get('html_url')}", file=sys.stderr)
            return 1

        # queued / in_progress / waiting
        if args.wait and time.monotonic() < deadline:
            print(f"waiting for completion ({status})…", flush=True)
            time.sleep(max(5, args.poll))
            continue
        if args.allow_in_progress:
            print(f"OK: run still {status} (--allow-in-progress)")
            return 0
        print(
            f"FAIL: hatchi-maxchi CI still {status} "
            f"(use --wait SEC to poll, or --allow-in-progress)",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
