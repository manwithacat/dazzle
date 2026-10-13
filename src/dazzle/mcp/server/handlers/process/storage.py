"""
Process storage — save composed processes.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from dazzle.core.ir.process import ProcessSpec
from dazzle.core.process_persistence import add_processes

from . import _helpers

if TYPE_CHECKING:
    from dazzle.core.ir.stories import StorySpec


# =============================================================================
# Save Processes Handler
# =============================================================================


def process_save_impl(
    project_root: Path,
    raw_processes: list[Any],
    overwrite: bool = False,
) -> dict[str, Any]:
    """Save composed processes to .dazzle/processes/processes.json.

    Validates that referenced story IDs exist and entity references are valid.

    Args:
        project_root: Root directory of the project.
        raw_processes: List of process dicts (ProcessSpec-compatible).
        overwrite: If True, replace processes with matching names.
    """
    if not raw_processes or not isinstance(raw_processes, list):
        return {"error": "processes list is required"}

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
        return {"error": "Validation failed", "details": errors}

    # Validate story references exist
    app_spec = _helpers.load_app_spec(project_root)
    stories: list[StorySpec] = list(app_spec.stories) if app_spec.stories else []

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

    # Save
    all_processes = add_processes(project_root, parsed, overwrite=overwrite)

    result: dict[str, Any] = {
        "saved": len(parsed),
        "total": len(all_processes),
        "process_names": [p.name for p in parsed],
    }
    if warnings:
        result["warnings"] = warnings

    return result
