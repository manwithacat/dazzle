"""Generate the canonical interaction inventory from an AppSpec.

The inventory enumerates every testable interaction point in a Dazzle app.
It is the denominator in UX coverage: interactions_tested / interactions_enumerated.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from dazzle.core.ir.appspec import AppSpec
from dazzle.core.ir.domain import PermissionKind


class InteractionClass(StrEnum):
    PAGE_LOAD = "page_load"
    DETAIL_VIEW = "detail_view"
    CREATE_SUBMIT = "create_submit"
    EDIT_SUBMIT = "edit_submit"
    DELETE_CONFIRM = "delete_confirm"
    DRAWER_OPEN = "drawer_open"
    DRAWER_CLOSE = "drawer_close"
    STATE_TRANSITION = "state_transition"
    ACCESS_DENIED = "access_denied"
    WORKSPACE_RENDER = "workspace_render"


@dataclass
class Interaction:
    cls: InteractionClass
    entity: str
    persona: str
    surface: str = ""
    workspace: str = ""
    action: str = ""
    description: str = ""
    status: Literal["pending", "passed", "failed", "skipped"] = "pending"
    error: str | None = None
    screenshot: str | None = None

    @property
    def interaction_id(self) -> str:
        key = f"{self.cls}:{self.entity}:{self.persona}:{self.surface}:{self.action}"
        return hashlib.sha256(key.encode()).hexdigest()[:12]


def _get_permitted_personas(
    appspec: AppSpec, entity_name: str, operation: PermissionKind
) -> list[str]:
    """Return persona IDs that have a permit rule for the given operation."""
    entity = next((e for e in appspec.domain.entities if e.name == entity_name), None)
    if not entity or not entity.access:
        return [p.id for p in appspec.personas]  # No access spec = open

    permitted: set[str] = set()
    for rule in entity.access.permissions:
        if rule.operation == operation:
            if rule.personas:
                permitted.update(rule.personas)
            else:
                # No persona restriction = all personas
                return [p.id for p in appspec.personas]
    return list(permitted)


def _get_denied_personas(
    appspec: AppSpec, entity_name: str, operation: PermissionKind
) -> list[str]:
    """Return persona IDs that do NOT have a permit rule for the given operation."""
    permitted = set(_get_permitted_personas(appspec, entity_name, operation))
    all_personas = {p.id for p in appspec.personas}
    return list(all_personas - permitted)


def generate_inventory(appspec: AppSpec) -> list[Interaction]:
    """Generate the full interaction inventory from an AppSpec."""
    interactions: list[Interaction] = []
    persona_ids = [p.id for p in appspec.personas]

    # Map entity names to their surfaces
    entity_surfaces: dict[str, list[str]] = {}
    for surface in appspec.surfaces:
        if surface.entity_ref:
            entity_surfaces.setdefault(surface.entity_ref, []).append(surface.name)

    # Per-entity interactions
    for entity in appspec.domain.entities:
        surfaces = entity_surfaces.get(entity.name, [])
        if not surfaces:
            continue  # No UI surface = not testable via UX

        for surface_name in surfaces:
            surface_spec = next((s for s in appspec.surfaces if s.name == surface_name), None)
            if not surface_spec:
                continue

            mode = (
                str(surface_spec.mode.value)
                if hasattr(surface_spec.mode, "value")
                else str(surface_spec.mode)
            )

            # PAGE_LOAD — for each persona with list/read permission
            for pid in _get_permitted_personas(appspec, entity.name, PermissionKind.LIST):
                interactions.append(
                    Interaction(
                        cls=InteractionClass.PAGE_LOAD,
                        entity=entity.name,
                        persona=pid,
                        surface=surface_name,
                        description=f"Load {surface_name} as {pid}",
                    )
                )

            # DETAIL_VIEW — for each persona with read permission
            if mode == "list":
                for pid in _get_permitted_personas(appspec, entity.name, PermissionKind.READ):
                    interactions.append(
                        Interaction(
                            cls=InteractionClass.DETAIL_VIEW,
                            entity=entity.name,
                            persona=pid,
                            surface=surface_name,
                            description=f"View {entity.name} detail as {pid}",
                        )
                    )

            # CREATE_SUBMIT — for each persona with create permission
            for pid in _get_permitted_personas(appspec, entity.name, PermissionKind.CREATE):
                interactions.append(
                    Interaction(
                        cls=InteractionClass.CREATE_SUBMIT,
                        entity=entity.name,
                        persona=pid,
                        surface=surface_name,
                        description=f"Create {entity.name} as {pid}",
                    )
                )

            # EDIT_SUBMIT — for each persona with update permission
            for pid in _get_permitted_personas(appspec, entity.name, PermissionKind.UPDATE):
                interactions.append(
                    Interaction(
                        cls=InteractionClass.EDIT_SUBMIT,
                        entity=entity.name,
                        persona=pid,
                        surface=surface_name,
                        description=f"Edit {entity.name} as {pid}",
                    )
                )

            # DELETE_CONFIRM — for each persona with delete permission
            for pid in _get_permitted_personas(appspec, entity.name, PermissionKind.DELETE):
                interactions.append(
                    Interaction(
                        cls=InteractionClass.DELETE_CONFIRM,
                        entity=entity.name,
                        persona=pid,
                        surface=surface_name,
                        description=f"Delete {entity.name} as {pid}",
                    )
                )

            # ACCESS_DENIED — for each persona WITHOUT list permission
            for pid in _get_denied_personas(appspec, entity.name, PermissionKind.LIST):
                interactions.append(
                    Interaction(
                        cls=InteractionClass.ACCESS_DENIED,
                        entity=entity.name,
                        persona=pid,
                        surface=surface_name,
                        description=f"Access denied {surface_name} for {pid}",
                    )
                )

        # STATE_TRANSITION — for entities with state machines
        if entity.state_machine:
            for transition in entity.state_machine.transitions:
                t_name = transition.name if hasattr(transition, "name") else str(transition)
                for pid in persona_ids:
                    interactions.append(
                        Interaction(
                            cls=InteractionClass.STATE_TRANSITION,
                            entity=entity.name,
                            persona=pid,
                            action=t_name,
                            description=f"Transition {entity.name} via {t_name} as {pid}",
                        )
                    )

    # Workspace interactions
    for workspace in appspec.workspaces:
        # WORKSPACE_RENDER — for each persona with access
        access_personas = persona_ids  # Default: all
        if workspace.access and workspace.access.allow_personas:
            access_personas = workspace.access.allow_personas

        for pid in access_personas:
            interactions.append(
                Interaction(
                    cls=InteractionClass.WORKSPACE_RENDER,
                    entity="",
                    persona=pid,
                    workspace=workspace.name,
                    description=f"Render {workspace.name} as {pid}",
                )
            )

        # DRAWER_OPEN / DRAWER_CLOSE — for each region
        for region in workspace.regions:
            source = region.source or ""
            for pid in access_personas:
                interactions.append(
                    Interaction(
                        cls=InteractionClass.DRAWER_OPEN,
                        entity=source,
                        persona=pid,
                        workspace=workspace.name,
                        action=region.name,
                        description=f"Open drawer for {region.name} in {workspace.name} as {pid}",
                    )
                )
                interactions.append(
                    Interaction(
                        cls=InteractionClass.DRAWER_CLOSE,
                        entity=source,
                        persona=pid,
                        workspace=workspace.name,
                        action=region.name,
                        description=f"Close drawer for {region.name} in {workspace.name} as {pid}",
                    )
                )

    return interactions
