#!/usr/bin/env python3
"""Fleet journey-maturity probe for example apps (agent-first dogfood).

Scores each ``examples/*/`` app for *agent journey readiness* — not warehouse
CRUD. A mature app has:

* Stories with ``status: accepted`` and ``executed_by: surface.*`` (bound)
* List surfaces with ``open: Entity via field`` (context hops)
* VIEW hubs with multi-section layout and/or ``related`` children
* Optional ``layout: strip`` on status/health sections

Thin residuals (no stories, zero bound journeys, no open-via on multi-entity
apps) rank highest for the next improve cycle.

Usage (from monorepo root)::

    python scripts/example_journey_maturity.py              # table + ranked residuals
    python scripts/example_journey_maturity.py --json       # full machine payload
    python scripts/example_journey_maturity.py --status     # one-line for cycle logs
    python scripts/example_journey_maturity.py --next       # next app id to dogfood
    python scripts/example_journey_maturity.py --app NAME   # one app
    python scripts/example_journey_maturity.py --strict     # exit 1 if any residual

Exit codes:
  0 — no residual (or --app meets min bar); --status always 0 when apps found
  1 — residuals remain (--strict, or default fleet mode when thin apps exist)
  2 — usage / environment error

Consumed by:
  - ``improve/strategies/journey_dogfood.md`` (example-apps lane)
  - ``scripts/example_agent_prove.sh`` (optional preflight ranking)
  - agents deciding which example to mature next
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EXAMPLES = REPO / "examples"

_STORY_RE = re.compile(r"^story\s+(\S+)", re.MULTILINE)
_EXECUTED_BY_RE = re.compile(r"^\s*executed_by:\s*surface\.\S+", re.MULTILINE)
_NARRATIVE_RE = re.compile(r"^\s*narrative_only:\s*true\b", re.MULTILINE)
_OPEN_RE = re.compile(r"^\s*open:\s+\S+", re.MULTILINE)
_RELATED_RE = re.compile(r"^\s*related\s+\S+", re.MULTILINE)
_STRIP_RE = re.compile(r"^\s*layout:\s*strip\b", re.MULTILINE)
_SURFACE_RE = re.compile(r"^surface\s+(\S+)", re.MULTILINE)
_MODE_LIST_RE = re.compile(r"^\s*mode:\s*list\b", re.MULTILINE)
_MODE_VIEW_RE = re.compile(r"^\s*mode:\s*view\b", re.MULTILINE)
_ENTITY_RE = re.compile(r"^entity\s+(\S+)", re.MULTILINE)
_REF_RE = re.compile(r"^\s+\w+:\s*ref\s+", re.MULTILINE)


@dataclass
class AppMaturity:
    app: str
    stories: int = 0
    bound: int = 0
    narrative_only: int = 0
    open_via: int = 0
    related: int = 0
    strips: int = 0
    list_surfaces: int = 0
    view_surfaces: int = 0
    entities: int = 0
    refs: int = 0
    score: int = 0  # higher = more residual / higher priority
    tier: str = "ok"  # critical | thin | deepen | ok
    reasons: list[str] = field(default_factory=list)

    @property
    def is_residual(self) -> bool:
        return self.tier in {"critical", "thin", "deepen"}


def _read_dsl(app_dir: Path) -> str:
    dsl = app_dir / "dsl"
    if not dsl.is_dir():
        return ""
    parts: list[str] = []
    for p in sorted(dsl.rglob("*.dsl")):
        try:
            parts.append(p.read_text(encoding="utf-8"))
        except OSError:
            continue
    return "\n".join(parts)


def score_app(app_dir: Path) -> AppMaturity:
    name = app_dir.name
    text = _read_dsl(app_dir)
    m = AppMaturity(app=name)
    if not text.strip():
        m.tier = "critical"
        m.score = 200
        m.reasons.append("no_dsl")
        return m

    m.stories = len(_STORY_RE.findall(text))
    m.bound = len(_EXECUTED_BY_RE.findall(text))
    m.narrative_only = len(_NARRATIVE_RE.findall(text))
    m.open_via = len(_OPEN_RE.findall(text))
    m.related = len(_RELATED_RE.findall(text))
    m.strips = len(_STRIP_RE.findall(text))
    m.list_surfaces = len(_MODE_LIST_RE.findall(text))
    m.view_surfaces = len(_MODE_VIEW_RE.findall(text))
    m.entities = len(_ENTITY_RE.findall(text))
    m.refs = len(_REF_RE.findall(text))

    score = 0
    reasons: list[str] = []

    if m.stories == 0:
        score += 100
        reasons.append("no_stories")
    if m.bound == 0:
        score += 80
        reasons.append("zero_bound_journeys")
    elif m.bound < 3:
        score += 40
        reasons.append(f"bound_lt_3({m.bound})")

    multi_entity = m.entities >= 2 or m.refs >= 1
    if multi_entity and m.open_via == 0 and m.list_surfaces >= 1:
        score += 35
        reasons.append("no_open_via_on_lists")
    # Prefer related/strip hubs when the app has FK graph — but once open-via
    # + bound journeys exist, a multi-section VIEW without related is OK
    # (single-product domains like announcement boards).
    if (
        multi_entity
        and m.view_surfaces >= 1
        and m.related == 0
        and m.strips == 0
        and not (m.bound >= 3 and m.open_via >= 1)
    ):
        score += 25
        reasons.append("flat_view_no_hub")

    if m.stories > 0 and m.bound > 0:
        narr_ratio = m.narrative_only / max(m.stories, 1)
        if narr_ratio >= 0.6 and m.bound < 6:
            score += 15
            reasons.append(f"narrative_heavy({m.narrative_only}/{m.stories})")

    m.score = score
    m.reasons = reasons

    if score >= 80 or "no_stories" in reasons or "zero_bound_journeys" in reasons:
        m.tier = "critical"
    elif score >= 35:
        m.tier = "thin"
    elif score >= 15:
        m.tier = "deepen"
    else:
        m.tier = "ok"

    return m


def discover_apps() -> list[Path]:
    if not EXAMPLES.is_dir():
        return []
    apps = []
    for p in sorted(EXAMPLES.iterdir()):
        if not p.is_dir():
            continue
        if not (p / "dazzle.toml").exists():
            continue
        apps.append(p)
    return apps


def scan(app_filter: str | None = None) -> list[AppMaturity]:
    rows: list[AppMaturity] = []
    for app_dir in discover_apps():
        if app_filter and app_dir.name != app_filter:
            continue
        rows.append(score_app(app_dir))
    rows.sort(key=lambda r: (-r.score, r.app))
    return rows


def format_table(rows: list[AppMaturity]) -> str:
    lines = [
        f"{'app':28} {'tier':10} {'score':5} {'st':>3} {'bnd':>3} {'nar':>3} "
        f"{'open':>4} {'rel':>3} {'strip':>5} reasons",
        "-" * 100,
    ]
    for r in rows:
        reasons = ",".join(r.reasons) if r.reasons else "-"
        lines.append(
            f"{r.app:28} {r.tier:10} {r.score:5} {r.stories:3} {r.bound:3} "
            f"{r.narrative_only:3} {r.open_via:4} {r.related:3} {r.strips:5} {reasons}"
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


def format_status(rows: list[AppMaturity]) -> str:
    residual = [r for r in rows if r.is_residual]
    crit = sum(1 for r in residual if r.tier == "critical")
    thin = sum(1 for r in residual if r.tier == "thin")
    deepen = sum(1 for r in residual if r.tier == "deepen")
    nxt = residual[0].app if residual else "-"
    return (
        f"journey_maturity apps={len(rows)} residual={len(residual)} "
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
        help="Exit 1 when any residual remains (default fleet table also exits 1)",
    )
    ap.add_argument(
        "--min-bound",
        type=int,
        default=3,
        help="With --app, require at least this many bound journeys (default 3)",
    )
    ap.add_argument(
        "--ok-exit",
        action="store_true",
        help="Always exit 0 when scan succeeds (report-only; ignore residual)",
    )
    args = ap.parse_args(argv)

    apps = discover_apps()
    if not apps:
        print("No examples/*/dazzle.toml found", file=sys.stderr)
        return 2
    if args.app and not any(a.name == args.app for a in apps):
        print(f"Unknown app: {args.app}", file=sys.stderr)
        return 2

    rows = scan(args.app)
    residual = [r for r in rows if r.is_residual]

    if args.next:
        if residual:
            print(residual[0].app)
            return 0
        print("")
        return 0

    if args.status:
        print(format_status(rows))
        return 0 if args.ok_exit or not residual or not args.strict else 1

    if args.json:
        payload = {
            "apps": [asdict(r) for r in rows],
            "residual": [r.app for r in residual],
            "next": residual[0].app if residual else None,
            "counts": {
                "apps": len(rows),
                "residual": len(residual),
                "critical": sum(1 for r in residual if r.tier == "critical"),
                "thin": sum(1 for r in residual if r.tier == "thin"),
                "deepen": sum(1 for r in residual if r.tier == "deepen"),
            },
        }
        print(json.dumps(payload, indent=2))
    else:
        print(format_table(rows))

    if args.ok_exit:
        return 0

    if args.app:
        row = rows[0]
        # Per-app bar: not critical, and bound >= min (or deepen-only is ok if bound>=min)
        if row.tier == "critical" or row.bound < args.min_bound:
            return 1
        return 0

    # Fleet mode: residual work remains → non-zero (loopable stop condition)
    if residual:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
