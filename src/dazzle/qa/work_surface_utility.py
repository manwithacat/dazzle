"""Work-surface utility ontology + static fit scan.

Pairs with ``packages/hatchi-maxchi/docs/agent/work_surface_utility.toml`` and
``pick-a-work-surface.md``. Answers:

* Which region Hyperpart fits a job (ontology)
* Where example apps' DSL display diverges from ontology hints (residual)

Used by improve (aggressive hyperpart utility digs) and agents choosing
``display:`` / region kinds. Not a visual/coherence score.
"""

from __future__ import annotations

import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from dazzle.core.appspec_loader import load_project_appspec

REPO = Path(__file__).resolve().parents[3]
ONTOLOGY_PATH = REPO / "packages" / "hatchi-maxchi" / "docs" / "agent" / "work_surface_utility.toml"

# Map DSL display / region tokens → ontology surface id
_DISPLAY_ALIASES: dict[str, str] = {
    "kanban": "kanban",
    "timeline": "timeline",
    "day_timeline": "day_timeline",
    "task_inbox": "task_inbox",
    "queue": "queue",
    "list": "list",
    "table": "list",
    "activity_feed": "activity_feed",
    "status_list": "status_list",
    "grid": "list",
    "grid_list": "list",
    "pdf_viewer": "list",  # document surface — not a work board; treat as list residual-free
}

# Charts / chrome / detail embeds are not work boards — skip in scan.
_CHROME_DISPLAYS: frozenset[str] = frozenset(
    {
        "metrics",
        "summary",
        "bar_chart",
        "line_chart",
        "area_chart",
        "sparkline",
        "heatmap",
        "histogram",
        "box_plot",
        "funnel",
        "funnel_chart",
        "pivot",
        "pivot_table",
        "comparison",
        "cohort_strip",
        "entity_card",
        "profile_card",
        "map",
        "search_box",
        "pdf_viewer",
        "diagram",
        "tree",
        "tabbed_list",
        "insight_summary",
        "radar",
        "bullet",
        "bar_track",
        "action_grid",
        "pipeline_steps",
        "confirm_action_panel",
        "progress",
        "detail",  # embedded detail region, not a board
    }
)

_MODE_SKIP = frozenset({"view", "detail", "create", "edit"})


@dataclass(frozen=True)
class WorkSurface:
    id: str
    layer: str
    job: str
    use_when: tuple[str, ...]
    refuse_when: tuple[str, ...]
    prefers_over: tuple[str, ...]
    utility_axes: tuple[str, ...]
    dsl_hints: tuple[str, ...]
    measure_proxy: str


@dataclass
class FitFinding:
    """One surface in an app vs ontology."""

    app: str
    surface_name: str
    entity: str
    display: str
    ontology_id: str | None
    status: str  # matched | unknown_display | missing_ontology
    severity: str
    description: str

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


def ontology_path() -> Path:
    return ONTOLOGY_PATH


def load_ontology(path: Path | None = None) -> dict[str, Any]:
    p = path or ONTOLOGY_PATH
    data = tomllib.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"ontology root must be a table: {p}")
    return data


def _str_tuple(val: Any) -> tuple[str, ...]:
    """Coerce a TOML list field to a tuple of strings."""
    if not val:
        return ()
    return tuple(str(x) for x in val)


def _row_to_surface(row: dict[str, Any]) -> WorkSurface | None:
    sid = str(row.get("id") or "").strip()
    if not sid:
        return None
    return WorkSurface(
        id=sid,
        layer=str(row.get("layer") or "region"),
        job=str(row.get("job") or ""),
        use_when=_str_tuple(row.get("use_when")),
        refuse_when=_str_tuple(row.get("refuse_when")),
        prefers_over=_str_tuple(row.get("prefers_over")),
        utility_axes=_str_tuple(row.get("utility_axes")),
        dsl_hints=_str_tuple(row.get("dsl_hints")),
        measure_proxy=str(row.get("measure_proxy") or ""),
    )


def surfaces_from_ontology(data: dict[str, Any] | None = None) -> list[WorkSurface]:
    raw = data if data is not None else load_ontology()
    out: list[WorkSurface] = []
    for row in list(raw.get("surface") or []):
        if not isinstance(row, dict):
            continue
        surface = _row_to_surface(row)
        if surface is not None:
            out.append(surface)
    return out


def surface_by_id(data: dict[str, Any] | None = None) -> dict[str, WorkSurface]:
    return {s.id: s for s in surfaces_from_ontology(data)}


def normalize_display(display: str) -> str | None:
    d = (display or "").strip().lower()
    if not d:
        return "list"  # mode list default
    return _DISPLAY_ALIASES.get(d)


def _surface_mode(surface: Any) -> str:
    mode = getattr(surface, "mode", None)
    return str(getattr(mode, "value", mode) or "").strip().lower()


def _first_display_token(obj: Any, attrs: tuple[str, ...]) -> str:
    for attr in attrs:
        val = getattr(obj, attr, None)
        if val is None:
            continue
        text = str(getattr(val, "value", val) or "").strip()
        if text and text.lower() not in _MODE_SKIP:
            return text
    return ""


