"""
Process storage handlers — save processes and manage process runs.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..common import extract_progress
from . import _helpers

if TYPE_CHECKING:
    from dazzle.core.ir.process import ProcessSpec
    from dazzle.core.ir.stories import StorySpec


# =============================================================================
# Data Classes
# =============================================================================


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
# Save Processes Handler
# =============================================================================


def save_processes_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Save composed processes to .dazzle/processes/processes.json.

    Accepts a list of process definitions and persists them. Validates
    that referenced story IDs exist and entity references are valid.

    Args (via args dict):
        processes: List of process dicts (ProcessSpec-compatible)
        overwrite: If True, replace processes with matching names (default: False)
    """
    progress = extract_progress(args)
    try:
        from dazzle.core.ir.process import ProcessSpec
        from dazzle.core.process_persistence import add_processes

        raw_processes = args.get("processes")
        if not raw_processes or not isinstance(raw_processes, list):
            return json.dumps({"error": "processes list is required"})

        overwrite = args.get("overwrite", False)

        progress.log_sync("Validating processes...")
        # Validate and parse processes
        parsed: list[ProcessSpec] = []
        errors: list[str] = []

        for i, raw in enumerate(raw_processes):
            try:
                proc = ProcessSpec.model_validate(raw)
                parsed.append(proc)
            except Exception as e:
                errors.append(f"Process {i}: {e}")

        if errors:
            return json.dumps({"error": "Validation failed", "details": errors})

        progress.log_sync("Validating story and entity references...")
        # Validate story references exist
        app_spec = _helpers._load_app_spec(project_root)
        stories: list[StorySpec] = list(app_spec.stories) if app_spec.stories else []
        if not stories:
            from dazzle.core.stories_persistence import load_stories

            stories = load_stories(project_root)

        story_ids = {s.story_id for s in stories}
        warnings: list[str] = []
        for proc in parsed:
            for sid in proc.implements:
                if sid not in story_ids:
                    warnings.append(f"Process '{proc.name}' references unknown story '{sid}'")

        # Validate entity references
        entity_names = {e.name for e in app_spec.domain.entities}
        for proc in parsed:
            if proc.trigger and proc.trigger.entity_name:
                if proc.trigger.entity_name not in entity_names:
                    warnings.append(
                        f"Process '{proc.name}' trigger references "
                        f"unknown entity '{proc.trigger.entity_name}'"
                    )

        progress.log_sync(f"Saving {len(parsed)} processes...")
        # Save
        all_processes = add_processes(project_root, parsed, overwrite=overwrite)

        result: dict[str, Any] = {
            "saved": len(parsed),
            "total": len(all_processes),
            "process_names": [p.name for p in parsed],
        }
        if warnings:
            result["warnings"] = warnings

        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


# =============================================================================
# Process Runs Handlers
# =============================================================================


async def _list_runs_async(project_root: Path, args: dict[str, Any]) -> str:
    """Async implementation for listing process runs."""
    from dazzle.core.process.adapter import ProcessStatus

    progress = extract_progress(args)
    try:
        progress.log_sync("Loading process runs...")
        adapter = _helpers._get_process_adapter(project_root)
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


async def list_process_runs_handler(project_root: Path, args: dict[str, Any]) -> str:
    """List process runs with optional filters."""
    try:
        return await _list_runs_async(project_root, args)
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


async def _get_run_async(project_root: Path, args: dict[str, Any]) -> str:
    """Async implementation for getting a process run."""
    progress = extract_progress(args)
    try:
        progress.log_sync("Fetching process run details...")
        adapter = _helpers._get_process_adapter(project_root)
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


async def get_process_run_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Get detailed information about a specific process run."""
    run_id = args.get("run_id") if args else None
    if not run_id:
        return json.dumps({"error": "run_id is required"})

    try:
        return await _get_run_async(project_root, args)
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)
