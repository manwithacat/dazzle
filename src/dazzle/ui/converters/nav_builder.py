"""Unified per-persona navigation builder (#1324).

Navigation is a pure function of (persona, appspec, rbac_matrix) — all static.
This module is the single source of a persona's sidebar: every page renders the
same precomputed NavModel for the current persona, so the three legacy builders
(workspace-page, entity-page, persona-union) can no longer drift.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from dazzle.rbac.matrix import PolicyDecision  # runtime import (ui may import rbac)

if TYPE_CHECKING:
    from dazzle.core.ir.appspec import AppSpec
    from dazzle.core.ir.personas import PersonaSpec
    from dazzle.core.ir.workspaces import NavSpec
    from dazzle.rbac.matrix import AccessMatrix


@dataclass(frozen=True)
class NavLink:
    label: str
    route: str
    icon: str | None = None
    entity: str | None = None  # target entity/workspace name (filtering + FR-6 lint)


@dataclass(frozen=True)
class NavGroup:
    label: str
    icon: str | None
    collapsed: bool
    links: tuple[NavLink, ...]


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


def _persona_can_list(matrix: AccessMatrix, role: str, entity: str) -> bool:
    """FR-3: a persona may see a nav link only if its role isn't DENYed list access."""
    return matrix.get(role, entity, "list") != PolicyDecision.DENY


def _resolve_curated(
    appspec: AppSpec,
    nav_def: NavSpec,
    persona: PersonaSpec,
    matrix: AccessMatrix,
) -> list[NavGroup]:
    role = persona.effective_role
    out: list[NavGroup] = []
    for g in nav_def.groups:
        links: list[NavLink] = []
        for item in g.items:
            if not _persona_can_list(matrix, role, item.entity):
                continue  # FR-3: drop dead links
            route = _route_for(appspec, item.entity)
            if route is None:
                continue
            links.append(
                NavLink(label=item.entity, route=route, icon=item.icon, entity=item.entity)
            )
        if links:
            out.append(
                NavGroup(label=g.label, icon=g.icon, collapsed=g.collapsed, links=tuple(links))
            )
    return out


def build_persona_nav(appspec: AppSpec, persona: PersonaSpec, matrix: AccessMatrix) -> NavModel:
    """The single source of a persona's sidebar (#1324).

    Curated path: if the persona binds a `uses nav <name>` that resolves to a
    declared `nav <name>:`, build groups from it (FR-3 access-filtered).
    Otherwise fall back to auto-discovery — implemented in the next task; for
    now this returns an empty auto-discovered placeholder."""
    if persona.nav_ref is not None:
        nav_def = next((n for n in appspec.navs if n.name == persona.nav_ref), None)
        if nav_def is not None:
            groups = _resolve_curated(appspec, nav_def, persona, matrix)
            return NavModel(groups=tuple(groups), auto_discovered=False)
    # Auto-discover fallback implemented in the next task; placeholder for now.
    return NavModel(groups=(), auto_discovered=True)