def _surface_display(surface: Any) -> str:
    """Explicit board/stream display token only — not mode (view/list)."""
    text = _first_display_token(surface, ("display", "region_kind", "list_display"))
    if text:
        return text
    ux = getattr(surface, "ux", None)
    if ux is not None:
        return _first_display_token(ux, ("display", "region"))
    return ""


def _region_display(region: Any) -> str:
    disp = getattr(region, "display", None)
    if disp is None:
        return ""
    return str(getattr(disp, "value", disp) or "").strip().lower()


def _entity_name(obj: Any) -> str:
    """Best-effort entity name from region/surface IR shapes.

    String-literal getattr keys are intentional — IR reader parity scans them.
    """
    for key in ("entity", "source"):
        val = getattr(obj, key, None)
        if val is not None and str(val).strip():
            return str(val).strip()
    # DocumentSpec / some regions use for_entity
    val = getattr(obj, "for_entity", None)
    if val is not None and str(val).strip():
        return str(val).strip()
    return ""


def _append_finding(
    findings: list[FitFinding],
    *,
    app: str,
    surface_name: str,
    entity: str,
    display_raw: str,
    known: dict[str, WorkSurface],
) -> None:
    oid = normalize_display(display_raw) if display_raw else "list"
    if oid is None:
        findings.append(
            FitFinding(
                app=app,
                surface_name=surface_name,
                entity=entity,
                display=display_raw,
                ontology_id=None,
                status="unknown_display",
                severity="low",
                description=(
                    f"{surface_name!r} display={display_raw!r} is not in the "
                    f"work-surface utility ontology — extend work_surface_utility.toml "
                    f"or map an alias (see pick-a-work-surface.md)."
                ),
            )
        )
        return
    if oid not in known:
        findings.append(
            FitFinding(
                app=app,
                surface_name=surface_name,
                entity=entity,
                display=display_raw,
                ontology_id=oid,
                status="missing_ontology",
                severity="medium",
                description=f"Ontology id {oid!r} missing from work_surface_utility.toml",
            )
        )
        return
    findings.append(
        FitFinding(
            app=app,
            surface_name=surface_name,
            entity=entity,
            display=display_raw or oid,
            ontology_id=oid,
            status="matched",
            severity="low",
            description=f"{surface_name} → {oid}: {known[oid].job}",
        )
    )


def _scan_workspace_regions(
    appspec: Any,
    *,
    app: str,
    known: dict[str, WorkSurface],
    findings: list[FitFinding],
    seen_keys: set[str],
) -> None:
    for ws in list(getattr(appspec, "workspaces", None) or []):
        ws_name = str(getattr(ws, "name", "") or "")
        for region in list(getattr(ws, "regions", None) or []):
            rname = str(getattr(region, "name", "") or "")
            entity = _entity_name(region)
            display_raw = _region_display(region) or "list"
            if display_raw in _CHROME_DISPLAYS:
                continue
            key = f"ws:{ws_name}/{rname}:{display_raw}"
            if key in seen_keys:
                continue
            seen_keys.add(key)
            _append_finding(
                findings,
                app=app,
                surface_name=f"{ws_name}.{rname}",
                entity=entity,
                display_raw=display_raw,
                known=known,
            )


def _scan_list_surfaces(
    appspec: Any,
    *,
    app: str,
    known: dict[str, WorkSurface],
    findings: list[FitFinding],
    seen_keys: set[str],
) -> None:
    """List-mode surfaces not already covered as regions (admin lists, etc.)."""
    for surface in list(getattr(appspec, "surfaces", None) or []):
        if _surface_mode(surface) != "list":
            continue
        name = str(getattr(surface, "name", "") or "")
        entity = _entity_name(surface)
        key = f"surf:{name}"
        if any(name in f.surface_name for f in findings):
            continue
        if key in seen_keys:
            continue
        seen_keys.add(key)
        _append_finding(
            findings,
            app=app,
            surface_name=name,
            entity=entity,
            display_raw="list",
            known=known,
        )


def scan_project(project: Path, *, app_name: str | None = None) -> list[FitFinding]:
    """Scan workspace regions (+ list surfaces) for work-surface ontology fit.

    Prefer **workspace.region.display** (where kanban/timeline/queue live).
    List surfaces without a workspace region still count as ``list``.
    """
    appspec = load_project_appspec(project)
    app = app_name or project.name
    known = surface_by_id()
    findings: list[FitFinding] = []
    seen_keys: set[str] = set()
    _scan_workspace_regions(appspec, app=app, known=known, findings=findings, seen_keys=seen_keys)
    _scan_list_surfaces(appspec, app=app, known=known, findings=findings, seen_keys=seen_keys)
    return findings


def residual(findings: list[FitFinding]) -> int:
    """Count actionable mismatches (not simple matched rows)."""
    return sum(1 for f in findings if f.status != "matched")


def summary(findings: list[FitFinding]) -> dict[str, Any]:
    by_status: dict[str, int] = {}
    by_ontology: dict[str, int] = {}
    for f in findings:
        by_status[f.status] = by_status.get(f.status, 0) + 1
        if f.ontology_id:
            by_ontology[f.ontology_id] = by_ontology.get(f.ontology_id, 0) + 1
    return {
        "count": len(findings),
        "residual": residual(findings),
        "by_status": by_status,
        "by_ontology": by_ontology,
    }
