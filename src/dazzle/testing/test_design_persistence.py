"""
Test design persistence layer for DAZZLE UX Coverage Testing.

Handles reading and writing test design specifications to the dsl/tests/
directory. Test designs are stored as JSON for easy inspection and editing.

Storage locations:
- Primary: dsl/tests/designs.json (version-controlled, alongside DSL)
- Runtime: .dazzle/test_designs/designs.json (for generated designs)
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from dazzle.core.ir.test_design import TestDesignSpec, TestDesignStatus


def _utcnow() -> datetime:
    """Return current UTC datetime (timezone-aware)."""
    return datetime.now(UTC)


# Storage paths
DSL_TESTS_DIR = "dsl/tests"
RUNTIME_TESTS_DIR = ".dazzle/test_designs"
DESIGNS_FILE = "designs.json"


class TestDesignsContainer(BaseModel):
    """Container for persisting test designs."""

    version: str = "1.0"
    project_name: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    designs: list[TestDesignSpec] = Field(default_factory=list)


def get_dsl_tests_dir(project_root: Path) -> Path:
    """Get the dsl/tests/ directory path (version-controlled location).

    Args:
        project_root: Root directory of the DAZZLE project.

    Returns:
        Path to the DSL tests directory.
    """
    return project_root / DSL_TESTS_DIR


def get_runtime_tests_dir(project_root: Path) -> Path:
    """Get the .dazzle/test_designs/ directory path (runtime location).

    Args:
        project_root: Root directory of the DAZZLE project.

    Returns:
        Path to the runtime test designs directory.
    """
    return project_root / RUNTIME_TESTS_DIR


def _find_designs_file(project_root: Path) -> Path | None:
    """Find the designs.json file, checking dsl/tests/ then runtime.

    Args:
        project_root: Root directory of the DAZZLE project.

    Returns:
        Path to existing designs.json, or None if not found.
    """
    # Check dsl/tests/ first (version-controlled)
    dsl_file = get_dsl_tests_dir(project_root) / DESIGNS_FILE
    if dsl_file.exists():
        return dsl_file

    # Fall back to runtime location
    runtime_file = get_runtime_tests_dir(project_root) / DESIGNS_FILE
    if runtime_file.exists():
        return runtime_file

    return None


def load_test_designs(project_root: Path) -> list[TestDesignSpec]:
    """Load all test designs from dsl/tests/ or runtime directory.

    Checks the version-controlled location (dsl/tests/) first, then falls
    back to the runtime location (.dazzle/test_designs/).

    Args:
        project_root: Root directory of the DAZZLE project.

    Returns:
        List of test design specifications. Returns empty list if file doesn't exist.
    """
    designs_file = _find_designs_file(project_root)

    if designs_file is None:
        return []

    try:
        content = designs_file.read_text(encoding="utf-8")
        data = json.loads(content)
        container = TestDesignsContainer.model_validate(data)
        return list(container.designs)
    except (json.JSONDecodeError, ValueError) as e:
        import logging

        logging.getLogger(__name__).warning(f"Failed to load test designs from {designs_file}: {e}")
        return []


def save_test_designs(
    project_root: Path,
    designs: list[TestDesignSpec],
    *,
    project_name: str | None = None,
    to_dsl: bool = True,
) -> Path:
    """Save test designs to storage.

    Args:
        project_root: Root directory of the DAZZLE project.
        designs: List of test design specifications to save.
        project_name: Optional project name for metadata.
        to_dsl: If True, save to dsl/tests/ (version-controlled).
            If False, save to .dazzle/test_designs/ (runtime).

    Returns:
        Path to the saved designs.json file.
    """
    if to_dsl:
        tests_dir = get_dsl_tests_dir(project_root)
    else:
        tests_dir = get_runtime_tests_dir(project_root)

    tests_dir.mkdir(parents=True, exist_ok=True)

    container = TestDesignsContainer(
        project_name=project_name,
        designs=designs,
        updated_at=datetime.now(UTC),
    )

    designs_file = tests_dir / DESIGNS_FILE
    designs_file.write_text(
        json.dumps(
            container.model_dump(mode="json"),
            indent=2,
            ensure_ascii=False,
            default=str,  # Handle datetime serialization
        ),
        encoding="utf-8",
    )

    return designs_file


def _extract_td_number(test_id: str) -> int | None:
    """Extract the numeric part from a TD-XXX format ID."""
    if test_id.startswith("TD-"):
        try:
            return int(test_id[3:])
        except ValueError:
            pass
    return None


def _get_max_td_number(test_ids: set[str]) -> int:
    """Get the maximum TD number from a set of test IDs."""
    max_num = 0
    for test_id in test_ids:
        num = _extract_td_number(test_id)
        if num is not None:
            max_num = max(max_num, num)
    return max_num


def get_next_test_design_id(project_root: Path) -> str:
    """Generate the next test design ID (TD-001, TD-002, etc.).

    Args:
        project_root: Root directory of the DAZZLE project.

    Returns:
        Next test design ID in format TD-XXX.
    """
    existing = load_test_designs(project_root)

    if not existing:
        return "TD-001"

    max_num = _get_max_td_number({d.test_id for d in existing})
    return f"TD-{max_num + 1:03d}"


def get_test_designs_by_status(
    project_root: Path,
    status: TestDesignStatus | None = None,
) -> list[TestDesignSpec]:
    """Get test designs filtered by status.

    Args:
        project_root: Root directory of the DAZZLE project.
        status: Filter by this status. None returns all designs.

    Returns:
        List of matching test designs.
    """
    designs = load_test_designs(project_root)

    if status is None:
        return designs

    return [d for d in designs if d.status == status]


def update_test_design_status(
    project_root: Path,
    test_id: str,
    new_status: TestDesignStatus,
    *,
    notes: str | None = None,
    implementation_path: str | None = None,
) -> TestDesignSpec | None:
    """Update the status of a test design.

    Args:
        project_root: Root directory of the DAZZLE project.
        test_id: ID of the test design to update.
        new_status: New status to set.
        notes: Optional notes to add.
        implementation_path: Path to implementation (if IMPLEMENTED).

    Returns:
        Updated test design spec, or None if not found.
    """
    designs = load_test_designs(project_root)

    updated_designs = []
    updated_design = None

    for design in designs:
        if design.test_id == test_id:
            # Create updated design
            updated_design = TestDesignSpec(
                test_id=design.test_id,
                title=design.title,
                description=design.description,
                persona=design.persona,
                scenario=design.scenario,
                trigger=design.trigger,
                steps=design.steps,
                expected_outcomes=design.expected_outcomes,
                entities=design.entities,
                surfaces=design.surfaces,
                tags=design.tags,
                status=new_status,
                implementation_path=implementation_path or design.implementation_path,
                notes=notes if notes is not None else design.notes,
                prompt_version=design.prompt_version,
                created_at=design.created_at,
                updated_at=datetime.now(UTC),
            )
            updated_designs.append(updated_design)
        else:
            updated_designs.append(design)

    if updated_design is not None:
        save_test_designs(project_root, updated_designs)

    return updated_design


class AddTestDesignsResult(BaseModel):
    """Result of adding test designs, including any ID remappings."""

    all_designs: list[TestDesignSpec]
    added_count: int
    remapped_ids: dict[str, str] = Field(default_factory=dict)  # old_id -> new_id


def add_test_designs(
    project_root: Path,
    new_designs: list[TestDesignSpec],
    *,
    overwrite: bool = False,
    to_dsl: bool = True,
) -> AddTestDesignsResult:
    """Add new test designs, optionally overwriting existing ones.

    When overwrite=False and a design has a colliding ID, a new unique ID
    is automatically assigned and the remapping is reported in the result.

    Args:
        project_root: Root directory of the DAZZLE project.
        new_designs: Test designs to add.
        overwrite: If True, replace designs with matching IDs.
            If False, auto-assign new IDs for collisions.
        to_dsl: If True, save to dsl/tests/.
            If False, save to .dazzle/test_designs/.

    Returns:
        AddTestDesignsResult with all designs and any ID remappings.
    """
    existing = load_test_designs(project_root)
    existing_ids = {d.test_id for d in existing}
    remapped_ids: dict[str, str] = {}
    added_count = 0

    if overwrite:
        new_ids = {d.test_id for d in new_designs}
        existing = [d for d in existing if d.test_id not in new_ids]
        existing.extend(new_designs)
        added_count = len(new_designs)
    else:
        # Track all IDs (existing + newly added) to avoid collisions
        all_ids = existing_ids.copy()

        for design in new_designs:
            if design.test_id in all_ids:
                # Collision - assign a new unique ID
                old_id = design.test_id
                next_num = _get_max_td_number(all_ids) + 1
                new_id = f"TD-{next_num:03d}"
                design.test_id = new_id
                remapped_ids[old_id] = new_id

            existing.append(design)
            all_ids.add(design.test_id)
            added_count += 1

    save_test_designs(project_root, existing, to_dsl=to_dsl)
    return AddTestDesignsResult(
        all_designs=existing,
        added_count=added_count,
        remapped_ids=remapped_ids,
    )


def get_test_designs_by_persona(
    project_root: Path,
    persona: str,
) -> list[TestDesignSpec]:
    """Get test designs for a specific persona.

    Args:
        project_root: Root directory of the DAZZLE project.
        persona: Persona name to filter by.

    Returns:
        List of test designs for this persona.
    """
    designs = load_test_designs(project_root)
    return [d for d in designs if d.persona == persona]


def get_test_designs_by_entity(
    project_root: Path,
    entity: str,
) -> list[TestDesignSpec]:
    """Get test designs that test a specific entity.

    Args:
        project_root: Root directory of the DAZZLE project.
        entity: Entity name to filter by.

    Returns:
        List of test designs involving this entity.
    """
    designs = load_test_designs(project_root)
    return [d for d in designs if entity in d.entities]


def delete_test_design(
    project_root: Path,
    test_id: str,
) -> bool:
    """Delete a test design by ID.

    Args:
        project_root: Root directory of the DAZZLE project.
        test_id: ID of the test design to delete.

    Returns:
        True if deleted, False if not found.
    """
    designs = load_test_designs(project_root)
    original_count = len(designs)

    designs = [d for d in designs if d.test_id != test_id]

    if len(designs) < original_count:
        save_test_designs(project_root, designs)
        return True

    return False
