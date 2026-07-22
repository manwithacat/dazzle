#!/usr/bin/env python3
"""Read/activate /improve prioritisation policy (steady_state vs campaign).

Usage::

    python scripts/improve_policy.py --status
    python scripts/improve_policy.py --pick          # recommended force args
    python scripts/improve_policy.py --activate land-l25-smoke
    python scripts/improve_policy.py --clear-campaign
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
POLICY_PATH = REPO / "improve" / "improve-policy.yaml"
LOG_PATH = REPO / "dev_docs" / "improve-log.md"


def _load_yaml(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(text)
        return data if isinstance(data, dict) else {}
    except ImportError:
        return _minimal_yaml(text)


def _minimal_yaml(text: str) -> dict[str, Any]:
    """Tiny subset parser for our policy file when PyYAML is unavailable."""
    # Prefer full PyYAML; this is a best-effort fallback for active_campaign + ids.
    out: dict[str, Any] = {"version": 1, "campaigns": {}, "steady_state": {}}
    m = re.search(r"^active_campaign:\s*(\S+)\s*$", text, re.M)
    if m:
        raw = m.group(1).strip()
        out["active_campaign"] = None if raw in ("null", "~", "None") else raw.strip("\"'")
    # campaign block names
    for _cm in re.finditer(r"^  ([a-zA-Z0-9_-]+):\s*$", text, re.M):
        # only under campaigns: — crude: collect after "campaigns:"
        pass
    if "land-l25-smoke" in text:
        out.setdefault("campaigns", {})["land-l25-smoke"] = {
            "prefer": {
                "lane": "example-apps",
                "strategy": "agent_qa_smoke",
                "force_args": "example-apps agent_qa_smoke",
            },
            "yield_to": ["regression", "ci_repair", "codeql", "github_inbox", "self_audit_cadence"],
            "boost_probe": "qa_smoke",
        }
    # recurring
    every = re.search(r"every_n_cycles:\s*(\d+)", text)
    if every:
        out.setdefault("steady_state", {})["recurring"] = [
            {
                "id": "agent_qa_smoke",
                "every_n_cycles": int(every.group(1)),
                "lane": "example-apps",
                "strategy": "agent_qa_smoke",
                "force_args": "example-apps agent_qa_smoke",
            }
        ]
    return out


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    if not path.is_file():
        return {"version": 1, "active_campaign": None, "steady_state": {}, "campaigns": {}}
    return _load_yaml(path)


def save_active_campaign(campaign_id: str | None, path: Path = POLICY_PATH) -> None:
    if not path.is_file():
        raise SystemExit(f"missing policy file: {path}")
    text = path.read_text(encoding="utf-8")
    val = "null" if not campaign_id else campaign_id
    if re.search(r"^active_campaign:\s*\S+\s*$", text, re.M):
        text = re.sub(
            r"^active_campaign:\s*\S+\s*$",
            f"active_campaign: {val}",
            text,
            count=1,
            flags=re.M,
        )
    else:
        text = f"active_campaign: {val}\n" + text
    path.write_text(text, encoding="utf-8")


def current_cycle_hint() -> int | None:
    """Best-effort current cycle from improve-log heading."""
    if not LOG_PATH.is_file():
        return None
    try:
        text = LOG_PATH.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    # Look for "## Cycle 1304" or "cycle 1304"
    nums = [int(x) for x in re.findall(r"(?i)cycle\s+(\d{3,5})", text)]
    return max(nums) if nums else None


def last_strategy_cycle(strategy: str) -> int | None:
    if not LOG_PATH.is_file():
        return None
    try:
        text = LOG_PATH.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    # Recent log entries mention strategy / agent_qa_smoke
    best: int | None = None
    for m in re.finditer(
        rf"(?i)cycle\s+(\d{{3,5}}).{{0,200}}{re.escape(strategy)}|{re.escape(strategy)}.{{0,80}}cycle\s+(\d{{3,5}})",
        text,
    ):
        n = int(m.group(1) or m.group(2))
        if best is None or n > best:
            best = n
    return best


def qa_smoke_residual() -> tuple[int, str | None]:
    bar = REPO / "scripts" / "qa_smoke_bar.py"
    if not bar.is_file():
        return 0, None
    import importlib.util

    spec = importlib.util.spec_from_file_location("qa_smoke_bar", bar)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["qa_smoke_bar"] = mod  # required for dataclass on 3.14
    spec.loader.exec_module(mod)
    rows = mod.scan()
    residual = [r for r in rows if r.is_residual()]
    nxt = residual[0].app if residual else None
    return len(residual), nxt


def pick(policy: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return recommended lane/strategy force for this cycle (policy layer only)."""
    policy = policy or load_policy()
    active = policy.get("active_campaign")
    smoke_n, smoke_next = qa_smoke_residual()
    cur = current_cycle_hint() or 0

    decision: dict[str, Any] = {
        "active_campaign": active,
        "qa_smoke_residual": smoke_n,
        "qa_smoke_next": smoke_next,
        "current_cycle_hint": cur or None,
        "force_args": None,
        "lane": None,
        "strategy": None,
        "reason": "steady_state_default",
    }

    campaigns = policy.get("campaigns") or {}
    if active and active in campaigns:
        camp = campaigns[active] or {}
        prefer = camp.get("prefer") or {}
        # Boost: non-empty smoke residual always forces smoke dig under campaign.
        if smoke_n > 0 or camp.get("boost_probe") == "qa_smoke":
            decision.update(
                {
                    "force_args": prefer.get("force_args") or "example-apps agent_qa_smoke",
                    "lane": prefer.get("lane") or "example-apps",
                    "strategy": prefer.get("strategy") or "agent_qa_smoke",
                    "reason": f"campaign:{active}"
                    + (
                        f" smoke_residual={smoke_n} next={smoke_next}"
                        if smoke_n
                        else " dig_exercise"
                    ),
                }
            )
            return decision

    # Recurring L2.5 when residual clear of campaign
    recurring = (policy.get("steady_state") or {}).get("recurring") or []
    for rec in recurring:
        if not isinstance(rec, dict):
            continue
        every = int(rec.get("every_n_cycles") or 0)
        if every <= 0:
            continue
        sid = str(rec.get("id") or rec.get("strategy") or "")
        last = last_strategy_cycle(sid) or last_strategy_cycle(str(rec.get("strategy") or ""))
        due = last is None or (cur and (cur - last) >= every)
        if due or smoke_n > 0:
            decision.update(
                {
                    "force_args": rec.get("force_args") or "example-apps agent_qa_smoke",
                    "lane": rec.get("lane") or "example-apps",
                    "strategy": rec.get("strategy") or "agent_qa_smoke",
                    "reason": (
                        f"recurring:{sid} due (last={last} every={every})"
                        if due
                        else f"qa_smoke residual={smoke_n}"
                    ),
                }
            )
            return decision

    if smoke_n > 0:
        decision.update(
            {
                "force_args": "example-apps agent_qa_smoke",
                "lane": "example-apps",
                "strategy": "agent_qa_smoke",
                "reason": f"qa_smoke residual={smoke_n} next={smoke_next}",
            }
        )
    return decision


