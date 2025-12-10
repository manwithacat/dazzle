"""
Build state management for incremental generation.

Tracks:
- Previous build metadata (timestamp, backend, output dir)
- DSL file hashes to detect changes
- AppSpec snapshot for diff comparison
"""

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import ir
from .errors import DazzleError


class StateError(DazzleError):
    """Raised when state operations fail."""

    pass


@dataclass
class BuildState:
    """
    Represents the state of a previous build.

    Used to detect changes and enable incremental updates.
    """

    timestamp: str  # ISO format datetime
    backend: str
    output_dir: str
    dsl_file_hashes: dict[str, str]  # {relative_path: sha256_hash}
    appspec_snapshot: dict[str, Any] | None = None  # Simplified AppSpec for diffing

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return asdict(self)

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "BuildState":
        """Create BuildState from dict."""
        return BuildState(**data)


def compute_file_hash(file_path: Path) -> str:
    """
    Compute SHA256 hash of a file.

    Args:
        file_path: Path to file

    Returns:
        Hex-encoded SHA256 hash

    Raises:
        StateError: If file cannot be read
    """
    try:
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
    except Exception as e:
        raise StateError(f"Failed to hash file {file_path}: {e}") from e


def compute_dsl_hashes(dsl_files: list[Path], root: Path) -> dict[str, str]:
    """
    Compute hashes for all DSL files.

    Args:
        dsl_files: List of absolute DSL file paths
        root: Project root for computing relative paths

    Returns:
        Dict mapping relative path to hash

    Raises:
        StateError: If hashing fails
    """
    hashes = {}
    for dsl_file in dsl_files:
        try:
            rel_path = str(dsl_file.relative_to(root))
        except ValueError:
            # File outside project root, use absolute path
            rel_path = str(dsl_file)

        hashes[rel_path] = compute_file_hash(dsl_file)

    return hashes


def simplify_appspec(appspec: ir.AppSpec) -> dict[str, Any]:
    """
    Create a simplified JSON-serializable snapshot of AppSpec.

    Extracts key information for change detection:
    - Entity names and field signatures
    - Surface names and modes
    - Service names
    - Experience names

    Args:
        appspec: Full AppSpec

    Returns:
        Simplified dict suitable for JSON storage
    """
    snapshot: dict[str, Any] = {
        "app": {
            "name": appspec.name,
            "title": appspec.title,
            "version": appspec.version,
        },
        "entities": {},
        "surfaces": {},
        "apis": {},
        "experiences": {},
    }

    # Entity signatures
    for entity in appspec.domain.entities:
        fields: dict[str, Any] = {}
        for field in entity.fields:
            fields[field.name] = {
                "type": str(field.type),
                "required": field.is_required,
                "modifiers": [str(m) for m in field.modifiers],
            }
        snapshot["entities"][entity.name] = {
            "title": entity.title,
            "fields": fields,
        }

    # Surface signatures
    for surface in appspec.surfaces:
        snapshot["surfaces"][surface.name] = {
            "title": surface.title,
            "mode": surface.mode,
            "entity": surface.entity_ref if hasattr(surface, "entity_ref") else None,
        }

    # API signatures (external services)
    for api in appspec.apis:
        snapshot["apis"][api.name] = {
            "title": api.title,
            "spec_url": api.spec_url if hasattr(api, "spec_url") else None,
        }

    # Experience signatures
    for experience in appspec.experiences:
        snapshot["experiences"][experience.name] = {
            "title": experience.title,
        }

    return snapshot


def get_state_file_path(project_root: Path) -> Path:
    """
    Get path to state file for a project.

    Args:
        project_root: Project root directory

    Returns:
        Path to .dazzle/state.json
    """
    return project_root / ".dazzle" / "state.json"


def load_state(project_root: Path) -> BuildState | None:
    """
    Load previous build state.

    Args:
        project_root: Project root directory

    Returns:
        BuildState if exists, None otherwise

    Raises:
        StateError: If state file is corrupted
    """
    state_file = get_state_file_path(project_root)

    if not state_file.exists():
        return None

    try:
        with open(state_file, encoding="utf-8") as f:
            data = json.load(f)
        return BuildState.from_dict(data)
    except Exception as e:
        raise StateError(f"Failed to load build state: {e}") from e


def save_state(
    project_root: Path,
    backend: str,
    output_dir: Path,
    dsl_files: list[Path],
    appspec: ir.AppSpec,
) -> None:
    """
    Save build state after successful generation.

    Args:
        project_root: Project root directory
        backend: Backend name used
        output_dir: Output directory for generated files
        dsl_files: List of DSL files processed
        appspec: Generated AppSpec

    Raises:
        StateError: If state cannot be saved
    """
    state_dir = project_root / ".dazzle"
    state_file = state_dir / "state.json"

    try:
        # Ensure .dazzle directory exists
        state_dir.mkdir(parents=True, exist_ok=True)

        # Compute hashes
        dsl_hashes = compute_dsl_hashes(dsl_files, project_root)

        # Compute output_dir path (relative if inside project, absolute otherwise)
        try:
            output_dir_str = str(output_dir.relative_to(project_root))
        except ValueError:
            # Output dir is outside project root, use absolute path
            output_dir_str = str(output_dir)

        # Create state
        state = BuildState(
            timestamp=datetime.now(UTC).isoformat() + "Z",
            backend=backend,
            output_dir=output_dir_str,
            dsl_file_hashes=dsl_hashes,
            appspec_snapshot=simplify_appspec(appspec),
        )

        # Write state file
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(state.to_dict(), f, indent=2)

    except Exception as e:
        raise StateError(f"Failed to save build state: {e}") from e


def clear_state(project_root: Path) -> None:
    """
    Clear build state (force full rebuild next time).

    Args:
        project_root: Project root directory
    """
    state_file = get_state_file_path(project_root)
    if state_file.exists():
        state_file.unlink()


__all__ = [
    "StateError",
    "BuildState",
    "compute_file_hash",
    "compute_dsl_hashes",
    "simplify_appspec",
    "get_state_file_path",
    "load_state",
    "save_state",
    "clear_state",
]
