"""Mechanical coverage inventory for agent QA ladder (#1625 T2).

Derives a walkable URL set from AppSpec surfaces + workspaces. Used by
``dazzle qa trial-coverage`` (static list and optional live HTTP probe).

Drive rule for **coverage** mode: direct URL from inventory is OK.
Drive rule for **journey** mode: do not use this inventory as a cheat sheet —
that mode is affordance-only (see trial mission ``mode=journey``).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class InventoryTarget:
    """One walkable target in the mechanical coverage set."""

    kind: str  # surface_list | surface_create | workspace | app_home
    name: str
    url: str
    entity: str = ""
    personas_hint: list[str] = field(default_factory=list)
    notes: str = ""

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


def _entity_slug(name: str) -> str:
    from dazzle.core.strings import entity_slug

    return entity_slug(name)


def _surface_mode(surface: Any) -> str:
    raw = getattr(surface, "mode", None)
    return str(getattr(raw, "value", raw) or "").lower()


def _add_unique(
    targets: list[InventoryTarget],
    seen: set[str],
    target: InventoryTarget,
) -> None:
    if target.url in seen:
        return
    seen.add(target.url)
    targets.append(target)


def _surface_target(surface: Any) -> InventoryTarget | None:
    entity = getattr(surface, "entity_ref", None) or getattr(surface, "entity", None)
    if not entity:
        return None
    slug = _entity_slug(str(entity))
    mode = _surface_mode(surface)
    sname = str(getattr(surface, "name", "") or slug)
    if "list" in mode:
        return InventoryTarget(
            kind="surface_list", name=sname, url=f"/app/{slug}", entity=str(entity)
        )
    if "create" in mode:
        return InventoryTarget(
            kind="surface_create",
            name=sname,
            url=f"/app/{slug}/create",
            entity=str(entity),
        )
    return None


def build_coverage_inventory(appspec: Any) -> list[InventoryTarget]:
    """Build list/create surface + workspace inventory from AppSpec.

    Detail/edit/view surfaces need record ids and are omitted (same as
    guide-walk scope A). Callers that seed data may extend the list later.
    """
    targets: list[InventoryTarget] = [
        InventoryTarget(kind="app_home", name="app", url="/app", notes="default landing"),
    ]
    seen: set[str] = {"/app"}
    for surface in list(getattr(appspec, "surfaces", None) or []):
        t = _surface_target(surface)
        if t is not None:
            _add_unique(targets, seen, t)
    for ws in list(getattr(appspec, "workspaces", None) or []):
        wname = str(getattr(ws, "name", "") or "")
        if not wname:
            continue
        _add_unique(
            targets,
            seen,
            InventoryTarget(
                kind="workspace",
                name=wname,
                url=f"/app/workspaces/{wname}",
                notes=str(getattr(ws, "title", "") or ""),
            ),
        )
    return targets


@dataclass
class CoverageHit:
    """Result of probing one inventory URL for one persona."""

    url: str
    name: str
    kind: str
    persona: str
    status: str  # reached | rbac_denied | blocked | error | skipped
    http_status: int | None = None
    detail: str = ""
    ownership_hint: str = "unclear"  # product | rbac_expected | harness | …

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


def classify_http_status(code: int) -> tuple[str, str]:
    """Map HTTP status → (status, ownership_hint)."""
    if 200 <= code < 400:
        return "reached", "unclear"
    if code in (401, 403):
        return "rbac_denied", "rbac_expected"
    if code == 404:
        return "blocked", "product"
    if code >= 500:
        return "error", "product"
    return "blocked", "unclear"


def matrix_expected_deny(appspec: Any, persona: str, target: InventoryTarget) -> bool | None:
    """True if RBAC matrix says persona should be denied list/create on entity.

    Returns None when matrix cannot decide (workspace / no entity).
    """
    if not target.entity:
        return None
    try:
        from dazzle.rbac.matrix import PolicyDecision, generate_access_matrix
    except Exception:
        return None
    matrix = generate_access_matrix(appspec)
    op = "create" if target.kind == "surface_create" else "list"
    # Persona id is usually the role name in examples.
    decision = matrix.get(persona, target.entity, op)
    return decision == PolicyDecision.DENY


def inventory_to_json(targets: list[InventoryTarget]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "count": len(targets),
        "targets": [t.to_json() for t in targets],
    }


def coverage_report_to_json(
    *,
    app: str,
    persona: str,
    targets: list[InventoryTarget],
    hits: list[CoverageHit],
) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for h in hits:
        counts[h.status] = counts.get(h.status, 0) + 1
    return {
        "schema_version": 1,
        "mode": "coverage",
        "app": app,
        "persona": persona,
        "inventory_count": len(targets),
        "hits": [h.to_json() for h in hits],
        "counts": counts,
    }
