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

**Warehouse Index (WI)** — continuous 0–1 objective (higher = more warehouse /
lower inverse product utility). Agents minimize when discrete residual is 0.

Components (anti-gaming v2):

* **D** warehouse density — product list surfaces vs *effective job desks*
  (workspace weight from mode/source diversity; desk-sprawl capped by
  entity scale so padding empty desks cannot dilute D forever)
* **N** ``nav_list_share`` — persona nav list-link share (compiled shell)
* **L** landing thinness — inverse of *signal richness* on default workspaces
  (unique display-mode × source pairs, not raw region count — pads of the
  same entity list do not score)
* **J** job thinness — unbound product stories / uncovered personas
* **G** graph poverty — product list surfaces without open-via

``WI = 0.30·D + 0.25·N + 0.25·L + 0.10·J + 0.10·G``

Residual (critical/thin/deepen) remains the *floor* gate; WI is the *gradient*
for managed scope-creep feature slices after residual clears.

This is the instance-level counterpart to framework ``ux-maturity``
(``docs/reference/ux-maturity.md``): that rubric asks whether *primitives*
default right; this probe asks whether *example products* use those
defaults as the primary path.

Usage (from monorepo root)::

    python scripts/example_product_maturity.py
    python scripts/example_product_maturity.py --json
    python scripts/example_product_maturity.py --status
    python scripts/example_product_maturity.py --warehouse-index
    python scripts/example_product_maturity.py --next
    python scripts/example_product_maturity.py --next-wi
    python scripts/example_product_maturity.py --app support_tickets
    python scripts/example_product_maturity.py --paths /path/to/other_app
    python scripts/example_product_maturity.py --strict

Exit codes:
  0 — no residual (or single --app meets bar)
  1 — residuals remain (--strict / default fleet)
  2 — usage / environment error

Consumed by:
  - ``improve/lanes/example-apps.md`` (prefer product residuals before Tier-1)
  - agents deciding whether an app is a warehouse or a product
  - quiet-fleet feature_creep: minimize ``wi_fleet`` / ``wi_next``
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

# Landing signal richness saturates at this many unique (mode_family, source) pairs.
_LANDING_SIGNAL_CAP = 5

# A product workspace counts as a full "job desk" toward D when job_weight ≥ this.
_JOB_DESK_WEIGHT_FULL = 0.55

# Soft cap: effective job desks cannot exceed this multiple of entity_count
# (prevents infinite D dilution by empty desk sprawl on thin domains).
_DESK_ENTITY_SCALE = 1.5
_DESK_SCALE_FLOOR = 3.0

# WI weights (sum = 1.0). Higher component → more warehouse.
# L weight raised (v2): signal richness is the inverse-utility proxy for landings.
_WI_WEIGHTS = {
    "D": 0.30,  # warehouse_density (effective job desks)
    "N": 0.25,  # nav_list_share
    "L": 0.25,  # landing thinness (signal richness)
    "J": 0.10,  # job thinness
    "G": 0.10,  # graph poverty
}

# Soft floor for "true all-clear" feature-creep stop (agents may still deepen).
WI_FLOOR = 0.25


def _mode_family(display: Any) -> str:
    """Collapse display modes into families so list+queue of same entity ≠ 2 jobs."""
    raw = str(getattr(display, "value", display) or "").lower()
    if not raw:
        return "unknown"
    if raw in {"list", "queue", "table", "scanner_table"}:
        return "listish"
    if raw in {"metrics", "summary", "kpi"}:
        return "metrics"
    if raw in {"bar_chart", "funnel_chart", "line_chart", "pie_chart", "chart"}:
        return "chart"
    if raw in {"kanban", "board"}:
        return "kanban"
    if raw in {"status_list", "strip", "activity", "timeline", "day_timeline"}:
        return "context"
    if raw in {"grid", "cards", "gallery"}:
        return "grid"
    return raw


def _region_source_key(region: Any) -> str:
    src = getattr(region, "source", None)
    if src is None:
        return ""
    return str(getattr(src, "name", src) or "").strip()


