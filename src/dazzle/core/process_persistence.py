"""
Process persistence layer for DAZZLE.

Handles reading and writing composed process specifications to the
.dazzle/processes/ directory. Processes are stored as JSON for easy
inspection and editing.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from dazzle.mcp.server.paths import project_processes_dir

from .ir.process import ProcessesContainer, ProcessSpec

SEEDS_PROCESSES_DIR = "dsl/seeds/processes"
PROCESSES_FILE = "processes.json"

logger = logging.getLogger(__name__)


def get_processes_dir(project_root: Path) -> Path:
    """Get the .dazzle/processes/ directory path (runtime location)."""
    return project_processes_dir(project_root)


def get_processes_file(project_root: Path) -> Path:
    """Get the processes.json file path (runtime location)."""
    return get_processes_dir(project_root) / PROCESSES_FILE


def _find_processes_file(project_root: Path) -> Path | None:
    """Find the processes.json file, checking runtime then seeds."""
    runtime_file = get_processes_dir(project_root) / PROCESSES_FILE
    if runtime_file.exists():
        return runtime_file

    seeds_file = project_root / SEEDS_PROCESSES_DIR / PROCESSES_FILE
    if seeds_file.exists():
        return seeds_file

    return None


def load_processes(project_root: Path) -> list[ProcessSpec]:
    """Load all persisted processes from .dazzle/processes/ or seeds fallback.

    Returns:
        List of process specifications. Returns empty list if file doesn't exist.
    """
    processes_file = _find_processes_file(project_root)
    if processes_file is None:
        return []

    try:
        content = processes_file.read_text(encoding="utf-8")
        data = json.loads(content)
        container = ProcessesContainer.model_validate(data)
        return list(container.processes)
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"Failed to load processes from {processes_file}: {e}")
        return []


def load_process_index(project_root: Path) -> list[dict[str, Any]]:
    """Load lightweight process summaries without full Pydantic validation."""
    processes_file = _find_processes_file(project_root)
    if processes_file is None:
        return []

    try:
        content = processes_file.read_text(encoding="utf-8")
        data = json.loads(content)
        return [
            {
                "name": p.get("name", ""),
                "title": p.get("title", ""),
                "implements": p.get("implements", []),
                "step_count": len(p.get("steps", [])),
            }
            for p in data.get("processes", [])
        ]
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"Failed to load process index from {processes_file}: {e}")
        return []


def save_processes(
    project_root: Path,
    processes: list[ProcessSpec],
    *,
    version: str = "1.0",
) -> Path:
    """Save processes to .dazzle/processes/processes.json.

    Returns:
        Path to the saved processes.json file.
    """
    processes_dir = get_processes_dir(project_root)
    processes_dir.mkdir(parents=True, exist_ok=True)

    container = ProcessesContainer(version=version, processes=processes)

    processes_file = get_processes_file(project_root)
    processes_file.write_text(
        json.dumps(
            container.model_dump(mode="json"),
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    return processes_file


def add_processes(
    project_root: Path,
    new_processes: list[ProcessSpec],
    *,
    overwrite: bool = False,
) -> list[ProcessSpec]:
    """Add new processes, optionally overwriting existing ones.

    Args:
        project_root: Root directory of the DAZZLE project.
        new_processes: Processes to add.
        overwrite: If True, replace processes with matching names.

    Returns:
        List of all processes after the operation.
    """
    existing = load_processes(project_root)
    existing_names = {p.name for p in existing}

    if overwrite:
        new_names = {p.name for p in new_processes}
        existing = [p for p in existing if p.name not in new_names]
        existing.extend(new_processes)
    else:
        for proc in new_processes:
            if proc.name not in existing_names:
                existing.append(proc)
                existing_names.add(proc.name)

    save_processes(project_root, existing)
    return existing
