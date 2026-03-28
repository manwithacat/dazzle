"""Completeness relevance rules for capability discovery.

Identifies CRUD completeness gaps where entities have permissions declared
but lack corresponding surfaces to expose those operations.
"""

from dazzle.core.ir.domain import EntitySpec, PermissionKind
from dazzle.core.ir.surfaces import SurfaceMode, SurfaceSpec

from .models import Relevance

# Maps a permission operation → the surface mode that covers it
_OP_TO_MODE: dict[PermissionKind, SurfaceMode] = {
    PermissionKind.CREATE: SurfaceMode.CREATE,
    PermissionKind.UPDATE: SurfaceMode.EDIT,
    PermissionKind.LIST: SurfaceMode.LIST,
}

# Maps missing surface mode → kg_entity tag
_MODE_TO_KG: dict[SurfaceMode, str] = {
    SurfaceMode.CREATE: "capability:completeness_missing_create",
    SurfaceMode.EDIT: "capability:completeness_missing_edit",
    SurfaceMode.LIST: "capability:completeness_missing_list",
}

# Friendly labels for context messages
_MODE_LABEL: dict[SurfaceMode, str] = {
    SurfaceMode.CREATE: "create",
    SurfaceMode.EDIT: "edit",
    SurfaceMode.LIST: "list",
}


def check_completeness_relevance(
    entities: list[EntitySpec],
    surfaces: list[SurfaceSpec],
) -> list[Relevance]:
    """Return Relevance items for CRUD completeness gaps.

    For each entity that declares permissions, checks whether the corresponding
    surface modes exist.  Reports:

    * Entity with ``update`` permit but no ``mode: edit`` surface.
    * Entity with ``list`` permit but no ``mode: list`` surface.
    * Entity with ``create`` permit but no ``mode: create`` surface.
    * Entity with *any* permissions but no surfaces at all (unreachable).

    Args:
        entities: List of EntitySpec objects.
        surfaces: List of SurfaceSpec objects.

    Returns:
        A list of Relevance instances, one per gap found.
    """
    # Build lookup: entity_name → set of surface modes present
    entity_modes: dict[str, set[SurfaceMode]] = {}
    for surface in surfaces:
        if surface.entity_ref is None:
            continue
        entity_modes.setdefault(surface.entity_ref, set()).add(surface.mode)

    results: list[Relevance] = []

    for entity_spec in entities:
        if entity_spec.access is None or not entity_spec.access.permissions:
            continue

        permitted_ops = {rule.operation for rule in entity_spec.access.permissions}
        if not permitted_ops:
            continue

        present_modes = entity_modes.get(entity_spec.name, set())

        # Check: entity has permissions but NO surfaces at all
        if not present_modes:
            results.append(
                Relevance(
                    context=(f"entity '{entity_spec.name}' has permissions but no surfaces"),
                    capability="surfaces (entity unreachable)",
                    category="completeness",
                    examples=[],
                    kg_entity="capability:completeness_unreachable",
                )
            )
            # Still check per-operation gaps even when unreachable (surfaces may
            # exist for some modes later); skip individual mode checks to avoid
            # redundant noise when the entity is fully unreachable.
            continue

        # Check per-operation gaps
        for op, mode in _OP_TO_MODE.items():
            if op not in permitted_ops:
                continue
            if mode in present_modes:
                continue
            results.append(
                Relevance(
                    context=(
                        f"entity '{entity_spec.name}' has '{op}' permission"
                        f" but no '{_MODE_LABEL[mode]}' surface"
                    ),
                    capability=f"{_MODE_LABEL[mode]} surface",
                    category="completeness",
                    examples=[],
                    kg_entity=_MODE_TO_KG[mode],
                )
            )

    return results
