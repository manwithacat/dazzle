"""
Infrastructure versioning utilities.

Provides change detection and version tracking for CDK stacks:
- Computes stack checksums for change detection
- Generates `.dazzle-infra-version.json` with version metadata
- Detects added/modified/removed stacks between versions
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass
class StackVersion:
    """Version info for a single stack."""

    name: str
    checksum: str
    generated_at: str
    file_path: str


@dataclass
class InfraVersion:
    """Version metadata for the entire infrastructure."""

    version: str
    dazzle_version: str
    generated_at: str
    environment: str
    stacks: list[StackVersion] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "version": self.version,
            "dazzle_version": self.dazzle_version,
            "generated_at": self.generated_at,
            "environment": self.environment,
            "stacks": [
                {
                    "name": s.name,
                    "checksum": s.checksum,
                    "generated_at": s.generated_at,
                    "file_path": s.file_path,
                }
                for s in self.stacks
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InfraVersion:
        """Create from dictionary."""
        return cls(
            version=data["version"],
            dazzle_version=data["dazzle_version"],
            generated_at=data["generated_at"],
            environment=data["environment"],
            stacks=[
                StackVersion(
                    name=s["name"],
                    checksum=s["checksum"],
                    generated_at=s["generated_at"],
                    file_path=s["file_path"],
                )
                for s in data.get("stacks", [])
            ],
        )


@dataclass
class VersionDiff:
    """Differences between two infrastructure versions."""

    added: list[str] = field(default_factory=list)
    modified: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)

    def has_changes(self) -> bool:
        """Check if there are any changes."""
        return bool(self.added or self.modified or self.removed)

    def summary(self) -> str:
        """Generate a human-readable summary."""
        parts = []
        if self.added:
            parts.append(f"Added: {', '.join(self.added)}")
        if self.modified:
            parts.append(f"Modified: {', '.join(self.modified)}")
        if self.removed:
            parts.append(f"Removed: {', '.join(self.removed)}")
        if not parts:
            return "No changes"
        return "; ".join(parts)


def compute_file_checksum(file_path: Path) -> str:
    """Compute SHA-256 checksum of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()[:16]  # Shortened for readability


def compute_content_checksum(content: str) -> str:
    """Compute SHA-256 checksum of string content."""
    sha256 = hashlib.sha256(content.encode("utf-8"))
    return sha256.hexdigest()[:16]


def generate_version_id(environment: str, stacks: list[StackVersion]) -> str:
    """Generate a version ID based on environment and stack checksums."""
    combined = (
        environment + ":" + ":".join(s.checksum for s in sorted(stacks, key=lambda x: x.name))
    )
    sha256 = hashlib.sha256(combined.encode("utf-8"))
    return sha256.hexdigest()[:12]


def create_infra_version(
    output_dir: Path,
    environment: str,
    dazzle_version: str | None = None,
) -> InfraVersion:
    """
    Create version metadata for generated infrastructure.

    Args:
        output_dir: Directory containing generated CDK stacks
        environment: Deployment environment (dev, staging, prod)
        dazzle_version: Optional Dazzle version string

    Returns:
        InfraVersion with checksums for all generated stacks
    """
    if dazzle_version is None:
        try:
            from dazzle import __version__

            dazzle_version = __version__
        except ImportError:
            dazzle_version = "unknown"

    stacks_dir = output_dir / "stacks"
    stacks: list[StackVersion] = []
    now = datetime.now(UTC).isoformat()

    if stacks_dir.exists():
        for stack_file in sorted(stacks_dir.glob("*.py")):
            if stack_file.name.startswith("__"):
                continue

            # Extract stack name from filename (e.g., network.py -> Network)
            stack_name = stack_file.stem.replace("_", " ").title().replace(" ", "")

            stacks.append(
                StackVersion(
                    name=stack_name,
                    checksum=compute_file_checksum(stack_file),
                    generated_at=now,
                    file_path=str(stack_file.relative_to(output_dir)),
                )
            )

    version_id = generate_version_id(environment, stacks)

    return InfraVersion(
        version=version_id,
        dazzle_version=dazzle_version,
        generated_at=now,
        environment=environment,
        stacks=stacks,
    )


def save_version_file(version: InfraVersion, output_dir: Path) -> Path:
    """
    Save version metadata to .dazzle-infra-version.json.

    Args:
        version: Version metadata to save
        output_dir: Directory to save the version file

    Returns:
        Path to the saved version file
    """
    version_file = output_dir / ".dazzle-infra-version.json"
    with open(version_file, "w") as f:
        json.dump(version.to_dict(), f, indent=2)
    return version_file


def load_version_file(output_dir: Path) -> InfraVersion | None:
    """
    Load version metadata from .dazzle-infra-version.json.

    Args:
        output_dir: Directory containing the version file

    Returns:
        InfraVersion if file exists, None otherwise
    """
    version_file = output_dir / ".dazzle-infra-version.json"
    if not version_file.exists():
        return None

    with open(version_file) as f:
        data = json.load(f)
    return InfraVersion.from_dict(data)


def compare_versions(old: InfraVersion | None, new: InfraVersion) -> VersionDiff:
    """
    Compare two infrastructure versions to detect changes.

    Args:
        old: Previous version (None if first deployment)
        new: New version

    Returns:
        VersionDiff with added/modified/removed/unchanged stacks
    """
    if old is None:
        return VersionDiff(added=sorted([s.name for s in new.stacks]))

    old_stacks = {s.name: s.checksum for s in old.stacks}
    new_stacks = {s.name: s.checksum for s in new.stacks}

    added = []
    modified = []
    unchanged = []

    for name, checksum in new_stacks.items():
        if name not in old_stacks:
            added.append(name)
        elif old_stacks[name] != checksum:
            modified.append(name)
        else:
            unchanged.append(name)

    removed = [name for name in old_stacks if name not in new_stacks]

    return VersionDiff(
        added=sorted(added),
        modified=sorted(modified),
        removed=sorted(removed),
        unchanged=sorted(unchanged),
    )


def check_for_changes(output_dir: Path, environment: str) -> tuple[bool, VersionDiff, InfraVersion]:
    """
    Check if infrastructure has changed since last generation.

    Args:
        output_dir: Directory containing generated CDK stacks
        environment: Deployment environment

    Returns:
        Tuple of (has_changes, diff, new_version)
    """
    old_version = load_version_file(output_dir)
    new_version = create_infra_version(output_dir, environment)
    diff = compare_versions(old_version, new_version)

    return diff.has_changes(), diff, new_version
