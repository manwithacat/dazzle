"""Unified per-persona navigation builder (#1324).

Navigation is a pure function of (persona, appspec, rbac_matrix) — all static.
This module is the single source of a persona's sidebar: every page renders the
same precomputed NavModel for the current persona, so the three legacy builders
(workspace-page, entity-page, persona-union) can no longer drift.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from dazzle.page.converters.workspace_converter import workspace_allowed_personas
from dazzle.rbac.matrix import PolicyDecision  # runtime import (ui may import rbac)

if TYPE_CHECKING:
    from dazzle.core.ir.appspec import AppSpec
    from dazzle.core.ir.personas import PersonaSpec
    from dazzle.core.ir.workspaces import NavSpec, WorkspaceSpec
    from dazzle.rbac.matrix import AccessMatrix


@dataclass(frozen=True)
class NavLink:
    label: str
    route: str
    icon: str | None = None
    entity: str | None = None  # target entity/workspace name (filtering + FR-6 lint)
    # #1324 FR-4: render-time VISIBILITY condition (model_dump'd ConditionExpr,
    # mirroring the ``visible_condition: dict`` convention). ``None`` = always
    # visible. Evaluated at render time against roles + per-tenant config; the
    # link is hidden when it evaluates falsy. Visibility only — NOT access
    # control (the RBAC matrix still gates reachability). Only the curated path
    # populates this; auto-discover / anon paths leave it ``None``.
    when: dict[str, Any] | None = None


@dataclass(frozen=True)
class NavGroup:
    label: str
    icon: str | None
    collapsed: bool
    links: tuple[NavLink, ...]
    # #1324 FR-4: render-time VISIBILITY condition for the whole group
    # (model_dump'd ConditionExpr). ``None`` = always visible. When it evaluates
    # falsy at render time, the entire group (header + links) is hidden.
    when: dict[str, Any] | None = None


@dataclass(frozen=True)
class NavModel:
    groups: tuple[NavGroup, ...]
    auto_discovered: bool


def _route_for(appspec: AppSpec, target: str) -> str | None:
    """Resolve a nav item target (entity or workspace name) to a route.

    NOTE: route shapes are placeholders here — they are reconciled with the
    renderer's real app_prefix in slice 3."""
    for ws in getattr(appspec, "workspaces", []) or []:
        if ws.name == target:
            return f"/workspaces/{ws.name}"
    for surface in getattr(appspec, "surfaces", []) or []:
        if surface.mode.value == "list" and surface.entity_ref == target:
            return f"/list/{target}"
    return None


def _titleize(name: str) -> str:
    return name.replace("_", " ").title()


def _label_for(appspec: AppSpec, target: str) -> str:
    """Human-friendly nav label for a target (entity or workspace name).

    Mirrors the legacy label precedence exactly (template_compiler /
    page_routes), so the nav_model renderer produces the same sidebar copy:

    - Workspace target → ``ws.title`` else ``ws.name.replace("_"," ").title()``
      (page_routes.py ~2588, template_compiler.py:1402).
    - Entity target → its LIST surface's ``title`` else
      ``entity.replace("_"," ").title()`` (template_compiler.py:1459 / :1505).
    """
    ws = _workspace_for(appspec, target)
    if ws is not None:
        return ws.title or _titleize(ws.name)
    for surface in appspec.surfaces or []:
        if surface.mode.value == "list" and surface.entity_ref == target:
            if surface.title:
                return surface.title
            break
    return _titleize(target)


def _persona_can_list(matrix: AccessMatrix, role: str, entity: str) -> bool:
    """FR-3: a persona may see a nav link only if its role isn't DENYed list access."""
    return matrix.get(role, entity, "list") != PolicyDecision.DENY


# #1626 P0-4: platform/admin infrastructure must not pollute product sidebars.
# System Health / Deploy History / Feedback Reports belong on `_platform_admin`,
# not next to Tickets for an agent persona.
_PLATFORM_NAV_ENTITY_NAMES: frozenset[str] = frozenset(
    {
        "SystemHealth",
        "DeployHistory",
        "FeedbackReport",
        "SystemMetric",
        "ProcessRun",
        "JobRun",
        "AuditEntry",
        "AIJob",
        "LogEntry",
        "EventTrace",
        "OnboardingState",
        "Session",
    }
)
_PLATFORM_PERSONA_IDS: frozenset[str] = frozenset(
    {"admin", "platform_admin", "superuser", "operator", "sysadmin"}
)


