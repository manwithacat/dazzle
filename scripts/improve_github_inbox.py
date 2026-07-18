#!/usr/bin/env python3
"""Poll GitHub issues + PRs for the /improve driver inbox.

Feeds Step 0c3 / selection rules:
  - **consumer bugs** (downstream authors, bug-shaped issues) → high priority intake
  - **owner / pilot bugs** (owner-filed bug-shaped, incl. pilot:cyfuture) → same intake
  - **Dependabot PRs** ready to merge (CI green, not draft) → auto-merge candidate
  - other open PRs → process/review queue (not auto-merged)

Does not mutate GitHub — prints JSON for the agent to act on.

Usage:
  uv run python scripts/improve_github_inbox.py
  uv run python scripts/improve_github_inbox.py --owner manwithacat --repo dazzle
  uv run python scripts/improve_github_inbox.py --owner-login manwithacat

Exit 0 always (empty inbox is success).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".dazzle" / "improve-github-inbox.json"

OWNER_DEFAULT = "manwithacat"
REPO_DEFAULT = "dazzle"
OWNER_LOGIN_DEFAULT = "manwithacat"

DEPENDABOT_LOGINS = frozenset(
    {
        "dependabot",
        "dependabot[bot]",
        "app/dependabot",
    }
)

# Labels that mark an issue as consumer / external feedback.
CONSUMER_LABELS = frozenset(
    {
        "consumer",
        "external",
        "customer",
        "downstream",
        "from-consumer",
        "user-report",
    }
)

BUG_LABELS = frozenset(
    {
        "bug",
        "regression",
        "crash",
        "security",
        "blocker",
        "critical",
        "type:bug",
        "kind/bug",
    }
)

# Multi-week epics / bake-off trackers often say "fail" in the title without
# being instant Tier-1 bugs. Keep them out of owner_bug heat so /improve can
# self-audit and other lanes while the epic stays open for partial work.
UMBRELLA_LABELS = frozenset(
    {
        "tracking",
        "epic",
        "umbrella",
        "multi-week",
    }
)

BUG_TITLE_RE = re.compile(
    r"(?i)\b(bugs?|crashes?|fails?|failed|broken|errors?|exceptions?|"
    r"regress(?:ion|ed|es)?|tracebacks?|panics?|cve)\b",
)

# Checks we ignore when deciding Dependabot readiness (optional/informational).
IGNORABLE_CHECK_NAMES = frozenset(
    {
        "claude-review",
        "deploy",
        "codecov/patch",
        "codecov/project",
        "semgrep-cloud-platform/scan",
        "CodeQL",  # standalone status; CodeQL Analyze jobs still count
    }
)


def _gh_json(args: list[str]) -> Any:
    raw = subprocess.check_output(
        ["gh", *args],
        cwd=ROOT,
        text=True,
        timeout=60,
        stderr=subprocess.PIPE,
    )
    return json.loads(raw or "null")


def _author_login(author: Any) -> str:
    if not isinstance(author, dict):
        return ""
    return str(author.get("login") or "").strip()


def _label_names(labels: Any) -> list[str]:
    if not isinstance(labels, list):
        return []
    out: list[str] = []
    for lab in labels:
        if isinstance(lab, dict) and lab.get("name"):
            out.append(str(lab["name"]))
        elif isinstance(lab, str):
            out.append(lab)
    return out


def is_dependabot(login: str) -> bool:
    low = login.lower()
    return low in DEPENDABOT_LOGINS or "dependabot" in low


def is_consumer_author(login: str, owner_login: str) -> bool:
    if not login:
        return False
    if is_dependabot(login):
        return False
    return login.lower() != owner_login.lower()


def is_bug_shaped(title: str, labels: list[str]) -> bool:
    """True when the issue should claim an improve cycle as a bug.

    Label ``bug`` / ``regression`` / etc. always win. Title keywords (fail,
    crash, …) also match — **except** for umbrella/tracking enhancement epics
    (e.g. #1626 antagonist bake-off) that must not starve self-audit forever
    once their P0 work is partial/complete.
    """
    lab = {x.lower() for x in labels}
    if lab & BUG_LABELS:
        return True
    # Tracking + enhancement (no bug label): product epic, not inbox heat.
    if (lab & UMBRELLA_LABELS) and "enhancement" in lab:
        return False
    if lab & UMBRELLA_LABELS and not (lab & {"regression", "crash", "security", "blocker"}):
        # Bare tracking without enhancement still suppresses title-only "fail"
        # unless a real bug-class label is present (already handled above).
        if not BUG_TITLE_RE.search(title or ""):
            return False
        # Title says fail/broken but labels say tracking-only → treat as epic.
        if "enhancement" in lab or "tracking" in lab:
            return False
    if BUG_TITLE_RE.search(title or ""):
        return True
    return False


def is_consumer_issue(
    *,
    login: str,
    owner_login: str,
    labels: list[str],
    title: str,
) -> bool:
    lab = {x.lower() for x in labels}
    if lab & CONSUMER_LABELS:
        return True
    if is_consumer_author(login, owner_login) and is_bug_shaped(title, labels):
        return True
    # External author + needs-triage on a bug-shaped title
    if is_consumer_author(login, owner_login) and "needs-triage" in lab:
        return True
    return False


def summarize_checks(rollup: Any) -> dict[str, Any]:
    """Classify PR statusCheckRollup for Dependabot readiness."""
    if not isinstance(rollup, list):
        return {
            "ready": False,
            "pending": 0,
            "failed": 0,
            "success": 0,
            "skipped": 0,
            "failed_names": [],
            "pending_names": [],
            "reason": "no_checks",
        }
    pending = 0
    failed = 0
    success = 0
    skipped = 0
    failed_names: list[str] = []
    pending_names: list[str] = []
    for item in rollup:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")
        if name in IGNORABLE_CHECK_NAMES:
            continue
        # Ignore CodeQL language analyze noise? Keep CI workflow jobs.
        status = str(item.get("status") or "").upper()
        conclusion = str(item.get("conclusion") or "").upper()
        if status and status not in ("COMPLETED", ""):
            pending += 1
            pending_names.append(name)
            continue
        if conclusion in ("SUCCESS", "NEUTRAL"):
            success += 1
        elif conclusion == "SKIPPED":
            skipped += 1
        elif conclusion in (
            "FAILURE",
            "CANCELLED",
            "TIMED_OUT",
            "STARTUP_FAILURE",
            "ACTION_REQUIRED",
        ):
            failed += 1
            failed_names.append(name)
        elif conclusion == "":
            pending += 1
            pending_names.append(name)
        else:
            # Unknown conclusion — treat as not-ready
            pending += 1
            pending_names.append(f"{name}:{conclusion or status}")
    ready = failed == 0 and pending == 0 and success > 0
    if failed:
        reason = "checks_failed"
    elif pending:
        reason = "checks_pending"
    elif success == 0:
        reason = "no_successful_checks"
    else:
        reason = "ready"
    return {
        "ready": ready,
        "pending": pending,
        "failed": failed,
        "success": success,
        "skipped": skipped,
        "failed_names": failed_names[:12],
        "pending_names": pending_names[:12],
        "reason": reason,
    }


def fetch_issues(owner: str, repo: str) -> list[dict[str, Any]]:
    return list(
        _gh_json(
            [
                "issue",
                "list",
                "--repo",
                f"{owner}/{repo}",
                "--state",
                "open",
                "--limit",
                "50",
                "--json",
                "number,title,labels,author,createdAt,updatedAt,url,body",
            ]
        )
        or []
    )


def fetch_prs(owner: str, repo: str) -> list[dict[str, Any]]:
    return list(
        _gh_json(
            [
                "pr",
                "list",
                "--repo",
                f"{owner}/{repo}",
                "--state",
                "open",
                "--limit",
                "30",
                "--json",
                "number,title,author,isDraft,mergeable,mergeStateStatus,statusCheckRollup,headRefName,url,updatedAt,body",
            ]
        )
        or []
    )


def classify(
    *,
    issues: list[dict[str, Any]],
    prs: list[dict[str, Any]],
    owner_login: str,
) -> dict[str, Any]:
    consumer_bugs: list[dict[str, Any]] = []
    owner_bugs: list[dict[str, Any]] = []
    other_issues: list[dict[str, Any]] = []

    for iss in issues:
        login = _author_login(iss.get("author"))
        labels = _label_names(iss.get("labels"))
        title = str(iss.get("title") or "")
        lab_lower = {x.lower() for x in labels}
        # Skip deferred futures unless they're bugs
        if "future" in lab_lower and not is_bug_shaped(title, labels):
            other_issues.append(
                {
                    "number": iss.get("number"),
                    "title": title,
                    "author": login,
                    "labels": labels,
                    "url": iss.get("url"),
                    "class": "deferred_future",
                }
            )
            continue
        entry = {
            "number": iss.get("number"),
            "title": title,
            "author": login,
            "labels": labels,
            "url": iss.get("url"),
            "updatedAt": iss.get("updatedAt"),
            "bug_shaped": is_bug_shaped(title, labels),
            "consumer": is_consumer_issue(
                login=login, owner_login=owner_login, labels=labels, title=title
            ),
        }
        if entry["consumer"] and entry["bug_shaped"]:
            entry["class"] = "consumer_bug"
            consumer_bugs.append(entry)
        elif entry["consumer"]:
            entry["class"] = "consumer_other"
            consumer_bugs.append(entry)  # still surface for triage
        elif entry["bug_shaped"] and login.lower() == owner_login.lower():
            entry["class"] = "owner_bug"
            owner_bugs.append(entry)
        else:
            entry["class"] = "other"
            other_issues.append(entry)

    dependabot_ready: list[dict[str, Any]] = []
    dependabot_blocked: list[dict[str, Any]] = []
    other_prs: list[dict[str, Any]] = []

    for pr in prs:
        login = _author_login(pr.get("author"))
        checks = summarize_checks(pr.get("statusCheckRollup"))
        mergeable = str(pr.get("mergeable") or "").upper()
        merge_state = str(pr.get("mergeStateStatus") or "").upper()
        draft = bool(pr.get("isDraft"))
        entry = {
            "number": pr.get("number"),
            "title": pr.get("title"),
            "author": login,
            "url": pr.get("url"),
            "headRefName": pr.get("headRefName"),
            "isDraft": draft,
            "mergeable": mergeable,
            "mergeStateStatus": merge_state,
            "checks": checks,
        }
        if is_dependabot(login):
            # Ready: checks green, not draft; mergeable CLEAN/UNKNOWN ok if checks green
            # (GitHub often reports UNKNOWN until refreshed).
            blocked_merge = mergeable == "CONFLICTING" or merge_state in (
                "DIRTY",
                "DRAFT",
            )
            if draft:
                entry["class"] = "dependabot_draft"
                entry["action"] = None
                dependabot_blocked.append(entry)
            elif checks["failed"]:
                entry["class"] = "dependabot_ci_red"
                entry["action"] = "investigate_ci"
                dependabot_blocked.append(entry)
            elif checks["pending"]:
                entry["class"] = "dependabot_ci_pending"
                entry["action"] = "wait_ci"
                dependabot_blocked.append(entry)
            elif blocked_merge:
                entry["class"] = "dependabot_conflict"
                entry["action"] = "update_branch_or_resolve"
                dependabot_blocked.append(entry)
            elif checks["ready"]:
                entry["class"] = "dependabot_merge_ready"
                entry["action"] = "merge"
                dependabot_ready.append(entry)
            else:
                entry["class"] = "dependabot_unknown"
                entry["action"] = "wait_ci"
                dependabot_blocked.append(entry)
        else:
            entry["class"] = "human_pr"
            entry["action"] = "review"
            other_prs.append(entry)

    # Recommended one-cycle actions (priority order for the driver)
    recommended: list[dict[str, Any]] = []
    for pr in dependabot_ready[:3]:
        recommended.append(
            {
                "priority": 1,
                "kind": "dependabot_merge",
                "pr": pr["number"],
                "title": pr["title"],
                "url": pr["url"],
                "merge_method": "squash",
                "playbook": "improve/strategies/github_prs.md",
            }
        )
    for iss in consumer_bugs[:5]:
        recommended.append(
            {
                "priority": 2 if iss.get("bug_shaped") else 3,
                "kind": "consumer_issue",
                "issue": iss["number"],
                "title": iss["title"],
                "author": iss["author"],
                "url": iss["url"],
                "bug_shaped": iss.get("bug_shaped"),
                "playbook": "improve/strategies/consumer_issues.md",
            }
        )
    # Owner / pilot bugs are first-class improve work (not deferred to /issues only).
    # Without this, heat stays idle while open bugs sit behind STALE map re-stamps.
    for iss in owner_bugs[:5]:
        if not iss.get("bug_shaped"):
            continue
        recommended.append(
            {
                "priority": 2,
                "kind": "owner_issue",
                "issue": iss["number"],
                "title": iss["title"],
                "author": iss["author"],
                "url": iss["url"],
                "bug_shaped": True,
                "labels": iss.get("labels") or [],
                "playbook": "improve/strategies/consumer_issues.md",
            }
        )
    for pr in dependabot_blocked:
        if pr.get("action") == "investigate_ci":
            recommended.append(
                {
                    "priority": 2,
                    "kind": "dependabot_ci_red",
                    "pr": pr["number"],
                    "title": pr["title"],
                    "url": pr["url"],
                    "failed_names": pr.get("checks", {}).get("failed_names", []),
                    "playbook": "improve/strategies/github_prs.md",
                }
            )
    for pr in other_prs[:3]:
        recommended.append(
            {
                "priority": 4,
                "kind": "human_pr_review",
                "pr": pr["number"],
                "title": pr["title"],
                "author": pr["author"],
                "url": pr["url"],
                "playbook": "improve/strategies/github_prs.md",
            }
        )

    recommended.sort(key=lambda x: int(x.get("priority", 99)))

    heat = "idle"
    if dependabot_ready:
        heat = "dependabot_merge"
    elif any(i.get("bug_shaped") for i in consumer_bugs):
        heat = "consumer_bug"
    elif any(i.get("bug_shaped") for i in owner_bugs):
        # Owner-filed bugs (incl. pilot:cyfuture) keep the chain hot so inbox
        # is not starved by explore STALE-clear or 2h all-clear waits.
        heat = "owner_bug"
    elif any(p.get("action") == "investigate_ci" for p in dependabot_blocked):
        heat = "dependabot_ci_red"
    elif consumer_bugs or other_prs:
        heat = "inbox_nonzero"

    return {
        "heat": heat,
        "counts": {
            "open_issues": len(issues),
            "consumer_issues": len(consumer_bugs),
            "consumer_bugs": sum(1 for i in consumer_bugs if i.get("bug_shaped")),
            "owner_bugs": len(owner_bugs),
            "open_prs": len(prs),
            "dependabot_ready": len(dependabot_ready),
            "dependabot_blocked": len(dependabot_blocked),
            "human_prs": len(other_prs),
        },
        "consumer_issues": consumer_bugs,
        "owner_bugs": owner_bugs,
        "other_issues": other_issues[:20],
        "dependabot_ready": dependabot_ready,
        "dependabot_blocked": dependabot_blocked,
        "other_prs": other_prs,
        "recommended": recommended,
        "primary": recommended[0] if recommended else None,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--owner", default=OWNER_DEFAULT)
    ap.add_argument("--repo", default=REPO_DEFAULT)
    ap.add_argument(
        "--owner-login",
        default=OWNER_LOGIN_DEFAULT,
        help="GitHub login treated as project owner (not a 'consumer')",
    )
    ap.add_argument(
        "--no-write-state",
        action="store_true",
        help="Skip writing .dazzle/improve-github-inbox.json",
    )
    args = ap.parse_args(argv)

    try:
        issues = fetch_issues(args.owner, args.repo)
        prs = fetch_prs(args.owner, args.repo)
        err = None
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError, ValueError) as exc:
        issues, prs = [], []
        err = str(exc)

    result = classify(issues=issues, prs=prs, owner_login=args.owner_login)
    result["repo"] = f"{args.owner}/{args.repo}"
    result["owner_login"] = args.owner_login
    result["ts"] = datetime.now(UTC).isoformat()
    result["error"] = err

    if not args.no_write_state:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
