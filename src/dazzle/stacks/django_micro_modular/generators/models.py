"""
Models generator for Django Micro backend.

Generates Django models.py from entity specifications.
"""

from pathlib import Path
from typing import Any

from ...base import Generator, GeneratorResult
from ....core import ir


class ModelsGenerator(Generator):
    """
    Generate Django models from entities.

    Creates models.py with:
    - Django model classes for each entity
    - Field definitions with appropriate types
    - Model metadata (verbose names, ordering)
    - __str__ methods
    """

    def __init__(self, spec: ir.AppSpec, output_dir: Path, app_name: str = "app"):
        """
        Initialize models generator.

        Args:
            spec: Application specification
            output_dir: Root output directory
            app_name: Name of the Django app
        """
        super().__init__(spec, output_dir)
        self.app_name = app_name

    def generate(self) -> GeneratorResult:
        """Generate models.py file."""
        result = GeneratorResult()

        # Build models code
        code = self._build_models_code()

        # Write file
        models_path = self.output_dir / self.app_name / "models.py"
        self._write_file(models_path, code)
        result.add_file(models_path)

        # Record model names for other generators
        model_names = [entity.name for entity in self.spec.domain.entities]
        result.add_artifact("model_names", model_names)

        return result

    def _build_models_code(self) -> str:
        """Build complete models.py content."""
        lines = [
            '"""',
            'Django models generated from DAZZLE DSL.',
            '"""',
            'import uuid',
            'from django.db import models',
            '',
            '',
        ]

        # Generate model for each entity
        for entity in self.spec.domain.entities:
            lines.append(self._generate_model_class(entity))
            lines.append('')
            lines.append('')

        # Handle case with no entities
        if not self.spec.domain.entities:
            lines.append('# No entities defined in specification')
            lines.append('')

        return '\n'.join(lines)

    def _generate_model_class(self, entity: ir.EntitySpec) -> str:
        """Generate a complete Django model class."""
        lines = [
            f'class {entity.name}(models.Model):',
            f'    """{entity.name} model."""',
            ''
        ]

        # Generate fields
        has_fields = False
        for field in entity.fields:
            field_def = self._generate_model_field(field, entity)
            if field_def:
                lines.append(f'    {field_def}')
                has_fields = True

        if not has_fields:
            lines.append('    pass')

        # Meta class
        lines.append('')
        lines.append('    class Meta:')
        lines.append(f'        verbose_name = "{entity.title or entity.name}"')
        lines.append(f'        verbose_name_plural = "{entity.title or entity.name}s"')

        # Add ordering by created_at if exists, otherwise by id
        if any(f.name == 'created_at' for f in entity.fields):
            lines.append('        ordering = ["-created_at"]')
        elif any(f.name == 'id' for f in entity.fields):
            lines.append('        ordering = ["-id"]')

        # __str__ method
        lines.append('')
        lines.append('    def __str__(self):')
        str_field = self._get_string_field(entity)
        lines.append(f'        return str(self.{str_field})')

        return '\n'.join(lines)

    def _generate_model_field(self, field: ir.FieldSpec, entity: ir.EntitySpec) -> str:
        """Generate Django field definition."""
        field_type = field.type
        field_params = []

        # Handle ForeignKey (REF) fields specially
        if field_type.kind == ir.FieldTypeKind.REF:
            return self._generate_foreign_key_field(field, entity)

        # Map DAZZLE types to Django fields
        django_field = self._map_field_type(field_type)

        # Handle UUID primary key default
        if field.is_primary_key and field_type.kind == ir.FieldTypeKind.UUID:
            field_params.append('primary_key=True')
            field_params.append('default=uuid.uuid4')
            field_params.append('editable=False')
        # Handle other primary keys
        elif field.is_primary_key:
            field_params.append('primary_key=True')
        # Handle non-primary key fields
        elif not field.is_required:
            field_params.append('null=True')
            field_params.append('blank=True')

        if field.is_unique:
            field_params.append('unique=True')

        # Handle auto timestamps
        if ir.FieldModifier.AUTO_ADD in field.modifiers:
            field_params.append('auto_now_add=True')
        if ir.FieldModifier.AUTO_UPDATE in field.modifiers:
            field_params.append('auto_now=True')

        # Handle default values (except for UUID PKs which already have default)
        if field.default is not None and not (field.is_primary_key and field_type.kind == ir.FieldTypeKind.UUID):
            default_val = self._format_default_value(field.default, field_type.kind)
            field_params.append(f'default={default_val}')

        # Add verbose name (formatted field name)
        verbose_name = field.name.replace("_", " ").title()
        field_params.append(f'verbose_name="{verbose_name}"')

        # Handle string and enum max length (CharField requires max_length)
        if field_type.kind in [ir.FieldTypeKind.STR, ir.FieldTypeKind.ENUM]:
            if field_type.kind == ir.FieldTypeKind.STR:
                max_len = field_type.max_length if field_type.max_length else 255
            else:  # ENUM
                max_len = 50  # Reasonable default for enum values
            field_params.insert(0, f'max_length={max_len}')

        params_str = ', '.join(field_params)
        return f'{field.name} = models.{django_field}({params_str})'

    def _generate_foreign_key_field(self, field: ir.FieldSpec, entity: ir.EntitySpec) -> str:
        """Generate Django ForeignKey field for REF types."""
        field_type = field.type
        field_params = []

        # Get referenced model name
        ref_model = field_type.ref_entity
        if not ref_model:
            # Fallback to CharField if ref_entity is missing
            return f'{field.name} = models.CharField(verbose_name="{field.name.replace("_", " ").title()}")'

        # Add referenced model as first parameter
        field_params.append(f'{ref_model}')

        # Determine on_delete behavior
        if field.is_required:
            # Required foreign keys use PROTECT (prevent deletion of referenced object)
            field_params.append('on_delete=models.PROTECT')
        else:
            # Optional foreign keys use SET_NULL (set to null when referenced object deleted)
            field_params.append('on_delete=models.SET_NULL')
            field_params.append('null=True')
            field_params.append('blank=True')

        # Generate related_name for reverse lookups
        # Format: {entity_name_lowercase}_{field_name}s or just {field_name}s
        related_name = f'{entity.name.lower()}_{field.name}s'
        field_params.append(f'related_name="{related_name}"')

        # Add verbose name
        verbose_name = field.name.replace("_", " ").title()
        field_params.append(f'verbose_name="{verbose_name}"')

        params_str = ', '.join(field_params)
        return f'{field.name} = models.ForeignKey({params_str})'

    def _map_field_type(self, field_type: ir.FieldType) -> str:
        """Map DAZZLE field type to Django field type."""
        type_map = {
            ir.FieldTypeKind.STR: 'CharField',
            ir.FieldTypeKind.TEXT: 'TextField',
            ir.FieldTypeKind.INT: 'IntegerField',
            ir.FieldTypeKind.DECIMAL: 'DecimalField',
            ir.FieldTypeKind.BOOL: 'BooleanField',
            ir.FieldTypeKind.DATE: 'DateField',
            ir.FieldTypeKind.DATETIME: 'DateTimeField',
            ir.FieldTypeKind.UUID: 'UUIDField',
            ir.FieldTypeKind.EMAIL: 'EmailField',
            ir.FieldTypeKind.ENUM: 'CharField',  # ENUMs map to CharField with choices
        }

        return type_map.get(field_type.kind, 'CharField')

    def _format_default_value(self, value: Any, field_type_kind: ir.FieldTypeKind) -> str:
        """Format default value for Python code."""
        if isinstance(value, str):
            return f'"{value}"'
        elif isinstance(value, bool):
            return str(value)
        elif value is None:
            return 'None'
        else:
            return str(value)

    def _get_string_field(self, entity: ir.EntitySpec) -> str:
        """Get best field for __str__ representation."""
        # Prefer: name, title, email, then first non-id field
        priority_fields = ['name', 'title', 'email', 'label']

        for field_name in priority_fields:
            if any(f.name == field_name for f in entity.fields):
                return field_name

        # Return first non-id field
        for field in entity.fields:
            if field.name != 'id':
                return field.name

        return 'id'
