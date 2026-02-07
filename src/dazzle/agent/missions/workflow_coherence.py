"""
Workflow coherence mission: static process/story integrity analysis + targeted verification.

Unlike the open-ended persona walkthrough, this mode:
1. Statically analyzes the DSL to find broken process references and story gaps
2. Builds a focused mission that guides the agent to verify specific issues

Checks:
- Process human_task steps reference existing surfaces
- Process subprocess steps reference existing processes
- entity_status_transition triggers reference entities with state machines
- Stories have implementing processes
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from ..core import AgentTool, Mission
from ._shared import (
    build_dsl_summary,
    is_step_kind,
    is_trigger_kind,
    make_observe_gap_tool,
    make_query_dsl_tool,
    make_stagnation_completion,
)

logger = logging.getLogger("dazzle.agent.missions.workflow_coherence")


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


def _static_workflow_analysis(appspec: Any) -> WorkflowCoherenceReport:
    """
    Analyze DSL spec for workflow coherence gaps.

    Checks process references, story coverage, and trigger validity.
    """
    report = WorkflowCoherenceReport()

    surfaces = getattr(appspec, "surfaces", []) or []
    processes = getattr(appspec, "processes", []) or []
    stories = getattr(appspec, "stories", []) or []
    entities = getattr(getattr(appspec, "domain", None), "entities", []) or []

    # Build lookup sets
    surface_names = {s.name for s in surfaces}
    process_names = {p.name for p in processes}
    entity_map: dict[str, Any] = {e.name: e for e in entities}

    # Build set of story IDs that have implementing processes
    implemented_story_ids: set[str] = set()
    for proc in processes:
        for story_id in getattr(proc, "implements", []):
            implemented_story_ids.add(story_id)

    # Check each process
    for proc in processes:
        for step in getattr(proc, "steps", []):
            # Check human_task steps reference existing surfaces
            if is_step_kind(step, "human_task"):
                human_task = getattr(step, "human_task", None)
                if human_task:
                    surface_ref = getattr(human_task, "surface", None)
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
                subprocess_ref = getattr(step, "subprocess", None)
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
        trigger = getattr(proc, "trigger", None)
        if trigger and is_trigger_kind(trigger, "entity_status_transition"):
            entity_name = getattr(trigger, "entity_name", None)
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
                elif not getattr(entity, "state_machine", None):
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
        story_id = getattr(story, "story_id", None)
        if story_id and story_id not in implemented_story_ids:
            report.gaps.append(
                WorkflowGap(
                    gap_type="story_no_process",
                    severity="medium",
                    description=f"Story '{story_id}' ({getattr(story, 'title', '')}) has no implementing process",
                    story_id=story_id,
                )
            )

    return report


# =============================================================================
# Mission Tools
# =============================================================================


def _make_check_process_coverage_tool(appspec: Any) -> AgentTool:
    """Tool: check_process_coverage — returns step-by-step coverage for a process."""
    processes = getattr(appspec, "processes", []) or []
    surfaces = getattr(appspec, "surfaces", []) or []
    surface_names = {s.name for s in surfaces}
    process_names = {p.name for p in processes}

    def check_process_coverage(process_name: str = "") -> dict[str, Any]:
        if not process_name:
            return {"error": "process_name is required"}

        # Find process
        proc = None
        for p in processes:
            if p.name == process_name:
                proc = p
                break
        if proc is None:
            return {"error": f"Process '{process_name}' not found"}

        steps_coverage = []
        for step in getattr(proc, "steps", []):
            kind_str = str(getattr(step, "kind", ""))
            step_info: dict[str, Any] = {
                "name": step.name,
                "kind": kind_str,
            }

            if is_step_kind(step, "human_task"):
                human_task = getattr(step, "human_task", None)
                if human_task:
                    surface_ref = getattr(human_task, "surface", None)
                    step_info["surface"] = surface_ref
                    step_info["surface_exists"] = (
                        surface_ref in surface_names if surface_ref else False
                    )

            if is_step_kind(step, "subprocess"):
                subprocess_ref = getattr(step, "subprocess", None)
                step_info["subprocess"] = subprocess_ref
                step_info["subprocess_exists"] = (
                    subprocess_ref in process_names if subprocess_ref else False
                )

            steps_coverage.append(step_info)

        return {
            "process": process_name,
            "title": getattr(proc, "title", None),
            "implements": getattr(proc, "implements", []),
            "step_count": len(steps_coverage),
            "steps": steps_coverage,
        }

    return AgentTool(
        name="check_process_coverage",
        description=(
            "Check step-by-step coverage for a process. Returns each step's kind, "
            "referenced surfaces/subprocesses, and whether they exist."
        ),
        schema={
            "type": "object",
            "properties": {
                "process_name": {
                    "type": "string",
                    "description": "Process name to check",
                },
            },
            "required": ["process_name"],
        },
        handler=check_process_coverage,
    )


def _make_list_workflow_gaps_tool(report: WorkflowCoherenceReport) -> AgentTool:
    """Tool: list_workflow_gaps — returns static analysis gaps for investigation."""

    def list_workflow_gaps(gap_type: str | None = None) -> dict[str, Any]:
        gaps = report.gaps
        if gap_type:
            gaps = [g for g in gaps if g.gap_type == gap_type]

        return {
            "total": len(gaps),
            "gaps": [
                {
                    "gap_type": g.gap_type,
                    "severity": g.severity,
                    "description": g.description,
                    "process_name": g.process_name,
                    "story_id": g.story_id,
                    "entity_name": g.entity_name,
                    "surface_name": g.surface_name,
                }
                for g in gaps
            ],
        }

    return AgentTool(
        name="list_workflow_gaps",
        description=(
            "List workflow gaps found by static analysis. Optionally filter by gap_type: "
            "missing_human_task_surface, missing_subprocess, trigger_no_state_machine, story_no_process."
        ),
        schema={
            "type": "object",
            "properties": {
                "gap_type": {
                    "type": "string",
                    "enum": [
                        "missing_human_task_surface",
                        "missing_subprocess",
                        "trigger_no_state_machine",
                        "story_no_process",
                    ],
                    "description": "Filter to a specific gap type",
                },
            },
        },
        handler=list_workflow_gaps,
    )


# =============================================================================
# System Prompt
# =============================================================================

WORKFLOW_COHERENCE_PROMPT = """You are a workflow coherence verification agent for a Dazzle application.

