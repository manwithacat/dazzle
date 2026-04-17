"""Component relevance rules for capability discovery.

Scans entities, surfaces, and workspaces for structural patterns where
Alpine/HTMX interactive component capabilities would improve the user
experience.
"""

from dazzle.core.ir.domain import EntitySpec
from dazzle.core.ir.fields import FieldTypeKind
from dazzle.core.ir.surfaces import SurfaceSpec
from dazzle.core.ir.workspaces import DisplayMode, WorkspaceSpec

from .models import Relevance

# Minimum number of surfaces before suggesting a command palette
_COMMAND_PALETTE_SURFACE_THRESHOLD = 5


def check_component_relevance(
    entities: list[EntitySpec],
    surfaces: list[SurfaceSpec],
    workspaces: list[WorkspaceSpec],
    *,
    fragments: list[str] | None = None,
) -> list[Relevance]:
    """Return Relevance items for interactive component capabilities applicable to the project.

    Applies two rules:

    1. **Command palette**: App with 5+ surfaces and no existing command
       palette fragment → suggest dzCommandPalette.
    2. **Toggle group**: Workspace region using GRID display whose source
       entity has an enum field with "status" in the name → suggest toggle
       group for view filtering.

    Args:
        entities: List of EntitySpec objects.
        surfaces: List of SurfaceSpec objects.
        workspaces: List of WorkspaceSpec objects.
        fragments: Fragment names already present in the project (used to
            avoid redundant suggestions). Defaults to None (treated as empty).

    Returns:
        A list of Relevance instances, one per matching pattern found.
    """
    active_fragments = set(fragments or [])
    results: list[Relevance] = []

    # --- Rule 1: Command palette for large apps ---
    if (
        len(surfaces) >= _COMMAND_PALETTE_SURFACE_THRESHOLD
        and "command_palette" not in active_fragments
    ):
        results.append(
            Relevance(
                context=(f"app has {len(surfaces)} surfaces but no command palette fragment"),
                capability="dzCommandPalette",
                category="component",
                examples=[],
                kg_entity="capability:component_command_palette",
            )
        )

    # --- Rule 2: Toggle group for grid views with enum status fields ---
    # Build a lookup from entity name → set of enum field names containing "status"
    # Framework-synthetic platform entities are skipped — they live in
    # framework-generated workspaces the app author cannot modify.
    entity_status_enum_fields: dict[str, list[str]] = {}
    for entity in entities:
        if getattr(entity, "domain", None) == "platform":
            continue
        status_enums = [
            f.name
            for f in entity.fields
            if f.type.kind == FieldTypeKind.ENUM and "status" in f.name.lower()
        ]
        if status_enums:
            entity_status_enum_fields[entity.name] = status_enums

    for workspace in workspaces:
        if workspace.name.startswith("_platform_"):
            continue
        for region in workspace.regions:
            if region.display != DisplayMode.GRID:
                continue
            if not region.source:
                continue
            if region.source not in entity_status_enum_fields:
                continue
            results.append(
                Relevance(
                    context=(
                        f"workspace '{workspace.name}' region '{region.name}' displays"
                        f" entity '{region.source}' in grid mode and the entity has an"
                        " enum status field"
                    ),
                    capability="toggle group for view filtering",
                    category="component",
                    examples=[],
                    kg_entity="capability:component_toggle_group",
                )
            )

    return results
