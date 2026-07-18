#!/usr/bin/env python3
"""Demo-fleet bar for #1626 (antagonist bake-off P0 checklist).

Structural product maturity can be green while stills/seeds still fail a
sales demo. This probe checks machine-checkable slices of P0-4..P0-9:

* product persona nav has no platform chrome (P0-4)
* showcase blueprints declare minimum story row counts (P0-5)
* QA screenshot dirs are not *only* stale ``_platform_admin_*`` stills (P0-6)
* known happy-path stills are not empty-state theater by file size (P0-6)
* invoice desk seeds have submitted/approved floors per tenant (P0-9)

Usage::

    python scripts/demo_fleet_bar.py
    python scripts/demo_fleet_bar.py --strict
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EXAMPLES = REPO / "examples"

# Showcase apps for the antagonist re-score path
SHOWCASE = (
    "simple_task",
    "support_tickets",
    "invoice_ops",
    "contact_manager",
    "ops_dashboard",
    "project_tracker",
    "design_studio",
    "hr_records",
    "fieldtest_hub",
)

# P0-5 minimums (primary entity → min rows in blueprint)
MIN_ROWS: dict[str, dict[str, int]] = {
    "simple_task": {"Task": 12},
    "support_tickets": {"Ticket": 8, "Comment": 8},
    "invoice_ops": {"Invoice": 9, "Supplier": 3},
    "contact_manager": {"Contact": 15},
    "project_tracker": {"Task": 8, "Project": 1},
    "ops_dashboard": {"Alert": 5},
    "design_studio": {"Asset": 6, "Brand": 2},
    "hr_records": {"Person": 8},
    "fieldtest_hub": {"Device": 6, "IssueReport": 6},
}

PLATFORM_STILL_PREFIX = "_platform_admin_"

# P0-6 empty-hero floors (bytes). Only enforced when the still file exists
# under the app's screenshot dir (CI often has no gitignored .dazzle stills —
# skip). Empty-state theater stills are ~40–55 KB; populated job desks
# typically ≥80 KB at desktop light above-fold.
# Structural demo_fleet floors (ship residual=0). Felt empty-hero expansion
# lives in dazzle.product_quality.stills.HERO_MIN_BYTES — agents use
# `dazzle demo quality` / product_quality MCP for antagonist desks.
HERO_MIN_BYTES: dict[str, dict[str, int]] = {
    "invoice_ops": {
        "approval_desk_approver_desktop_light.png": 80_000,
        "pay_desk_finance_desktop_light.png": 70_000,
    },
    "support_tickets": {
        "manager_ops_manager_desktop_light.png": 80_000,
    },
    "simple_task": {
        "task_board_manager_desktop_light.png": 90_000,
    },
}


@dataclass
class AppDemoBar:
    app: str
    issues: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues


def _blueprint_rows(app_dir: Path) -> dict[str, int]:
    bp = app_dir / "dsl" / "seeds" / "demo_data" / "blueprint.json"
    if not bp.is_file():
        # alternate layout
        for cand in app_dir.rglob("blueprint.json"):
            if "seeds" in cand.parts:
                bp = cand
                break
        else:
            return {}
    try:
        data = json.loads(bp.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    entities = (data.get("blueprint") or data).get("entities") or []
    out: dict[str, int] = {}
    for ent in entities:
        name = ent.get("name")
        if name:
            out[str(name)] = int(ent.get("row_count_default") or 0)
    # explicit jsonl overrides
    seed_dir = bp.parent
    for jsonl in seed_dir.glob("*.jsonl"):
        try:
            n = sum(1 for line in jsonl.read_text(encoding="utf-8").splitlines() if line.strip())
        except OSError:
            continue
        out[jsonl.stem] = max(out.get(jsonl.stem, 0), n)
    return out


def _shot_dir(app_dir: Path) -> Path | None:
    for p in (
        app_dir / ".dazzle" / "qa" / "screenshots",
        app_dir / "screenshots",
    ):
        if p.is_dir():
            return p
    return None


def score_app(app: str) -> AppDemoBar:
    row = AppDemoBar(app=app)
    app_dir = EXAMPLES / app
    if not app_dir.is_dir():
        row.issues.append("missing_app")
        return row

    # P0-5 seed mins
    mins = MIN_ROWS.get(app) or {}
    counts = _blueprint_rows(app_dir)
    for entity, need in mins.items():
        have = counts.get(entity, 0)
        if have < need:
            row.issues.append(f"seed_thin:{entity}={have}<{need}")

    # P0-9 desk population (invoice_ops): explicit Invoice.jsonl must put
    # ≥3 submitted (Approval Desk) and ≥3 approved (Pay Desk) per status —
    # weighted random alone can leave a tenant's queue empty.
    if app == "invoice_ops":
        inv = app_dir / "dsl" / "seeds" / "demo_data" / "Invoice.jsonl"
        if inv.is_file():
            by_status: dict[str, int] = {}
            by_tenant_submitted: dict[str, int] = {}
            try:
                for line in inv.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    rec = json.loads(line)
                    st = str(rec.get("status") or "")
                    by_status[st] = by_status.get(st, 0) + 1
                    if st == "submitted":
                        tid = str(rec.get("tenant_id") or "")
                        by_tenant_submitted[tid] = by_tenant_submitted.get(tid, 0) + 1
            except (OSError, json.JSONDecodeError) as exc:
                row.issues.append(f"seed_invoice_unreadable:{type(exc).__name__}")
            else:
                if by_status.get("submitted", 0) < 3:
                    row.issues.append(f"seed_desk_thin:submitted={by_status.get('submitted', 0)}<3")
                if by_status.get("approved", 0) < 3:
                    row.issues.append(f"seed_desk_thin:approved={by_status.get('approved', 0)}<3")
                thin_tenants = [t for t, n in by_tenant_submitted.items() if n < 3]
                if thin_tenants:
                    row.issues.append(
                        f"seed_desk_thin:submitted_per_tenant<{3} ({len(thin_tenants)} tenants)"
                    )
        else:
            row.issues.append("seed_desk_thin:missing_Invoice.jsonl")

    # P0-5 project_tracker: kanban columns not empty (todo / in_progress / review)
    if app == "project_tracker":
        task = app_dir / "dsl" / "seeds" / "demo_data" / "Task.jsonl"
        if not task.is_file():
            row.issues.append("seed_board_thin:missing_Task.jsonl")
        else:
            try:
                by_st: dict[str, int] = {}
                for line in task.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    rec = json.loads(line)
                    st = str(rec.get("status") or "")
                    by_st[st] = by_st.get(st, 0) + 1
                for col, need in (("todo", 3), ("in_progress", 3), ("review", 2)):
                    if by_st.get(col, 0) < need:
                        row.issues.append(f"seed_board_thin:{col}={by_st.get(col, 0)}<{need}")
            except (OSError, json.JSONDecodeError) as exc:
                row.issues.append(f"seed_board_unreadable:{type(exc).__name__}")

    # P0-8 design_studio: explicit Brand.jsonl with hex palettes (swatch seeds)
    if app == "design_studio":
        brand = app_dir / "dsl" / "seeds" / "demo_data" / "Brand.jsonl"
        if not brand.is_file():
            row.issues.append("seed_swatches:missing_Brand.jsonl")
        else:
            try:
                hex_ok = 0
                for line in brand.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    rec = json.loads(line)
                    pc = str(rec.get("primary_color") or "")
                    if pc.startswith("#") and len(pc) in (4, 7):
                        hex_ok += 1
                if hex_ok < 3:
                    row.issues.append(f"seed_swatches:hex_brands={hex_ok}<3")
            except (OSError, json.JSONDecodeError) as exc:
                row.issues.append(f"seed_swatches_unreadable:{type(exc).__name__}")

    # P0-6 stale platform-only stills + empty-hero size floors
    shots = _shot_dir(app_dir)
    if shots is not None:
        pngs = list(shots.glob("*.png"))
        if pngs:
            product = [p for p in pngs if not p.name.startswith(PLATFORM_STILL_PREFIX)]
            if not product:
                row.issues.append("stills_platform_only")
            # Empty-hero: known happy-path stills must not be empty-state theater
            for name, min_bytes in (HERO_MIN_BYTES.get(app) or {}).items():
                path = shots / name
                if not path.is_file():
                    continue
                size = path.stat().st_size
                if size < min_bytes:
                    row.issues.append(f"empty_hero:{name}={size}<{min_bytes}")

    # P0-4 nav (needs appspec load)
    try:
        sys.path.insert(0, str(REPO / "src"))
        from dazzle.core.appspec_loader import load_project_appspec
        from dazzle.page.converters.nav_builder import (
            _PLATFORM_PERSONA_IDS,
            build_persona_nav,
        )
        from dazzle.rbac.matrix import generate_access_matrix

        appspec = load_project_appspec(app_dir)
        matrix = generate_access_matrix(appspec)
        banned = (
            "system health",
            "deploy history",
            "feedback report",
            "_platform_admin",
            "systemhealth",
            "deployhistory",
        )
        for persona in appspec.personas or []:
            if (persona.id or "").lower() in _PLATFORM_PERSONA_IDS:
                continue
            nav = build_persona_nav(appspec, persona, matrix)
            blob = " ".join(
                f"{link.label} {link.route or ''}".lower() for g in nav.groups for link in g.links
            )
            for b in banned:
                if b in blob:
                    row.issues.append(f"nav_platform:{persona.id}:{b}")
                    break
    except Exception as exc:  # noqa: BLE001 — probe must not crash fleet
        row.issues.append(f"nav_check_failed:{type(exc).__name__}")

    return row


def format_status(rows: list[AppDemoBar]) -> str:
    residual = [r for r in rows if not r.ok]
    nxt = residual[0].app if residual else "-"
    return (
        f"demo_fleet apps={len(rows)} residual={len(residual)} "
        f"ok={len(rows) - len(residual)} next={nxt}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", help="Score a single showcase app")
    parser.add_argument("--status", action="store_true", help="One-line cycle log line")
    parser.add_argument(
        "--next",
        action="store_true",
        help="Print only the next residual app id (empty if fleet mature)",
    )
    parser.add_argument("--strict", action="store_true", help="exit 1 if any residual")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    apps = list(SHOWCASE)
    if args.app:
        apps = [args.app]
    rows = [score_app(a) for a in apps if (EXAMPLES / a).is_dir()]
    residual = [r for r in rows if not r.ok]

    if args.next:
        print(residual[0].app if residual else "")
        return 0 if not residual else 1

    if args.status:
        print(format_status(rows))
        return 0 if not residual else 1

    if args.json:
        print(
            json.dumps(
                [{"app": r.app, "ok": r.ok, "issues": r.issues} for r in rows],
                indent=2,
            )
        )
    else:
        print(f"{'app':28} {'status':8} issues")
        print("-" * 72)
        for r in rows:
            st = "ok" if r.ok else "residual"
            print(f"{r.app:28} {st:8} {', '.join(r.issues) or '-'}")
        print(
            f"\ndemo_fleet apps={len(rows)} residual={len(residual)} ok={len(rows) - len(residual)}"
        )
        if residual:
            print(f"next={residual[0].app}")
        else:
            print("next=")

    if args.strict and residual:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
