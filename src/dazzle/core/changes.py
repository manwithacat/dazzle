"""
Change detection for incremental builds.

Analyzes differences between previous and current AppSpec to determine
what needs to be regenerated.
"""

from dataclasses import dataclass
from typing import Optional, Set

from . import ir
from .state import BuildState, simplify_appspec


@dataclass
class ChangeSet:
    """
    Describes what changed between two AppSpec versions.

    Used to determine what needs to be regenerated.
    """
    # Files changed
    dsl_files_added: Set[str]
    dsl_files_removed: Set[str]
    dsl_files_modified: Set[str]

    # Entities
    entities_added: Set[str]
    entities_removed: Set[str]
    entities_modified: Set[str]  # Field changes

    # Surfaces
    surfaces_added: Set[str]
    surfaces_removed: Set[str]
    surfaces_modified: Set[str]  # Mode or field changes

    # Services
    services_added: Set[str]
    services_removed: Set[str]
    services_modified: Set[str]

    # Experiences
    experiences_added: Set[str]
    experiences_removed: Set[str]
    experiences_modified: Set[str]

    # App-level changes
    app_modified: bool  # Title or ID changed

    def is_empty(self) -> bool:
        """Check if there are no changes."""
        return (
            not self.dsl_files_added
            and not self.dsl_files_removed
            and not self.dsl_files_modified
            and not self.entities_added
            and not self.entities_removed
            and not self.entities_modified
            and not self.surfaces_added
            and not self.surfaces_removed
            and not self.surfaces_modified
            and not self.services_added
            and not self.services_removed
            and not self.services_modified
            and not self.experiences_added
            and not self.experiences_removed
            and not self.experiences_modified
            and not self.app_modified
        )

    def requires_full_rebuild(self) -> bool:
        """
        Check if changes require full rebuild.

        Some changes are too complex for incremental updates:
        - App ID changed (affects all artifacts)
        - Entities removed (affects dependent surfaces)
        - Major structural changes
        """
        return (
            self.app_modified
            or bool(self.entities_removed)
            or bool(self.dsl_files_removed)
        )

    def summary(self) -> str:
        """Generate human-readable summary of changes."""
        lines = []

        if self.app_modified:
            lines.append("  App: modified")

        if self.dsl_files_added:
            lines.append(f"  DSL Files: +{len(self.dsl_files_added)}")
        if self.dsl_files_removed:
            lines.append(f"  DSL Files: -{len(self.dsl_files_removed)}")
        if self.dsl_files_modified:
            lines.append(f"  DSL Files: ~{len(self.dsl_files_modified)}")

        if self.entities_added:
            lines.append(f"  Entities: +{len(self.entities_added)} ({', '.join(sorted(self.entities_added))})")
        if self.entities_removed:
            lines.append(f"  Entities: -{len(self.entities_removed)} ({', '.join(sorted(self.entities_removed))})")
        if self.entities_modified:
            lines.append(f"  Entities: ~{len(self.entities_modified)} ({', '.join(sorted(self.entities_modified))})")

        if self.surfaces_added:
            lines.append(f"  Surfaces: +{len(self.surfaces_added)}")
        if self.surfaces_removed:
            lines.append(f"  Surfaces: -{len(self.surfaces_removed)}")
        if self.surfaces_modified:
            lines.append(f"  Surfaces: ~{len(self.surfaces_modified)}")

        if self.services_added:
            lines.append(f"  Services: +{len(self.services_added)}")
        if self.services_removed:
            lines.append(f"  Services: -{len(self.services_removed)}")
        if self.services_modified:
            lines.append(f"  Services: ~{len(self.services_modified)}")

        if self.experiences_added:
            lines.append(f"  Experiences: +{len(self.experiences_added)}")
        if self.experiences_removed:
            lines.append(f"  Experiences: -{len(self.experiences_removed)}")
        if self.experiences_modified:
            lines.append(f"  Experiences: ~{len(self.experiences_modified)}")

        return "\n".join(lines) if lines else "  No changes detected"


