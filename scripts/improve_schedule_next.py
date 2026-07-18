#!/usr/bin/env python3
"""Decide whether / how soon to self-schedule the next /improve cycle.

Port of CyFuture's self-chaining pattern, adapted for Dazzle's multi-lane
driver. **Opportunistic**: intervals track work heat and **main CI status**
(not a fixed 15–20m ticker). After a push, poll while CI is in progress; when
CI is green, arm a near-term / immediate one-shot so the next product cycle
starts as soon as the badge allows.

Called at end of REPORT. Prints JSON for the agent; does **not** call the host
scheduler — the agent must `scheduler_create` with the fields under
`scheduler_create` when `action == "schedule"`.

Usage:
  uv run python scripts/improve_schedule_next.py
  uv run python scripts/improve_schedule_next.py --result PASS --deployed 1
  uv run python scripts/improve_schedule_next.py --result PASS --ci green
  uv run python scripts/improve_schedule_next.py --result FAIL
  uv run python scripts/improve_schedule_next.py --stop

Exit: always 0 (stop is a clean outcome, not a process failure).
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
BACKLOG = ROOT / "dev_docs" / "improve-backlog.md"
LOG = ROOT / "dev_docs" / "improve-log.md"
EXPLORE_COUNT = ROOT / ".dazzle" / "improve-explore-count"
STATE = ROOT / ".dazzle" / "improve-schedule-state.json"
GITHUB_INBOX = ROOT / ".dazzle" / "improve-github-inbox.json"

EXPLORE_CAP = 100
SELF_AUDIT_EVERY = 15
CAPABILITY_SWEEP_EVERY = 20

# Opportunistic intervals (Grok scheduler min is 60s).
INTERVAL_HOT = "2m"  # CI green + work, REGRESSION, CI red repair, open bugs
INTERVAL_CI_POLL = "3m"  # waiting for main CI after deploy
INTERVAL_WORK = "5m"  # backlog / explore / cadence, no CI urgency
INTERVAL_FAIL = "10m"
# Quiet product state still re-probes GitHub inbox regularly so newly filed
# issues are not left waiting an arbitrary multi-hour gap.
INTERVAL_INBOX_POLL = "15m"
INTERVAL_SLOW = "2h"  # reserved; prefer INTERVAL_INBOX_POLL when chain continues

# Driver Step 1 "actionable" statuses + TR rows that still justify a hot chain.
ACTIONABLE_STATUSES = frozenset(
    {
        "REGRESSION",
        "PENDING",
        "IN_PROGRESS",
        "DRAFT",
        "OPEN",
        "OPEN_FRAMEWORK",
        "OPEN_DSL",
        "FIXED-VERIFY",
    }
)
URGENT_STATUSES = frozenset({"REGRESSION"})
SETTLED_STATUSES = frozenset(
    {
        "DONE",
        "VERIFIED",
        "CLEAN",
        "RESOLVED",
        "CLOSED",
        "FIXED",
        "DEFERRED",
        "BLOCKED",
        "HOUSEKEEPING",
    }
)

PROMPT = (
    "/improve\n\n"
    "Dazzle self-chained cycle. Run **one** improve cycle end-to-end per "
    "`.claude/commands/improve.md` (lock → preflight → CI/CodeQL → signals → "
    "lane pick → playbook → log → unlock). Prefer `make` / `uv run` (uv-only "
    "toolchain; primary Python from `.python-version`). At REPORT end, run:\n"
    "  uv run python scripts/improve_schedule_next.py --result PASS|FAIL "
    "[--deployed 1] [--ci auto|green|red|in_progress|unavailable] [--stop]\n"
    "then call `scheduler_create` with the JSON's `scheduler_create` fields when "
    "`action=schedule` (use interval + fire_immediately + durable=true + "
    "recurring=false from the JSON). Keep a single pending /improve one-shot; "
    "do not create recurring:true for the main chain. Prefer opportunistic "
    "CI-aware intervals over fixed 15–20m waits."
)

_CYCLE_RE = re.compile(
    r"^## Cycle\s+(\d+)\s+—\s+.*?lane:\s*([^\s—]+)",
    re.MULTILINE,
)


def _read_int_file(path: Path, default: int = 0) -> int:
    try:
        return int(path.read_text(encoding="utf-8").strip() or default)
    except (OSError, ValueError):
        return default


_STATUS_TOKENS = (
    ACTIONABLE_STATUSES
    | URGENT_STATUSES
    | SETTLED_STATUSES
    | frozenset({"PROPOSED", "HOUSEKEEPING", "OPEN_UNKNOWN", "NEEDS_REINFORCE", "NOTED-POLLUTED"})
)
_TR_ID_RE = re.compile(r"^TR-\d+$", re.IGNORECASE)
# Autonomous TR severity gate (improve.md Step 1 rule 6): high/medium or FIXED-VERIFY.
_TR_HOT_SEVERITIES = frozenset({"high", "medium"})


def _is_status_summary_row(cells: list[str]) -> bool:
    """True for count tables like ``| PENDING | 0 |`` (not work rows)."""
    if len(cells) < 2:
        return False
    head = cells[0]
    if (
        head not in _STATUS_TOKENS
        and not head.startswith("OPEN_")
        and not head.startswith("BLOCKED")
    ):
        return False
    # Remaining cells are pure integers (counts) or empty.
    rest = [c for c in cells[1:] if c]
    return bool(rest) and all(c.isdigit() for c in rest)


def _tr_row_is_schedule_hot(cells: list[str], status: str) -> bool:
    """Whether a trials TR-* row should heat the improve chain.

    Matches driver autonomous TR eligibility (severity high/medium, or
    FIXED-VERIFY / OPEN_FRAMEWORK / OPEN_DSL). Plain OPEN + low is watch-only.
    """
    base = status.split("→", 1)[0]
    if base in URGENT_STATUSES or base == "FIXED-VERIFY":
        return True
    if base in {"OPEN_FRAMEWORK", "OPEN_DSL"}:
        return True
    if base == "OPEN":
        # TR tables: id | kind | severity | … | status
        severity = cells[2].lower() if len(cells) > 2 else ""
        return severity in _TR_HOT_SEVERITIES
    return base in ACTIONABLE_STATUSES


def parse_backlog_counts(text: str) -> dict[str, int]:
    """Count status tokens in markdown table rows (any lane section)."""
    counts: dict[str, int] = {
        "actionable": 0,
        "urgent": 0,
        "blocked": 0,
        "settled": 0,
        "by_status": {},  # type: ignore[dict-item]
    }
    by_status: dict[str, int] = {}
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 2:
            continue
        # Skip markdown separators and status-count summary tables.
        if all(set(c) <= {"-", ":", " "} for c in cells):
            continue
        if _is_status_summary_row(cells):
            continue
        hits = [
            c
            for c in cells
            if c in ACTIONABLE_STATUSES
            or c in URGENT_STATUSES
            or c in SETTLED_STATUSES
            or c.startswith("BLOCKED")
            or c.startswith("OPEN_")
        ]
        if not hits:
            continue
        status = hits[-1]
        base = status.split("→", 1)[0]
        by_status[base] = by_status.get(base, 0) + 1
        if base in URGENT_STATUSES or status in URGENT_STATUSES:
            counts["urgent"] = int(counts["urgent"]) + 1
            counts["actionable"] = int(counts["actionable"]) + 1
        elif base.startswith("BLOCKED") or base == "BLOCKED":
            counts["blocked"] = int(counts["blocked"]) + 1
        elif base in SETTLED_STATUSES:
            counts["settled"] = int(counts["settled"]) + 1
        elif base in ACTIONABLE_STATUSES or status in ACTIONABLE_STATUSES:
            # TR watch-only rows must not thrash the 2m opportunistic chain.
            if _TR_ID_RE.match(cells[0]) and not _tr_row_is_schedule_hot(cells, status):
                continue
            counts["actionable"] = int(counts["actionable"]) + 1
    counts["by_status"] = by_status  # type: ignore[assignment]
    return counts


def parse_log_meta(text: str) -> dict[str, int | None]:
    """Latest cycle number + last self-audit / capability-sweep cycle ids."""
    cycles: list[tuple[int, str]] = []
    for m in _CYCLE_RE.finditer(text):
        cycles.append((int(m.group(1)), m.group(2).rstrip()))
    if not cycles:
        return {
            "current_cycle": None,
            "last_self_audit": None,
            "last_capability_sweep": None,
        }
    current = max(c[0] for c in cycles)
    last_audit = None
    last_sweep = None
    for num, lane in cycles:
        if lane == "self-audit":
            last_audit = num if last_audit is None else max(last_audit, num)
        if lane == "capability-sweep":
            last_sweep = num if last_sweep is None else max(last_sweep, num)
    return {
        "current_cycle": current,
        "last_self_audit": last_audit,
        "last_capability_sweep": last_sweep,
    }


def probe_ci_main() -> dict[str, Any]:
    """Snapshot latest ci.yml run on main via `gh` (best-effort)."""
    try:
        raw = subprocess.check_output(
            [
                "gh",
                "run",
                "list",
                "--workflow",
                "ci.yml",
                "--branch",
                "main",
                "--limit",
                "1",
                "--json",
                "status,conclusion,databaseId,url,displayTitle",
            ],
            cwd=ROOT,
            text=True,
            timeout=30,
            stderr=subprocess.DEVNULL,
        )
        rows = json.loads(raw or "[]")
        if not rows:
            return {"ci": "unavailable", "detail": "no_runs"}
        row = rows[0]
        status = (row.get("status") or "").lower()
        conclusion = (row.get("conclusion") or "").lower()
        if status in ("in_progress", "queued", "waiting", "requested", "pending"):
            ci = "in_progress"
        elif conclusion == "success":
            ci = "green"
        elif conclusion in ("failure", "cancelled", "timed_out", "startup_failure"):
            ci = "red"
        else:
            ci = "unavailable"
        return {
            "ci": ci,
            "run_id": row.get("databaseId"),
            "url": row.get("url"),
            "displayTitle": row.get("displayTitle"),
            "status": status,
            "conclusion": conclusion,
        }
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError, ValueError) as exc:
        return {"ci": "unavailable", "detail": str(exc)}


def _github_inbox_heat() -> str | None:
    """Read last inbox probe heat if fresh enough (file mtime < 2h)."""
    try:
        if not GITHUB_INBOX.exists():
            return None
        age = datetime.now(UTC).timestamp() - GITHUB_INBOX.stat().st_mtime
        if age > 2 * 3600:
            return None
        data = json.loads(GITHUB_INBOX.read_text(encoding="utf-8"))
        heat = str(data.get("heat") or "")
        if heat and heat != "idle":
            return heat
    except (OSError, json.JSONDecodeError, ValueError, TypeError):
        return None
    return None


def _has_work(
    *,
    counts: dict[str, int],
    explore_used: int,
    current_cycle: int | None,
    last_self_audit: int | None,
    last_capability_sweep: int | None,
    github_heat: str | None = None,
) -> tuple[bool, str]:
    """Whether the next cycle has product/governance work worth a hot chain."""
    if github_heat in (
        "dependabot_merge",
        "consumer_bug",
        "owner_bug",
        "dependabot_ci_red",
    ):
        return True, f"github_inbox={github_heat}"
    if int(counts.get("urgent", 0)) > 0:
        return True, "regression"
    if int(counts.get("actionable", 0)) > 0:
        return True, f"actionable={counts.get('actionable')}"
    if explore_used < EXPLORE_CAP:
        return True, f"explore {explore_used}/{EXPLORE_CAP}"
    if current_cycle is not None:
        nxt = current_cycle + 1
        if last_self_audit is None or (nxt - last_self_audit) >= SELF_AUDIT_EVERY:
            return True, "self_audit_due"
        if last_capability_sweep is None or (nxt - last_capability_sweep) >= CAPABILITY_SWEEP_EVERY:
            return True, "capability_sweep_due"
    if github_heat and github_heat != "idle":
        return True, f"github_inbox={github_heat}"
    return False, "idle"


def decide(
    *,
    counts: dict[str, int],
    explore_used: int,
    current_cycle: int | None,
    last_self_audit: int | None,
    last_capability_sweep: int | None,
    result: str,
    deployed: bool,
    force_stop: bool,
    ci: str = "unavailable",
    github_heat: str | None = None,
) -> dict:
    """Return schedule decision (action, interval, fire_immediately, reason).

    ``ci`` ∈ {green, red, in_progress, unavailable}.
    ``github_heat`` optional override (tests); default reads inbox state file.
    """
    ci = (ci or "unavailable").lower()

    def _sched(interval: str, reason: str, *, fire_immediately: bool = False) -> dict:
        return {
            "action": "schedule",
            "interval": interval,
            "fire_immediately": fire_immediately,
            "reason": reason,
            "prompt": PROMPT,
            "ci": ci,
        }

    if force_stop:
        return {
            "action": "stop",
            "interval": None,
            "fire_immediately": False,
            "reason": "force_stop",
            "prompt": PROMPT,
            "ci": ci,
        }

    if result.upper() in ("FAIL", "FAILED", "ERROR", "BLOCKED"):
        return _sched(INTERVAL_FAIL, "cycle_failed_backoff")

    urgent = int(counts.get("urgent", 0))
    if urgent > 0:
        # Ship-broken: hot chain, no long wait.
        return _sched(
            INTERVAL_HOT,
            f"regression_urgent count={urgent}",
            fire_immediately=True,
        )

    if github_heat is None:
        github_heat = _github_inbox_heat()
    # Dependabot ready / consumer bugs — fire ASAP even before generic work heat.
    if github_heat == "dependabot_merge":
        return _sched(
            INTERVAL_HOT,
            "github_dependabot_merge_ready",
            fire_immediately=True,
        )
    if github_heat == "consumer_bug":
        return _sched(
            INTERVAL_HOT,
            "github_consumer_bug",
            fire_immediately=True,
        )
    if github_heat == "owner_bug":
        # Owner/pilot open bugs (e.g. CyFuture pilot labels) — same urgency as
        # consumer bugs so the chain does not wait on STALE map work.
        return _sched(
            INTERVAL_HOT,
            "github_owner_bug",
            fire_immediately=True,
        )
    if github_heat == "dependabot_ci_red":
        return _sched(
            INTERVAL_HOT,
            "github_dependabot_ci_red",
            fire_immediately=True,
        )

    has_work, work_why = _has_work(
        counts=counts,
        explore_used=max(0, min(explore_used, EXPLORE_CAP)),
        current_cycle=current_cycle,
        last_self_audit=last_self_audit,
        last_capability_sweep=last_capability_sweep,
        github_heat=github_heat,
    )

    # --- CI-opportunistic path (post-deploy or always when status is known) ---
    if deployed or ci in ("green", "red", "in_progress"):
        if ci == "in_progress":
            return _sched(
                INTERVAL_CI_POLL,
                f"ci_waiting in_progress work={work_why}",
            )
        if ci == "red":
            # Next cycle is CI repair — don't sit for 20m.
            return _sched(
                INTERVAL_HOT,
                f"ci_red repair_soon work={work_why}",
                fire_immediately=True,
            )
        if ci == "green" and has_work:
            # Badge green → start product work ASAP (especially after push).
            return _sched(
                INTERVAL_HOT,
                f"ci_green opportunistic work={work_why}" + (" deployed" if deployed else ""),
                fire_immediately=True,
            )
        if deployed and ci == "unavailable" and has_work:
            return _sched(
                INTERVAL_WORK,
                f"post_deploy_ci_unknown work={work_why}",
            )
        if deployed and not has_work and ci == "green":
            return _sched(INTERVAL_SLOW, "post_deploy_ci_green_idle")

    # --- Work heat without CI urgency ---
    if has_work:
        if work_why.startswith("actionable"):
            return _sched(INTERVAL_WORK, f"work_remaining {work_why}")
        if work_why.startswith("explore"):
            return _sched(
                INTERVAL_WORK,
                f"explore_budget_remaining {explore_used}/{EXPLORE_CAP}",
            )
        if work_why == "self_audit_due":
            return _sched(
                INTERVAL_WORK,
                f"self_audit_due next={(current_cycle or 0) + 1} "
                f"last={last_self_audit if last_self_audit is not None else 'never'}",
            )
        if work_why == "capability_sweep_due":
            return _sched(
                INTERVAL_WORK,
                f"capability_sweep_due next={(current_cycle or 0) + 1} "
                f"last={last_capability_sweep if last_capability_sweep is not None else 'never'}",
            )
        return _sched(INTERVAL_WORK, f"work_remaining {work_why}")

    # Quiet: explore cap + no actionable + cadences not due.
    # Still schedule a near-term one-shot so Step 0c3 re-polls GitHub for new
    # issues (rather than an arbitrary multi-hour wait).
    blocked = int(counts.get("blocked", 0))
    if blocked > 0:
        return _sched(
            INTERVAL_INBOX_POLL,
            f"only_blocked_inbox_reprobe blocked={blocked} explore={explore_used}/{EXPLORE_CAP}",
        )

    return _sched(
        INTERVAL_INBOX_POLL,
        f"inbox_reprobe_poll explore={explore_used}/{EXPLORE_CAP}",
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--result", default="PASS", help="PASS|FAIL|BLOCKED for this cycle")
    ap.add_argument(
        "--deployed",
        type=int,
        default=0,
        help="1 if this cycle pushed / shipped runtime behaviour",
    )
    ap.add_argument(
        "--ci",
        default="auto",
        choices=("auto", "green", "red", "in_progress", "unavailable"),
        help="Main CI badge status (default: probe via gh)",
    )
    ap.add_argument(
        "--stop",
        action="store_true",
        help="Force stop (human cancel / unresolvable escalation)",
    )
    ap.add_argument(
        "--no-write-state",
        action="store_true",
        help="Skip writing .dazzle/improve-schedule-state.json",
    )
    args = ap.parse_args(argv)

    backlog_text = BACKLOG.read_text(encoding="utf-8") if BACKLOG.exists() else ""
    log_text = LOG.read_text(encoding="utf-8") if LOG.exists() else ""
    counts = parse_backlog_counts(backlog_text)
    meta = parse_log_meta(log_text)
    explore_used = _read_int_file(EXPLORE_COUNT, 0)

    if args.ci == "auto":
        ci_probe = probe_ci_main()
        ci_status = str(ci_probe.get("ci") or "unavailable")
    else:
        ci_probe = {"ci": args.ci, "detail": "cli_override"}
        ci_status = args.ci

    decision = decide(
        counts=counts,
        explore_used=explore_used,
        current_cycle=meta["current_cycle"],  # type: ignore[arg-type]
        last_self_audit=meta["last_self_audit"],  # type: ignore[arg-type]
        last_capability_sweep=meta["last_capability_sweep"],  # type: ignore[arg-type]
        result=args.result,
        deployed=bool(args.deployed),
        force_stop=bool(args.stop),
        ci=ci_status,
    )
    decision["backlog_counts"] = {k: v for k, v in counts.items() if k != "by_status"}
    decision["backlog_by_status"] = counts.get("by_status", {})
    decision["explore_used"] = explore_used
    decision["explore_cap"] = EXPLORE_CAP
    decision["log_meta"] = meta
    decision["ci_probe"] = ci_probe
    decision["recurring"] = False
    decision["durable"] = True
    decision["ts"] = datetime.now(UTC).isoformat()
    fire = bool(decision.get("fire_immediately"))
    decision["fire_immediately"] = fire

    if decision["action"] == "schedule":
        decision["scheduler_create"] = {
            "interval": decision["interval"],
            "prompt": decision["prompt"],
            "recurring": False,
            "fire_immediately": fire,
            "durable": True,
        }
    else:
        decision["scheduler_create"] = None

    if not args.no_write_state:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(decision, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(decision, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
