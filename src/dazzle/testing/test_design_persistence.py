"""
Test design persistence layer for DAZZLE UX Coverage Testing.

Handles reading and writing test design specifications to the dsl/tests/
directory. Test designs are stored as JSON for easy inspection and editing.

Storage locations:
- Primary: dsl/tests/designs.json (version-controlled, alongside DSL)
- Runtime: .dazzle/test_designs/designs.json (for generated designs)
"""

from __future__ import annotations  # required: forward reference

import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from dazzle.core.clock import utcnow
from dazzle.core.ir.test_design import TestDesignSpec

# Storage paths
DSL_TESTS_DIR = "dsl/tests"
RUNTIME_TESTS_DIR = ".dazzle/test_designs"
DESIGNS_FILE = "designs.json"


class TestDesignsContainer(BaseModel):
    """Container for persisting test designs."""

    version: str = "1.0"
    project_name: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
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

        logging.getLogger(__name__).warning(
            "Failed to load test designs from %s: %s", designs_file, e
        )

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
