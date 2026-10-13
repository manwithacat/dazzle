"""
Workflow coherence: static process/story integrity analysis.

Deterministic pass over the DSL that finds broken process references and story
gaps; ``persona_journey.run_headless_discovery`` folds its gaps into
``discovery(operation=coherence)``.

Checks:
- Process human_task steps reference existing surfaces
- Process subprocess steps reference existing processes
- entity_status_transition triggers reference entities with state machines
- Stories have implementing processes
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dazzle.core.ir.appspec import AppSpec
from ._shared import (
    is_step_kind,
    is_trigger_kind,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Static Analysis Types
# =============================================================================


@dataclass
class WorkflowGap:
    """A gap in workflow coherence."""

    gap_type: str  # "missing_human_task_surface", "missing_subprocess", "trigger_no_state_machine", "story_no_process"
    severity: str  # "critical", "high", "medium", "low"
    description: str
    process_name: str | None = None
    story_id: str | None = None
    entity_name: str | None = None
    surface_name: str | None = None


@dataclass
class WorkflowCoherenceReport:
    """Result of static workflow coherence analysis."""

    gaps: list[WorkflowGap] = field(default_factory=list)

    @property
    def gap_count(self) -> int:
        return len(self.gaps)

    def to_summary(self) -> str:
        """Build a compact summary for embedding in system prompts."""
        if not self.gaps:
            return "No workflow coherence gaps found."

        lines: list[str] = [f"Found {self.gap_count} workflow coherence gaps:\n"]
        for gap in self.gaps:
            lines.append(f"- [{gap.severity.upper()}] {gap.gap_type}: {gap.description}")
        return "\n".join(lines)


# =============================================================================
# Static Analysis
# =============================================================================


def _static_workflow_analysis(appspec: AppSpec) -> WorkflowCoherenceReport:
    """
    Analyze DSL spec for workflow coherence gaps.

    Checks process references, story coverage, and trigger validity.
    """
    report = WorkflowCoherenceReport()

    surfaces = appspec.surfaces
    processes = appspec.processes
    stories = appspec.stories
    entities = appspec.domain.entities

    # Build lookup sets
    surface_names = {s.name for s in surfaces}
    process_names = {p.name for p in processes}
    entity_map: dict[str, Any] = {e.name: e for e in entities}

    # Build set of story IDs that have implementing processes
    implemented_story_ids: set[str] = set()
    for proc in processes:
        for story_id in proc.implements:
            implemented_story_ids.add(story_id)

    # Check each process
    for proc in processes:
        for step in proc.steps:
            # Check human_task steps reference existing surfaces
            if is_step_kind(step, "human_task"):
                human_task = step.human_task
                if human_task:
                    surface_ref = human_task.surface
                    if surface_ref and surface_ref not in surface_names:
                        report.gaps.append(
                            WorkflowGap(
                                gap_type="missing_human_task_surface",
                                severity="critical",
                                description=f"Process '{proc.name}' step '{step.name}' references surface '{surface_ref}' which does not exist",
                                process_name=proc.name,
                                surface_name=surface_ref,
                            )
                        )

            # Check subprocess steps reference existing processes
            if is_step_kind(step, "subprocess"):
                subprocess_ref = step.subprocess
                if subprocess_ref and subprocess_ref not in process_names:
                    report.gaps.append(
                        WorkflowGap(
                            gap_type="missing_subprocess",
                            severity="high",
                            description=f"Process '{proc.name}' step '{step.name}' references subprocess '{subprocess_ref}' which does not exist",
                            process_name=proc.name,
                        )
                    )

        # Check entity_status_transition triggers reference entities with state machines
        trigger = proc.trigger
        if trigger and is_trigger_kind(trigger, "entity_status_transition"):
            entity_name = trigger.entity_name
            if entity_name:
                entity = entity_map.get(entity_name)
                if not entity:
                    report.gaps.append(
                        WorkflowGap(
                            gap_type="trigger_no_state_machine",
                            severity="high",
                            description=f"Process '{proc.name}' trigger references entity '{entity_name}' which does not exist",
                            process_name=proc.name,
                            entity_name=entity_name,
                        )
                    )
                elif not entity.state_machine:
                    report.gaps.append(
                        WorkflowGap(
                            gap_type="trigger_no_state_machine",
                            severity="high",
                            description=f"Process '{proc.name}' trigger references entity '{entity_name}' which has no state machine",
                            process_name=proc.name,
                            entity_name=entity_name,
                        )
                    )

    # Check stories have implementing processes
    for story in stories:
        story_id = story.story_id
        if story_id not in implemented_story_ids:
            report.gaps.append(
                WorkflowGap(
                    gap_type="story_no_process",
                    severity="medium",
                    description=f"Story '{story_id}' ({story.title}) has no implementing process",
                    story_id=story_id,
                )
            )

    return report
