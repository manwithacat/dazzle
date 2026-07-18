#!/usr/bin/env python3
"""Fleet product-maturity probe for example apps (anti-warehouse gate).

Scores each ``examples/*/`` app for *product essence* — not DSL completeness
or HM purity. A product-mature app has:

* **Answer-first landing** — product personas declare ``default_workspace``
  that points at a real workspace with regions (not an entity list dump)
* **Warehouse containment** — entity ``mode: list`` surfaces exist for CRUD
  but do not dominate: density = list_surfaces / (list + workspaces) is bounded
* **Job coverage** — product personas have bound stories (``executed_by``) or
  at least one accessible workspace with multiple regions (a job surface)

This is the instance-level counterpart to framework ``ux-maturity``
(``docs/reference/ux-maturity.md``): that rubric asks whether *primitives*
default right; this probe asks whether *example products* use those
defaults as the primary path.

Usage (from monorepo root)::

    python scripts/example_product_maturity.py
    python scripts/example_product_maturity.py --json
    python scripts/example_product_maturity.py --status
    python scripts/example_product_maturity.py --next
    python scripts/example_product_maturity.py --app support_tickets
    python scripts/example_product_maturity.py --strict

Exit codes:
  0 — no residual (or single --app meets bar)
  1 — residuals remain (--strict / default fleet)
  2 — usage / environment error

Consumed by:
  - ``improve/lanes/example-apps.md`` (prefer product residuals before Tier-1)
  - agents deciding whether an app is a warehouse or a product
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
EXAMPLES = REPO / "examples"

# Personas that are infrastructure / platform, not domain product jobs.
_PLATFORM_PERSONA_IDS = frozenset(
    {
        "admin",
        "platform_admin",
        "superuser",
        "operator",
        "sysadmin",
    }
)
_PLATFORM_WORKSPACE_PREFIXES = ("_", "platform_", "admin_")


@dataclass
class PersonaLanding:
    persona_id: str
    default_workspace: str | None
    workspace_exists: bool = False
    region_count: int = 0
    ok: bool = False
    reason: str = ""


@dataclass
class AppProductMaturity:
    app: str
    product_personas: int = 0
    landing_ok: int = 0
    landing_fail: int = 0
    workspaces: int = 0
    product_workspaces: int = 0
    list_surfaces: int = 0
    crud_surfaces: int = 0  # list+create+edit
    warehouse_density: float = 0.0
    bound_stories: int = 0
    product_stories: int = 0
    job_personas_covered: int = 0
    score: int = 0  # residual priority (higher = worse / act sooner)
    tier: str = "ok"  # critical | thin | deepen | ok
    reasons: list[str] = field(default_factory=list)
    landings: list[dict[str, Any]] = field(default_factory=list)

    @property
    def is_residual(self) -> bool:
        return self.tier in {"critical", "thin", "deepen"}


def _is_platform_workspace(name: str) -> bool:
    n = (name or "").lower()
    return n.startswith(_PLATFORM_WORKSPACE_PREFIXES) or n in {
        "admin",
        "platform",
        "settings",
    }


def _is_product_persona(persona_id: str) -> bool:
    return persona_id.lower() not in _PLATFORM_PERSONA_IDS


def _mode_str(surface: Any) -> str:
    raw = getattr(surface, "mode", None)
    return str(getattr(raw, "value", raw) or "").lower()


def score_app(app_dir: Path) -> AppProductMaturity:
    name = app_dir.name
    m = AppProductMaturity(app=name)
    if not (app_dir / "dazzle.toml").exists():
        m.tier = "critical"
        m.score = 200
        m.reasons.append("no_dazzle_toml")
        return m

    try:
        # Prefer monorepo import path
        sys.path.insert(0, str(REPO / "src"))
        from dazzle.core.appspec_loader import load_project_appspec

        appspec = load_project_appspec(app_dir)
    except Exception as exc:  # noqa: BLE001 — probe must never crash fleet
        m.tier = "critical"
        m.score = 180
        m.reasons.append(f"load_failed:{type(exc).__name__}")
        return m

    workspaces = list(getattr(appspec, "workspaces", None) or [])
    ws_by_name = {w.name: w for w in workspaces}
    m.workspaces = len(workspaces)
    m.product_workspaces = sum(1 for w in workspaces if not _is_platform_workspace(w.name))

    surfaces = list(getattr(appspec, "surfaces", None) or [])
    list_n = 0
    crud_n = 0
    for s in surfaces:
        mode = _mode_str(s)
        if "list" in mode:
            list_n += 1
            crud_n += 1
        elif "create" in mode or "edit" in mode:
            crud_n += 1
    m.list_surfaces = list_n
    m.crud_surfaces = crud_n

    # Density: lists relative to product workspaces. High = warehouse.
    denom = list_n + max(m.product_workspaces, 0)
    m.warehouse_density = (list_n / denom) if denom else (1.0 if list_n else 0.0)

    personas = list(getattr(appspec, "personas", None) or [])
    product_personas = [p for p in personas if _is_product_persona(str(p.id))]
    m.product_personas = len(product_personas)

    stories = list(getattr(appspec, "stories", None) or [])
    product_story_personas: set[str] = set()
    bound = 0
    product_stories = 0
    for st in stories:
        persona = str(getattr(st, "persona", "") or "")
        executed = getattr(st, "executed_by", None)
        narrative = bool(getattr(st, "narrative_only", False))
        if persona and _is_product_persona(persona):
            product_stories += 1
            if executed and not narrative:
                bound += 1
                product_story_personas.add(persona)
    m.bound_stories = bound
    m.product_stories = product_stories

    # --- Landing (answer-first path) ---
    landing_ok = 0
    landing_fail = 0
    landings: list[dict[str, Any]] = []
    for p in product_personas:
        pid = str(p.id)
        dws = getattr(p, "default_workspace", None) or None
        if isinstance(dws, str):
            dws = dws.strip() or None
        pl = PersonaLanding(persona_id=pid, default_workspace=dws)
        if not dws:
            pl.reason = "no_default_workspace"
            landing_fail += 1
        elif _is_platform_workspace(dws) and pid not in _PLATFORM_PERSONA_IDS:
            # product persona landing on platform admin is wrong
            pl.reason = "default_workspace_platform"
            landing_fail += 1
        else:
            ws = ws_by_name.get(dws)
            if ws is None:
                pl.reason = "default_workspace_missing"
                landing_fail += 1
            else:
                regions = list(getattr(ws, "regions", None) or [])
                pl.workspace_exists = True
                pl.region_count = len(regions)
                if pl.region_count == 0:
                    pl.reason = "landing_workspace_empty"
                    landing_fail += 1
                else:
                    pl.ok = True
                    pl.reason = "ok"
                    landing_ok += 1
        landings.append(asdict(pl))
    m.landing_ok = landing_ok
    m.landing_fail = landing_fail
    m.landings = landings

    # Job coverage: stories bound OR multi-region workspace access for persona
    # (structural stand-in for "has a job surface")
    job_covered = set(product_story_personas)
    for p in product_personas:
        pid = str(p.id)
        if pid in job_covered:
            continue
        dws = getattr(p, "default_workspace", None)
        if dws and dws in ws_by_name:
            regions = list(getattr(ws_by_name[dws], "regions", None) or [])
            if len(regions) >= 2:
                job_covered.add(pid)
    m.job_personas_covered = len(job_covered)

    # --- Residual score ---
    score = 0
    reasons: list[str] = []

    if m.product_personas == 0 and m.workspaces == 0 and list_n > 0:
        score += 100
        reasons.append("warehouse_only_no_product_personas")
    if landing_fail > 0:
        score += 50 * landing_fail
        reasons.append(f"landing_fail({landing_fail})")
    if m.product_personas > 0 and landing_ok == 0:
        score += 40
        reasons.append("no_answer_first_landing")

    if m.warehouse_density >= 0.85 and m.product_workspaces <= 1:
        score += 60
        reasons.append(f"warehouse_density({m.warehouse_density:.2f})")
    elif m.warehouse_density >= 0.7:
        score += 30
        reasons.append(f"warehouse_density({m.warehouse_density:.2f})")

    if m.product_personas > 0:
        uncovered = m.product_personas - m.job_personas_covered
        if uncovered > 0:
            score += 25 * uncovered
            reasons.append(f"job_uncovered({uncovered})")
        if m.product_stories == 0 and m.product_workspaces < 2:
            score += 35
            reasons.append("no_product_stories_thin_workspaces")

    if list_n >= 6 and m.product_workspaces == 0:
        score += 50
        reasons.append("crud_lists_without_workspaces")

    m.score = score
    m.reasons = reasons

    if score >= 80 or "warehouse_only_no_product_personas" in reasons:
        m.tier = "critical"
    elif score >= 40:
        m.tier = "thin"
    elif score >= 15:
        m.tier = "deepen"
    else:
        m.tier = "ok"

    return m


def discover_apps() -> list[Path]:
    if not EXAMPLES.is_dir():
        return []
    return sorted(p for p in EXAMPLES.iterdir() if p.is_dir() and (p / "dazzle.toml").exists())


def scan(app_filter: str | None = None) -> list[AppProductMaturity]:
    rows: list[AppProductMaturity] = []
    for app_dir in discover_apps():
        if app_filter and app_dir.name != app_filter:
            continue
        rows.append(score_app(app_dir))
    rows.sort(key=lambda r: (-r.score, r.app))
    return rows


def format_table(rows: list[AppProductMaturity]) -> str:
    lines = [
        f"{'app':28} {'tier':10} {'score':5} {'land':>5} {'dens':>5} "
        f"{'list':>4} {'ws':>3} {'jobs':>5} reasons",
        "-" * 100,
    ]
    for r in rows:
        land = f"{r.landing_ok}/{r.product_personas}"
        jobs = f"{r.job_personas_covered}/{r.product_personas}"
        reasons = ",".join(r.reasons) if r.reasons else "-"
        lines.append(
            f"{r.app:28} {r.tier:10} {r.score:5} {land:>5} {r.warehouse_density:5.2f} "
            f"{r.list_surfaces:4} {r.product_workspaces:3} {jobs:>5} {reasons}"
        )
    residual = [r for r in rows if r.is_residual]
    lines.append("")
    lines.append(
        f"residual={len(residual)}/{len(rows)}  "
        f"critical={sum(1 for r in residual if r.tier == 'critical')}  "
        f"thin={sum(1 for r in residual if r.tier == 'thin')}  "
        f"deepen={sum(1 for r in residual if r.tier == 'deepen')}"
    )
    if residual:
        lines.append(f"next={residual[0].app}")
    else:
        lines.append("next=")
    return "\n".join(lines)


def format_status(rows: list[AppProductMaturity]) -> str:
    residual = [r for r in rows if r.is_residual]
    crit = sum(1 for r in residual if r.tier == "critical")
    thin = sum(1 for r in residual if r.tier == "thin")
    deepen = sum(1 for r in residual if r.tier == "deepen")
    nxt = residual[0].app if residual else "-"
    return (
        f"product_maturity apps={len(rows)} residual={len(residual)} "
        f"critical={crit} thin={thin} deepen={deepen} next={nxt}"
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--app", help="Score a single app")
    ap.add_argument("--json", action="store_true", help="Emit full JSON payload")
    ap.add_argument("--status", action="store_true", help="One-line cycle log line")
    ap.add_argument(
        "--next",
        action="store_true",
        help="Print only the next residual app id (empty if fleet mature)",
    )
    ap.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 when any residual remains",
    )
    args = ap.parse_args(argv)

    rows = scan(args.app)
    if not rows:
        print("no example apps found", file=sys.stderr)
        return 2

    if args.next:
        residual = [r for r in rows if r.is_residual]
        print(residual[0].app if residual else "")
        return 0 if not residual else 1

    if args.status:
        print(format_status(rows))
        return 0

    if args.json:
        print(json.dumps([asdict(r) for r in rows], indent=2))
    else:
        print(format_table(rows))

    residual = [r for r in rows if r.is_residual]
    if args.app and not residual:
        return 0
    if args.strict or (not args.app and residual):
        return 1 if residual else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