def _is_platform_nav_target(appspec: AppSpec, target: str) -> bool:
    """True for framework-injected admin/platform destinations."""
    if not target:
        return False
    if target.startswith("_platform_") or target.startswith("_admin_"):
        return True
    if target in _PLATFORM_NAV_ENTITY_NAMES:
        return True
    for entity in getattr(getattr(appspec, "domain", None), "entities", None) or []:
        if entity.name == target and getattr(entity, "domain", None) == "platform":
            return True
    return False


def _persona_is_platform_operator(persona: PersonaSpec) -> bool:
    return (persona.id or "").lower() in _PLATFORM_PERSONA_IDS


def _workspace_for(appspec: AppSpec, target: str) -> WorkspaceSpec | None:
    """Return the WorkspaceSpec named ``target``, or ``None`` if ``target`` is
    not a declared workspace (i.e. it should be treated as an entity)."""
    for ws in appspec.workspaces or []:
        if ws.name == target:
            return ws
    return None


def _persona_can_reach(
    appspec: AppSpec,
    target: str,
    persona: PersonaSpec,
    matrix: AccessMatrix,
) -> bool:
    """FR-3 access filter for a nav item's target, dispatching on target kind.

    A curated ``NavItemIR.entity`` may name a **workspace** rather than an
    entity. Workspaces aren't in the RBAC entity matrix, so the entity-matrix
    check (``_persona_can_list``) would wrongly DENY them. Disambiguate by
    name: if ``target`` matches a declared workspace, filter by **workspace
    access** (``workspace_allowed_personas``); otherwise filter by the entity
    matrix. ``_auto_discover`` only emits entity sources, so it stays on the
    entity-matrix path."""
    ws = _workspace_for(appspec, target)
    if ws is not None:
        personas = list(getattr(appspec, "personas", []) or [])
        allowed = workspace_allowed_personas(ws, personas)  # None = all personas
        return allowed is None or persona.id in set(allowed)
    return _persona_can_list(matrix, persona.effective_role, target)


def _resolve_curated(
    appspec: AppSpec,
    nav_def: NavSpec,
    persona: PersonaSpec,
    matrix: AccessMatrix,
) -> list[NavGroup]:
    out: list[NavGroup] = []
    for g in nav_def.groups:
        links: list[NavLink] = []
        for item in g.items:
            if not _persona_can_reach(appspec, item.entity, persona, matrix):
                continue  # FR-3: drop dead links (entity- or workspace-gated)
            # #1626 P0-4: curated nav still must not promote platform ops to
            # product personas (authors sometimes copy admin groups).
            if not _persona_is_platform_operator(persona) and _is_platform_nav_target(
                appspec, item.entity
            ):
                continue
            route = _route_for(appspec, item.entity)
            if route is None:
                continue
            links.append(
                NavLink(
                    label=_label_for(appspec, item.entity),
                    route=route,
                    icon=item.icon,
                    entity=item.entity,
                    when=(item.when.model_dump() if item.when else None),
                )
            )
        if links:
            out.append(
                NavGroup(
                    label=g.label,
                    icon=g.icon,
                    collapsed=g.collapsed,
                    links=tuple(links),
                    when=(g.when.model_dump() if g.when else None),
                )
            )
    return out


