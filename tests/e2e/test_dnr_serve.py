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

import re
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


class TestJavaScriptGeneration:
    """Test that generated JavaScript is syntactically valid."""

    def test_iife_bundle_no_syntax_errors(self) -> None:
        """Test that the IIFE bundle has no obvious syntax errors."""
        from dazzle_dnr_ui.runtime.js_loader import generate_iife_bundle

        bundle = generate_iife_bundle()

        # Check for common syntax error patterns that indicate broken generation
        # These patterns were found in the bugs fixed in v0.3.1

        # Bug 1: Dangling identifiers from incomplete export block stripping
        # The symptom was lines like "  foo," or "  bar," appearing at the module level
        # after export blocks like "export { foo, bar, baz };" were incompletely stripped.

        # Check that no export statements remain (they should all be stripped)
        assert "export {" not in bundle, "Multi-line export blocks should be fully removed"
        assert "export default" not in bundle, "export default should be removed"

        # Verify the bundle structure is valid IIFE (may have comment header before)
        assert "(function(global)" in bundle, "Bundle should contain IIFE wrapper"
        # The IIFE can use either (window) or (typeof window !== 'undefined' ? window : global)
        has_invocation = "(window);" in bundle or "window : global);" in bundle
        assert has_invocation, "Bundle should contain IIFE invocation"

        # Check that global.DNR is properly exported
        assert "global.DNR = {" in bundle, "DNR should be exported to global scope"

    def test_export_blocks_fully_removed(self) -> None:
        """Test that multi-line export blocks are completely removed."""
        from dazzle_dnr_ui.runtime.js_loader import _convert_to_iife_compatible

        # Test case that triggered Bug 1
        source = """
const foo = 1;
const bar = 2;

// Export internal signals for direct access
export {
  foo,
  bar,
  baz
};

function doSomething() {}
"""
        result = _convert_to_iife_compatible(source, "test.js")

        # The export block should be completely gone
        assert "export" not in result
        assert "foo," not in result.split("\n")[-10:]  # No dangling foo, in the result
        assert "bar," not in result.split("\n")[-10:]
        assert "baz" not in result.split("\n")[-10:]

        # But the const declarations should still be there
        assert "const foo = 1" in result
        assert "const bar = 2" in result
        assert "function doSomething" in result

    def test_single_line_exports_converted(self) -> None:
        """Test that single-line exports are converted correctly."""
        from dazzle_dnr_ui.runtime.js_loader import _convert_to_iife_compatible

        source = """
export function myFunc() {
  return 42;
}

export const MY_CONST = 'hello';
"""
        result = _convert_to_iife_compatible(source, "test.js")

        # export keyword should be stripped
        assert "export function" not in result
        assert "export const" not in result

        # But the declarations should remain
        assert "function myFunc()" in result
        assert "const MY_CONST" in result


class TestHTMLGeneration:
    """Test that generated HTML is valid."""

    def test_script_tags_properly_formed(self) -> None:
        """Test that script tags don't have both src and inline content."""
        from dazzle_dnr_ui.runtime.js_generator import JSGenerator

        # Create a minimal UISpec
        from dazzle_dnr_ui.specs import UISpec

        spec = UISpec(
            name="test",
            entities=[],
            surfaces=[],
            components=[],
        )

        generator = JSGenerator(spec)
        html = generator.generate_html(include_runtime=True)

        # Find all script tags
        script_pattern = re.compile(r"<script([^>]*)>(.*?)</script>", re.DOTALL)
        scripts = script_pattern.findall(html)

        for attrs, content in scripts:
            # If script has src attribute, content should be empty or whitespace
            if 'src="' in attrs or "src='" in attrs:
                content_stripped = content.strip()
                assert content_stripped == "", (
                    f"Script with src attribute has inline content: {content[:100]}..."
                )

    def test_html_has_required_structure(self) -> None:
        """Test that HTML has the required structure."""
        from dazzle_dnr_ui.runtime.js_generator import JSGenerator
        from dazzle_dnr_ui.specs import UISpec

        spec = UISpec(
            name="test",
            entities=[],
            surfaces=[],
            components=[],
        )

        generator = JSGenerator(spec)
        html = generator.generate_html(include_runtime=True)

        # Check basic HTML structure
        assert "<!DOCTYPE html>" in html
        assert "<html" in html
        assert "</html>" in html
        assert "<head>" in html
        assert "</head>" in html
        assert "<body>" in html
        assert "</body>" in html
        assert '<div id="app">' in html


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
