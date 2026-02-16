"""
Process diagram generation — Mermaid flowchart and state diagram rendering.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..common import extract_progress, wrap_handler_errors
from . import _helpers

if TYPE_CHECKING:
    from dazzle.core.ir.process import ProcessSpec, ProcessStepSpec


# =============================================================================
# Constants
# =============================================================================

# Flow control keywords used in step transitions
FLOW_COMPLETE_KEYWORDS = ("complete", "end")
FLOW_FAILURE_KEYWORDS = ("fail", "error")


# =============================================================================
# Diagram Handler
# =============================================================================


@wrap_handler_errors
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
    progress = extract_progress(args)
    process_name = args.get("process_name") if args else None
    include_compensations = args.get("include_compensations", False) if args else False
    diagram_type = args.get("type", "flowchart") if args else "flowchart"

    if not process_name:
        return json.dumps({"error": "process_name is required"})

    try:
        progress.log_sync(f"Generating {diagram_type} diagram for '{process_name}'...")
        app_spec = _helpers.load_app_spec(project_root)

        processes: list[ProcessSpec] = list(app_spec.processes) if app_spec.processes else []

        # Merge with persisted processes
        from dazzle.core.process_persistence import load_processes as load_persisted_processes

        persisted = load_persisted_processes(project_root)
        dsl_names = {p.name for p in processes}
        for p in persisted:
            if p.name not in dsl_names:
                processes.append(p)

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


# =============================================================================
# Mermaid Generation
# =============================================================================


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
            if step.on_success in FLOW_COMPLETE_KEYWORDS:
                lines.append(f"    {step.name} --> [*]: success")
            else:
                lines.append(f"    {step.name} --> {step.on_success}: success")
        else:
            lines.append(f"    {step.name} --> {next_step}")

        if step.on_failure:
            if step.on_failure in FLOW_FAILURE_KEYWORDS:
                lines.append(f"    {step.name} --> [*]: failure")
            else:
                lines.append(f"    {step.name} --> {step.on_failure}: failure")

        # Human task outcomes
        if step.kind == StepKind.HUMAN_TASK and step.human_task:
            for outcome in step.human_task.outcomes:
                if outcome.goto:
                    if outcome.goto in FLOW_COMPLETE_KEYWORDS:
                        lines.append(f"    {step.name} --> [*]: {outcome.name}")
                    else:
                        lines.append(f"    {step.name} --> {outcome.goto}: {outcome.name}")

    return "\n".join(lines)


# =============================================================================
# Mermaid Helpers
# =============================================================================


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
            return f"\U0001f464 {step.human_task.surface or step.name}"
        return f"\U0001f464 {step.name}"
    elif step.kind == StepKind.SUBPROCESS:
        return f"\u2192 {step.subprocess}"
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
        if true_target in FLOW_COMPLETE_KEYWORDS:
            true_target = "COMPLETE"
        if false_target in FLOW_FAILURE_KEYWORDS:
            false_target = "FAILED"
        lines.append(f"    {step.name} -->|Yes| {true_target}")
        lines.append(f"    {step.name} -->|No| {false_target}")
    elif step.kind == StepKind.HUMAN_TASK and step.human_task and step.human_task.outcomes:
        # Human task outcomes as branches
        for outcome in step.human_task.outcomes:
            target = outcome.goto or next_step
            if target in FLOW_COMPLETE_KEYWORDS:
                target = "COMPLETE"
            elif target in FLOW_FAILURE_KEYWORDS:
                target = "FAILED"
            label = outcome.label or outcome.name
            lines.append(f"    {step.name} -->|{label}| {target}")
    else:
        # Normal flow
        if step.on_success:
            target = step.on_success
            if target in FLOW_COMPLETE_KEYWORDS:
                target = "COMPLETE"
            lines.append(f"    {step.name} --> {target}")
        else:
            lines.append(f"    {step.name} --> {next_step}")

        # Error flow
        if step.on_failure:
            target = step.on_failure
            if target in FLOW_FAILURE_KEYWORDS:
                target = "FAILED"
            lines.append(f"    {step.name} -.->|error| {target}")

    return lines