def detect_changes(
    prev_state: BuildState,
    current_appspec: ir.AppSpec,
    current_dsl_hashes: dict[str, str],
) -> ChangeSet:
    """
    Detect changes between previous build and current AppSpec.

    Args:
        prev_state: Previous build state
        current_appspec: Current AppSpec
        current_dsl_hashes: Current DSL file hashes

    Returns:
        ChangeSet describing differences
    """
    # Initialize change sets
    changeset = ChangeSet(
        dsl_files_added=set(),
        dsl_files_removed=set(),
        dsl_files_modified=set(),
        entities_added=set(),
        entities_removed=set(),
        entities_modified=set(),
        surfaces_added=set(),
        surfaces_removed=set(),
        surfaces_modified=set(),
        services_added=set(),
        services_removed=set(),
        services_modified=set(),
        experiences_added=set(),
        experiences_removed=set(),
        experiences_modified=set(),
        app_modified=False,
    )

    # Detect DSL file changes
    prev_files = set(prev_state.dsl_file_hashes.keys())
    curr_files = set(current_dsl_hashes.keys())

    changeset.dsl_files_added = curr_files - prev_files
    changeset.dsl_files_removed = prev_files - curr_files

    for file_path in prev_files & curr_files:
        if prev_state.dsl_file_hashes[file_path] != current_dsl_hashes[file_path]:
            changeset.dsl_files_modified.add(file_path)

    # If no snapshot available, can't detect semantic changes
    if prev_state.appspec_snapshot is None:
        return changeset

    # Simplify current appspec for comparison
    current_snapshot = simplify_appspec(current_appspec)

    # Detect app changes
    prev_app = prev_state.appspec_snapshot.get("app", {})
    curr_app = current_snapshot.get("app", {})
    if prev_app != curr_app:
        changeset.app_modified = True

    # Detect entity changes
    prev_entities = set(prev_state.appspec_snapshot.get("entities", {}).keys())
    curr_entities = set(current_snapshot.get("entities", {}).keys())

    changeset.entities_added = curr_entities - prev_entities
    changeset.entities_removed = prev_entities - curr_entities

    for ent_id in prev_entities & curr_entities:
        prev_ent = prev_state.appspec_snapshot["entities"][ent_id]
        curr_ent = current_snapshot["entities"][ent_id]
        if prev_ent != curr_ent:
            changeset.entities_modified.add(ent_id)

    # Detect surface changes
    prev_surfaces = set(prev_state.appspec_snapshot.get("surfaces", {}).keys())
    curr_surfaces = set(current_snapshot.get("surfaces", {}).keys())

    changeset.surfaces_added = curr_surfaces - prev_surfaces
    changeset.surfaces_removed = prev_surfaces - curr_surfaces

    for surf_id in prev_surfaces & curr_surfaces:
        prev_surf = prev_state.appspec_snapshot["surfaces"][surf_id]
        curr_surf = current_snapshot["surfaces"][surf_id]
        if prev_surf != curr_surf:
            changeset.surfaces_modified.add(surf_id)

    # Detect service changes
    prev_services = set(prev_state.appspec_snapshot.get("services", {}).keys())
    curr_services = set(current_snapshot.get("services", {}).keys())

    changeset.services_added = curr_services - prev_services
    changeset.services_removed = prev_services - curr_services

    for svc_id in prev_services & curr_services:
        prev_svc = prev_state.appspec_snapshot["services"][svc_id]
        curr_svc = current_snapshot["services"][svc_id]
        if prev_svc != curr_svc:
            changeset.services_modified.add(svc_id)

    # Detect experience changes
    prev_experiences = set(prev_state.appspec_snapshot.get("experiences", {}).keys())
    curr_experiences = set(current_snapshot.get("experiences", {}).keys())

    changeset.experiences_added = curr_experiences - prev_experiences
    changeset.experiences_removed = prev_experiences - curr_experiences

    for exp_id in prev_experiences & curr_experiences:
        prev_exp = prev_state.appspec_snapshot["experiences"][exp_id]
        curr_exp = current_snapshot["experiences"][exp_id]
        if prev_exp != curr_exp:
            changeset.experiences_modified.add(exp_id)

    return changeset


__all__ = [
    "ChangeSet",
    "detect_changes",
]