def _workspace_region_signals(regions: list[Any]) -> tuple[int, int, int, float]:
    """Return (region_count, mode_families, sources, signal_richness 0–1).

    Signal richness uses unique ``(mode_family, source)`` pairs (cap
    ``_LANDING_SIGNAL_CAP``). Padding six list regions of one entity yields
    one signal; metrics + queue + chart + status_list yield four.
    """
    n = len(regions)
    if n == 0:
        return 0, 0, 0, 0.0
    modes: set[str] = set()
    sources: set[str] = set()
    signals: set[tuple[str, str]] = set()
    for r in regions:
        fam = _mode_family(getattr(r, "display", None))
        src = _region_source_key(r)
        modes.add(fam)
        if src:
            sources.add(src)
        # Sourceless context regions still count (status strips, readiness).
        signals.add((fam, src or f"__{fam}__"))
    richness = min(len(signals), _LANDING_SIGNAL_CAP) / float(_LANDING_SIGNAL_CAP)
    return n, len(modes), len(sources), _clamp01(richness)


def _workspace_job_weight(regions: list[Any]) -> float:
    """0–1 how job-like a product workspace is (feeds D effective desks).

    Requires multi-signal desks: a single list dump scores near zero even if
    the workspace exists. Mix of mode families + entity sources scores high.
    """
    _n, modes, sources, richness = _workspace_region_signals(regions)
    if _n == 0:
        return 0.0
    # Half from signal richness, half from mode diversity (cap 4 families).
    mode_part = min(modes, 4) / 4.0
    return _clamp01(0.55 * richness + 0.45 * mode_part)


@dataclass
class PersonaLanding:
    persona_id: str
    default_workspace: str | None
    workspace_exists: bool = False
    region_count: int = 0
    mode_count: int = 0
    source_count: int = 0
    signal_count: int = 0
    richness: float = 0.0  # 0–1 anti-game landing quality
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
    # Job-weighted product workspaces (anti desk-sprawl); used in D.
    effective_product_workspaces: float = 0.0
    list_surfaces: int = 0
    crud_surfaces: int = 0  # list+create+edit
    warehouse_density: float = 0.0
    # Compiled-nav share of entity-list links among product personas (0–1).
    nav_list_share: float = 0.0
    nav_personas_scored: int = 0
    bound_stories: int = 0
    product_stories: int = 0
    job_personas_covered: int = 0
    entity_count: int = 0
    open_via_lists: int = 0  # list surfaces with open_via / open_entity
    # Continuous warehouse components (0–1, higher = more warehouse).
    wi_D: float = 0.0
    wi_N: float = 0.0
    wi_L: float = 0.0
    wi_J: float = 0.0
    wi_G: float = 0.0
    wi: float = 0.0  # weighted Warehouse Index
    wi_primary: str = "-"  # largest component key (D|N|L|J|G)
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


def _is_platform_surface(name: str) -> bool:
    """Framework/platform list shells — not product warehouse lists.

    Injected admin surfaces (``_admin_health``, ``auditentry_admin``, …)
    must not inflate D/G: product open-via coverage is the graph signal.
    """
    n = (name or "").lower()
    if not n:
        return False
    if n.startswith("_") or n.startswith("platform_") or n.startswith("admin_"):
        return True
    if n.endswith("_admin") or n.endswith("_platform"):
        return True
    return n in {
        "admin",
        "platform",
        "settings",
        "health",
        "deploys",
    }


def _is_product_persona(persona_id: str) -> bool:
    return persona_id.lower() not in _PLATFORM_PERSONA_IDS


def _mode_str(surface: Any) -> str:
    raw = getattr(surface, "mode", None)
    return str(getattr(raw, "value", raw) or "").lower()


