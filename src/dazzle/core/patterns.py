"""
Pattern detection for DAZZLE AppSpec.

Analyzes AppSpec to detect common structural patterns like CRUD operations,
pipelines, and event flows. Useful for:
- Auto-generating missing boilerplate
- Informing DSL syntax improvements
- Identifying opportunities for DSL shortcuts
"""

from dataclasses import dataclass
from typing import Any

from . import ir

# Patterns that indicate an entity is system-managed (read-only, no user create/edit)
SYSTEM_MANAGED_PATTERNS = frozenset(
    {
        "audit",
        "system",
        "read_only",
        "readonly",
        "system_managed",
        "log",
        "event",
        "notification",
    }
)


@dataclass
class CrudPattern:
    """Detected CRUD pattern for an entity."""

    entity_name: str
    has_create: bool = False
    has_list: bool = False
    has_detail: bool = False
    has_edit: bool = False
    create_surface: str | None = None
    list_surface: str | None = None
    detail_surface: str | None = None
    edit_surface: str | None = None
    is_system_managed: bool = False  # True if entity is intentionally read-only

    @property
    def is_complete(self) -> bool:
        """Check if all expected CRUD operations are present."""
        if self.is_system_managed:
            # System-managed entities only need list and optionally detail
            return self.has_list
        return self.has_create and self.has_list and self.has_detail and self.has_edit

    @property
    def missing_operations(self) -> list[str]:
        """Get list of missing CRUD operations (only those expected for this entity)."""
        missing = []
        if self.is_system_managed:
            # System-managed entities only expect list (and optionally detail)
            if not self.has_list:
                missing.append("list")
        else:
            # Normal entities expect full CRUD
            if not self.has_create:
                missing.append("create")
            if not self.has_list:
                missing.append("list")
            if not self.has_detail:
                missing.append("detail")
            if not self.has_edit:
                missing.append("edit")
        return missing


@dataclass
class IntegrationPattern:
    """Detected integration pattern."""

    integration_name: str
    service_name: str
    has_actions: bool = False
    has_syncs: bool = False
    action_count: int = 0
    sync_count: int = 0
    connected_entities: set[str] | None = None
    connected_surfaces: set[str] | None = None

    def __post_init__(self) -> None:
        if self.connected_entities is None:
            self.connected_entities = set()
        if self.connected_surfaces is None:
            self.connected_surfaces = set()


@dataclass
class ExperiencePattern:
    """Detected experience/flow pattern."""

    experience_name: str
    step_count: int
    surface_steps: list[str]
    integration_steps: list[str]
    has_cycles: bool = False
    unreachable_steps: list[str] | None = None

    def __post_init__(self) -> None:
        if self.unreachable_steps is None:
            self.unreachable_steps = []


def _is_system_managed_entity(entity: ir.EntitySpec) -> bool:
    """Check if an entity is system-managed (read-only) based on patterns or name.

    System-managed entities are those that are created/updated by the system
    rather than by users, such as audit logs, system events, and notifications.
    These entities intentionally lack create/edit surfaces.
    """
    # Check explicit patterns
    entity_patterns = {p.lower() for p in entity.patterns}
    if entity_patterns & SYSTEM_MANAGED_PATTERNS:
        return True

    # Heuristic: check entity name for common system-managed patterns
    name_lower = entity.name.lower()
    name_hints = ["log", "event", "audit", "notification", "history", "activity"]
    for hint in name_hints:
        if hint in name_lower:
            return True

    return False


