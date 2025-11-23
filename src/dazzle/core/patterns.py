"""
Pattern detection for DAZZLE AppSpec.

Analyzes AppSpec to detect common structural patterns like CRUD operations,
pipelines, and event flows. Useful for:
- Auto-generating missing boilerplate
- Informing DSL syntax improvements
- Identifying opportunities for DSL shortcuts
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Set

from . import ir


@dataclass
class CrudPattern:
    """Detected CRUD pattern for an entity."""

    entity_name: str
    has_create: bool = False
    has_list: bool = False
    has_detail: bool = False
    has_edit: bool = False
    create_surface: Optional[str] = None
    list_surface: Optional[str] = None
    detail_surface: Optional[str] = None
    edit_surface: Optional[str] = None

    @property
    def is_complete(self) -> bool:
        """Check if all CRUD operations are present."""
        return self.has_create and self.has_list and self.has_detail and self.has_edit

    @property
    def missing_operations(self) -> List[str]:
        """Get list of missing CRUD operations."""
        missing = []
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
    connected_entities: Set[str] = None
    connected_surfaces: Set[str] = None

    def __post_init__(self):
        if self.connected_entities is None:
            self.connected_entities = set()
        if self.connected_surfaces is None:
            self.connected_surfaces = set()


@dataclass
class ExperiencePattern:
    """Detected experience/flow pattern."""

    experience_name: str
    step_count: int
    surface_steps: List[str]
    integration_steps: List[str]
    has_cycles: bool = False
    unreachable_steps: List[str] = None

    def __post_init__(self):
        if self.unreachable_steps is None:
            self.unreachable_steps = []


def detect_crud_patterns(spec: ir.AppSpec) -> List[CrudPattern]:
    """
    Detect CRUD patterns for entities.

    Looks for entity + create/list/detail/edit surface combinations.

    Args:
        spec: AppSpec to analyze

    Returns:
        List of detected CRUD patterns
    """
    patterns: Dict[str, CrudPattern] = {}

    # Initialize pattern for each entity
    for entity in spec.domain.entities:
        patterns[entity.name] = CrudPattern(entity_name=entity.name)

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


def detect_integration_patterns(spec: ir.AppSpec) -> List[IntegrationPattern]:
    """
    Detect integration patterns.

    Analyzes how integrations connect services, entities, and surfaces.

    Args:
        spec: AppSpec to analyze

    Returns:
        List of detected integration patterns
    """
    patterns: List[IntegrationPattern] = []

    for integration in spec.integrations:
        # Get primary service (first in list, or None)
        service_name = integration.service_refs[0] if integration.service_refs else "unknown"

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
            if action.response_entity:
                pattern.connected_entities.add(action.response_entity)
            if action.when_surface:
                pattern.connected_surfaces.add(action.when_surface)

        for sync in integration.syncs:
            pattern.connected_entities.add(sync.into_entity)

        patterns.append(pattern)

    return patterns


def detect_experience_patterns(spec: ir.AppSpec) -> List[ExperiencePattern]:
    """
    Detect experience/flow patterns.

    Analyzes experiences for structure, cycles, and unreachable steps.

    Args:
        spec: AppSpec to analyze

    Returns:
        List of detected experience patterns
    """
    patterns: List[ExperiencePattern] = []

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
    graph: Dict[str, List[str]] = {}
    for step in experience.steps:
        graph[step.name] = [t.next_step for t in step.transitions]

    # DFS with visited and recursion stack
    visited: Set[str] = set()
    rec_stack: Set[str] = set()

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


def _detect_unreachable_steps(experience: ir.ExperienceSpec) -> List[str]:
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
    reachable: Set[str] = set()
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


def analyze_patterns(spec: ir.AppSpec) -> Dict[str, List]:
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


def format_pattern_report(patterns: Dict[str, List]) -> str:
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
        lines.append(f"  Steps: {pattern.step_count} (surfaces: {len(pattern.surface_steps)}, integrations: {len(pattern.integration_steps)})")
        if pattern.has_cycles:
            lines.append("  ⚠ Contains cycles")
        if pattern.unreachable_steps:
            lines.append(f"  ⚠ Unreachable steps: {', '.join(pattern.unreachable_steps)}")

    return "\n".join(lines)