def _auto_discover(appspec: AppSpec, persona: PersonaSpec, matrix: AccessMatrix) -> list[NavGroup]:
    """Product-first nav for a persona (FR-3 + #1626 P0-4).

    Order: accessible **product workspaces** first (job desks), then entity
    list surfaces from those workspaces. Platform/admin destinations are
    omitted for non-platform personas so System Health never sits next to
    Tickets on a business desk.
    """
    role = persona.effective_role
    personas = list(getattr(appspec, "personas", []) or [])
    platform_ops = _persona_is_platform_operator(persona)
    seen: set[str] = set()
    links: list[NavLink] = []

    for ws in getattr(appspec, "workspaces", []) or []:
        ws_name = str(getattr(ws, "name", "") or "")
        if not platform_ops and _is_platform_nav_target(appspec, ws_name):
            continue
        allowed = workspace_allowed_personas(ws, personas)  # None = all personas
        if allowed is not None and persona.id not in set(allowed):
            continue
        # Workspace destination first (product maturity + antagonist bar)
        if ws_name and ws_name not in seen:
            route = _route_for(appspec, ws_name)
            if route is not None:
                seen.add(ws_name)
                links.append(
                    NavLink(
                        label=_label_for(appspec, ws_name),
                        route=route,
                        entity=ws_name,
                    )
                )
        for region in ws.regions:
            region_sources = ([region.source] if region.source else []) + list(
                getattr(region, "sources", []) or []
            )
            for src in region_sources:
                if not src or src in seen:
                    continue
                if not platform_ops and _is_platform_nav_target(appspec, src):
                    continue
                if not _persona_can_list(matrix, role, src):
                    continue
                route = _route_for(appspec, src)
                if route is None:
                    continue
                seen.add(src)
                links.append(NavLink(label=_label_for(appspec, src), route=route, entity=src))
    return [NavGroup(label="", icon=None, collapsed=False, links=tuple(links))] if links else []


def build_persona_nav(appspec: AppSpec, persona: PersonaSpec, matrix: AccessMatrix) -> NavModel:
    """The single source of a persona's sidebar (#1324).

    Curated path: if the persona binds a `uses nav <name>` that resolves to a
    declared `nav <name>:`, build groups from it (FR-3 access-filtered).
    Otherwise fall back to auto-discovery over the persona's accessible
    workspaces' entity list-surfaces."""
    if persona.nav_ref is not None:
        nav_def = next((n for n in appspec.navs if n.name == persona.nav_ref), None)
        if nav_def is not None:
            groups = _resolve_curated(appspec, nav_def, persona, matrix)
            return NavModel(groups=tuple(groups), auto_discovered=False)
    groups = _auto_discover(appspec, persona, matrix)
    return NavModel(groups=tuple(groups), auto_discovered=True)


def build_all_persona_navs(appspec: AppSpec, matrix: AccessMatrix) -> dict[str, NavModel]:
    """Precompute every persona's nav once (link/build time). Keyed by persona.id."""
    return {
        p.id: build_persona_nav(appspec, p, matrix) for p in getattr(appspec, "personas", []) or []
    }


def build_anon_nav(appspec: AppSpec, matrix: AccessMatrix) -> NavModel:
    """The sidebar for an UNAUTHENTICATED visitor (#1324, mirroring #1127).

    Anon-safety is **not** an RBAC-matrix concept — the matrix has no anon /
    unauthenticated role. Per #1127 (``template_compiler``), a workspace is
    anon-safe iff ``workspace_allowed_personas(ws, personas) is None`` — i.e.
    it declares no persona gate (no ``access: persona(...)`` and no persona
    claiming it as ``default_workspace``). An entity link is anon-safe once an
    anon-safe workspace surfaces it; gated workspaces can't retract it. This
    builder discovers exactly those items, so anon behaviour matches #1127.

    The ``matrix`` still filters entity sources by list access
    (``_persona_can_list`` keyed on the persona-less ``""`` role, which DENYs
    under any real matrix and PERMITs under an open/unprotected one) — the same
    posture as the authenticated auto-discover path."""
    personas = list(getattr(appspec, "personas", []) or [])
    seen: set[str] = set()
    links: list[NavLink] = []
    for ws in getattr(appspec, "workspaces", []) or []:
        # #1127: anon-safe iff the workspace declared no persona gate.
        if workspace_allowed_personas(ws, personas) is not None:
            continue
        for region in ws.regions:
            region_sources = ([region.source] if region.source else []) + list(
                getattr(region, "sources", []) or []
            )
            for src in region_sources:
                if src in seen or not _persona_can_list(matrix, "", src):
                    continue
                route = _route_for(appspec, src)
                if route is None:
                    continue
                seen.add(src)
                links.append(NavLink(label=_label_for(appspec, src), route=route, entity=src))
    groups = [NavGroup(label="", icon=None, collapsed=False, links=tuple(links))] if links else []
    return NavModel(groups=tuple(groups), auto_discovered=True)