def _clamp01(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return float(x)


def _list_has_open_via(surface: Any) -> bool:
    """True when a list surface declares context-hop open targets."""
    ov = getattr(surface, "open_via", None)
    oe = getattr(surface, "open_entity", None)
    targets = getattr(surface, "open_via_targets", None)
    if ov is not None and str(ov).strip():
        return True
    if oe is not None and str(oe).strip():
        return True
    if targets:
        return True
    return False


def compute_warehouse_index(m: AppProductMaturity) -> AppProductMaturity:
    """Fill continuous WI fields on an already-scored maturity row.

    Pure-ish: only uses fields already on ``m`` (no IR re-load). Idempotent.

    Inverse-utility intent: higher WI ⇒ more warehouse structure (list-primary
    shells, thin/padded landings, unbound jobs, list-soup nav, no graph hops).
    Anti-gaming v2: L uses signal richness; D uses effective job desks.
    """
    d = _clamp01(m.warehouse_density)
    n = _clamp01(m.nav_list_share)

    # L — landing thinness (inverse mean signal richness, not raw region count).
    region_rich: list[float] = []
    for pl in m.landings:
        if not isinstance(pl, dict):
            continue
        if not pl.get("ok"):
            region_rich.append(0.0)
            continue
        # Prefer precomputed richness; fall back for synthetic test rows.
        if "richness" in pl:
            region_rich.append(_clamp01(float(pl.get("richness") or 0.0)))
        else:
            rc = int(pl.get("region_count") or 0)
            # Legacy fallback: raw count / cap (tests without richness).
            region_rich.append(min(rc, _LANDING_SIGNAL_CAP) / float(_LANDING_SIGNAL_CAP))
    if region_rich:
        landing_thin = _clamp01(1.0 - (sum(region_rich) / len(region_rich)))
    elif m.product_personas > 0:
        landing_thin = 1.0
    elif m.list_surfaces > 0:
        landing_thin = 1.0
    else:
        landing_thin = 0.0

    # J — job thinness (unbound stories or uncovered personas).
    if m.product_stories > 0:
        job_thin = _clamp01(1.0 - (m.bound_stories / float(m.product_stories)))
    elif m.product_personas > 0:
        job_thin = _clamp01(1.0 - (m.job_personas_covered / float(m.product_personas)))
    elif m.list_surfaces > 0:
        job_thin = 1.0
    else:
        job_thin = 0.0

    # G — graph poverty (lists without open-via on multi-entity apps).
    list_n = max(m.list_surfaces, 0)
    if list_n <= 0 or m.entity_count < 2:
        graph_poor = 0.0
    else:
        open_share = m.open_via_lists / float(list_n)
        graph_poor = _clamp01(1.0 - open_share)
        if m.entity_count < 3:
            graph_poor = _clamp01(graph_poor * 0.5)

    m.wi_D = d
    m.wi_N = n
    m.wi_L = landing_thin
    m.wi_J = job_thin
    m.wi_G = graph_poor
    m.wi = _clamp01(
        _WI_WEIGHTS["D"] * d
        + _WI_WEIGHTS["N"] * n
        + _WI_WEIGHTS["L"] * landing_thin
        + _WI_WEIGHTS["J"] * job_thin
        + _WI_WEIGHTS["G"] * graph_poor
    )
    components = {
        "D": d,
        "N": n,
        "L": landing_thin,
        "J": job_thin,
        "G": graph_poor,
    }
    _order = {"D": 0, "N": 1, "L": 2, "J": 3, "G": 4}
    m.wi_primary = max(components.items(), key=lambda kv: (kv[1], -_order[kv[0]]))[0]
    return m


def _accessible_product_workspaces(appspec: Any, persona: Any) -> int:
    """Count product workspaces this persona may open (access gate)."""
    try:
        from dazzle.page.converters.workspace_converter import workspace_allowed_personas
    except Exception:  # noqa: BLE001
        return 0
    personas = list(getattr(appspec, "personas", None) or [])
    n = 0
    for ws in getattr(appspec, "workspaces", None) or []:
        if _is_platform_workspace(ws.name):
            continue
        allowed = workspace_allowed_personas(ws, personas)
        if allowed is None or persona.id in set(allowed):
            n += 1
    return n


def _nav_list_share(appspec: Any, product_personas: list[Any]) -> tuple[float, int]:
    """Average warehouse-ness of each product persona's navigation path.

    Uses ``build_persona_nav`` (live shell). Auto-discover only emits entity
    list links (by design); we therefore credit **accessible product
    workspaces** as non-warehouse destinations so apps with strong
    ``default_workspace`` landings are not false-flagged solely because
    the sidebar still lists region source entities.
    """
    if not product_personas:
        return 0.0, 0
    try:
        from dazzle.page.converters.nav_builder import build_persona_nav
        from dazzle.rbac.matrix import generate_access_matrix

        matrix = generate_access_matrix(appspec)
        shares: list[float] = []
        for p in product_personas:
            nav = build_persona_nav(appspec, p, matrix)
            list_n = 0
            ws_n = 0
            for g in nav.groups:
                for link in g.links:
                    route = link.route or ""
                    if "/workspaces/" in route or route.startswith("/workspaces"):
                        ws_n += 1
                    else:
                        list_n += 1
            # Auto-discover never adds workspace destinations — credit access.
            if getattr(nav, "auto_discovered", True):
                ws_n = max(ws_n, _accessible_product_workspaces(appspec, p))
            # Landing workspace is always a product destination for this persona.
            dws = getattr(p, "default_workspace", None)
            if dws and not _is_platform_workspace(str(dws)):
                ws_n = max(ws_n, 1)
            total = list_n + ws_n
            if total:
                shares.append(list_n / total)
        if not shares:
            return 0.0, 0
        return sum(shares) / len(shares), len(shares)
    except Exception:  # noqa: BLE001
        return 0.0, 0


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
    open_via_lists = 0
    for s in surfaces:
        sname = str(getattr(s, "name", "") or "")
        if _is_platform_surface(sname):
            continue  # platform/admin shells — not product D/G numerator
        mode = _mode_str(s)
        if "list" in mode:
            list_n += 1
            crud_n += 1
            if _list_has_open_via(s):
                open_via_lists += 1
        elif "create" in mode or "edit" in mode:
            crud_n += 1
    m.list_surfaces = list_n
    m.crud_surfaces = crud_n
    m.open_via_lists = open_via_lists

    domain = getattr(appspec, "domain", None)
    entities = list(getattr(domain, "entities", None) or getattr(appspec, "entities", None) or [])
    m.entity_count = len(entities)

    # Effective job desks for D (anti desk-sprawl): weight each product
    # workspace by mode/source signal diversity, then scale-cap by entities.
    job_weight_sum = 0.0
    for w in workspaces:
        if _is_platform_workspace(w.name):
            continue
        regions = list(getattr(w, "regions", None) or [])
        job_weight_sum += _workspace_job_weight(regions)
    scale_cap = max(_DESK_SCALE_FLOOR, float(m.entity_count) * _DESK_ENTITY_SCALE)
    m.effective_product_workspaces = min(job_weight_sum, scale_cap)

    # Density: lists vs effective job desks (not raw workspace count).
    denom = list_n + max(m.effective_product_workspaces, 0.0)
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

    # --- Compiled nav (entity-list share) ---
    m.nav_list_share, m.nav_personas_scored = _nav_list_share(appspec, product_personas)

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
                rc, modes, sources, richness = _workspace_region_signals(regions)
                pl.region_count = rc
                pl.mode_count = modes
                pl.source_count = sources
                # signal_count approximated via richness * cap for diagnostics
                pl.signal_count = int(round(richness * _LANDING_SIGNAL_CAP))
                pl.richness = richness
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
    elif m.warehouse_density > 0.70:
        # Strict > so 7 lists + 3 workspaces (0.70) can clear after job landings.
        score += 30
        reasons.append(f"warehouse_density({m.warehouse_density:.2f})")

    # Nav: if product personas' paths are mostly entity lists, warehouse.
    if m.nav_personas_scored > 0 and m.nav_list_share >= 0.85:
        score += 40
        reasons.append(f"nav_list_share({m.nav_list_share:.2f})")
    elif m.nav_personas_scored > 0 and m.nav_list_share > 0.70:
        score += 20
        reasons.append(f"nav_list_share({m.nav_list_share:.2f})")

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

    return compute_warehouse_index(m)


def discover_apps() -> list[Path]:
    if not EXAMPLES.is_dir():
        return []
    return sorted(p for p in EXAMPLES.iterdir() if p.is_dir() and (p / "dazzle.toml").exists())


def scan(
    app_filter: str | None = None,
    paths: list[Path] | None = None,
) -> list[AppProductMaturity]:
    """Score example fleet and/or arbitrary project paths (sibling apps)."""
    rows: list[AppProductMaturity] = []
    if paths:
        for p in paths:
            app_dir = Path(p).expanduser().resolve()
            if app_dir.is_file() and app_dir.name == "dazzle.toml":
                app_dir = app_dir.parent
            rows.append(score_app(app_dir))
    else:
        for app_dir in discover_apps():
            if app_filter and app_dir.name != app_filter:
                continue
            rows.append(score_app(app_dir))
    rows.sort(key=lambda r: (-r.score, -r.wi, r.app))
    return rows


def fleet_wi_mean(rows: list[AppProductMaturity]) -> float:
    if not rows:
        return 0.0
    return sum(r.wi for r in rows) / float(len(rows))


def next_wi_app(rows: list[AppProductMaturity]) -> AppProductMaturity | None:
    """Highest-WI app (managed scope-creep target)."""
    if not rows:
        return None
    return max(rows, key=lambda r: (r.wi, r.score, r.app))


def format_table(rows: list[AppProductMaturity]) -> str:
    lines = [
        f"{'app':28} {'tier':10} {'score':5} {'WI':>5} {'pri':>3} {'land':>5} "
        f"{'dens':>5} {'navL':>5} {'list':>4} {'ws':>3} {'jobs':>5} reasons",
        "-" * 115,
    ]
    for r in rows:
        land = f"{r.landing_ok}/{r.product_personas}"
        jobs = f"{r.job_personas_covered}/{r.product_personas}"
        reasons = ",".join(r.reasons) if r.reasons else "-"
        lines.append(
            f"{r.app:28} {r.tier:10} {r.score:5} {r.wi:5.2f} {r.wi_primary:>3} "
            f"{land:>5} {r.warehouse_density:5.2f} {r.nav_list_share:5.2f} "
            f"{r.list_surfaces:4} {r.product_workspaces:3} {jobs:>5} {reasons}"
        )
    residual = [r for r in rows if r.is_residual]
    wi_mean = fleet_wi_mean(rows)
    wi_next = next_wi_app(rows)
    lines.append("")
    lines.append(
        f"residual={len(residual)}/{len(rows)}  "
        f"critical={sum(1 for r in residual if r.tier == 'critical')}  "
        f"thin={sum(1 for r in residual if r.tier == 'thin')}  "
        f"deepen={sum(1 for r in residual if r.tier == 'deepen')}"
    )
    lines.append(
        f"wi_fleet={wi_mean:.3f}  wi_floor={WI_FLOOR:.2f}  "
        f"wi_next={wi_next.app if wi_next else '-'}  "
        f"wi_primary={wi_next.wi_primary if wi_next else '-'}"
    )
    if residual:
        lines.append(f"next={residual[0].app}")
    else:
        lines.append("next=")
    return "\n".join(lines)


def format_warehouse_index(rows: list[AppProductMaturity]) -> str:
    """Component breakdown for managed scope-creep (minimize WI)."""
    ordered = sorted(rows, key=lambda r: (-r.wi, r.app))
    lines = [
        f"{'app':28} {'WI':>5} {'D':>5} {'N':>5} {'L':>5} {'J':>5} {'G':>5} "
        f"{'pri':>3}  intervention",
        "-" * 90,
    ]
    interventions = {
        "D": "job desks with mixed modes/sources (not empty desk sprawl / list shells)",
        "N": "persona nav job destinations (not auto entity-list soup)",
        "L": "diversify landing signals (mode×source); pads of same-entity lists do not score",
        "J": "bind stories executed_by + process/surface paths",
        "G": "open-via on lists + related hubs for multi-entity graphs",
    }
    for r in ordered:
        hint = interventions.get(r.wi_primary, "-")
        lines.append(
            f"{r.app:28} {r.wi:5.2f} {r.wi_D:5.2f} {r.wi_N:5.2f} {r.wi_L:5.2f} "
            f"{r.wi_J:5.2f} {r.wi_G:5.2f} {r.wi_primary:>3}  {hint}"
        )
    wi_mean = fleet_wi_mean(rows)
    wi_next = next_wi_app(rows)
    lines.append("")
    lines.append(
        f"wi_fleet={wi_mean:.3f}  wi_floor={WI_FLOOR:.2f}  "
        f"wi_next={wi_next.app if wi_next else '-'}  "
        f"wi_primary={wi_next.wi_primary if wi_next else '-'}  "
        f"above_floor={sum(1 for r in rows if r.wi > WI_FLOOR)}/{len(rows)}"
    )
    lines.append(
        "objective: when residual=0, minimize wi_next (product DSL slice that "
        "moves wi_primary); map-only commits do not count"
    )
    return "\n".join(lines)


def format_status(rows: list[AppProductMaturity]) -> str:
    residual = [r for r in rows if r.is_residual]
    crit = sum(1 for r in residual if r.tier == "critical")
    thin = sum(1 for r in residual if r.tier == "thin")
    deepen = sum(1 for r in residual if r.tier == "deepen")
    nxt = residual[0].app if residual else "-"
    wi_mean = fleet_wi_mean(rows)
    wi_next = next_wi_app(rows)
    wi_n = wi_next.app if wi_next else "-"
    wi_p = wi_next.wi_primary if wi_next else "-"
    return (
        f"product_maturity apps={len(rows)} residual={len(residual)} "
        f"critical={crit} thin={thin} deepen={deepen} next={nxt} "
        f"wi_fleet={wi_mean:.3f} wi_next={wi_n} wi_primary={wi_p} "
        f"wi_floor={WI_FLOOR:.2f}"
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--app", help="Score a single example app by name")
    ap.add_argument(
        "--paths",
        nargs="+",
        metavar="DIR",
        help="Score arbitrary project dirs (sibling/real apps; not only examples/)",
    )
    ap.add_argument("--json", action="store_true", help="Emit full JSON payload")
    ap.add_argument("--status", action="store_true", help="One-line cycle log line")
    ap.add_argument(
        "--warehouse-index",
        action="store_true",
        help="Print continuous Warehouse Index table (minimize wi_next)",
    )
    ap.add_argument(
        "--next",
        action="store_true",
        help="Print only the next residual app id (empty if fleet mature)",
    )
    ap.add_argument(
        "--next-wi",
        action="store_true",
        help="Print highest-WI app id for feature_creep (empty if no apps)",
    )
    ap.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 when any residual remains",
    )
    ap.add_argument(
        "--strict-wi",
        action="store_true",
        help=f"Exit 1 when wi_fleet > wi_floor ({WI_FLOOR})",
    )
    args = ap.parse_args(argv)

    path_list = [Path(p) for p in (args.paths or [])] or None
    rows = scan(args.app, paths=path_list)
    if not rows:
        print("no example apps found", file=sys.stderr)
        return 2

    if args.next_wi:
        nxt = next_wi_app(rows)
        print(nxt.app if nxt else "")
        return 0

    if args.next:
        residual = [r for r in rows if r.is_residual]
        print(residual[0].app if residual else "")
        return 0 if not residual else 1

    if args.status:
        print(format_status(rows))
        return 0

    if args.warehouse_index:
        print(format_warehouse_index(rows))
        if args.strict_wi and fleet_wi_mean(rows) > WI_FLOOR:
            return 1
        return 0

    if args.json:
        print(json.dumps([asdict(r) for r in rows], indent=2))
    else:
        print(format_table(rows))

    residual = [r for r in rows if r.is_residual]
    if args.app and not residual:
        rc = 0
    elif args.strict or (not args.app and residual):
        rc = 1 if residual else 0
    else:
        rc = 0
    if args.strict_wi and fleet_wi_mean(rows) > WI_FLOOR:
        return 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
