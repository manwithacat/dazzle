"""Tests for the test_design MCP handlers."""

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tests.unit.mcp.conftest import install_handlers_common_real


def _import_test_design():
    """Import test_design handlers directly to avoid MCP package init issues.

    The dazzle.mcp.__init__.py imports mcp.server which may not be installed
    in test environments. We need to import the handlers module directly.
    """
    # Create mock modules to satisfy imports
    mock_state = MagicMock()
    sys.modules["dazzle.mcp.server.handlers"] = MagicMock(pytest_plugins=[])

    install_handlers_common_real()
    sys.modules["dazzle.mcp.server.state"] = mock_state

    handlers_dir = (
        Path(__file__).parent.parent.parent.parent
        / "src"
        / "dazzle"
        / "mcp"
        / "server"
        / "handlers"
    )

    # Pre-load the serializers module so test_design submodules' `from ..serializers import ...` resolves
    ser_path = handlers_dir / "serializers.py"
    ser_spec = importlib.util.spec_from_file_location(
        "dazzle.mcp.server.handlers.serializers",
        ser_path,
    )
    ser_mod = importlib.util.module_from_spec(ser_spec)
    sys.modules["dazzle.mcp.server.handlers.serializers"] = ser_mod
    ser_spec.loader.exec_module(ser_mod)

    # Attach serializers to the handlers mock so relative import resolves
    sys.modules["dazzle.mcp.server.handlers"].serializers = ser_mod

    pkg_dir = handlers_dir / "test_design"

    # Import the submodule first so the package __init__ can re-export it
    for submod_name in ("gaps",):
        submod_path = pkg_dir / f"{submod_name}.py"
        sub_spec = importlib.util.spec_from_file_location(
            f"dazzle.mcp.server.handlers.test_design.{submod_name}",
            submod_path,
        )
        sub_module = importlib.util.module_from_spec(sub_spec)
        sys.modules[f"dazzle.mcp.server.handlers.test_design.{submod_name}"] = sub_module
        sub_spec.loader.exec_module(sub_module)

    # Now import the package __init__
    init_path = pkg_dir / "__init__.py"
    spec = importlib.util.spec_from_file_location(
        "dazzle.mcp.server.handlers.test_design",
        init_path,
        submodule_search_locations=[str(pkg_dir)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["dazzle.mcp.server.handlers.test_design"] = module

    spec.loader.exec_module(module)
    return module


# Import the module once at module load time
_td = _import_test_design()

# Get references to the functions we need
get_test_gaps_handler = _td.get_test_gaps_handler

# Pure predicate from the gaps submodule (loaded via the isolation dance above).
_state_transition_flow_covered = sys.modules[
    "dazzle.mcp.server.handlers.test_design.gaps"
]._state_transition_flow_covered


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_project(tmp_path):
    """Create a temporary project with minimal DSL structure."""
    project_dir = tmp_path / "test_project"
    project_dir.mkdir()

    # Create dazzle.toml manifest
    manifest = project_dir / "dazzle.toml"
    manifest.write_text(
        """
[project]
name = "test_project"
version = "0.1.0"
root = "test_project"

[modules]
paths = ["./dsl"]
"""
    )

    # Create dsl directory
    dsl_dir = project_dir / "dsl"
    dsl_dir.mkdir()

    # Create main.dsl with persona
    main_dsl = dsl_dir / "main.dsl"
    main_dsl.write_text(
        """
module test_project
app test_project "Test Project"

persona admin "Admin":
    description: "System administrator"
    goals:
        - "Manage all users"
        - "Configure system settings"

entity Task "Task":
    id: uuid pk
    title: str(200) required
    status: enum[pending,in_progress,completed]=pending
"""
    )

    # Create .dazzle directory
    dazzle_dir = project_dir / ".dazzle"
    dazzle_dir.mkdir()

    # Create test_designs directory
    test_designs_dir = dazzle_dir / "test_designs"
    test_designs_dir.mkdir()

    return project_dir


_BARE = "CohortAssessment_transition_marking_to_marked"


# Regression for #1335: the gap check must accept the `_as_{persona}` suffix that
# generate_state_machine_flows emits for role-guarded transitions.
@pytest.mark.parametrize(
    ("flow_ids", "covered"),
    [
        # A role-guarded transition emits only `_as_{persona}` flows — no bare id.
        pytest.param(
            {f"{_BARE}_as_teacher", f"{_BARE}_as_head_of_dept"},
            True,
            id="role-guarded-covered-by-suffixed-flow-1335",
        ),
        pytest.param({_BARE}, True, id="unguarded-covered-by-bare-flow-1335"),
        # Only a no-persona skip stub exists — genuinely untested by any persona.
        pytest.param({f"{_BARE}_skipped_no_persona"}, False, id="skip-stub-is-a-gap-1335"),
        pytest.param(set(), False, id="no-flows-is-a-gap-1335"),
        # A different transition that merely shares a string prefix must not count.
        pytest.param(
            {f"{_BARE}_late_as_teacher"}, False, id="no-false-match-on-shared-prefix-1335"
        ),
    ],
)
def test_state_transition_flow_covered(flow_ids: set[str], covered: bool) -> None:
    assert _state_transition_flow_covered(_BARE, flow_ids) is covered


def test_get_test_gaps_analyzes_project(temp_project) -> None:
    data = json.loads(get_test_gaps_handler(temp_project, {}))
    assert data["project"] == "test_project"
    gaps = {(g["category"], g["target"]): g["severity"] for g in data["gaps"]}
    # Untested app entity and the persona with goals but no test designs are gaps
    # (framework-linked entities appear too; their exact set is not pinned here).
    assert gaps[("untested_entity", "Task")] == "medium"
    assert gaps[("untested_persona_goal", "admin")] == "high"
    assert data["gap_count"] == len(data["gaps"])


def test_get_test_gaps_missing_project(tmp_path) -> None:
    assert "error" in json.loads(get_test_gaps_handler(tmp_path, {}))
