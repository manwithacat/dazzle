#!/usr/bin/env python3
"""Dig receipt writer/checker for /improve dig contracts.

See: docs/superpowers/specs/2026-07-21-improve-dig-contracts-and-process-sensors-design.md

Receipts live under ``.dazzle/improve-digs/`` (gitignored). They prove a dig
cited maps and fired actuators without claiming product beauty.

Usage::

    python scripts/improve_dig_receipt.py write --app contact_manager \\
        --strategy story_walk --cycle 1260 --stories ST-004,ST-005 \\
        --maps stems/story-driven-jobs.md --walks fixtures/scene_walks/x.yaml \\
        --walk-validate 0 --walk-dry-run 0 --live-skip no_db --outcome PASS

    python scripts/improve_dig_receipt.py check --app contact_manager --strategy story_walk
    python scripts/improve_dig_receipt.py process-status   # process residual line
    python scripts/improve_dig_receipt.py mark-live --app simple_task --walk land_and_see_tasks
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
RECEIPT_DIR = REPO / ".dazzle" / "improve-digs"
LIVE_GREEN_NAME = ".live_green.json"
SCHEMA_VERSION = 1

REQUIRED_STRATEGIES = frozenset({"story_walk", "agent_acceptance_panel"})


@dataclass
class DigReceipt:
    schema_version: int = SCHEMA_VERSION
    cycle: int | None = None
    app: str = ""
    strategy: str = ""
    ts: str = ""
    stories: list[str] = field(default_factory=list)
    maps_cited: list[dict[str, str]] = field(default_factory=list)
    walks_touched: list[str] = field(default_factory=list)
    actuators: dict[str, Any] = field(default_factory=dict)
    outcome: str = "PASS"  # PASS | FAIL | BLOCKED | contract_incomplete
    epistemic: list[str] = field(default_factory=list)
    residual_before: int | None = None
    residual_after: int | None = None
    notes: str = ""

    def contract_ok(self) -> bool:
        """Minimum contract for story_walk / acceptance."""
        if self.outcome in {"FAIL", "contract_incomplete"}:
            return False
        if self.outcome == "BLOCKED":
            return True  # honest block
        if not self.maps_cited and self.strategy in REQUIRED_STRATEGIES:
            return False
        act = self.actuators
        if self.strategy == "story_walk":
            if not self.stories:
                return False
            if act.get("walk_validate") not in (0, "0"):
                return False
            if act.get("walk_dry_run") not in (0, "0"):
                return False
        if self.strategy == "agent_acceptance_panel":
            ran = act.get("trial_ran") in (True, 1, "1", "true")
            if not ran and not act.get("trial_report"):
                # allow authoring-only with explicit skip
                if act.get("trial_skip_reason"):
                    return True
                return False
        return True


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def receipt_dir() -> Path:
    RECEIPT_DIR.mkdir(parents=True, exist_ok=True)
    return RECEIPT_DIR


def write_receipt(receipt: DigReceipt) -> Path:
    d = receipt_dir()
    ts_slug = re.sub(r"[^\d]", "", receipt.ts or _now_iso())[:14]
    name = f"{ts_slug}-{receipt.app}-{receipt.strategy}.json"
    path = d / name
    if not receipt.ts:
        receipt.ts = _now_iso()
    if not receipt.contract_ok() and receipt.outcome == "PASS":
        receipt.outcome = "contract_incomplete"
    path.write_text(json.dumps(asdict(receipt), indent=2) + "\n", encoding="utf-8")
    return path


def list_receipts(*, app: str | None = None, strategy: str | None = None) -> list[Path]:
    d = RECEIPT_DIR
    if not d.is_dir():
        return []
    paths = sorted(d.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    out: list[Path] = []
    for p in paths:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if app and data.get("app") != app:
            continue
        if strategy and data.get("strategy") != strategy:
            continue
        out.append(p)
    return out


def load_receipt(path: Path) -> DigReceipt:
    data = json.loads(path.read_text(encoding="utf-8"))
    return DigReceipt(
        schema_version=int(data.get("schema_version") or SCHEMA_VERSION),
        cycle=data.get("cycle"),
        app=str(data.get("app") or ""),
        strategy=str(data.get("strategy") or ""),
        ts=str(data.get("ts") or ""),
        stories=list(data.get("stories") or []),
        maps_cited=list(data.get("maps_cited") or []),
        walks_touched=list(data.get("walks_touched") or []),
        actuators=dict(data.get("actuators") or {}),
        outcome=str(data.get("outcome") or "PASS"),
        epistemic=list(data.get("epistemic") or []),
        residual_before=data.get("residual_before"),
        residual_after=data.get("residual_after"),
        notes=str(data.get("notes") or ""),
    )


def check_latest(app: str, strategy: str) -> tuple[bool, str, DigReceipt | None]:
    paths = list_receipts(app=app, strategy=strategy)
    if not paths:
        return False, "no_receipt", None
    r = load_receipt(paths[0])
    if r.outcome in {"FAIL", "contract_incomplete"}:
        return False, f"outcome:{r.outcome}", r
    if not r.contract_ok():
        return False, "contract_incomplete", r
    return True, "ok", r


def live_green_path(app_dir: Path) -> Path:
    return app_dir / "fixtures" / "scene_walks" / LIVE_GREEN_NAME


def mark_live_green(app: str, walk_ids: list[str]) -> Path:
    root = REPO / "examples" / app
    path = live_green_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = {}
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
    walks = dict(data.get("walks") or {})
    now = _now_iso()
    for wid in walk_ids:
        walks[wid] = {"live_ok_at": now}
    data = {"schema_version": 1, "walks": walks}
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


def is_walk_live_green(app_dir: Path, walk_id: str) -> bool:
    path = live_green_path(app_dir)
    if not path.is_file():
        # also accept any receipt with live run for this walk
        app = app_dir.name
        for rp in list_receipts(app=app, strategy="story_walk")[:20]:
            try:
                r = load_receipt(rp)
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                continue
            if r.actuators.get("walk_live_run") in (0, "0") and (
                not walk_id or walk_id in (r.walks_touched or []) or walk_id in str(r.walks_touched)
            ):
                return True
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    walks = data.get("walks") or {}
    return walk_id in walks


def process_residual_apps() -> list[dict[str, str]]:
    """Apps with latest dig contract incomplete (process residual)."""
    if not RECEIPT_DIR.is_dir():
        return []
    # latest receipt per (app, strategy)
    latest: dict[tuple[str, str], DigReceipt] = {}
    for p in list_receipts():
        try:
            r = load_receipt(p)
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            continue
        key = (r.app, r.strategy)
        if key not in latest:
            latest[key] = r
    out: list[dict[str, str]] = []
    for (app, strategy), r in latest.items():
        if r.outcome in {"contract_incomplete", "FAIL"} or (
            r.strategy in REQUIRED_STRATEGIES and not r.contract_ok()
        ):
            out.append(
                {
                    "app": app,
                    "strategy": strategy,
                    "issue": f"process:{r.outcome or 'contract_incomplete'}",
                    "ts": r.ts,
                }
            )
    return out


def format_process_status() -> str:
    rows = process_residual_apps()
    nxt = rows[0]["app"] if rows else "-"
    return f"process_dig apps={len(rows)} residual={len(rows)} next={nxt}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    w = sub.add_parser("write", help="Write a dig receipt")
    w.add_argument("--app", required=True)
    w.add_argument("--strategy", required=True)
    w.add_argument("--cycle", type=int, default=None)
    w.add_argument("--stories", default="", help="Comma-separated ST ids")
    w.add_argument("--maps", default="", help="Comma-separated map paths")
    w.add_argument("--walks", default="", help="Comma-separated walk paths")
    w.add_argument("--walk-validate", type=int, default=None)
    w.add_argument("--walk-dry-run", type=int, default=None)
    w.add_argument("--walk-live-run", type=int, default=None)
    w.add_argument("--live-skip", default="", help="Reason if live skipped")
    w.add_argument("--trial-ran", action="store_true")
    w.add_argument("--trial-report", default="")
    w.add_argument("--trial-skip-reason", default="")
    w.add_argument("--outcome", default="PASS")
    w.add_argument("--epistemic", default="", help="Comma-separated flags")
    w.add_argument("--residual-before", type=int, default=None)
    w.add_argument("--residual-after", type=int, default=None)
    w.add_argument("--notes", default="")

    c = sub.add_parser("check", help="Check latest receipt for app/strategy")
    c.add_argument("--app", required=True)
    c.add_argument("--strategy", required=True)

    sub.add_parser("process-status", help="Process residual status line")
    sub.add_parser("process-json", help="Process residual JSON")

    m = sub.add_parser("mark-live", help="Mark walk ids live-green")
    m.add_argument("--app", required=True)
    m.add_argument("--walk", action="append", dest="walks", default=[], help="Walk id (repeatable)")

    args = ap.parse_args(argv)

    if args.cmd == "write":
        maps = []
        for p in [x.strip() for x in args.maps.split(",") if x.strip()]:
            kind = "stem" if "stem" in p else "spec" if "SPEC" in p else "map"
            maps.append({"path": p, "kind": kind})
        act: dict[str, Any] = {}
        if args.walk_validate is not None:
            act["walk_validate"] = args.walk_validate
        if args.walk_dry_run is not None:
            act["walk_dry_run"] = args.walk_dry_run
        if args.walk_live_run is not None:
            act["walk_live_run"] = args.walk_live_run
        if args.live_skip:
            act["live_skip_reason"] = args.live_skip
        if args.trial_ran:
            act["trial_ran"] = True
        if args.trial_report:
            act["trial_report"] = args.trial_report
        if args.trial_skip_reason:
            act["trial_skip_reason"] = args.trial_skip_reason
        epistemic = [x.strip() for x in args.epistemic.split(",") if x.strip()]
        if args.live_skip and "live_unproven" not in epistemic:
            epistemic.append("live_unproven")
        receipt = DigReceipt(
            cycle=args.cycle,
            app=args.app,
            strategy=args.strategy,
            ts=_now_iso(),
            stories=[x.strip() for x in args.stories.split(",") if x.strip()],
            maps_cited=maps,
            walks_touched=[x.strip() for x in args.walks.split(",") if x.strip()],
            actuators=act,
            outcome=args.outcome,
            epistemic=epistemic,
            residual_before=args.residual_before,
            residual_after=args.residual_after,
            notes=args.notes,
        )
        path = write_receipt(receipt)
        print(path)
        return 0 if receipt.contract_ok() or receipt.outcome == "BLOCKED" else 1

    if args.cmd == "check":
        ok, reason, r = check_latest(args.app, args.strategy)
        print(
            json.dumps({"ok": ok, "reason": reason, "receipt": asdict(r) if r else None}, indent=2)
        )
        return 0 if ok else 1

    if args.cmd == "process-status":
        print(format_process_status())
        return 0 if not process_residual_apps() else 1

    if args.cmd == "process-json":
        print(
            json.dumps(
                {"apps": process_residual_apps(), "status": format_process_status()}, indent=2
            )
        )
        return 0

    if args.cmd == "mark-live":
        if not args.walks:
            print("need --walk", flush=True)
            return 2
        path = mark_live_green(args.app, args.walks)
        print(path)
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
