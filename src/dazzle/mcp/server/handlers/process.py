"""
Process and coverage tool handlers for MCP server.

Handles process inspection, story coverage analysis, process proposal generation,
and process run monitoring.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from dazzle.core.fileset import discover_dsl_files
from dazzle.core.linker import build_appspec
from dazzle.core.manifest import load_manifest
from dazzle.core.parser import parse_modules

if TYPE_CHECKING:
    from dazzle.core.ir.appspec import AppSpec
    from dazzle.core.ir.process import ProcessSpec, ProcessStepSpec
    from dazzle.core.ir.stories import StorySpec
    from dazzle.core.process.adapter import ProcessAdapter


# =============================================================================
# Data Classes for Coverage Results
# =============================================================================


@dataclass
class StoryCoverage:
    """Coverage status for a single story."""

    story_id: str
    title: str
    status: Literal["covered", "partial", "uncovered"]
    implementing_processes: list[str]
    missing_aspects: list[str]


@dataclass
class CoverageReport:
    """Full coverage analysis."""

    total_stories: int
    covered: int
    partial: int
    uncovered: int
    coverage_percent: float
    stories: list[StoryCoverage]


@dataclass
class ProposedProcess:
    """A proposed process generated from stories."""

    name: str
    title: str
    implements: list[str]
    trigger_suggestion: str
    steps_outline: list[str]
    dsl_code: str


@dataclass
class ProcessRunSummary:
    """Summary of a process run."""

    run_id: str
    process_name: str
    status: str
    current_step: str | None
    started_at: str
    duration_seconds: float | None
    error: str | None


# =============================================================================
# Helper Functions
# =============================================================================


def _load_app_spec(project_root: Path) -> AppSpec:
    """Load and build AppSpec from project."""
    manifest = load_manifest(project_root / "dazzle.toml")
    dsl_files = discover_dsl_files(project_root, manifest)
    modules = parse_modules(dsl_files)
    return build_appspec(modules, manifest.project_root)


def _get_process_adapter(project_root: Path) -> ProcessAdapter:
    """Get process adapter for project."""
    from dazzle.core.process import LiteProcessAdapter

    db_path = project_root / ".dazzle" / "processes.db"
    return LiteProcessAdapter(db_path=db_path)


def _slugify(text: str) -> str:
    """Convert text to snake_case slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[-\s]+", "_", text)
    return text[:30]


def _story_id_to_process_name(story_id: str, title: str) -> str:
    """Convert story ID and title to process name."""
    # Clean title to create base name
    base = _slugify(title)
    # Append story ID suffix
    suffix = story_id.lower().replace("-", "_")
    return f"proc_{base}_{suffix}"


# =============================================================================
# Story Coverage Handler
# =============================================================================


