"""
Process inspection and listing handlers.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..common import extract_progress, handler_error_json
from . import _helpers

if TYPE_CHECKING:
    from dazzle.core.ir.process import ProcessSpec, ProcessStepSpec
    from dazzle.core.ir.stories import StorySpec


# =============================================================================
# Inspect Process Handler
# =============================================================================


@handler_error_json
def inspect_process_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Inspect a process definition."""
    progress = extract_progress(args)
    process_name = args.get("process_name") if args else None

    if not process_name:
        return json.dumps({"error": "process_name is required"})

    try:
        progress.log_sync(f"Inspecting process '{process_name}'...")
        app_spec = _helpers._load_app_spec(project_root)

        processes: list[ProcessSpec] = list(app_spec.processes) if app_spec.processes else []

        # Merge with persisted processes
        from dazzle.core.process_persistence import load_processes as load_persisted_processes

        persisted = load_persisted_processes(project_root)
        dsl_names = {p.name for p in processes}
        for p in persisted:
            if p.name not in dsl_names:
                processes.append(p)

        stories: list[StorySpec] = list(app_spec.stories) if app_spec.stories else []

        # Fall back to persisted stories from .dazzle/stories/stories.json
        if not stories:
            from dazzle.core.stories_persistence import load_stories

            stories = load_stories(project_root)

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


@handler_error_json
def list_processes_handler(project_root: Path, args: dict[str, Any]) -> str:
    """List all processes in the project."""
    progress = extract_progress(args)
    try:
        progress.log_sync("Loading processes...")
        app_spec = _helpers._load_app_spec(project_root)

        processes: list[ProcessSpec] = list(app_spec.processes) if app_spec.processes else []

        # Merge with persisted processes
        from dazzle.core.process_persistence import load_processes as load_persisted_processes

        persisted = load_persisted_processes(project_root)
        dsl_names = {p.name for p in processes}
        for p in persisted:
            if p.name not in dsl_names:
                processes.append(p)

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
