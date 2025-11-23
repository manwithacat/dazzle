"""Golden-master (snapshot) tests for DSL → IR stability."""

from pathlib import Path

import pytest

from dazzle.core.linker import build_appspec
from dazzle.core.parser import parse_modules


@pytest.fixture
def simple_test_dsl_path() -> Path:
    """Path to simple_test.dsl fixture."""
    return Path(__file__).parent.parent / "fixtures" / "dsl" / "simple_test.dsl"


def test_simple_dsl_to_ir_snapshot(simple_test_dsl_path: Path, snapshot):
    """Test that simple_test.dsl produces consistent IR (snapshot test)."""
    # Parse DSL to IR
    modules = parse_modules([simple_test_dsl_path])
    appspec = build_appspec(modules, "test.simple")

    # Convert to dict for snapshot comparison
    appspec_dict = appspec.model_dump(mode="python")

    # Remove metadata that might vary (timestamps, etc.)
    if "metadata" in appspec_dict:
        appspec_dict.pop("metadata")

    # Compare against snapshot
    assert appspec_dict == snapshot


def test_simple_dsl_has_expected_structure(simple_test_dsl_path: Path):
    """Test that simple_test.dsl has expected structure (explicit checks)."""
    modules = parse_modules([simple_test_dsl_path])
    appspec = build_appspec(modules, "test.simple")

    # Check app metadata
    assert appspec.name == "simple_test"
    assert appspec.title == "Simple Test App"
    assert appspec.version == "0.1.0"

    # Check entities
    assert len(appspec.domain.entities) == 1
    task_entity = appspec.domain.entities[0]
    assert task_entity.name == "Task"
    assert task_entity.title == "Task"
    assert len(task_entity.fields) == 5  # id, title, description, status, created_at

    # Check surfaces
    assert len(appspec.surfaces) == 4
    surface_names = {s.name for s in appspec.surfaces}
    assert surface_names == {"task_list", "task_detail", "task_create", "task_edit"}

    # Check surface modes
    surface_modes = {s.name: s.mode for s in appspec.surfaces}
    assert surface_modes["task_list"] == "list"
    assert surface_modes["task_detail"] == "view"
    assert surface_modes["task_create"] == "create"
    assert surface_modes["task_edit"] == "edit"


def test_dsl_parsing_is_deterministic(simple_test_dsl_path: Path):
    """Test that parsing the same DSL twice produces identical IR."""
    # Parse twice
    modules1 = parse_modules([simple_test_dsl_path])
    appspec1 = build_appspec(modules1, "test.simple")

    modules2 = parse_modules([simple_test_dsl_path])
    appspec2 = build_appspec(modules2, "test.simple")

    # Should be identical (excluding metadata)
    dict1 = appspec1.model_dump(mode="python")
    dict2 = appspec2.model_dump(mode="python")

    if "metadata" in dict1:
        dict1.pop("metadata")
    if "metadata" in dict2:
        dict2.pop("metadata")

    assert dict1 == dict2
