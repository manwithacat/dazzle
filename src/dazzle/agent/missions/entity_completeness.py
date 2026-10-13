"""
Entity completeness: static CRUD coverage and state-machine UI analysis.

Deterministic pass over the DSL that finds missing CRUD surfaces and missing
state-transition UI; ``persona_journey.run_headless_discovery`` folds its gaps
into ``discovery(operation=coherence)``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from dazzle.core.patterns import SYSTEM_MANAGED_PATTERNS

if TYPE_CHECKING:
    from dazzle.core.ir.appspec import AppSpec
from ._shared import (
    get_surface_entity,
    is_step_kind,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Static Analysis Types
# =============================================================================


@dataclass
class EntityCoverageGap:
    """A gap in CRUD coverage or state machine UI for an entity."""

    entity_name: str
    gap_type: str  # "no_surface", "missing_list", "missing_create", "missing_edit", "missing_view", "no_transition_ui", "process_referenced"
    severity: str  # "critical", "high", "medium", "low"
    description: str
    process_name: str | None = None  # For process_referenced gaps


@dataclass
class EntityCompletenessReport:
    """Result of static entity completeness analysis."""

    gaps: list[EntityCoverageGap] = field(default_factory=list)
    entity_coverage: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def gap_count(self) -> int:
        return len(self.gaps)

    def to_summary(self) -> str:
        """Build a compact summary for embedding in system prompts."""
        if not self.gaps:
            return "No entity coverage gaps found."

        lines: list[str] = [f"Found {self.gap_count} entity coverage gaps:\n"]
        for gap in self.gaps:
            lines.append(f"- [{gap.severity.upper()}] {gap.entity_name}: {gap.description}")
        return "\n".join(lines)


# =============================================================================
# Static Analysis
# =============================================================================


def _is_system_managed(entity: Any) -> bool:
    """Check if an entity is system-managed (read-only) based on patterns or name.

    Wraps the patterns check with getattr safety so SimpleNamespace test fixtures
    (which lack .patterns) don't crash.
    """
    # Check explicit patterns
    entity_patterns = {p.lower() for p in getattr(entity, "patterns", [])}
    if entity_patterns & SYSTEM_MANAGED_PATTERNS:
        return True

    # Heuristic: check entity name for common system-managed patterns
    name_lower = getattr(entity, "name", "").lower()
    name_hints = ["log", "event", "audit", "notification", "history", "activity"]
    return any(hint in name_lower for hint in name_hints)


def _is_operation_forbidden(entity: Any, operation: str) -> bool:
    """Check if an entity has a blanket forbid rule for a given operation.

    Returns True when the entity's access spec contains a FORBID rule for the
    operation that applies to all personas (empty personas list).

    Args:
        entity: EntitySpec or SimpleNamespace with optional .access attribute
        operation: One of "create", "update", "delete"
    """
    access = getattr(entity, "access", None)
    if not access:
        return False
    permissions = getattr(access, "permissions", []) or []
    for rule in permissions:
        rule_op = str(getattr(rule, "operation", ""))
        rule_effect = str(getattr(rule, "effect", ""))
        rule_personas = getattr(rule, "personas", []) or []
        if (
            rule_op == operation
            and rule_effect in ("forbid", "FORBID", "PolicyEffect.FORBID")
            and not rule_personas
        ):
            return True
    return False


def _static_entity_analysis(appspec: AppSpec) -> EntityCompletenessReport:
    """
    Analyze DSL spec for entity CRUD coverage gaps.

    Builds a map of entity -> {mode: [surface_names]} from surfaces,
    then checks each entity for completeness.
    """
    report = EntityCompletenessReport()

    entities = appspec.domain.entities
    surfaces = appspec.surfaces
    processes = appspec.processes

    # Build entity -> surface coverage map
    entity_surface_map: dict[str, dict[str, list[str]]] = {}
    for entity in entities:
        entity_surface_map[entity.name] = {}

    for surface in surfaces:
        entity_ref = get_surface_entity(surface)
        if not entity_ref or entity_ref not in entity_surface_map:
            continue
        mode = str(surface.mode)
        entity_surface_map[entity_ref].setdefault(mode, []).append(surface.name)

    # Track entities referenced by process human_task steps
    process_referenced_entities: dict[str, list[str]] = {}  # entity -> [process_names]
    for proc in processes:
        for step in proc.steps:
            if is_step_kind(step, "human_task"):
                human_task = step.human_task
                if human_task:
                    surface_name = human_task.surface
                    # Find entity for this surface
                    for s in surfaces:
                        if s.name == surface_name:
                            eref = get_surface_entity(s)
                            if eref:
                                process_referenced_entities.setdefault(eref, []).append(proc.name)

    # Check each entity
    for entity in entities:
        coverage = entity_surface_map.get(entity.name, {})
        has_any_surface = bool(coverage)
        is_sys = _is_system_managed(entity)

        # Store coverage info
        report.entity_coverage[entity.name] = {
            "list": bool(coverage.get("list")),
            "create": bool(coverage.get("create")),
            "edit": bool(coverage.get("edit")),
            "view": bool(coverage.get("view")),
            "surfaces": [s for modes in coverage.values() for s in modes],
            "is_system_managed": is_sys,
        }

        # Check: no surface at all
        if not has_any_surface:
            severity = "critical"
            if entity.name in process_referenced_entities:
                severity = "critical"
            report.gaps.append(
                EntityCoverageGap(
                    entity_name=entity.name,
                    gap_type="no_surface",
                    severity=severity,
                    description=f"Entity '{entity.name}' has no surfaces at all",
                )
            )
            continue

        # Check individual CRUD modes
        if not coverage.get("list"):
            report.gaps.append(
                EntityCoverageGap(
                    entity_name=entity.name,
                    gap_type="missing_list",
                    severity="high",
                    description=f"Entity '{entity.name}' has no list surface",
                )
            )

        # Skip create/edit gaps for system-managed entities or RBAC-forbidden ops
        skip_create = is_sys or _is_operation_forbidden(entity, "create")
        skip_edit = is_sys or _is_operation_forbidden(entity, "update")

        if not coverage.get("create") and not skip_create:
            report.gaps.append(
                EntityCoverageGap(
                    entity_name=entity.name,
                    gap_type="missing_create",
                    severity="high",
                    description=f"Entity '{entity.name}' has no create surface",
                )
            )

        if not coverage.get("edit") and not skip_edit:
            report.gaps.append(
                EntityCoverageGap(
                    entity_name=entity.name,
                    gap_type="missing_edit",
                    severity="medium",
                    description=f"Entity '{entity.name}' has no edit surface",
                )
            )

        if not coverage.get("view"):
            report.gaps.append(
                EntityCoverageGap(
                    entity_name=entity.name,
                    gap_type="missing_view",
                    severity="low",
                    description=f"Entity '{entity.name}' has no view surface",
                )
            )

        # Check state machine UI
        sm = entity.state_machine
        if sm and sm.transitions:
            # Check if any surface for this entity has actions (transition UI)
            has_transition_ui = False
            for surface in surfaces:
                if get_surface_entity(surface) == entity.name:
                    actions = surface.actions
                    if actions:
                        has_transition_ui = True
                        break
            if not has_transition_ui:
                report.gaps.append(
                    EntityCoverageGap(
                        entity_name=entity.name,
                        gap_type="no_transition_ui",
                        severity="medium",
                        description=f"Entity '{entity.name}' has state machine but no surface with transition actions",
                    )
                )

    # Check process-referenced entities with no surfaces
    for entity_name, proc_names in process_referenced_entities.items():
        if entity_name not in entity_surface_map or not entity_surface_map[entity_name]:
            # Already caught as no_surface above, but add process context
            report.gaps.append(
                EntityCoverageGap(
                    entity_name=entity_name,
                    gap_type="process_referenced",
                    severity="critical",
                    description=f"Entity '{entity_name}' referenced in process human_task but has no surfaces",
                    process_name=proc_names[0],
                )
            )

    return report
