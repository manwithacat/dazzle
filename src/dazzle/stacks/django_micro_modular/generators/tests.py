"""
Test generator for Django Micro backend.

Generates comprehensive Django test suites for models, views, forms, and admin.
"""

from pathlib import Path
from typing import Any

from ....core import ir
from ...base import Generator, GeneratorResult


class TestGenerator(Generator):
    """
    Generate Django tests from entities and surfaces.

    Creates comprehensive test suite with:
    - Model tests (validation, constraints, relationships)
    - View tests (CRUD operations, auto-population)
    - Form tests (validation, required fields)
    - Admin tests (pages load, configurations)
    """

    def __init__(self, spec: ir.AppSpec, output_dir: Path, app_name: str = "app"):
        """
        Initialize test generator.

        Args:
            spec: Application specification
            output_dir: Root output directory
            app_name: Name of the Django app
        """
        super().__init__(spec, output_dir)
        self.app_name = app_name

    def generate(self) -> GeneratorResult:
        """Generate all test files."""
        result = GeneratorResult()

        # Create tests directory
        tests_dir = self.output_dir / self.app_name / "tests"
        tests_dir.mkdir(parents=True, exist_ok=True)

        # Generate __init__.py
        init_path = tests_dir / "__init__.py"
        self._write_file(init_path, "# Test package\n")
        result.add_file(init_path)

        # Generate model tests
        model_tests = self._generate_model_tests()
        model_tests_path = tests_dir / "test_models.py"
        self._write_file(model_tests_path, model_tests)
        result.add_file(model_tests_path)

        # Generate view tests
        view_tests = self._generate_view_tests()
        view_tests_path = tests_dir / "test_views.py"
        self._write_file(view_tests_path, view_tests)
        result.add_file(view_tests_path)

        # Generate form tests
        form_tests = self._generate_form_tests()
        form_tests_path = tests_dir / "test_forms.py"
        self._write_file(form_tests_path, form_tests)
        result.add_file(form_tests_path)

        # Generate admin tests
        admin_tests = self._generate_admin_tests()
        admin_tests_path = tests_dir / "test_admin.py"
        self._write_file(admin_tests_path, admin_tests)
        result.add_file(admin_tests_path)

        # Generate DSL tests (if any defined)
        if self.spec.tests:
            dsl_tests = self._generate_dsl_tests()
            dsl_tests_path = tests_dir / "test_dsl.py"
            self._write_file(dsl_tests_path, dsl_tests)
            result.add_file(dsl_tests_path)

        return result

    # =========================================================================
    # Model Tests Generation
    # =========================================================================

    def _generate_model_tests(self) -> str:
        """Generate model tests for all entities."""
        lines = [
            '"""',
            "Model tests generated from DAZZLE DSL.",
            "",
            "Tests cover:",
            "- Basic model creation",
            "- Field validation and constraints",
            "- Foreign key relationships",
            "- Auto-generated fields",
            "- String representation",
            '"""',
            "from django.test import TestCase",
            "from django.core.exceptions import ValidationError",
            "from django.db import IntegrityError",
            "from django.db.models import ProtectedError",
            "",
            "from app.models import (",
        ]

        # Import models
        for entity in self.spec.domain.entities:
            lines.append(f"    {entity.name},")
        lines.append(")")
        lines.append("")
        lines.append("")

        # Generate test class for each entity
        for entity in self.spec.domain.entities:
            lines.append(self._generate_model_test_class(entity))
            lines.append("")
            lines.append("")

        return "\n".join(lines)

    def _generate_model_test_class(self, entity: ir.EntitySpec) -> str:
        """Generate test class for a single model."""
        lines = [
            f"class {entity.name}ModelTest(TestCase):",
            f'    """Tests for {entity.name} model."""',
            "",
        ]

        # Generate setUp if entity has foreign keys
        fk_fields = [f for f in entity.fields if f.type.kind == ir.FieldTypeKind.REF]
        if fk_fields:
            lines.extend(self._generate_setUp_for_entity(entity, fk_fields))
            lines.append("")

        # Test: Basic creation
        lines.extend(self._generate_test_create(entity))
        lines.append("")

        # Test: Required fields
        for field in entity.fields:
            if (
                field.is_required
                and not field.is_primary_key
                and field.type.kind != ir.FieldTypeKind.REF
            ):
                lines.extend(self._generate_test_required_field(entity, field))
                lines.append("")

        # Test: Unique constraints
        for field in entity.fields:
            if field.is_unique and not field.is_primary_key:
                lines.extend(self._generate_test_unique_field(entity, field))
                lines.append("")

        # Test: Max length
        for field in entity.fields:
            if field.type.kind == ir.FieldTypeKind.STR and field.type.max_length:
                lines.extend(self._generate_test_max_length(entity, field))
                lines.append("")

        # Test: Foreign key relationships
        for field in fk_fields:
            lines.extend(self._generate_test_foreign_key(entity, field))
            lines.append("")

        # Test: String representation
        lines.extend(self._generate_test_str_method(entity))

        return "\n".join(lines)

    def _generate_setUp_for_entity(
        self, entity: ir.EntitySpec, fk_fields: list[ir.FieldSpec]
    ) -> list[str]:
        """Generate setUp method that creates required FK objects."""
        lines = [
            "    def setUp(self):",
            '        """Set up test data."""',
        ]

        # Create objects for each unique referenced entity
        referenced_entities = set()
        for fk_field in fk_fields:
            ref_entity_name = fk_field.type.ref_entity
            if ref_entity_name not in referenced_entities:
                referenced_entities.add(ref_entity_name)
                ref_entity = self._get_entity_by_name(ref_entity_name)
                if ref_entity:
                    create_params = self._get_minimal_create_params(ref_entity)
                    param_str = ",\n            ".join(f"{k}={v}" for k, v in create_params.items())
                    lines.append(
                        f"        self.{ref_entity_name.lower()} = {ref_entity_name}.objects.create("
                    )
                    lines.append(f"            {param_str}")
                    lines.append("        )")

        return lines

    def _generate_test_create(self, entity: ir.EntitySpec) -> list[str]:
        """Generate basic creation test."""
        lines = [
            f"    def test_create_{entity.name.lower()}(self):",
            f'        """Test creating a {entity.name} with required fields."""',
        ]

        # Build create params
        create_params = self._get_minimal_create_params(entity, use_self=True)
        param_str = ",\n            ".join(f"{k}={v}" for k, v in create_params.items())

        lines.append(f"        {entity.name.lower()} = {entity.name}.objects.create(")
        lines.append(f"            {param_str}")
        lines.append("        )")

        # Add assertions for key fields
        for field_name, value in list(create_params.items())[:3]:  # Check first 3 fields
            if "self." not in value:
                lines.append(
                    f"        self.assertEqual({entity.name.lower()}.{field_name}, {value})"
                )

        return lines

    def _generate_test_required_field(
        self, entity: ir.EntitySpec, field: ir.FieldSpec
    ) -> list[str]:
        """Generate test for required field constraint."""
        lines = [
            f"    def test_{field.name}_required(self):",
            f'        """Test {field.name} is required."""',
            "        with self.assertRaises(IntegrityError):",
        ]

        # Build create params excluding this field
        create_params = self._get_minimal_create_params(entity, use_self=True, exclude=[field.name])
        param_str = ",\n                ".join(f"{k}={v}" for k, v in create_params.items())

        lines.append(f"            {entity.name}.objects.create(")
        lines.append(f"                {param_str}")
        lines.append(f"                # {field.name} missing (required)")
        lines.append("            )")

        return lines

    def _generate_test_unique_field(self, entity: ir.EntitySpec, field: ir.FieldSpec) -> list[str]:
        """Generate test for unique field constraint."""
        field_value = self._get_sample_value_for_field(field)
        lines = [
            f"    def test_{field.name}_unique(self):",
            f'        """Test {field.name} unique constraint."""',
        ]

        # Create first object
        create_params = self._get_minimal_create_params(entity, use_self=True)
        create_params[field.name] = field_value
        param_str = ",\n            ".join(f"{k}={v}" for k, v in create_params.items())

        lines.append(f"        {entity.name}.objects.create(")
        lines.append(f"            {param_str}")
        lines.append("        )")

        # Try to create duplicate
        lines.append("        with self.assertRaises(IntegrityError):")
        lines.append(f"            {entity.name}.objects.create(")
        lines.append(f"                {param_str}")
        lines.append("            )")

        return lines

    def _generate_test_max_length(self, entity: ir.EntitySpec, field: ir.FieldSpec) -> list[str]:
        """Generate test for max_length constraint."""
        max_len = field.type.max_length
        lines = [
            f"    def test_{field.name}_max_length(self):",
            f'        """Test {field.name} max_length constraint ({max_len} chars)."""',
            f'        long_value = "x" * {max_len + 1}',
            "        with self.assertRaises(ValidationError):",
        ]

        create_params = self._get_minimal_create_params(entity, use_self=True)
        create_params[field.name] = "long_value"
        param_str = ",\n                ".join(f"{k}={v}" for k, v in create_params.items())

        lines.append(f"            {entity.name.lower()} = {entity.name}(")
        lines.append(f"                {param_str}")
        lines.append("            )")
        lines.append(f"            {entity.name.lower()}.full_clean()")

        return lines

    def _generate_test_foreign_key(self, entity: ir.EntitySpec, field: ir.FieldSpec) -> list[str]:
        """Generate test for foreign key relationship."""
        ref_entity = field.type.ref_entity
        lines = [
            f"    def test_{field.name}_foreign_key(self):",
            f'        """Test {field.name} foreign key relationship."""',
        ]

        # Create object with FK
        create_params = self._get_minimal_create_params(entity, use_self=True)
        param_str = ",\n            ".join(f"{k}={v}" for k, v in create_params.items())

        lines.append(f"        {entity.name.lower()} = {entity.name}.objects.create(")
        lines.append(f"            {param_str}")
        lines.append("        )")
        lines.append(
            f"        self.assertEqual({entity.name.lower()}.{field.name}, self.{ref_entity.lower()})"
        )

        # Test cascade behavior if required (PROTECT)
        if field.is_required:
            lines.append("")
            lines.append(f"        # Test PROTECT cascade - cannot delete referenced {ref_entity}")
            lines.append("        with self.assertRaises(ProtectedError):")
            lines.append(f"            self.{ref_entity.lower()}.delete()")

        return lines

    def _generate_test_str_method(self, entity: ir.EntitySpec) -> list[str]:
        """Generate test for __str__ method."""
        lines = [
            "    def test_str_method(self):",
            f'        """Test {entity.name} string representation."""',
        ]

        create_params = self._get_minimal_create_params(entity, use_self=True)
        param_str = ",\n            ".join(f"{k}={v}" for k, v in create_params.items())

        lines.append(f"        {entity.name.lower()} = {entity.name}.objects.create(")
        lines.append(f"            {param_str}")
        lines.append("        )")
        lines.append("        # __str__ should return a non-empty string")
        lines.append(f"        self.assertTrue(str({entity.name.lower()}))")
        lines.append(f"        self.assertIsInstance(str({entity.name.lower()}), str)")

        return lines

    # =========================================================================
    # View Tests Generation
    # =========================================================================

    def _generate_view_tests(self) -> str:
        """Generate view tests for all surfaces."""
        lines = [
            '"""',
            "View tests generated from DAZZLE DSL.",
            "",
            "Tests cover:",
            "- List views return 200",
            "- Detail views return 200/404",
            "- Create views (GET and POST)",
            "- Update views (GET and POST)",
            "- Auto-population logic",
            '"""',
            "from django.test import TestCase, Client",
            "from django.urls import reverse",
            "",
            "from app.models import (",
        ]

        # Import models
        for entity in self.spec.domain.entities:
            lines.append(f"    {entity.name},")
        lines.append(")")
        lines.append("")
        lines.append("")

        # Generate test class for each entity that has surfaces
        for entity in self.spec.domain.entities:
            if self._entity_has_surfaces(entity):
                lines.append(self._generate_view_test_class(entity))
                lines.append("")
                lines.append("")

        return "\n".join(lines)

    def _generate_view_test_class(self, entity: ir.EntitySpec) -> str:
        """Generate view test class for an entity."""
        lines = [
            f"class {entity.name}ViewTest(TestCase):",
            f'    """Tests for {entity.name} views."""',
            "",
            "    def setUp(self):",
            '        """Set up test client and data."""',
            "        self.client = Client()",
        ]

        # Create FK dependencies
        fk_fields = [f for f in entity.fields if f.type.kind == ir.FieldTypeKind.REF]
        referenced_entities = set()
        for fk_field in fk_fields:
            ref_entity_name = fk_field.type.ref_entity
            if ref_entity_name not in referenced_entities:
                referenced_entities.add(ref_entity_name)
                ref_entity = self._get_entity_by_name(ref_entity_name)
                if ref_entity:
                    create_params = self._get_minimal_create_params(ref_entity)
                    param_str = ",\n            ".join(f"{k}={v}" for k, v in create_params.items())
                    lines.append(
                        f"        self.{ref_entity_name.lower()} = {ref_entity_name}.objects.create("
                    )
                    lines.append(f"            {param_str}")
                    lines.append("        )")

        lines.append("")

        # Generate tests for each surface mode
        entity.name.lower()

        # List view test
        if self._find_surface_for_entity(entity.name, ir.SurfaceMode.LIST):
            lines.extend(self._generate_list_view_test(entity))
            lines.append("")

        # Detail view test
        if self._find_surface_for_entity(entity.name, ir.SurfaceMode.VIEW):
            lines.extend(self._generate_detail_view_test(entity))
            lines.append("")

        # Create view test
        if self._find_surface_for_entity(entity.name, ir.SurfaceMode.CREATE):
            lines.extend(self._generate_create_view_test(entity))
            lines.append("")

        # Update view test
        if self._find_surface_for_entity(entity.name, ir.SurfaceMode.EDIT):
            lines.extend(self._generate_update_view_test(entity))
            lines.append("")

        return "\n".join(lines)

    def _generate_list_view_test(self, entity: ir.EntitySpec) -> list[str]:
        """Generate list view test."""
        entity_lower = entity.name.lower()
        return [
            f"    def test_{entity_lower}_list_view(self):",
            f'        """Test {entity.name} list view returns 200."""',
            f'        response = self.client.get(reverse("{entity_lower}-list"))',
            "        self.assertEqual(response.status_code, 200)",
            f'        self.assertIn("{entity_lower}s", response.context)',
        ]

    def _generate_detail_view_test(self, entity: ir.EntitySpec) -> list[str]:
        """Generate detail view test."""
        entity_lower = entity.name.lower()
        create_params = self._get_minimal_create_params(entity, use_self=True)
        param_str = ",\n            ".join(f"{k}={v}" for k, v in create_params.items())

        return [
            f"    def test_{entity_lower}_detail_view(self):",
            f'        """Test {entity.name} detail view returns 200."""',
            f"        obj = {entity.name}.objects.create(",
            f"            {param_str}",
            "        )",
            f'        response = self.client.get(reverse("{entity_lower}-detail", kwargs={{"pk": obj.pk}}))',
            "        self.assertEqual(response.status_code, 200)",
            f'        self.assertEqual(response.context["{entity_lower}"], obj)',
        ]

    def _generate_create_view_test(self, entity: ir.EntitySpec) -> list[str]:
        """Generate create view test."""
        entity_lower = entity.name.lower()
        create_surface = self._find_surface_for_entity(entity.name, ir.SurfaceMode.CREATE)

        # Get fields from surface
        post_data = {}
        if create_surface and create_surface.sections:
            for section in create_surface.sections:
                for element in section.elements:
                    if element.field_name:
                        field = self._get_field_by_name(entity, element.field_name)
                        if field:
                            post_data[element.field_name] = self._get_sample_value_for_field(field)

        lines = [
            f"    def test_{entity_lower}_create_view_get(self):",
            f'        """Test {entity.name} create view GET returns 200."""',
            f'        response = self.client.get(reverse("{entity_lower}-create"))',
            "        self.assertEqual(response.status_code, 200)",
            "",
            f"    def test_{entity_lower}_create_view_post(self):",
            f'        """Test {entity.name} create view POST creates object."""',
            "        data = {",
        ]

        for field_name, value in post_data.items():
            lines.append(f'            "{field_name}": {value},')

        lines.append("        }")
        lines.append(f'        response = self.client.post(reverse("{entity_lower}-create"), data)')
        lines.append("        self.assertEqual(response.status_code, 302)  # Redirect on success")
        lines.append(f"        self.assertEqual({entity.name}.objects.count(), 1)")

        return lines

    def _generate_update_view_test(self, entity: ir.EntitySpec) -> list[str]:
        """Generate update view test."""
        entity_lower = entity.name.lower()
        create_params = self._get_minimal_create_params(entity, use_self=True)
        param_str = ",\n            ".join(f"{k}={v}" for k, v in create_params.items())

        return [
            f"    def test_{entity_lower}_update_view(self):",
            f'        """Test {entity.name} update view."""',
            f"        obj = {entity.name}.objects.create(",
            f"            {param_str}",
            "        )",
            f'        response = self.client.get(reverse("{entity_lower}-edit", kwargs={{"pk": obj.pk}}))',
            "        self.assertEqual(response.status_code, 200)",
        ]

    # =========================================================================
    # Form Tests Generation
    # =========================================================================

    def _generate_form_tests(self) -> str:
        """Generate form tests."""
        lines = [
            '"""',
            "Form tests generated from DAZZLE DSL.",
            "",
            "Tests cover:",
            "- Valid form submission",
            "- Required field validation",
            "- Unique constraint validation",
            '"""',
            "from django.test import TestCase",
            "",
            "from app.models import (",
        ]

        for entity in self.spec.domain.entities:
            lines.append(f"    {entity.name},")
        lines.append(")")
        lines.append("from app.forms import (")
        for entity in self.spec.domain.entities:
            if self._find_surface_for_entity(entity.name, ir.SurfaceMode.CREATE):
                lines.append(f"    {entity.name}CreateForm,")
        lines.append(")")
        lines.append("")

        return "\n".join(lines)

    # =========================================================================
    # Admin Tests Generation
    # =========================================================================

    def _generate_admin_tests(self) -> str:
        """Generate admin tests."""
        lines = [
            '"""',
            "Admin tests generated from DAZZLE DSL.",
            "",
            "Tests cover:",
            "- Admin pages load correctly",
            "- List display works",
            "- Search functionality",
            '"""',
            "from django.test import TestCase, Client",
            "from django.contrib.auth.models import User",
            "",
        ]

        return "\n".join(lines)

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _get_entity_by_name(self, entity_name: str) -> ir.EntitySpec | None:
        """Get entity spec by name."""
        for entity in self.spec.domain.entities:
            if entity.name == entity_name:
                return entity
        return None

    def _get_field_by_name(self, entity: ir.EntitySpec, field_name: str) -> ir.FieldSpec | None:
        """Get field spec by name."""
        for field in entity.fields:
            if field.name == field_name:
                return field
        return None

    def _find_surface_for_entity(
        self, entity_name: str, mode: ir.SurfaceMode
    ) -> ir.SurfaceSpec | None:
        """Find surface for an entity with specific mode."""
        for surface in self.spec.surfaces:
            if surface.entity_ref == entity_name and surface.mode == mode:
                return surface
        return None

    def _entity_has_surfaces(self, entity: ir.EntitySpec) -> bool:
        """Check if entity has any surfaces defined."""
        for surface in self.spec.surfaces:
            if surface.entity_ref == entity.name:
                return True
        return False

    def _get_minimal_create_params(
        self, entity: ir.EntitySpec, use_self: bool = False, exclude: list[str] | None = None
    ) -> dict[str, str]:
        """Get minimal parameters needed to create an instance."""
        params = {}
        exclude = exclude or []

        for field in entity.fields:
            if field.name in exclude:
                continue

            # Skip auto-generated fields
            if (
                field.is_primary_key
                or ir.FieldModifier.AUTO_ADD in field.modifiers
                or ir.FieldModifier.AUTO_UPDATE in field.modifiers
            ):
                continue

            # Include required fields
            if field.is_required:
                if field.type.kind == ir.FieldTypeKind.REF:
                    # Use self.ref_entity if available
                    if use_self:
                        params[field.name] = f"self.{field.type.ref_entity.lower()}"
                    else:
                        # Will be handled in setUp
                        continue
                else:
                    params[field.name] = self._get_sample_value_for_field(field)
            # Include fields with defaults (use default value)
            elif field.default is not None:
                params[field.name] = self._format_default_value(field.default, field.type.kind)

        return params

    def _get_sample_value_for_field(self, field: ir.FieldSpec) -> str:
        """Get a sample value for testing."""
        field_type = field.type.kind

        if field_type == ir.FieldTypeKind.EMAIL:
            return '"test@example.com"'
        elif field_type == ir.FieldTypeKind.STR:
            if "name" in field.name.lower():
                return '"Test Name"'
            elif "title" in field.name.lower():
                return '"Test Title"'
            else:
                return f'"test_{field.name}"'
        elif field_type == ir.FieldTypeKind.TEXT:
            return '"Test description"'
        elif field_type == ir.FieldTypeKind.BOOL:
            return "True"
        elif field_type == ir.FieldTypeKind.INT:
            return "1"
        elif field_type == ir.FieldTypeKind.DECIMAL:
            return "10.50"
        elif field_type == ir.FieldTypeKind.ENUM:
            if field.type.enum_values:
                return f'"{field.type.enum_values[0]}"'
            return '"default"'
        elif field_type == ir.FieldTypeKind.DATE:
            return '"2025-01-01"'
        elif field_type == ir.FieldTypeKind.DATETIME:
            return '"2025-01-01T00:00:00Z"'
        else:
            return '""'

    def _format_default_value(self, value: Any, field_type_kind: ir.FieldTypeKind) -> str:
        """Format default value for Python code."""
        if isinstance(value, str):
            return f'"{value}"'
        elif isinstance(value, bool):
            return str(value)
        elif value is None:
            return "None"
        else:
            return str(value)

    # =========================================================================
    # DSL Tests Generation
    # =========================================================================

    def _generate_dsl_tests(self) -> str:
        """Generate tests from DSL test specifications."""
        lines = [
            '"""',
            "Tests defined in DSL test blocks.",
            "",
            "These tests are generated from test definitions in your DSL files.",
            '"""',
            "from django.test import TestCase",
            "from django.core.exceptions import ValidationError",
            "from django.db import IntegrityError",
            "from django.db.models import ProtectedError",
            "",
            "from app.models import (",
        ]

        # Import all models
        for entity in self.spec.domain.entities:
            lines.append(f"    {entity.name},")
        lines.append(")")
        lines.append("")
        lines.append("")

        # Generate test class
        lines.append("class DSLTestCase(TestCase):")
        lines.append('    """Tests generated from DSL test blocks."""')
        lines.append("")

        # Generate each test from spec
        for test_spec in self.spec.tests:
            lines.extend(self._generate_test_from_spec(test_spec))
            lines.append("")

        return "\n".join(lines)

    def _generate_test_from_spec(self, test_spec: ir.TestSpec) -> list[str]:
        """Generate a single test method from TestSpec."""
        lines = [
            f"    def test_{test_spec.name}(self):",
        ]

        # Add description as docstring
        if test_spec.description:
            lines.append(f'        """{test_spec.description}"""')
        else:
            lines.append(f'        """Test {test_spec.name} (from DSL)."""')

        # Generate setup steps
        if test_spec.setup_steps:
            lines.append("        # Setup")
            lines.extend(self._generate_setup_steps(test_spec.setup_steps))
            lines.append("")

        # Generate action
        lines.append("        # Action")
        action_result_var = self._generate_test_action(test_spec.action, lines)
        lines.append("")

        # Generate assertions
        lines.append("        # Assertions")
        lines.extend(self._generate_test_assertions(test_spec.assertions, action_result_var))

        return lines

    def _generate_setup_steps(self, setup_steps: list[ir.TestSetupStep]) -> list[str]:
        """Generate Python code for setup steps."""
        lines = []

        for step in setup_steps:
            var_name = step.variable_name
            entity_name = step.entity_name

            # Build field assignments
            field_assignments = []
            for field_name, field_value in step.data.items():
                # Check if value is a variable reference (from previous setup step)
                if isinstance(field_value, str) and not field_value.startswith('"'):
                    # It's a variable reference
                    field_assignments.append(f"{field_name}={field_value}")
                else:
                    # It's a literal value
                    formatted_value = self._format_value(field_value)
                    field_assignments.append(f"{field_name}={formatted_value}")

            assignments_str = ", ".join(field_assignments)
            lines.append(f"        {var_name} = {entity_name}.objects.create({assignments_str})")

        return lines

    def _generate_test_action(self, action: ir.TestAction, lines: list[str]) -> str:
        """
        Generate Python code for test action.

        Returns the variable name containing the result.
        """
        action_kind = action.kind
        target = action.target
        data = action.data

        if action_kind == ir.TestActionKind.CREATE:
            # Generate create action
            field_assignments = []
            for field_name, field_value in data.items():
                formatted_value = self._format_value(field_value)
                field_assignments.append(f"{field_name}={formatted_value}")

            if field_assignments:
                assignments_str = ", ".join(field_assignments)
                lines.append(f"        result = {target}.objects.create({assignments_str})")
            else:
                lines.append(f"        result = {target}.objects.create()")

            return "result"

        elif action_kind == ir.TestActionKind.UPDATE:
            # target is a variable name from setup
            field_assignments = []
            for field_name, field_value in data.items():
                formatted_value = self._format_value(field_value)
                field_assignments.append(f"{field_name}={formatted_value}")

            for assignment in field_assignments:
                field_name, value = assignment.split("=", 1)
                lines.append(f"        {target}.{field_name} = {value}")

            lines.append(f"        {target}.save()")
            return target

        elif action_kind == ir.TestActionKind.DELETE:
            # target is a variable name from setup
            lines.append(f"        {target}.delete()")
            return target

        elif action_kind == ir.TestActionKind.GET:
            # Generate query
            # Note: filter/search/order_by would be in the test_spec but not in action.data
            # For now, just do a basic query
            lines.append(f"        result = {target}.objects.all()")
            return "result"

        else:
            lines.append(f"        pass  # Action kind: {action_kind}")
            return "result"

    def _generate_test_assertions(
        self, assertions: list[ir.TestAssertion], result_var: str
    ) -> list[str]:
        """Generate Django test assertions from assertion specs."""
        lines = []

        for assertion in assertions:
            kind = assertion.kind

            if kind == ir.TestAssertionKind.STATUS:
                # Status assertions check if operation succeeded or failed
                if assertion.expected_value == "success":
                    lines.append("        # Expecting success (object should exist)")
                    lines.append(f"        self.assertIsNotNone({result_var})")
                else:
                    lines.append("        # Expecting error")
                    lines.append("        pass  # Error handling not yet implemented")

            elif kind == ir.TestAssertionKind.CREATED:
                # Check if object was created
                if assertion.expected_value:
                    lines.append(f"        self.assertIsNotNone({result_var})")
                else:
                    lines.append(f"        self.assertIsNone({result_var})")

            elif kind == ir.TestAssertionKind.FIELD:
                # Field value assertions
                field_name = assertion.field_name
                operator = assertion.operator
                expected_value = assertion.expected_value

                # Handle special field names (first.field, last.field)
                if field_name.startswith("first."):
                    actual_field = field_name.split(".", 1)[1]
                    lines.append(f"        obj = {result_var}.first()")
                    field_ref = f"obj.{actual_field}"
                elif field_name.startswith("last."):
                    actual_field = field_name.split(".", 1)[1]
                    lines.append(f"        obj = {result_var}.last()")
                    field_ref = f"obj.{actual_field}"
                else:
                    field_ref = f"{result_var}.{field_name}"

                # Generate assertion based on operator
                formatted_value = self._format_value(expected_value)

                if operator == ir.TestComparisonOperator.EQUALS:
                    lines.append(f"        self.assertEqual({field_ref}, {formatted_value})")
                elif operator == ir.TestComparisonOperator.NOT_EQUALS:
                    lines.append(f"        self.assertNotEqual({field_ref}, {formatted_value})")
                elif operator == ir.TestComparisonOperator.GREATER_THAN:
                    lines.append(f"        self.assertGreater({field_ref}, {formatted_value})")
                elif operator == ir.TestComparisonOperator.LESS_THAN:
                    lines.append(f"        self.assertLess({field_ref}, {formatted_value})")
                elif operator == ir.TestComparisonOperator.CONTAINS:
                    lines.append(f"        self.assertIn({formatted_value}, {field_ref})")
                elif operator == ir.TestComparisonOperator.NOT_CONTAINS:
                    lines.append(f"        self.assertNotIn({formatted_value}, {field_ref})")

            elif kind == ir.TestAssertionKind.COUNT:
                # Count assertions on querysets
                operator = assertion.operator
                expected_value = assertion.expected_value

                if operator == ir.TestComparisonOperator.EQUALS:
                    lines.append(
                        f"        self.assertEqual({result_var}.count(), {expected_value})"
                    )
                elif operator == ir.TestComparisonOperator.GREATER_THAN:
                    lines.append(
                        f"        self.assertGreater({result_var}.count(), {expected_value})"
                    )
                elif operator == ir.TestComparisonOperator.LESS_THAN:
                    lines.append(f"        self.assertLess({result_var}.count(), {expected_value})")

            elif kind == ir.TestAssertionKind.ERROR:
                # Error message assertions
                operator = assertion.operator
                expected_value = assertion.expected_value
                formatted_value = self._format_value(expected_value)

                if operator == ir.TestComparisonOperator.CONTAINS:
                    lines.append(
                        f"        pass  # Error message validation: contains {formatted_value}"
                    )
                elif operator == ir.TestComparisonOperator.EQUALS:
                    lines.append(
                        f"        pass  # Error message validation: equals {formatted_value}"
                    )

        return lines

    def _format_value(self, value: Any) -> str:
        """Format a value for Python code generation."""
        if isinstance(value, str):
            # Already quoted strings are returned as-is
            if (value.startswith('"') and value.endswith('"')) or (
                value.startswith("'") and value.endswith("'")
            ):
                return value
            # Strings should be quoted for Python
            return f'"{value}"'
        elif isinstance(value, bool):
            return "True" if value else "False"
        elif isinstance(value, (int, float)):
            return str(value)
        elif value is None:
            return "None"
        else:
            return f'"{value}"'
