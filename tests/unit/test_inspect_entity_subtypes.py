"""#1217 Phase 3e.v — MCP inspect_entity returns subtype info."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def project_root_with_appspec(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build a temporary project with subtype DSL.

    inspect_entity takes project_root and calls load_project_appspec; that
    function discovers DSL files from the project's dazzle.toml. The test
    needs to provide a minimal valid project layout."""
    project = tmp_path_factory.mktemp("subtype_inspect")
    (project / "dazzle.toml").write_text(
        """\
[project]
name = "test"
title = "Test"
root = "test"
version = "0.1.0"

[modules]
paths = ["./dsl"]

[stack]
name = "dnr"

[auth]
enabled = false
"""
    )
    (project / "dsl").mkdir()
    (project / "dsl" / "app.dsl").write_text(
        """\
module test
app a "A"

entity Asset "Asset":
  id: uuid pk
  acquired_at: date required
  location: str(120)

entity Vehicle "Vehicle":
  subtype_of: Asset
  wheels: int required
  vin: str(17) required

entity Building "Building":
  subtype_of: Asset
  floors: int required
"""
    )
    return project


class TestInspectEntityReturnsSubtypeInfo:
    def test_base_inspect_lists_children_and_kind(self, project_root_with_appspec: Path) -> None:
        from dazzle.mcp.server.handlers.dsl.inspect import inspect_entity

        result = json.loads(inspect_entity(project_root_with_appspec, {"entity_name": "Asset"}))
        # subtype_children populated, sorted alphabetically
        assert result["subtype_children"] == ["Building", "Vehicle"]
        # subtype_of is None on the base
        assert result["subtype_of"] is None
        # Synthesised `kind` field appears in fields list
        field_names = [f["name"] for f in result["fields"]]
        assert "kind" in field_names

    def test_child_inspect_shows_subtype_of_and_inherited_fields(
        self, project_root_with_appspec: Path
    ) -> None:
        from dazzle.mcp.server.handlers.dsl.inspect import inspect_entity

        result = json.loads(inspect_entity(project_root_with_appspec, {"entity_name": "Vehicle"}))
        assert result["subtype_of"] == "Asset"
        assert result["subtype_children"] == []
        # Child's own fields present and NOT marked inherited
        wheels = next(f for f in result["fields"] if f["name"] == "wheels")
        assert wheels.get("inherited_from") is None
        # Inherited fields from base appear with inherited_from marker
        inherited = [f for f in result["fields"] if f.get("inherited_from") == "Asset"]
        inherited_names = {f["name"] for f in inherited}
        assert "acquired_at" in inherited_names
        assert "location" in inherited_names
        # The synthesised `kind` field is inherited from the base too
        assert "kind" in inherited_names

    def test_non_subtype_entity_has_clean_subtype_fields(
        self, project_root_with_appspec: Path
    ) -> None:
        from dazzle.mcp.server.handlers.dsl.inspect import inspect_entity

        # Building is a child of Asset but has no children of its own — pins
        # that subtype_children is [] for a leaf child.
        result = json.loads(inspect_entity(project_root_with_appspec, {"entity_name": "Building"}))
        assert result["subtype_of"] == "Asset"
        assert result["subtype_children"] == []