def format_status(policy: dict[str, Any] | None = None) -> str:
    policy = policy or load_policy()
    d = pick(policy)
    lines = [
        f"improve_policy active_campaign={policy.get('active_campaign') or '-'}",
        f"pick force={d.get('force_args') or '-'} reason={d.get('reason')}",
        f"qa_smoke residual={d.get('qa_smoke_residual')} next={d.get('qa_smoke_next') or '-'}",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--status", action="store_true")
    p.add_argument("--pick", action="store_true")
    p.add_argument("--json", action="store_true")
    p.add_argument("--activate", metavar="CAMPAIGN_ID")
    p.add_argument("--clear-campaign", action="store_true")
    args = p.parse_args(argv)

    if args.activate:
        pol = load_policy()
        if args.activate not in (pol.get("campaigns") or {}) and args.activate != "land-l25-smoke":
            print(f"unknown campaign: {args.activate}", file=sys.stderr)
            return 2
        save_active_campaign(args.activate)
        print(f"active_campaign={args.activate}")
        return 0
    if args.clear_campaign:
        save_active_campaign(None)
        print("active_campaign=null")
        return 0

    policy = load_policy()
    d = pick(policy)
    if args.json:
        print(json.dumps({"policy_active": policy.get("active_campaign"), **d}, indent=2))
    elif args.pick:
        print(d.get("force_args") or "")
    else:
        print(format_status(policy))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
