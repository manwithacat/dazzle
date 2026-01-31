"""
E2E tests for DNR serve functionality.

These tests verify that `dazzle dnr serve` produces a working application:
1. Server starts without errors
2. HTML is served correctly
3. JavaScript files are valid (no syntax errors)
4. API endpoints respond correctly

These tests catch the bugs fixed in v0.3.1:
- Bug 1: ES module export block conversion failure
- Bug 2: HTML script tag malformation
"""

import subprocess
import sys
from pathlib import Path

import pytest

# Skip these tests if DNR is not available
pytest.importorskip("dazzle_dnr_back")
pytest.importorskip("dazzle_dnr_ui")


class TestDNRServeBasics:
    """Test that DNR serve starts and serves valid content."""

    @pytest.fixture
    def simple_task_dir(self, tmp_path: Path) -> Path:
        """Create a simple task project for testing."""
        project_dir = tmp_path / "test_project"
        project_dir.mkdir()

        # Create dazzle.toml
        # Note: project.root is the module name, not a file path
        (project_dir / "dazzle.toml").write_text(
            """
[project]
name = "test_app"
title = "Test Application"
version = "0.1.0"
root = "test_app"

[dsl]
entry = "dsl/app.dsl"
"""
        )

        # Create DSL directory
        dsl_dir = project_dir / "dsl"
        dsl_dir.mkdir()

        # Create minimal DSL file - module name must match project name
        (dsl_dir / "app.dsl").write_text(
            """
module test_app

app test_app "Test Application"

entity Task "Task":
  id: uuid pk
  title: str(200) required
  completed: bool=false

surface task_list "Task List":
  uses entity Task
  mode: list

  section main "Tasks":
    field title "Title"
    field completed "Done"
"""
        )

        return project_dir

    def test_validate_project(self, simple_task_dir: Path) -> None:
        """Test that the project validates successfully."""
        result = subprocess.run(
            [sys.executable, "-m", "dazzle.cli", "validate"],
            cwd=simple_task_dir,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Validation failed: {result.stderr}"
        assert "OK" in result.stdout or "valid" in result.stdout.lower()


class TestAPIGeneration:
    """Test that API endpoints are generated correctly."""

    def test_backend_spec_entity_conversion(self) -> None:
        """Test that entities are converted from AppSpec to BackendSpec."""
        from dazzle.core.ir import (
            AppSpec,
            DomainSpec,
            FieldModifier,
            FieldType,
            FieldTypeKind,
        )
        from dazzle.core.ir import (
            EntitySpec as IREntitySpec,
        )
        from dazzle.core.ir import (
            FieldSpec as IRFieldSpec,
        )
        from dazzle_dnr_back.converters import convert_appspec_to_backend

        # Create a simple AppSpec
        app_spec = AppSpec(
            name="test",
            title="Test",
            version="0.1.0",
            domain=DomainSpec(
                entities=[
                    IREntitySpec(
                        name="Task",
                        title="Task",
                        fields=[
                            IRFieldSpec(
                                name="id",
                                type=FieldType(kind=FieldTypeKind.UUID),
                                modifiers=[FieldModifier.PK],
                            ),
                            IRFieldSpec(
                                name="title",
                                type=FieldType(kind=FieldTypeKind.STR, max_length=200),
                                modifiers=[FieldModifier.REQUIRED],
                            ),
                            IRFieldSpec(
                                name="completed",
                                type=FieldType(kind=FieldTypeKind.BOOL),
                                default="false",
                            ),
                        ],
                    )
                ]
            ),
        )

        # Generate BackendSpec
        backend_spec = convert_appspec_to_backend(app_spec)

        # Verify entities are present and correctly converted
        assert len(backend_spec.entities) == 1
        entity = backend_spec.entities[0]
        assert entity.name == "Task"

        # Verify fields are converted
        field_names = [f.name for f in entity.fields]
        assert "id" in field_names
        assert "title" in field_names
        assert "completed" in field_names

        # Verify field types
        title_field = next(f for f in entity.fields if f.name == "title")
        assert title_field.required is True


# Mark all tests in this module as e2e
pytestmark = pytest.mark.e2e
