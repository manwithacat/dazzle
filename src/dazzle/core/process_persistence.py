"""
Process persistence layer for DAZZLE.

Handles reading and writing composed process specifications to the
.dazzle/processes/ directory. Processes are stored as JSON for easy
inspection and editing.
"""

import json
import logging
import tempfile
from pathlib import Path

from pydantic import ValidationError

from dazzle.core.paths import project_processes_dir

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
        data = json.loads(processes_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning("Failed to load processes from %s: %s", processes_file, e)
        return []
    if not isinstance(data, dict) or not isinstance(data.get("processes", []), list):
        logger.warning(
            "Failed to load processes from %s: not a processes container", processes_file
        )
        return []

    # Validate entry by entry so one stale entry (e.g. a trigger kind a newer
    # IR removed) skips only itself, not the whole file (#1837).
    processes: list[ProcessSpec] = []
    for index, entry in enumerate(data.get("processes", [])):
        try:
            processes.append(ProcessSpec.model_validate(entry))
        except ValidationError as e:
            name = entry.get("name") if isinstance(entry, dict) else None
            logger.error(
                "Skipping persisted process %s (entry %d) in %s; it will not run: %s",
                name or "<unnamed>",
                index,
                processes_file,
                e,
            )
    return processes


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
    content = json.dumps(
        container.model_dump(mode="json"),
        indent=2,
        ensure_ascii=False,
    )

    # Atomic write: write to temp file then rename to prevent corruption
    # on crash (rename is atomic on POSIX filesystems).
    fd, tmp_path = tempfile.mkstemp(dir=str(processes_dir), suffix=".tmp", prefix=".processes_")
    try:
        with open(fd, "w", encoding="utf-8") as f:
            f.write(content)
        Path(tmp_path).replace(processes_file)
    except BaseException:
        Path(tmp_path).unlink(missing_ok=True)
        raise

    return processes_file
