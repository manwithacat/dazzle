"""
Admin generator for Django Micro backend.

Generates Django admin.py configuration.
"""

from pathlib import Path

from ...base import Generator, GeneratorResult
from ....core import ir


class AdminGenerator(Generator):
    """
    Generate Django admin configuration.

    Creates admin.py with:
    - ModelAdmin classes for each entity
    - List display configuration
    - Search fields
    - Filters
    - Read-only fields for auto-generated data
    """

    def __init__(self, spec: ir.AppSpec, output_dir: Path, app_name: str = "app"):
        """
        Initialize admin generator.

        Args:
            spec: Application specification
            output_dir: Root output directory
            app_name: Name of the Django app
        """
        super().__init__(spec, output_dir)
        self.app_name = app_name

    def generate(self) -> GeneratorResult:
        """Generate admin.py file."""
        result = GeneratorResult()

        # Build admin code
        code = self._build_admin_code()

        # Write file
        admin_path = self.output_dir / self.app_name / "admin.py"
        self._write_file(admin_path, code)
        result.add_file(admin_path)

        return result

    def _build_admin_code(self) -> str:
        """Build complete admin.py content."""
        lines = [
            '"""',
            'Django admin configuration generated from DAZZLE DSL.',
            '"""',
            'from django.contrib import admin',
        ]

        # Handle no entities case
        if not self.spec.domain.entities:
            lines.append('')
            lines.append('# No entities defined')
            lines.append('')
            return '\n'.join(lines)

        # Import models
        lines.append('from .models import (')
        for entity in self.spec.domain.entities:
            lines.append(f'    {entity.name},')
        lines.append(')')
        lines.append('')
        lines.append('')

        # Register models with customized admin
        for entity in self.spec.domain.entities:
            lines.append(self._generate_admin_class(entity))
            lines.append('')

        return '\n'.join(lines)

    def _generate_admin_class(self, entity: ir.EntitySpec) -> str:
        """Generate ModelAdmin class for entity."""
        lines = [
            f'@admin.register({entity.name})',
            f'class {entity.name}Admin(admin.ModelAdmin):',
            f'    """{entity.title or entity.name} admin."""',
        ]

        # List display
        list_display_fields = self._get_list_display_fields(entity)
        if list_display_fields:
            fields_str = ', '.join(f'"{f}"' for f in list_display_fields)
            # Add trailing comma for single-item tuples
            if len(list_display_fields) == 1:
                lines.append(f'    list_display = ({fields_str},)')
            else:
                lines.append(f'    list_display = ({fields_str})')

        # Search fields (text fields only)
        search_fields = self._get_search_fields(entity)
        if search_fields:
            fields_str = ', '.join(f'"{f}"' for f in search_fields)
            # Add trailing comma for single-item tuples
            if len(search_fields) == 1:
                lines.append(f'    search_fields = ({fields_str},)')
            else:
                lines.append(f'    search_fields = ({fields_str})')

        # List filters (choice fields, booleans, dates)
        list_filter = self._get_list_filter_fields(entity)
        if list_filter:
            fields_str = ', '.join(f'"{f}"' for f in list_filter)
            # Add trailing comma for single-item tuples
            if len(list_filter) == 1:
                lines.append(f'    list_filter = ({fields_str},)')
            else:
                lines.append(f'    list_filter = ({fields_str})')

        # Read-only fields (auto-generated)
        readonly_fields = self._get_readonly_fields(entity)
        if readonly_fields:
            fields_str = ', '.join(f'"{f}"' for f in readonly_fields)
            # Add trailing comma for single-item tuples
            if len(readonly_fields) == 1:
                lines.append(f'    readonly_fields = ({fields_str},)')
            else:
                lines.append(f'    readonly_fields = ({fields_str})')

        return '\n'.join(lines)

    def _get_list_display_fields(self, entity: ir.EntitySpec) -> list:
        """Get fields to display in list view."""
        fields = []

        # Add up to 5 most important fields
        priority_fields = ['id', 'name', 'title', 'email', 'status', 'created_at']

        for field_name in priority_fields:
            field = next((f for f in entity.fields if f.name == field_name), None)
            if field:
                fields.append(field.name)

        # If we don't have enough fields, add more
        if len(fields) < 5:
            for field in entity.fields:
                if field.name not in fields:
                    fields.append(field.name)
                    if len(fields) >= 5:
                        break

        return fields

    def _get_search_fields(self, entity: ir.EntitySpec) -> list:
        """Get text fields for searching."""
        search_fields = []

        for field in entity.fields:
            if field.type.kind in [ir.FieldTypeKind.STR, ir.FieldTypeKind.TEXT, ir.FieldTypeKind.EMAIL]:
                search_fields.append(field.name)

        return search_fields

    def _get_list_filter_fields(self, entity: ir.EntitySpec) -> list:
        """Get fields suitable for filtering."""
        filter_fields = []

        for field in entity.fields:
            # ENUMs, booleans, and dates make good filters
            if field.type.kind in [ir.FieldTypeKind.ENUM, ir.FieldTypeKind.BOOL, ir.FieldTypeKind.DATE, ir.FieldTypeKind.DATETIME]:
                filter_fields.append(field.name)

        return filter_fields

    def _get_readonly_fields(self, entity: ir.EntitySpec) -> list:
        """Get auto-generated fields that should be read-only."""
        readonly = []

        for field in entity.fields:
            # Auto-generated fields should be read-only
            if ir.FieldModifier.AUTO_ADD in field.modifiers or ir.FieldModifier.AUTO_UPDATE in field.modifiers:
                readonly.append(field.name)
            # UUID fields are typically auto-generated
            elif field.type.kind == ir.FieldTypeKind.UUID:
                readonly.append(field.name)

        return readonly