Your mission is to verify process integrity, story coverage, and trigger validity.
A static analysis has already identified potential gaps. Your job is to verify them
against the running application and the DSL specification.

## Static Analysis Results
{gap_summary}

## DSL Specification Summary
{dsl_summary}

## Verification Strategy
1. **Review gaps**: Use `list_workflow_gaps` to see all static analysis findings
2. **Check processes**: Use `check_process_coverage` for each flagged process
3. **Verify surfaces**: Navigate to referenced surfaces and check they exist
4. **Record findings**: Use `observe_gap` for confirmed gaps with accurate severity
5. **Query DSL**: Use `query_dsl` to get entity/surface details when needed

## Gap Types
- **missing_human_task_surface**: Process step references a surface that doesn't exist
- **missing_subprocess**: Process step references a subprocess that doesn't exist
- **trigger_no_state_machine**: Process trigger uses entity_status_transition on entity without state machine
- **story_no_process**: Story has no implementing process

## Severity Guidelines
- **critical**: Process step references missing surface (workflow is broken)
- **high**: Missing subprocess; trigger references entity without state machine
- **medium**: Story has no implementing process
- **low**: Minor workflow issues

## Output Format
Respond with ONLY a single JSON object for each action. No extra text."""


# =============================================================================
# Mission Builder
# =============================================================================


def build_workflow_coherence_mission(
    appspec: Any,
    base_url: str = "http://localhost:3000",
    kg_store: Any | None = None,
    max_steps: int = 30,
    token_budget: int = 150_000,
) -> Mission:
    """
    Build a Mission for workflow coherence verification.

    Runs static analysis first, then builds a focused mission to verify gaps.

    Args:
        appspec: Parsed AppSpec from the DSL
        base_url: Base URL of the running application
        kg_store: Optional KnowledgeGraphStore for adjacency checks
        max_steps: Maximum verification steps
        token_budget: Token budget for the LLM

    Returns:
        Mission configured for workflow coherence verification
    """
    # Run static analysis
    report = _static_workflow_analysis(appspec)

    # Build system prompt
    dsl_summary = build_dsl_summary(appspec)
    system_prompt = WORKFLOW_COHERENCE_PROMPT.format(
        gap_summary=report.to_summary(),
        dsl_summary=dsl_summary,
    )

    # Build tools
    tools = [
        make_observe_gap_tool(kg_store),
        make_query_dsl_tool(appspec),
        _make_check_process_coverage_tool(appspec),
        _make_list_workflow_gaps_tool(report),
    ]

    return Mission(
        name="workflow_coherence",
        system_prompt=system_prompt,
        tools=tools,
        completion_criteria=make_stagnation_completion(6, "Workflow coherence"),
        max_steps=max_steps,
        token_budget=token_budget,
        start_url=base_url,
        context={
            "mode": "workflow_coherence",
            "app_name": getattr(appspec, "name", "unknown"),
            "static_analysis": {
                "gaps_found": report.gap_count,
            },
        },
    )