def stories_coverage_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Analyze story coverage by processes."""
    try:
        app_spec = _load_app_spec(project_root)

        stories: list[StorySpec] = list(app_spec.stories) if app_spec.stories else []
        processes: list[ProcessSpec] = list(app_spec.processes) if app_spec.processes else []

        if not stories:
            return json.dumps(
                {
                    "error": "No stories found in project",
                    "hint": "Use propose_stories_from_dsl to generate stories, or define them in DSL.",
                }
            )

        # Build implements mapping: story_id -> [process_names]
        implements_map: dict[str, list[str]] = {}
        for proc in processes:
            for story_id in proc.implements:
                implements_map.setdefault(story_id, []).append(proc.name)

        coverage_results: list[StoryCoverage] = []
        covered_count = 0
        partial_count = 0
        uncovered_count = 0

        for story in stories:
            implementing = implements_map.get(story.story_id, [])

            if not implementing:
                status: Literal["covered", "partial", "uncovered"] = "uncovered"
                uncovered_count += 1
                missing = ["No implementing process"]
            else:
                # Check if all 'then' outcomes are addressed by process steps
                missing = _find_missing_aspects(story, processes, implementing)
                if missing:
                    status = "partial"
                    partial_count += 1
                else:
                    status = "covered"
                    covered_count += 1

            coverage_results.append(
                StoryCoverage(
                    story_id=story.story_id,
                    title=story.title,
                    status=status,
                    implementing_processes=implementing,
                    missing_aspects=missing,
                )
            )

        total = len(stories)
        coverage_percent = (covered_count / total * 100) if total > 0 else 0.0

        report = CoverageReport(
            total_stories=total,
            covered=covered_count,
            partial=partial_count,
            uncovered=uncovered_count,
            coverage_percent=round(coverage_percent, 1),
            stories=coverage_results,
        )

        return json.dumps(
            {
                "total_stories": report.total_stories,
                "covered": report.covered,
                "partial": report.partial,
                "uncovered": report.uncovered,
                "coverage_percent": report.coverage_percent,
                "stories": [asdict(s) for s in report.stories],
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


def _find_missing_aspects(
    story: StorySpec,
    processes: list[ProcessSpec],
    implementing: list[str],
) -> list[str]:
    """Identify story aspects not covered by implementing processes."""
    missing: list[str] = []

    # Get all step names from implementing processes
    all_steps: list[str] = []
    for proc_name in implementing:
        proc = next((p for p in processes if p.name == proc_name), None)
        if proc:
            for step in proc.steps:
                all_steps.append(step.name.lower())
                # Include parallel steps
                for parallel_step in step.parallel_steps:
                    all_steps.append(parallel_step.name.lower())

    # Get 'then' outcomes from story (both legacy and Gherkin-style)
    then_outcomes: list[str] = []
    if story.then:
        then_outcomes = [c.expression for c in story.then]
    elif story.happy_path_outcome:
        then_outcomes = story.happy_path_outcome

    # Check each outcome against step names (simple word matching)
    for outcome in then_outcomes:
        outcome_words = set(outcome.lower().split())
        # Filter to meaningful words (> 3 chars)
        meaningful_words = {w for w in outcome_words if len(w) > 3}

        matched = any(any(word in step for word in meaningful_words) for step in all_steps)
        if not matched:
            missing.append(outcome)

    # Check 'unless' exceptions
    for exception in story.unless:
        unless_words = set(exception.condition.lower().split())
        meaningful_words = {w for w in unless_words if len(w) > 3}

        matched = any(any(word in step for word in meaningful_words) for step in all_steps)
        if not matched:
            missing.append(f"Exception: {exception.condition}")

    return missing


# =============================================================================
# Process Proposal Handler
# =============================================================================


def propose_processes_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Generate process proposals for uncovered stories."""
    try:
        app_spec = _load_app_spec(project_root)
        story_ids = args.get("story_ids")

        stories: list[StorySpec] = list(app_spec.stories) if app_spec.stories else []
        processes: list[ProcessSpec] = list(app_spec.processes) if app_spec.processes else []

        if not stories:
            return json.dumps(
                {
                    "error": "No stories found",
                    "hint": "Use propose_stories_from_dsl first.",
                }
            )

        # Build implements mapping
        implements_map: dict[str, list[str]] = {}
        for proc in processes:
            for sid in proc.implements:
                implements_map.setdefault(sid, []).append(proc.name)

        # Find target stories
        if story_ids:
            target_stories = [s for s in stories if s.story_id in story_ids]
        else:
            # Find uncovered or partial stories
            target_stories = [
                s
                for s in stories
                if s.story_id not in implements_map
                or _find_missing_aspects(s, processes, implements_map.get(s.story_id, []))
            ]

        if not target_stories:
            return json.dumps(
                {
                    "status": "all_covered",
                    "message": "All stories are fully covered by processes.",
                }
            )

        proposals: list[ProposedProcess] = []
        for story in target_stories:
            proposal = _generate_proposal(story, app_spec)
            proposals.append(proposal)

        return json.dumps(
            {
                "proposed_count": len(proposals),
                "proposals": [asdict(p) for p in proposals],
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


def _generate_proposal(story: StorySpec, app_spec: AppSpec) -> ProposedProcess:
    """Generate a process proposal from a story."""

    name = _story_id_to_process_name(story.story_id, story.title)

    # Infer trigger from story
    trigger = _infer_trigger(story, app_spec)

    # Generate steps from 'then' outcomes
    steps = _infer_steps(story, app_spec)

    # Generate DSL code
    dsl = _generate_process_dsl(name, story, trigger, steps)

    return ProposedProcess(
        name=name,
        title=story.title,
        implements=[story.story_id],
        trigger_suggestion=trigger,
        steps_outline=[s["name"] for s in steps],
        dsl_code=dsl,
    )


def _infer_trigger(story: StorySpec, app_spec: AppSpec) -> str:
    """Infer process trigger from story."""
    from dazzle.core.ir.stories import StoryTrigger

    if story.trigger == StoryTrigger.STATUS_CHANGED:
        # Try to extract entity and status from 'when' conditions
        for when_cond in story.when:
            expr_lower = when_cond.expression.lower()
            if "changes to" in expr_lower or "status" in expr_lower:
                # Extract the target status if possible
                if story.scope:
                    entity = story.scope[0]
                    return f"entity {entity} status_change"
        if story.scope:
            return f"entity {story.scope[0]} status_change"
        return "manual"

    elif story.trigger == StoryTrigger.FORM_SUBMITTED:
        if story.scope:
            return f"entity {story.scope[0]} created"
        return "manual"

    elif story.trigger == StoryTrigger.CRON_DAILY:
        return 'cron "0 8 * * *"'

    elif story.trigger == StoryTrigger.CRON_HOURLY:
        return 'cron "0 * * * *"'

    elif story.trigger == StoryTrigger.TIMER_ELAPSED:
        return "schedule interval 3600"

    return "manual"


def _infer_steps(story: StorySpec, app_spec: AppSpec) -> list[dict[str, Any]]:
    """Infer process steps from story outcomes."""
    steps: list[dict[str, Any]] = []

    # Get 'then' outcomes
    outcomes: list[str] = story.effective_then

    for i, outcome in enumerate(outcomes, 1):
        step: dict[str, Any] = {
            "name": f"step_{i}",
            "description": outcome,
        }

        # Detect step type from outcome text
        expr_lower = outcome.lower()
        if "email" in expr_lower or "notification" in expr_lower or "sent" in expr_lower:
            step["kind"] = "send"
            step["suggestion"] = "channel: notifications"
        elif "saved" in expr_lower or "created" in expr_lower or "recorded" in expr_lower:
            step["kind"] = "service"
            if story.scope:
                step["suggestion"] = f"service: {story.scope[0].lower()}_service"
            else:
                step["suggestion"] = "service: entity_service"
        elif "wait" in expr_lower:
            step["kind"] = "wait"
            step["suggestion"] = "duration: 1h"
        else:
            step["kind"] = "service"
            step["suggestion"] = "service: handle_outcome"

        steps.append(step)

    # Add exception handling steps from 'unless' branches
    for exception in story.unless:
        step = {
            "name": f"handle_{_slugify(exception.condition)}",
            "kind": "service",
            "description": f"Handle exception: {exception.condition}",
            "condition": exception.condition,
            "suggestion": "service: handle_exception",
        }
        steps.append(step)

    return steps


def _generate_process_dsl(
    name: str,
    story: StorySpec,
    trigger: str,
    steps: list[dict[str, Any]],
) -> str:
    """Generate DSL code for a process."""
    lines = [
        f'process {name} "{story.title}":',
        f"  implements: [{story.story_id}]",
        "",
        "  trigger:",
        f"    {trigger}",
        "",
        "  steps:",
    ]

    for step in steps:
        lines.append(f"    - step {step['name']}:")
        lines.append(f"        # {step['description']}")

        if step.get("kind") == "send":
            lines.append(f"        {step.get('suggestion', 'channel: notifications')}")
        elif step.get("kind") == "wait":
            lines.append(f"        {step.get('suggestion', 'duration: 1h')}")
        else:
            lines.append(f"        {step.get('suggestion', 'service: TODO')}")

        if step.get("condition"):
            lines.append(f"        condition: when {step['condition']}")

        lines.append("        timeout: 30s")
        lines.append("")

    return "\n".join(lines)


# =============================================================================
# Process Runs Handler
# =============================================================================


async def _list_runs_async(project_root: Path, args: dict[str, Any]) -> str:
    """Async implementation for listing process runs."""
    from dazzle.core.process.adapter import ProcessStatus

    try:
        adapter = _get_process_adapter(project_root)
        await adapter.initialize()

        process_name = args.get("process_name")
        status_filter = args.get("status")
        limit = args.get("limit", 50)

        status = ProcessStatus(status_filter) if status_filter else None

        runs = await adapter.list_runs(
            process_name=process_name,
            status=status,
            limit=limit,
        )

        summaries: list[ProcessRunSummary] = []
        for run in runs:
            duration = None
            if run.completed_at:
                duration = (run.completed_at - run.started_at).total_seconds()

            summaries.append(
                ProcessRunSummary(
                    run_id=run.run_id,
                    process_name=run.process_name,
                    status=run.status.value,
                    current_step=run.current_step,
                    started_at=run.started_at.isoformat(),
                    duration_seconds=duration,
                    error=run.error,
                )
            )

        return json.dumps(
            {
                "count": len(summaries),
                "runs": [asdict(s) for s in summaries],
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


def list_process_runs_handler(project_root: Path, args: dict[str, Any]) -> str:
    """List process runs with optional filters."""
    import asyncio

    try:
        return asyncio.run(_list_runs_async(project_root, args))
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


async def _get_run_async(project_root: Path, args: dict[str, Any]) -> str:
    """Async implementation for getting a process run."""
    try:
        adapter = _get_process_adapter(project_root)
        await adapter.initialize()

        run_id = args.get("run_id")
        if not run_id:
            return json.dumps({"error": "run_id is required"})

        run = await adapter.get_run(run_id)
        if not run:
            return json.dumps({"error": f"Run '{run_id}' not found"})

        duration = None
        if run.completed_at:
            duration = (run.completed_at - run.started_at).total_seconds()

        return json.dumps(
            {
                "run_id": run.run_id,
                "process_name": run.process_name,
                "process_version": run.process_version,
                "dsl_version": run.dsl_version,
                "status": run.status.value,
                "current_step": run.current_step,
                "inputs": run.inputs,
                "context": run.context,
                "outputs": run.outputs,
                "error": run.error,
                "idempotency_key": run.idempotency_key,
                "started_at": run.started_at.isoformat(),
                "updated_at": run.updated_at.isoformat(),
                "completed_at": run.completed_at.isoformat() if run.completed_at else None,
                "duration_seconds": duration,
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


def get_process_run_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Get detailed information about a specific process run."""
    import asyncio

    run_id = args.get("run_id") if args else None
    if not run_id:
        return json.dumps({"error": "run_id is required"})

    try:
        return asyncio.run(_get_run_async(project_root, args))
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


# =============================================================================
# Process Inspection Handler
# =============================================================================


def inspect_process_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Inspect a process definition."""
    process_name = args.get("process_name") if args else None

    if not process_name:
        return json.dumps({"error": "process_name is required"})

    try:
        app_spec = _load_app_spec(project_root)

        processes: list[ProcessSpec] = list(app_spec.processes) if app_spec.processes else []
        stories: list[StorySpec] = list(app_spec.stories) if app_spec.stories else []

        proc = next((p for p in processes if p.name == process_name), None)
        if not proc:
            available = [p.name for p in processes]
            return json.dumps(
                {
                    "error": f"Process '{process_name}' not found",
                    "available_processes": available,
                }
            )

        # Get linked stories
        linked_stories = [
            {"story_id": s.story_id, "title": s.title}
            for s in stories
            if s.story_id in proc.implements
        ]

        # Format trigger
        trigger_info = None
        if proc.trigger:
            trigger_info = {
                "kind": proc.trigger.kind.value,
                "entity_name": proc.trigger.entity_name,
                "event_type": proc.trigger.event_type,
                "from_status": proc.trigger.from_status,
                "to_status": proc.trigger.to_status,
                "cron": proc.trigger.cron,
                "interval_seconds": proc.trigger.interval_seconds,
            }

        # Format steps
        formatted_steps = [_format_step(s) for s in proc.steps]

        return json.dumps(
            {
                "name": proc.name,
                "title": proc.title,
                "description": proc.description,
                "implements": proc.implements,
                "linked_stories": linked_stories,
                "trigger": trigger_info,
                "inputs": [
                    {
                        "name": i.name,
                        "type": i.type,
                        "required": i.required,
                        "default": i.default,
                        "description": i.description,
                    }
                    for i in proc.inputs
                ],
                "outputs": [
                    {"name": o.name, "type": o.type, "description": o.description}
                    for o in proc.outputs
                ],
                "steps": formatted_steps,
                "compensations": [
                    {"name": c.name, "service": c.service, "timeout_seconds": c.timeout_seconds}
                    for c in proc.compensations
                ],
                "timeout_seconds": proc.timeout_seconds,
                "overlap_policy": proc.overlap_policy.value,
                "events": {
                    "on_start": proc.events.on_start,
                    "on_complete": proc.events.on_complete,
                    "on_failure": proc.events.on_failure,
                },
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


def _format_step(step: ProcessStepSpec) -> dict[str, Any]:
    """Format a process step for JSON output."""
    from dazzle.core.ir.process import StepKind

    result: dict[str, Any] = {
        "name": step.name,
        "kind": step.kind.value,
        "timeout_seconds": step.timeout_seconds,
    }

    if step.kind == StepKind.SERVICE:
        result["service"] = step.service
    elif step.kind == StepKind.SEND:
        result["channel"] = step.channel
        result["message"] = step.message
    elif step.kind == StepKind.WAIT:
        result["wait_duration_seconds"] = step.wait_duration_seconds
        result["wait_for_signal"] = step.wait_for_signal
    elif step.kind == StepKind.HUMAN_TASK and step.human_task:
        result["surface"] = step.human_task.surface
        result["assignee_role"] = step.human_task.assignee_role
        result["outcomes"] = [
            {"name": o.name, "label": o.label, "goto": o.goto} for o in step.human_task.outcomes
        ]
    elif step.kind == StepKind.SUBPROCESS:
        result["subprocess"] = step.subprocess
    elif step.kind == StepKind.PARALLEL:
        result["parallel_steps"] = [_format_step(s) for s in step.parallel_steps]
        result["parallel_policy"] = step.parallel_policy.value

    if step.condition:
        result["condition"] = step.condition

    if step.retry:
        result["retry"] = {
            "max_attempts": step.retry.max_attempts,
            "backoff": step.retry.backoff.value,
        }

    if step.on_success:
        result["on_success"] = step.on_success
    if step.on_failure:
        result["on_failure"] = step.on_failure
    if step.compensate_with:
        result["compensate_with"] = step.compensate_with

    return result


# =============================================================================
# List Processes Handler
# =============================================================================


def list_processes_handler(project_root: Path, args: dict[str, Any]) -> str:
    """List all processes in the project."""
    try:
        app_spec = _load_app_spec(project_root)

        processes: list[ProcessSpec] = list(app_spec.processes) if app_spec.processes else []

        process_list = []
        for proc in processes:
            process_list.append(
                {
                    "name": proc.name,
                    "title": proc.title,
                    "description": proc.description,
                    "implements": proc.implements,
                    "trigger_kind": proc.trigger.kind.value if proc.trigger else None,
                    "step_count": len(proc.steps),
                    "timeout_seconds": proc.timeout_seconds,
                }
            )

        return json.dumps(
            {
                "count": len(process_list),
                "processes": process_list,
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


# =============================================================================
# Process Diagram Handler
# =============================================================================


def get_process_diagram_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Generate a Mermaid diagram for a process.

    Produces a flowchart showing:
    - Process trigger (start node)
    - Steps as nodes with kind-specific shapes
    - Flow control edges (on_success, on_failure)
    - Human task outcome branches
    - Parallel step groupings
    - Compensation handlers (optional)
    """
    process_name = args.get("process_name") if args else None
    include_compensations = args.get("include_compensations", False) if args else False
    diagram_type = args.get("type", "flowchart") if args else "flowchart"

    if not process_name:
        return json.dumps({"error": "process_name is required"})

    try:
        app_spec = _load_app_spec(project_root)

        processes: list[ProcessSpec] = list(app_spec.processes) if app_spec.processes else []

        proc = next((p for p in processes if p.name == process_name), None)
        if not proc:
            available = [p.name for p in processes]
            return json.dumps(
                {
                    "error": f"Process '{process_name}' not found",
                    "available_processes": available,
                }
            )

        # Generate diagram
        mermaid_code = _generate_process_mermaid(proc, include_compensations, diagram_type)

        return json.dumps(
            {
                "process_name": proc.name,
                "title": proc.title,
                "type": diagram_type,
                "diagram": mermaid_code,
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


def _generate_process_mermaid(
    proc: ProcessSpec,
    include_compensations: bool = False,
    diagram_type: str = "flowchart",
) -> str:
    """Generate Mermaid diagram code for a process."""
    from dazzle.core.ir.process import StepKind

    lines: list[str] = []

    if diagram_type == "stateDiagram":
        return _generate_state_diagram(proc, include_compensations)

    # Use flowchart TD (top-down)
    lines.append("flowchart TD")
    lines.append(f"    %% Process: {proc.name}")
    if proc.title:
        lines.append(f"    %% Title: {proc.title}")
    lines.append("")

    # Start node (trigger)
    trigger_label = _get_trigger_label(proc)
    lines.append(f"    START([{trigger_label}])")
    lines.append("")

    # Steps subgraph
    lines.append("    subgraph steps [Process Steps]")

    step_count = len(proc.steps)
    for i, step in enumerate(proc.steps):
        step_lines = _step_to_mermaid(step, i, step_count)
        lines.extend(step_lines)

    lines.append("    end")
    lines.append("")

    # End node
    lines.append("    COMPLETE([Complete])")
    lines.append("    FAILED([Failed])")
    lines.append("")

    # Flow edges
    lines.append("    %% Flow")
    if proc.steps:
        lines.append(f"    START --> {proc.steps[0].name}")

    for i, step in enumerate(proc.steps):
        step_edges = _step_edges(step, i, proc.steps)
        lines.extend(step_edges)

    lines.append("")

    # Compensation handlers (optional)
    if include_compensations and proc.compensations:
        lines.append("    subgraph compensations [Compensations]")
        for comp in proc.compensations:
            lines.append(f"        {comp.name}[/{comp.name}/]")
        lines.append("    end")
        lines.append("")
        lines.append("    FAILED -.-> compensations")

    # Styling
    lines.append("")
    lines.append("    %% Styling")
    lines.append("    classDef startEnd fill:#f9f,stroke:#333,stroke-width:2px")
    lines.append("    classDef serviceStep fill:#bbf,stroke:#333")
    lines.append("    classDef humanTask fill:#fbb,stroke:#333")
    lines.append("    classDef waitStep fill:#bfb,stroke:#333")
    lines.append("    class START,COMPLETE,FAILED startEnd")

    # Apply styling to steps
    for step in proc.steps:
        if step.kind == StepKind.SERVICE:
            lines.append(f"    class {step.name} serviceStep")
        elif step.kind == StepKind.HUMAN_TASK:
            lines.append(f"    class {step.name} humanTask")
        elif step.kind == StepKind.WAIT:
            lines.append(f"    class {step.name} waitStep")

    return "\n".join(lines)


def _generate_state_diagram(proc: ProcessSpec, include_compensations: bool) -> str:
    """Generate state diagram variant."""
    from dazzle.core.ir.process import StepKind

    lines: list[str] = []
    lines.append("stateDiagram-v2")
    lines.append(f"    %% Process: {proc.name}")
    lines.append("")

    # State declarations
    lines.append("    [*] --> " + (proc.steps[0].name if proc.steps else "[*]"))
    lines.append("")

    for step in proc.steps:
        label = _get_step_label(step)
        lines.append(f"    {step.name}: {label}")

    lines.append("")

    # Transitions
    for i, step in enumerate(proc.steps):
        next_step = proc.steps[i + 1].name if i + 1 < len(proc.steps) else "[*]"

        if step.on_success:
            if step.on_success == "complete" or step.on_success == "end":
                lines.append(f"    {step.name} --> [*]: success")
            else:
                lines.append(f"    {step.name} --> {step.on_success}: success")
        else:
            lines.append(f"    {step.name} --> {next_step}")

        if step.on_failure:
            if step.on_failure == "fail" or step.on_failure == "error":
                lines.append(f"    {step.name} --> [*]: failure")
            else:
                lines.append(f"    {step.name} --> {step.on_failure}: failure")

        # Human task outcomes
        if step.kind == StepKind.HUMAN_TASK and step.human_task:
            for outcome in step.human_task.outcomes:
                if outcome.goto:
                    if outcome.goto in ("complete", "end"):
                        lines.append(f"    {step.name} --> [*]: {outcome.name}")
                    else:
                        lines.append(f"    {step.name} --> {outcome.goto}: {outcome.name}")

    return "\n".join(lines)


def _get_trigger_label(proc: ProcessSpec) -> str:
    """Get human-readable label for process trigger."""
    if not proc.trigger:
        return "Manual Start"

    from dazzle.core.ir.process import ProcessTriggerKind

    kind = proc.trigger.kind
    if kind == ProcessTriggerKind.ENTITY_EVENT:
        event = proc.trigger.event_type or "event"
        entity = proc.trigger.entity_name or "entity"
        return f"{entity}.{event}"
    elif kind == ProcessTriggerKind.ENTITY_STATUS_TRANSITION:
        entity = proc.trigger.entity_name or "entity"
        from_s = proc.trigger.from_status or "*"
        to_s = proc.trigger.to_status or "*"
        return f"{entity}: {from_s} → {to_s}"
    elif kind == ProcessTriggerKind.SCHEDULE_CRON:
        return f"cron: {proc.trigger.cron}"
    elif kind == ProcessTriggerKind.SCHEDULE_INTERVAL:
        return f"every {proc.trigger.interval_seconds}s"
    elif kind == ProcessTriggerKind.SIGNAL:
        return "External Signal"
    elif kind == ProcessTriggerKind.PROCESS_COMPLETED:
        return f"after: {proc.trigger.process_name}"
    else:
        return "Manual"


def _get_step_label(step: ProcessStepSpec) -> str:
    """Get human-readable label for a step."""
    from dazzle.core.ir.process import StepKind

    if step.kind == StepKind.SERVICE:
        return step.service or step.name
    elif step.kind == StepKind.SEND:
        return f"Send: {step.message or step.channel}"
    elif step.kind == StepKind.WAIT:
        if step.wait_for_signal:
            return f"Wait for: {step.wait_for_signal}"
        elif step.wait_duration_seconds:
            return f"Wait: {step.wait_duration_seconds}s"
        else:
            return "Wait"
    elif step.kind == StepKind.HUMAN_TASK:
        if step.human_task:
            return f"👤 {step.human_task.surface or step.name}"
        return f"👤 {step.name}"
    elif step.kind == StepKind.SUBPROCESS:
        return f"→ {step.subprocess}"
    elif step.kind == StepKind.PARALLEL:
        return f"Parallel ({len(step.parallel_steps)})"
    elif step.kind == StepKind.CONDITION:
        return f"? {step.condition or step.name}"
    else:
        return step.name


def _step_to_mermaid(step: ProcessStepSpec, index: int, total: int) -> list[str]:
    """Convert a step to Mermaid node definition."""
    from dazzle.core.ir.process import StepKind

    lines: list[str] = []
    label = _get_step_label(step)

    # Use different shapes for different step kinds
    if step.kind == StepKind.SERVICE:
        lines.append(f"        {step.name}[{label}]")
    elif step.kind == StepKind.SEND:
        lines.append(f"        {step.name}>{label}]")  # Asymmetric shape
    elif step.kind == StepKind.WAIT:
        lines.append(f"        {step.name}{{{{{label}}}}}")  # Hexagon
    elif step.kind == StepKind.HUMAN_TASK:
        lines.append(f"        {step.name}[/{label}\\]")  # Trapezoid
    elif step.kind == StepKind.SUBPROCESS:
        lines.append(f'        {step.name}[["{label}"]]')  # Subroutine
    elif step.kind == StepKind.PARALLEL:
        lines.append(f"        subgraph {step.name} [{label}]")
        lines.append("            direction LR")
        for i, ps in enumerate(step.parallel_steps):
            ps_lines = _step_to_mermaid(ps, i, len(step.parallel_steps))
            lines.extend(ps_lines)
        lines.append("        end")
    elif step.kind == StepKind.CONDITION:
        lines.append(f"        {step.name}{{{label}}}")  # Diamond/rhombus
    else:
        lines.append(f"        {step.name}[{label}]")

    return lines


def _step_edges(step: ProcessStepSpec, index: int, steps: list[ProcessStepSpec]) -> list[str]:
    """Generate edges for a step."""
    from dazzle.core.ir.process import StepKind

    lines: list[str] = []
    next_step = steps[index + 1].name if index + 1 < len(steps) else "COMPLETE"

    if step.kind == StepKind.CONDITION:
        # Conditional branching
        true_target = step.on_true or next_step
        false_target = step.on_false or "FAILED"
        if true_target in ("complete", "end"):
            true_target = "COMPLETE"
        if false_target in ("fail", "error"):
            false_target = "FAILED"
        lines.append(f"    {step.name} -->|Yes| {true_target}")
        lines.append(f"    {step.name} -->|No| {false_target}")
    elif step.kind == StepKind.HUMAN_TASK and step.human_task and step.human_task.outcomes:
        # Human task outcomes as branches
        for outcome in step.human_task.outcomes:
            target = outcome.goto or next_step
            if target in ("complete", "end"):
                target = "COMPLETE"
            elif target in ("fail", "error"):
                target = "FAILED"
            label = outcome.label or outcome.name
            lines.append(f"    {step.name} -->|{label}| {target}")
    else:
        # Normal flow
        if step.on_success:
            target = step.on_success
            if target in ("complete", "end"):
                target = "COMPLETE"
            lines.append(f"    {step.name} --> {target}")
        else:
            lines.append(f"    {step.name} --> {next_step}")

        # Error flow
        if step.on_failure:
            target = step.on_failure
            if target in ("fail", "error"):
                target = "FAILED"
            lines.append(f"    {step.name} -.->|error| {target}")

    return lines
