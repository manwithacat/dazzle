#!/usr/bin/env python3
"""Cross-repo gate: hatchi-maxchi standalone CI must be green.

Dazzle monorepo CI runs the *non-browser* HM package suite in-tree, but the
standalone repo (github.com/manwithacat/hatchi-maxchi) owns behaviour /
visual / WCAG / Nu validity. Until those go green after a subtree sync,
shipping Dazzle "green" while HM is red is a false sense of security.

This script queries the public Actions API for the standalone ``CI``
workflow on ``main`` and exits non-zero when the latest relevant run is
not successful — so Dazzle CI can fail transitively.

**Fast-fail (2026-07-28):** while a run is still ``in_progress``, poll the
run's *jobs*. If any job has already concluded ``failure`` / ``timed_out`` /
``cancelled``, exit red immediately — do not wait for sibling jobs (or
fail-fast cancel propagation) to finish the run. That is what made
"Wait for hatchi-maxchi CI" look stalled when Visual was red but Behaviour
kept running for another 10+ minutes.

**Stale completed red + --wait (cycle 2142):** a monorepo push often
starts Dazzle CI before the sibling HM workflow is listed. ``--wait``
must keep polling that previous completed failure until a newer run
appears (or grace expires). A *fresh* completed red is the tip and
still fails immediately.

**New tip resets the wait budget (cycle 2147):** ``--wait`` is the
budget for the *selected* run, not the whole script. Stale-red hunting
plus a ~15 min HM visual suite burned a 900s clock in 2146 (HM
#31920607365 finished 46s after Dazzle timed out). When pick_run
switches to a new in-flight tip, restart the deadline.

Usage (from monorepo root)::

    python scripts/hm_standalone_ci_status.py
    python scripts/hm_standalone_ci_status.py --wait 1200
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
from datetime import UTC, datetime
from typing import Any

# A completed failure newer than this is the tip (fail now). Older reds
# with --wait may still be the previous SHA while the sibling HM run
# from a monorepo sync has not appeared in the Actions list yet
# (cycle 2141: sampled 31912865017 at 23:11 while 31914122384 was
# still queuing).
_DEFAULT_FRESH_RED_SECONDS = 90
# How long --wait keeps polling that stale completed red for a newer tip.
_DEFAULT_STALE_RED_GRACE = 180
# CI workflows pass this (or more). HM visual is ~15 min; 900s expired
# 46s early in cycle 2146 once sync lag + the visual suite stacked.
_MIN_CI_WAIT_SECONDS = 1200

REPO = "manwithacat/hatchi-maxchi"
WORKFLOW = "ci.yml"  # path under .github/workflows
API = f"https://api.github.com/repos/{REPO}/actions/workflows/{WORKFLOW}/runs"
# Job conclusions that mean the tip is already red (run may still be
# "in_progress" while siblings wind down or fail-fast cancels them).
_EARLY_FAIL_CONCLUSIONS = frozenset({"failure", "timed_out", "cancelled"})


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
        # Mirror mode: skip an in-flight tip when the last completed
        # run is green so a new sync does not flake every concurrent
        # Dazzle CI. Do *not* sample a stale red/cancelled completed
        # run while a newer tip is still running (cycle 2136/2137:
        # leftover-honesty baseline refresh was already in flight).
        newest = runs[0]
        if newest.get("status") == "completed":
            return newest
        newest_completed = next(
            (r for r in runs if r.get("status") == "completed"),
            None,
        )
        if newest_completed is not None and newest_completed.get("conclusion") == "success":
            return newest_completed
        return newest
    return runs[0]


def completed_run_age_seconds(
    run: dict[str, Any],
    *,
    now: datetime | None = None,
) -> float | None:
    """Age of ``updated_at`` in seconds, or None if missing/unparseable."""
    raw = run.get("updated_at") or run.get("updatedAt")
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip().replace("Z", "+00:00")
    try:
        ts = datetime.fromisoformat(text)
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    stamp = now or datetime.now(UTC)
    return max(0.0, (stamp - ts).total_seconds())


def is_fresh_completed_failure(
    run: dict[str, Any],
    *,
    fresh_red_seconds: float = _DEFAULT_FRESH_RED_SECONDS,
) -> bool:
    """True when this completed red just finished (it is the tip).

    Missing ``updated_at`` is treated as stale so --wait can cover the
    monorepo-sync race and unit fixtures without timestamps.
    """
    age = completed_run_age_seconds(run)
    if age is None:
        return False
    return age < fresh_red_seconds


def maybe_reset_wait_deadline(
    *,
    wait: int,
    run_id: Any,
    status: str | None,
    tracked_id: Any,
    now_mono: float,
) -> tuple[float | None, Any]:
    """Restart ``--wait`` when pick_run switches to a new in-flight tip.

    Cycle 2146: Dazzle mirror started 01:52:53, hunted stale red
    #31919355191, then followed HM #31920607365 from 01:54:09. The
    original 900s deadline expired at 02:07:54 while visual was still
    running; the tip went green at 02:08:40. Wait applies to the
    selected run, not the stale-red hunt that found it.
    """
    if not wait or run_id is None:
        return None, tracked_id if run_id is None else run_id
    if (
        tracked_id is not None
        and run_id != tracked_id
        and status in ("in_progress", "queued", "waiting")
    ):
        return now_mono + wait, run_id
    return None, run_id


def should_poll_for_newer_after_completed_red(
    run: dict[str, Any],
    *,
    wait: int,
    sha: str | None,
    deadline: float,
    fresh_red_seconds: float,
    stale_red_grace: float,
    state: dict[str, Any],
    now_mono: float | None = None,
) -> bool:
    """Keep polling when --wait saw a stale completed red (cycle 2142)."""
    if not wait or sha:
        return False
    now = time.monotonic() if now_mono is None else now_mono
    if now >= deadline:
        return False
    if is_fresh_completed_failure(run, fresh_red_seconds=fresh_red_seconds):
        return False
    rid = run.get("id")
    if state.get("id") != rid:
        state["id"] = rid
        state["started"] = now
    started = float(state.get("started") or now)
    if now - started >= stale_red_grace:
        return False
    return True


def format_run(run: dict[str, Any]) -> str:
    return (
        f"run={run.get('id')} status={run.get('status')} "
        f"conclusion={run.get('conclusion')} "
        f"sha={(run.get('head_sha') or '')[:8]} "
        f"url={run.get('html_url')}"
    )


def first_failed_job(run_id: int | str) -> dict[str, Any] | None:
    """Return the first job on *run_id* that has already failed (if any).

    Used for early-exit while the workflow run is still ``in_progress``.
    """
    url = f"https://api.github.com/repos/{REPO}/actions/runs/{run_id}/jobs?per_page=50"
    data = _get(url)
    for job in data.get("jobs") or []:
        conclusion = job.get("conclusion")
        if conclusion in _EARLY_FAIL_CONCLUSIONS:
            return job
    return None


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
            "skip an in-flight tip when the last completed run is green. "
            "A stale red completed run never wins over a newer in-flight tip. "
            "With --wait, a stale completed red also polls until a newer run "
            "appears (monorepo sync may not have listed the sibling yet)."
        ),
    )
    p.add_argument(
        "--fresh-red-seconds",
        type=int,
        default=_DEFAULT_FRESH_RED_SECONDS,
        help=(
            "a completed failure updated within this many seconds is the tip "
            "(fail immediately). Older reds with --wait poll for a newer run."
        ),
    )
    p.add_argument(
        "--stale-red-grace",
        type=int,
        default=_DEFAULT_STALE_RED_GRACE,
        help=(
            "seconds to keep polling after sampling a stale completed red "
            "while waiting for a newer HM tip to appear (monorepo sync lag)."
        ),
    )
    p.add_argument(
        "--no-early-fail",
        action="store_true",
        help=(
            "disable fast-fail on individual job failure while the run is still "
            "in_progress (wait for full run conclusion only)"
        ),
    )
    args = p.parse_args(argv)

    deadline = time.monotonic() + max(0, args.wait)
    run: dict[str, Any] | None = None
    prefer_completed = bool(args.prefer_completed) and not args.sha
    stale_red_wait: dict[str, Any] = {"id": None, "started": None}
    tracked_id: Any = None

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

        # Cycle 2147: stale-red hunt must not steal the new tip's budget.
        reset_at, tracked_id = maybe_reset_wait_deadline(
            wait=args.wait,
            run_id=run.get("id"),
            status=status if isinstance(status, str) else None,
            tracked_id=tracked_id,
            now_mono=time.monotonic(),
        )
        if reset_at is not None:
            deadline = reset_at
            print(
                f"waiting: new HM tip {run.get('id')} — reset wait budget to {args.wait}s",
                flush=True,
            )

        if status == "completed":
            if conclusion == "success":
                print("OK: hatchi-maxchi standalone CI is green")
                return 0
            # Cycle 2142: --wait + no --sha must not fail immediately on a
            # completed red. Monorepo push often starts Dazzle CI *before*
            # the sibling HM workflow is listed; pick_run then returns the
            # previous completed failure and we used to exit 1 in ~1s
            # (2141: sampled 31912865017 while 31914122384 was still
            # queuing). Keep polling for a newer run until grace/deadline.
            if should_poll_for_newer_after_completed_red(
                run,
                wait=args.wait,
                sha=args.sha,
                deadline=deadline,
                fresh_red_seconds=float(args.fresh_red_seconds),
                stale_red_grace=float(args.stale_red_grace),
                state=stale_red_wait,
            ):
                print(
                    f"waiting: completed {conclusion!r} — checking for a newer HM tip…",
                    flush=True,
                )
                time.sleep(max(5, args.poll))
                continue
            print(
                f"FAIL: hatchi-maxchi standalone CI conclusion={conclusion!r} "
                f"(Dazzle must not treat main as green while HM is red)",
                file=sys.stderr,
            )
            print(f"  {run.get('html_url')}", file=sys.stderr)
            return 1

        # queued / in_progress / waiting — fast-fail if any job already red
        if not args.no_early_fail and status in ("in_progress", "queued", "waiting"):
            run_id = run.get("id")
            if run_id is not None:
                try:
                    bad = first_failed_job(run_id)
                except RuntimeError as e:
                    print(f"warn: job poll failed ({e}); continuing", flush=True)
                    bad = None
                if bad is not None:
                    print(
                        f"FAIL: hatchi-maxchi CI job already red "
                        f"(job={bad.get('name')!r} conclusion={bad.get('conclusion')!r}) "
                        f"— early exit, not waiting for siblings",
                        file=sys.stderr,
                    )
                    print(f"  {run.get('html_url')}", file=sys.stderr)
                    return 1

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