def detect_crud_patterns(spec: ir.AppSpec) -> list[CrudPattern]:
    """
    Detect CRUD patterns for entities.

    Looks for entity + create/list/detail/edit surface combinations.

    Args:
        spec: AppSpec to analyze

    Returns:
        List of detected CRUD patterns
    """
    patterns: dict[str, CrudPattern] = {}

    # Initialize pattern for each entity
    for entity in spec.domain.entities:
        # Check if entity is system-managed based on patterns or name heuristics
        is_system_managed = _is_system_managed_entity(entity)
        patterns[entity.name] = CrudPattern(
            entity_name=entity.name,
            is_system_managed=is_system_managed,
        )

    # Check surfaces for CRUD patterns
    for surface in spec.surfaces:
        if not surface.entity_ref:
            continue

        entity_name = surface.entity_ref
        if entity_name not in patterns:
            continue

        pattern = patterns[entity_name]

        # Match surface mode to CRUD operation
        if surface.mode == ir.SurfaceMode.CREATE:
            pattern.has_create = True
            pattern.create_surface = surface.name
        elif surface.mode == ir.SurfaceMode.LIST:
            pattern.has_list = True
            pattern.list_surface = surface.name
        elif surface.mode == ir.SurfaceMode.VIEW:
            pattern.has_detail = True
            pattern.detail_surface = surface.name
        elif surface.mode == ir.SurfaceMode.EDIT:
            pattern.has_edit = True
            pattern.edit_surface = surface.name

    return list(patterns.values())


def detect_integration_patterns(spec: ir.AppSpec) -> list[IntegrationPattern]:
    """
    Detect integration patterns.

    Analyzes how integrations connect services, entities, and surfaces.

    Args:
        spec: AppSpec to analyze

    Returns:
        List of detected integration patterns
    """
    patterns: list[IntegrationPattern] = []

    for integration in spec.integrations:
        # Get primary API (first in list, or None)
        service_name = integration.api_refs[0] if integration.api_refs else "unknown"

        pattern = IntegrationPattern(
            integration_name=integration.name,
            service_name=service_name,
            has_actions=len(integration.actions) > 0,
            has_syncs=len(integration.syncs) > 0,
            action_count=len(integration.actions),
            sync_count=len(integration.syncs),
        )

        # Collect connected entities from actions and syncs
        for action in integration.actions:
            if action.response_entity and pattern.connected_entities is not None:
                pattern.connected_entities.add(action.response_entity)
            if action.when_surface and pattern.connected_surfaces is not None:
                pattern.connected_surfaces.add(action.when_surface)

        for sync in integration.syncs:
            if pattern.connected_entities is not None:
                pattern.connected_entities.add(sync.into_entity)

        patterns.append(pattern)

    return patterns


def detect_experience_patterns(spec: ir.AppSpec) -> list[ExperiencePattern]:
    """
    Detect experience/flow patterns.

    Analyzes experiences for structure, cycles, and unreachable steps.

    Args:
        spec: AppSpec to analyze

    Returns:
        List of detected experience patterns
    """
    patterns: list[ExperiencePattern] = []

    for experience in spec.experiences:
        surface_steps = []
        integration_steps = []

        # Categorize steps
        for step in experience.steps:
            if step.kind == ir.StepKind.SURFACE:
                surface_steps.append(step.name)
            elif step.kind == ir.StepKind.INTEGRATION:
                integration_steps.append(step.name)

        # Detect cycles using DFS
        has_cycles = _detect_cycles_in_experience(experience)

        # Detect unreachable steps
        unreachable = _detect_unreachable_steps(experience)

        pattern = ExperiencePattern(
            experience_name=experience.name,
            step_count=len(experience.steps),
            surface_steps=surface_steps,
            integration_steps=integration_steps,
            has_cycles=has_cycles,
            unreachable_steps=unreachable,
        )

        patterns.append(pattern)

    return patterns


def _detect_cycles_in_experience(experience: ir.ExperienceSpec) -> bool:
    """
    Detect cycles in experience flow using DFS.

    Args:
        experience: Experience to check

    Returns:
        True if cycles detected, False otherwise
    """
    # Build adjacency list
    graph: dict[str, list[str]] = {}
    for step in experience.steps:
        graph[step.name] = [t.next_step for t in step.transitions]

    # DFS with visited and recursion stack
    visited: set[str] = set()
    rec_stack: set[str] = set()

    def dfs(node: str) -> bool:
        visited.add(node)
        rec_stack.add(node)

        for neighbor in graph.get(node, []):
            if neighbor not in visited:
                if dfs(neighbor):
                    return True
            elif neighbor in rec_stack:
                return True

        rec_stack.remove(node)
        return False

    # Check from start step
    if experience.start_step in graph:
        return dfs(experience.start_step)

    return False


