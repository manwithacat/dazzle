"""Layout relevance rules for capability discovery.

Scans entities, surfaces, and workspaces for structural patterns where
layout capabilities would improve the user experience.
"""

from dazzle.core.ir.fields import FieldTypeKind
from dazzle.core.ir.surfaces import SurfaceMode, SurfaceSpec
from dazzle.core.ir.workspaces import DisplayMode, WorkspaceSpec

from .models import Relevance

# Field type kinds that indicate temporal data
_DATE_KINDS = {FieldTypeKind.DATE, FieldTypeKind.DATETIME}

# Surface modes that represent create/edit forms
_FORM_MODES = {SurfaceMode.CREATE, SurfaceMode.EDIT}


def check_layout_relevance(
    entities: list,
    surfaces: list[SurfaceSpec],
    workspaces: list[WorkspaceSpec],
) -> list[Relevance]:
    """Return Relevance items for layout capabilities applicable to the project.

    Applies four rules:

    1. **Kanban**: Entity with a state machine (transitions) but no kanban
       workspace region sourced from it → suggest kanban display mode.
    2. **Timeline**: Entity with date/datetime fields but no timeline workspace
       region sourced from it → suggest timeline display mode.
    3. **Related groups**: VIEW surface whose entity is referenced by 3+
       other entities via REF fields, but the surface has no related_groups
       → suggest related group display modes.
    4. **Multi-section form**: CREATE/EDIT surface with exactly one section
       containing 5+ elements → suggest breaking into multiple sections.

    Args:
        entities: List of EntitySpec objects.
        surfaces: List of SurfaceSpec objects.
        workspaces: List of WorkspaceSpec objects.

    Returns:
        A list of Relevance instances, one per matching pattern found.
    """
    # --- Build lookup: entity_name → set of DisplayModes used for that entity ---
    entity_display_modes: dict[str, set[DisplayMode]] = {}
    for workspace in workspaces:
        for region in workspace.regions:
            if region.source:
                entity_display_modes.setdefault(region.source, set()).add(region.display)

    # --- Build lookup: entity_name → list of other entity names with REF to it ---
    referencing_entities: dict[str, list[str]] = {}
    for entity in entities:
        for field in entity.fields:
            if field.type.kind == FieldTypeKind.REF and field.type.ref_entity:
                target = field.type.ref_entity
                referencing_entities.setdefault(target, []).append(entity.name)

    results: list[Relevance] = []

    # --- Rule 1: Kanban for entities with state machines ---
    for entity in entities:
        if entity.state_machine is not None:
            modes = entity_display_modes.get(entity.name, set())
            if DisplayMode.KANBAN not in modes:
                results.append(
                    Relevance(
                        context=(
                            f"entity '{entity.name}' has a state machine but no"
                            " kanban workspace region"
                        ),
                        capability="kanban display mode",
                        category="layout",
                        examples=[],
                        kg_entity="capability:layout_kanban",
                    )
                )

    # --- Rule 2: Timeline for entities with date/datetime fields ---
    for entity in entities:
        has_date_field = any(f.type.kind in _DATE_KINDS for f in entity.fields)
        if has_date_field:
            modes = entity_display_modes.get(entity.name, set())
            if DisplayMode.TIMELINE not in modes:
                results.append(
                    Relevance(
                        context=(
                            f"entity '{entity.name}' has date/datetime fields but no"
                            " timeline workspace region"
                        ),
                        capability="timeline display mode",
                        category="layout",
                        examples=[],
                        kg_entity="capability:layout_timeline",
                    )
                )

    # --- Rule 3: Related groups for heavily-referenced entities ---
    for surface in surfaces:
        if surface.mode != SurfaceMode.VIEW:
            continue
        if not surface.entity_ref:
            continue
        refs = referencing_entities.get(surface.entity_ref, [])
        if len(refs) >= 3 and not surface.related_groups:
            results.append(
                Relevance(
                    context=(
                        f"view surface '{surface.name}' for entity"
                        f" '{surface.entity_ref}' is referenced by"
                        f" {len(refs)} entities via REF but has no related_groups"
                    ),
                    capability="related group display modes",
                    category="layout",
                    examples=[],
                    kg_entity="capability:layout_related_groups",
                )
            )

    # --- Rule 4: Multi-section forms for large single-section surfaces ---
    for surface in surfaces:
        if surface.mode not in _FORM_MODES:
            continue
        if len(surface.sections) == 1:
            total_elements = sum(len(s.elements) for s in surface.sections)
            if total_elements >= 5:
                results.append(
                    Relevance(
                        context=(
                            f"surface '{surface.name}' ({surface.mode}) has"
                            f" {total_elements} fields in a single section"
                        ),
                        capability="multi-section form",
                        category="layout",
                        examples=[],
                        kg_entity="capability:layout_multi_section",
                    )
                )

    return results
