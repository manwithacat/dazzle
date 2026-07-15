#!/usr/bin/env python3
"""Decide whether / how soon to self-schedule the next /improve cycle.

Port of CyFuture's self-chaining pattern, adapted for Dazzle's multi-lane
driver (explore budget, self-audit / capability-sweep cadences, REGRESSION
preemption). Called at end of REPORT. Prints JSON for the agent; does **not**
call the host scheduler — the agent must `scheduler_create` with the fields
under `scheduler_create` when `action == "schedule"`.

Usage:
  uv run python scripts/improve_schedule_next.py
  uv run python scripts/improve_schedule_next.py --result PASS --deployed 1
  uv run python scripts/improve_schedule_next.py --result FAIL
  uv run python scripts/improve_schedule_next.py --stop

Exit: always 0 (stop is a clean outcome, not a process failure).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKLOG = ROOT / "dev_docs" / "improve-backlog.md"
LOG = ROOT / "dev_docs" / "improve-log.md"
EXPLORE_COUNT = ROOT / ".dazzle" / "improve-explore-count"
STATE = ROOT / ".dazzle" / "improve-schedule-state.json"

EXPLORE_CAP = 100
SELF_AUDIT_EVERY = 15
CAPABILITY_SWEEP_EVERY = 20

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
# Settled / non-actionable tokens we still tally for reporting.
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
    "[--deployed 1] [--stop]\n"
    "then call `scheduler_create` with the JSON's `scheduler_create` fields when "
    "`action=schedule` (durable=true, recurring=false, fire_immediately=false). "
    "Keep a single pending /improve one-shot; do not create recurring:true for "
    "the main chain."
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
        # Status is usually the last non-empty cell that looks like a STATUS token,
        # or any cell that exactly matches a known status (tables vary by lane).
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
        # Prefer the rightmost match (notes columns can mention DONE mid-text rarely;
        # exact cell match already filters).
        status = hits[-1]
        # Normalize BLOCKED_ON→… and PARTIALLY_FIXED→#n
        base = status.split("→", 1)[0]
        by_status[base] = by_status.get(base, 0) + 1
        if base in URGENT_STATUSES or status in URGENT_STATUSES:
            counts["urgent"] = int(counts["urgent"]) + 1
            counts["actionable"] = int(counts["actionable"]) + 1
        elif base in ACTIONABLE_STATUSES or status in ACTIONABLE_STATUSES:
            counts["actionable"] = int(counts["actionable"]) + 1
        elif base.startswith("BLOCKED") or base == "BLOCKED":
            counts["blocked"] = int(counts["blocked"]) + 1
        elif base in SETTLED_STATUSES:
            counts["settled"] = int(counts["settled"]) + 1
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
) -> dict:
    """Return schedule decision (action, interval, reason)."""
    if force_stop:
        return {
            "action": "stop",
            "interval": None,
            "reason": "force_stop",
            "prompt": PROMPT,
        }

    if result.upper() in ("FAIL", "FAILED", "ERROR", "BLOCKED"):
        return {
            "action": "schedule",
            "interval": "30m",
            "reason": "cycle_failed_backoff",
            "prompt": PROMPT,
        }

    urgent = int(counts.get("urgent", 0))
    if urgent > 0:
        return {
            "action": "schedule",
            "interval": "15m",
            "reason": f"regression_urgent count={urgent}",
            "prompt": PROMPT,
        }

    if deployed:
        return {
            "action": "schedule",
            "interval": "20m",
            "reason": "post_deploy_settle",
            "prompt": PROMPT,
        }

    actionable = int(counts.get("actionable", 0))
    if actionable > 0:
        return {
            "action": "schedule",
            "interval": "15m",
            "reason": f"work_remaining actionable={actionable}",
            "prompt": PROMPT,
        }

    # Cadence: self-audit every 15 cycles, capability-sweep every 20.
    # Schedule hot if the *next* cycle would trip either gate.
    if current_cycle is not None:
        next_cycle = current_cycle + 1
        if last_self_audit is None or (next_cycle - last_self_audit) >= SELF_AUDIT_EVERY:
            return {
                "action": "schedule",
                "interval": "15m",
                "reason": (
                    f"self_audit_due next={next_cycle} "
                    f"last={last_self_audit if last_self_audit is not None else 'never'}"
                ),
                "prompt": PROMPT,
            }
        if (
            last_capability_sweep is None
            or (next_cycle - last_capability_sweep) >= CAPABILITY_SWEEP_EVERY
        ):
            return {
                "action": "schedule",
                "interval": "15m",
                "reason": (
                    f"capability_sweep_due next={next_cycle} "
                    f"last={last_capability_sweep if last_capability_sweep is not None else 'never'}"
                ),
                "prompt": PROMPT,
            }

    explore_used = max(0, min(explore_used, EXPLORE_CAP))
    if explore_used < EXPLORE_CAP:
        return {
            "action": "schedule",
            "interval": "15m",
            "reason": f"explore_budget_remaining {explore_used}/{EXPLORE_CAP}",
            "prompt": PROMPT,
        }

    # Explore cap + no actionable + cadences not due → slow poll (dead-man
    # still re-arms if this one-shot expires). Chain stays alive for the next
    # dazzle-updated budget reset.
    blocked = int(counts.get("blocked", 0))
    if blocked > 0:
        return {
            "action": "schedule",
            "interval": "2h",
            "reason": f"only_blocked_or_settled blocked={blocked} explore={explore_used}/{EXPLORE_CAP}",
            "prompt": PROMPT,
        }

    return {
        "action": "schedule",
        "interval": "2h",
        "reason": f"all_clear_or_explore_cap explore={explore_used}/{EXPLORE_CAP}",
        "prompt": PROMPT,
    }


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

    decision = decide(
        counts=counts,
        explore_used=explore_used,
        current_cycle=meta["current_cycle"],  # type: ignore[arg-type]
        last_self_audit=meta["last_self_audit"],  # type: ignore[arg-type]
        last_capability_sweep=meta["last_capability_sweep"],  # type: ignore[arg-type]
        result=args.result,
        deployed=bool(args.deployed),
        force_stop=bool(args.stop),
    )
    decision["backlog_counts"] = {k: v for k, v in counts.items() if k != "by_status"}
    decision["backlog_by_status"] = counts.get("by_status", {})
    decision["explore_used"] = explore_used
    decision["explore_cap"] = EXPLORE_CAP
    decision["log_meta"] = meta
    decision["recurring"] = False
    decision["fire_immediately"] = False
    decision["durable"] = True
    decision["ts"] = datetime.now(UTC).isoformat()

    if decision["action"] == "schedule":
        decision["scheduler_create"] = {
            "interval": decision["interval"],
            "prompt": decision["prompt"],
            "recurring": False,
            "fire_immediately": False,
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