def _detect_unreachable_steps(experience: ir.ExperienceSpec) -> list[str]:
    """
    Detect unreachable steps in experience.

    Args:
        experience: Experience to check

    Returns:
        List of unreachable step names
    """
    # Build set of all steps
    all_steps = {step.name for step in experience.steps}

    # BFS from start step to find reachable steps
    reachable: set[str] = set()
    queue = [experience.start_step]

    while queue:
        current = queue.pop(0)
        if current in reachable:
            continue

        reachable.add(current)

        # Find step and add transitions
        step = experience.get_step(current)
        if step:
            for transition in step.transitions:
                if transition.next_step not in reachable:
                    queue.append(transition.next_step)

    # Unreachable = all steps - reachable steps
    unreachable = all_steps - reachable
    return sorted(unreachable)


def analyze_patterns(spec: ir.AppSpec) -> dict[str, list[Any]]:
    """
    Run all pattern detection analyses on an AppSpec.

    Args:
        spec: AppSpec to analyze

    Returns:
        Dictionary with pattern detection results:
        - crud: List of CRUD patterns
        - integrations: List of integration patterns
        - experiences: List of experience patterns
    """
    return {
        "crud": detect_crud_patterns(spec),
        "integrations": detect_integration_patterns(spec),
        "experiences": detect_experience_patterns(spec),
    }


def format_pattern_report(patterns: dict[str, list[Any]]) -> str:
    """
    Format pattern analysis results as a human-readable report.

    Args:
        patterns: Results from analyze_patterns()

    Returns:
        Formatted string report
    """
    lines = []

    # CRUD patterns
    lines.append("CRUD Patterns")
    lines.append("=" * 50)
    crud_patterns = patterns.get("crud", [])
    complete_count = sum(1 for p in crud_patterns if p.is_complete)
    lines.append(f"Entities: {len(crud_patterns)}")
    lines.append(f"Complete CRUD: {complete_count}/{len(crud_patterns)}")
    lines.append("")

    for pattern in crud_patterns:
        if pattern.is_complete:
            lines.append(f"✓ {pattern.entity_name}: Complete CRUD")
        else:
            missing = ", ".join(pattern.missing_operations)
            lines.append(f"⚠ {pattern.entity_name}: Missing {missing}")

    lines.append("")

    # Integration patterns
    lines.append("Integration Patterns")
    lines.append("=" * 50)
    integration_patterns = patterns.get("integrations", [])
    lines.append(f"Total integrations: {len(integration_patterns)}")
    lines.append("")

    for pattern in integration_patterns:
        lines.append(f"• {pattern.integration_name} ({pattern.service_name})")
        lines.append(f"  Actions: {pattern.action_count}, Syncs: {pattern.sync_count}")
        if pattern.connected_entities:
            lines.append(f"  Entities: {', '.join(sorted(pattern.connected_entities))}")
        if pattern.connected_surfaces:
            lines.append(f"  Surfaces: {', '.join(sorted(pattern.connected_surfaces))}")

    lines.append("")

    # Experience patterns
    lines.append("Experience Patterns")
    lines.append("=" * 50)
    experience_patterns = patterns.get("experiences", [])
    lines.append(f"Total experiences: {len(experience_patterns)}")
    lines.append("")

    for pattern in experience_patterns:
        lines.append(f"• {pattern.experience_name}")
        lines.append(
            f"  Steps: {pattern.step_count} (surfaces: {len(pattern.surface_steps)}, integrations: {len(pattern.integration_steps)})"
        )
        if pattern.has_cycles:
            lines.append("  ⚠ Contains cycles")
        if pattern.unreachable_steps:
            lines.append(f"  ⚠ Unreachable steps: {', '.join(pattern.unreachable_steps)}")

    return "\n".join(lines)
