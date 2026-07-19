"""Unified product/demo quality bar for agents (#1626).

Aggregates structural maturity probes + persona-home residual + still floors
into one OBSERVE payload for MCP / CLI / improve.
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

from dazzle.product_quality.metric_list import MetricListHome, score_metric_list
from dazzle.product_quality.persona_homes import PersonaHome, score_persona_homes
from dazzle.product_quality.stills import StillScore, score_stills

REPO = Path(__file__).resolve().parents[3]


def _load_script(name: str, path: Path) -> ModuleType:
    # Unique module name so reloads don't collide with other probes.
    mod_name = f"_dazzle_pq_{name}"
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    spec = importlib.util.spec_from_file_location(mod_name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


@dataclass
class ProbeSlice:
    name: str
    residual: int
    next_app: str | None
    status: str
    ok: bool


@dataclass
class ProductQualityReport:
    project: str
    app: str | None
    probes: list[ProbeSlice] = field(default_factory=list)
    persona_homes: list[dict[str, Any]] = field(default_factory=list)
    stills: list[dict[str, Any]] = field(default_factory=list)
    metric_list: list[dict[str, Any]] = field(default_factory=list)
    residual_total: int = 0
    next: str | None = None
    next_strategy: str | None = None
    force: str | None = None
    recommended: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project": self.project,
            "app": self.app,
            "probes": [asdict(p) for p in self.probes],
            "persona_homes": self.persona_homes,
            "stills": self.stills,
            "metric_list": self.metric_list,
            "residual_total": self.residual_total,
            "next": self.next,
            "next_strategy": self.next_strategy,
            "force": self.force,
            "recommended": self.recommended,
        }


def _probe_maturity_script(name: str, script: str, examples: Path) -> ProbeSlice:
    """Shared loader for product_maturity / journey_maturity probe scripts."""
    mod = _load_script(name, REPO / "scripts" / script)
    if (examples / "dazzle.toml").is_file():
        row = mod.score_app(examples)
        residual = 1 if row.is_residual else 0
        nxt = examples.name if residual else None
        status = f"{name} app={examples.name} residual={residual} tier={row.tier} next={nxt or '-'}"
        return ProbeSlice(name, residual, nxt, status, residual == 0)
    rows = mod.scan()
    residual_rows = [r for r in rows if r.is_residual]
    nxt = residual_rows[0].app if residual_rows else None
    status = mod.format_status(rows)
    return ProbeSlice(name, len(residual_rows), nxt, status, not residual_rows)


def _probe_product(examples: Path) -> ProbeSlice:
    return _probe_maturity_script("product_maturity", "example_product_maturity.py", examples)


def _probe_demo(examples: Path, app: str | None) -> ProbeSlice:
    mod = _load_script("demo_fleet_bar", REPO / "scripts" / "demo_fleet_bar.py")
    if app:
        if not hasattr(mod, "score_app"):
            return ProbeSlice("demo_fleet", -1, None, "demo_fleet unavailable", False)
        row = mod.score_app(app)
        residual = 0 if row.ok else 1
        status = f"demo_fleet app={app} residual={residual} issues={','.join(row.issues) or '-'}"
        return ProbeSlice("demo_fleet", residual, app if residual else None, status, residual == 0)
    # fleet under examples/
    apps = list(getattr(mod, "SHOWCASE", ()))
    rows = [mod.score_app(a) for a in apps if (examples / a).is_dir()]
    residual_rows = [r for r in rows if not r.ok]
    nxt = residual_rows[0].app if residual_rows else None
    status = (
        mod.format_status(rows)
        if hasattr(mod, "format_status")
        else f"demo_fleet residual={len(residual_rows)}"
    )
    return ProbeSlice("demo_fleet", len(residual_rows), nxt, status, not residual_rows)


def _probe_journey(examples: Path) -> ProbeSlice:
    return _probe_maturity_script("journey_maturity", "example_journey_maturity.py", examples)


def _persona_payload(homes: list[PersonaHome]) -> tuple[list[dict[str, Any]], int]:
    residual = 0
    out: list[dict[str, Any]] = []
    for h in homes:
        if h.residual:
            residual += 1
        out.append(
            {
                "persona": h.persona,
                "default_workspace": h.default_workspace,
                "stable_user_id": h.stable_user_id,
                "residual": h.residual,
                "reasons": h.residual_reasons,
                "regions": [
                    {
                        "region": r.region,
                        "source": r.source,
                        "bind_field": r.bind_field,
                        "status": r.status,
                        "seed_hits": r.seed_hits,
                        "residual": r.residual,
                        "reason": r.reason,
                    }
                    for r in h.regions
                ],
            }
        )
    return out, residual


def _stills_payload(stills: list[StillScore]) -> tuple[list[dict[str, Any]], int]:
    residual = sum(1 for s in stills if s.residual)
    return [
        {
            "name": s.name,
            "path": s.path,
            "size": s.size,
            "min_bytes": s.min_bytes,
            "residual": s.residual,
            "reason": s.reason,
        }
        for s in stills
    ], residual


def _metric_list_payload(homes: list[MetricListHome]) -> tuple[list[dict[str, Any]], int, int]:
    """Serialize metric↔list; residual personas + risk personas (#1632).

    Only seed-level metric-empty + list-full counts as residual (force path).
    Pattern risk (current_user metrics + seeded lists) is reported separately.
    """
    residual = 0
    risk = 0
    out: list[dict[str, Any]] = []
    for h in homes:
        if h.residual:
            residual += 1
        if h.risk:
            risk += 1
        out.append(
            {
                "persona": h.persona,
                "default_workspace": h.default_workspace,
                "residual": h.residual,
                "risk": h.risk,
                "reasons": h.residual_reasons,
                "risk_reasons": h.risk_reasons,
                "pairs": [
                    {
                        "metric_region": p.metric_region,
                        "list_region": p.list_region,
                        "list_seed_hits": p.list_seed_hits,
                        "metric_seed_hits": p.metric_seed_hits,
                        "residual": p.residual,
                        "risk": p.risk,
                        "reason": p.reason,
                    }
                    for p in h.pairs
                ],
            }
        )
    return out, residual, risk


_SHOWCASE = (
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


def _probe_or_error(name: str, fn: Callable[[], ProbeSlice]) -> ProbeSlice:
    try:
        result: ProbeSlice = fn()
    except Exception as exc:  # noqa: BLE001 — probe isolation
        return ProbeSlice(name, -1, None, f"{name} error={type(exc).__name__}:{exc}", False)
    return result


def _first_probe(probes: list[ProbeSlice], name: str) -> ProbeSlice | None:
    for p in probes:
        if p.name == name and p.residual > 0:
            return p
    return None


def _recommend(
    probes: list[ProbeSlice],
    persona_residual: int,
    stills_residual: int,
    metric_list_residual: int = 0,
) -> tuple[str | None, str | None, str | None, list[str]]:
    """Prefer product → persona_homes → metric_list → demo → stills → journey."""
    product = _first_probe(probes, "product_maturity")
    if product is not None:
        rec = (
            f"Structural product residual={product.residual} — "
            "add job desks / default_workspace (not more entity lists)."
        )
        return product.next_app, "product_maturity", "example-apps product_maturity", [rec]

    if persona_residual > 0:
        rec = (
            f"Persona-home residual={persona_residual} — seed jsonl must assign "
            "rows to STABLE_PERSONA_USER_IDS for current_user filters "
            "(assigned_to / created_by / submitted_by)."
        )
        return None, "demo_fleet", "example-apps demo_fleet", [rec]

    if metric_list_residual > 0:
        rec = (
            f"Metric/list residual={metric_list_residual} — workspace metrics with "
            "current_user disagree with sibling lists (F10 / metric_current_user_lie). "
            "Trust list/queue stills over KPI tiles until aggregate materialization is fixed."
        )
        return None, "metric_list", "example-apps demo_fleet", [rec]

    demo = _first_probe(probes, "demo_fleet")
    if demo is not None:
        rec = (
            f"Demo fleet residual={demo.residual} — nav/seeds/stills floors "
            "(see demo_fleet_bar issues)."
        )
        return demo.next_app, "demo_fleet", "example-apps demo_fleet", [rec]

    if stills_residual > 0:
        rec = (
            f"Empty-hero still residual={stills_residual} — re-seed + "
            "dazzle qa capture after assignment-aware data."
        )
        return None, "demo_fleet", "example-apps demo_fleet", [rec]

    journey = _first_probe(probes, "journey_maturity")
    if journey is not None:
        rec = f"Journey residual={journey.residual} — bind stories + hubs."
        return journey.next_app, "journey_dogfood", "example-apps journey_dogfood", [rec]

    rec = (
        "Structural + persona-home + metric/list + still floors clean for this scope. "
        "Machine demo bar is green; human bake-off re-score (#1626) is separate "
        "from residual (stills are local under .dazzle/ — re-run recapture after "
        "seed changes)."
    )
    return None, None, None, [rec]


def _resolve_targets(
    *,
    is_app: bool,
    app_dir: Path | None,
    examples_root: Path,
) -> list[Path]:
    if app_dir is not None and app_dir.is_dir():
        return [app_dir]
    if is_app:
        return []
    return [examples_root / a for a in _SHOWCASE if (examples_root / a).is_dir()]


def _score_targets(
    report: ProductQualityReport,
    targets: list[Path],
    *,
    min_home_hits: int,
) -> tuple[int, int, int]:
    persona_residual = 0
    stills_residual = 0
    metric_list_residual = 0
    for tdir in targets:
        homes = score_persona_homes(tdir, min_hits=min_home_hits)
        payload, pr = _persona_payload(homes)
        for row in payload:
            row["app"] = tdir.name
            report.persona_homes.append(row)
        persona_residual += pr

        ml_homes = score_metric_list(tdir, min_list_hits=min_home_hits)
        ml_payload, mlr, _ml_risk = _metric_list_payload(ml_homes)
        for row in ml_payload:
            row["app"] = tdir.name
            report.metric_list.append(row)
        metric_list_residual += mlr

        stills = score_stills(tdir, tdir.name)
        sp, sr = _stills_payload(stills)
        for row in sp:
            row["app"] = tdir.name
            report.stills.append(row)
        stills_residual += sr
    return persona_residual, stills_residual, metric_list_residual


def score_project(
    project_root: Path,
    *,
    app: str | None = None,
    min_home_hits: int = 1,
) -> ProductQualityReport:
    """Score one project (example app) or an examples/ fleet root.

    * If *project_root* has ``dazzle.toml``, score that app.
    * If *project_root* is an ``examples/`` directory, score the fleet
      (optionally filter with *app*).
    """
    project_root = project_root.resolve()
    report = ProductQualityReport(project=str(project_root), app=app)

    is_app = (project_root / "dazzle.toml").is_file()
    examples_root = project_root if not is_app else project_root.parent
    app_name = project_root.name if is_app else app
    app_dir = project_root if is_app else ((examples_root / app) if app else None)
    probe_root = project_root if is_app else examples_root

    report.probes.append(_probe_or_error("product_maturity", lambda: _probe_product(probe_root)))
    report.probes.append(
        _probe_or_error(
            "demo_fleet",
            lambda: _probe_demo(examples_root, app_name if is_app else app),
        )
    )
    report.probes.append(_probe_or_error("journey_maturity", lambda: _probe_journey(probe_root)))

    targets = _resolve_targets(is_app=is_app, app_dir=app_dir, examples_root=examples_root)
    persona_residual, stills_residual, metric_list_residual = _score_targets(
        report, targets, min_home_hits=min_home_hits
    )

    probe_res = sum(max(p.residual, 0) for p in report.probes)
    report.residual_total = probe_res + persona_residual + stills_residual + metric_list_residual

    nxt, strategy, force, recs = _recommend(
        report.probes, persona_residual, stills_residual, metric_list_residual
    )
    report.next = nxt or _next_from_felt(report)
    report.next_strategy = strategy
    report.force = force
    report.recommended = recs
    return report


def _next_from_felt(report: ProductQualityReport) -> str | None:
    """Prefer residual persona-home app, metric/list, then residual empty-hero still app."""
    for row in report.persona_homes:
        if row.get("residual") and row.get("app"):
            return str(row["app"])
    for row in report.metric_list:
        if row.get("residual") and row.get("app"):
            return str(row["app"])
    for row in report.stills:
        if row.get("residual") and row.get("app"):
            return str(row["app"])
    return None


def score_status_lines(report: ProductQualityReport) -> list[str]:
    """One-line status strings for cycle logs / agent OBSERVE."""
    lines = [p.status for p in report.probes]
    ph_res = sum(1 for h in report.persona_homes if h.get("residual"))
    lines.append(
        f"persona_homes apps={len({h.get('app') for h in report.persona_homes})} "
        f"residual={ph_res} next={report.next or '-'}"
    )
    ml_res = sum(1 for h in report.metric_list if h.get("residual"))
    ml_risk = sum(1 for h in report.metric_list if h.get("risk"))
    lines.append(
        f"metric_list apps={len({h.get('app') for h in report.metric_list})} "
        f"residual={ml_res} risk={ml_risk} next={report.next or '-'}"
    )
    st_res = sum(1 for s in report.stills if s.get("residual"))
    lines.append(f"stills residual={st_res} next={report.next or '-'}")
    force = f" force={report.force}" if report.force else ""
    lines.append(
        f"product_quality residual_total={report.residual_total} next={report.next or '-'}{force}"
    )
    return lines
