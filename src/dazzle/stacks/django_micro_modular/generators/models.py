"""
Models generator for Django Micro backend.

Generates Django models.py from entity specifications.
"""

from pathlib import Path
from typing import Any

from ....core import ir
from ...base import Generator, GeneratorResult


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
            "Django models generated from DAZZLE DSL.",
            '"""',
            "import uuid",
            "from django.db import models",
            "from django.utils import timezone",
            "from django.core.exceptions import ValidationError",
            "",
            "",
        ]

        # Check if any entity uses soft_delete pattern
        has_soft_delete = any(self._has_soft_delete_pattern(e) for e in self.spec.domain.entities)

        # Generate SoftDeleteManager if needed
        if has_soft_delete:
            lines.extend(self._generate_soft_delete_manager())
            lines.append("")
            lines.append("")

        # Generate model for each entity
        for entity in self.spec.domain.entities:
            # Generate TextChoices classes for enum fields first
            enum_classes = self._generate_enum_choices(entity)
            if enum_classes:
                lines.extend(enum_classes)
                lines.append("")
                lines.append("")

            lines.append(self._generate_model_class(entity))
            lines.append("")
            lines.append("")

        # Handle case with no entities
        if not self.spec.domain.entities:
            lines.append("# No entities defined in specification")
            lines.append("")

        return "\n".join(lines)

    def _generate_enum_choices(self, entity: ir.EntitySpec) -> list[str]:
        """
        Generate Django TextChoices classes for enum fields.

        Returns list of TextChoices class definitions to insert before the model.
        """
        enum_classes = []

        for field in entity.fields:
            if field.type.kind == ir.FieldTypeKind.ENUM and field.type.enum_values:
                # Generate class name: {EntityName}{FieldName}Choices
                class_name = f"{entity.name}{self._to_pascal_case(field.name)}Choices"

                # Start class definition
                lines = [
                    f"class {class_name}(models.TextChoices):",
                    f'    """{field.name.replace("_", " ").title()} choices for {entity.name}."""',
                ]

                # Generate choice constants
                for enum_value in field.type.enum_values:
                    # Constant name: ALL_CAPS_WITH_UNDERSCORES
                    const_name = self._to_constant_case(enum_value)
                    # Display name: Title Case With Spaces
                    display_name = self._to_display_name(enum_value)
                    lines.append(f'    {const_name} = "{enum_value}", "{display_name}"')

                enum_classes.extend(lines)

        return enum_classes

    def _to_pascal_case(self, snake_str: str) -> str:
        """Convert snake_case to PascalCase."""
        return "".join(word.capitalize() for word in snake_str.split("_"))

    def _to_constant_case(self, camel_or_word: str) -> str:
        """Convert CamelCase or word to CONSTANT_CASE."""
        # Insert underscores before uppercase letters (except at start)
        result = []
        for i, char in enumerate(camel_or_word):
            if i > 0 and char.isupper() and camel_or_word[i - 1].islower():
                result.append("_")
            result.append(char.upper())
        return "".join(result)

    def _to_display_name(self, camel_or_word: str) -> str:
        """Convert CamelCase to Display Name with spaces."""
        # Insert spaces before uppercase letters (except at start)
        result = []
        for i, char in enumerate(camel_or_word):
            if i > 0 and char.isupper() and camel_or_word[i - 1].islower():
                result.append(" ")
            result.append(char)
        return "".join(result)

    def _generate_model_class(self, entity: ir.EntitySpec) -> str:
        """Generate a complete Django model class."""
        lines = [f"class {entity.name}(models.Model):", f'    """{entity.name} model."""', ""]

        # Generate fields
        has_fields = False
        for field in entity.fields:
            field_def = self._generate_model_field(field, entity)
            if field_def:
                lines.append(f"    {field_def}")
                has_fields = True

        if not has_fields:
            lines.append("    pass")

        # Add managers if soft delete pattern detected
        has_soft_delete = self._has_soft_delete_pattern(entity)
        if has_soft_delete:
            lines.append("")
            lines.append("    # Soft delete managers")
            lines.append("    objects = SoftDeleteManager()  # Default: exclude deleted")
            lines.append("    all_objects = models.Manager()  # Include deleted")

        # Meta class
        lines.append("")
        lines.append("    class Meta:")
        lines.append(f'        verbose_name = "{entity.title or entity.name}"')
        lines.append(f'        verbose_name_plural = "{entity.title or entity.name}s"')

        # Add ordering by created_at if exists, otherwise by id
        if any(f.name == "created_at" for f in entity.fields):
            lines.append('        ordering = ["-created_at"]')
        elif any(f.name == "id" for f in entity.fields):
            lines.append('        ordering = ["-id"]')

        # __str__ method
        lines.append("")
        lines.append("    def __str__(self):")
        str_field = self._get_string_field(entity)
        lines.append(f"        return str(self.{str_field})")

        # Add soft delete methods if pattern detected
        if has_soft_delete:
            lines.append("")
            lines.append(self._generate_soft_delete_methods(entity))

        # Add status workflow methods if pattern detected
        workflow_field = self._get_workflow_field(entity)
        if workflow_field:
            lines.append("")
            lines.append(self._generate_status_workflow_methods(entity, workflow_field))

        # Add multi-tenant helper if pattern detected
        tenant_field = self._get_tenant_field(entity)
        if tenant_field:
            lines.append("")
            lines.append(self._generate_multi_tenant_helpers(entity, tenant_field))

        return "\n".join(lines)

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
            field_params.append("primary_key=True")
            field_params.append("default=uuid.uuid4")
            field_params.append("editable=False")
        # Handle other primary keys
        elif field.is_primary_key:
            field_params.append("primary_key=True")
        # Handle non-primary key fields
        elif not field.is_required:
            field_params.append("null=True")
            field_params.append("blank=True")

        if field.is_unique:
            field_params.append("unique=True")

        # Handle auto timestamps
        if ir.FieldModifier.AUTO_ADD in field.modifiers:
            field_params.append("auto_now_add=True")
        if ir.FieldModifier.AUTO_UPDATE in field.modifiers:
            field_params.append("auto_now=True")

        # Handle default values (except for UUID PKs which already have default)
        if field.default is not None and not (
            field.is_primary_key and field_type.kind == ir.FieldTypeKind.UUID
        ):
            default_val = self._format_default_value(field.default, field_type.kind)
            field_params.append(f"default={default_val}")

        # Add verbose name (formatted field name)
        verbose_name = field.name.replace("_", " ").title()
        field_params.append(f'verbose_name="{verbose_name}"')

        # Handle decimal precision (DecimalField requires max_digits and decimal_places)
        if field_type.kind == ir.FieldTypeKind.DECIMAL:
            max_digits = field_type.precision if field_type.precision else 10
            decimal_places = field_type.scale if field_type.scale else 2
            field_params.insert(0, f"max_digits={max_digits}")
            field_params.insert(1, f"decimal_places={decimal_places}")

        # Handle string and enum max length (CharField requires max_length)
        if field_type.kind in [ir.FieldTypeKind.STR, ir.FieldTypeKind.ENUM]:
            if field_type.kind == ir.FieldTypeKind.STR:
                max_len = field_type.max_length if field_type.max_length else 255
            else:  # ENUM
                max_len = 50  # Reasonable default for enum values
            field_params.insert(0, f"max_length={max_len}")

        # Handle enum choices
        if field_type.kind == ir.FieldTypeKind.ENUM and field_type.enum_values:
            choices_class = f"{entity.name}{self._to_pascal_case(field.name)}Choices"
            field_params.insert(1, f"choices={choices_class}.choices")

            # Handle default value for enums - use the constant
            if field.default is not None:
                # Find and remove the default parameter if it exists
                field_params = [p for p in field_params if not p.startswith("default=")]
                # Convert default value to constant name
                const_name = self._to_constant_case(field.default)
                field_params.append(f"default={choices_class}.{const_name}")

        params_str = ", ".join(field_params)
        return f"{field.name} = models.{django_field}({params_str})"

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
        field_params.append(f"{ref_model}")

        # Determine on_delete behavior
        if field.is_required:
            # Required foreign keys use PROTECT (prevent deletion of referenced object)
            field_params.append("on_delete=models.PROTECT")
        else:
            # Optional foreign keys use SET_NULL (set to null when referenced object deleted)
            field_params.append("on_delete=models.SET_NULL")
            field_params.append("null=True")
            field_params.append("blank=True")

        # Generate related_name for reverse lookups
        # Format: {entity_name_lowercase}_{field_name}s or just {field_name}s
        related_name = f"{entity.name.lower()}_{field.name}s"
        field_params.append(f'related_name="{related_name}"')

        # Add verbose name
        verbose_name = field.name.replace("_", " ").title()
        field_params.append(f'verbose_name="{verbose_name}"')

        params_str = ", ".join(field_params)
        return f"{field.name} = models.ForeignKey({params_str})"

    def _map_field_type(self, field_type: ir.FieldType) -> str:
        """Map DAZZLE field type to Django field type."""
        type_map = {
            ir.FieldTypeKind.STR: "CharField",
            ir.FieldTypeKind.TEXT: "TextField",
            ir.FieldTypeKind.INT: "IntegerField",
            ir.FieldTypeKind.DECIMAL: "DecimalField",
            ir.FieldTypeKind.BOOL: "BooleanField",
            ir.FieldTypeKind.DATE: "DateField",
            ir.FieldTypeKind.DATETIME: "DateTimeField",
            ir.FieldTypeKind.UUID: "UUIDField",
            ir.FieldTypeKind.EMAIL: "EmailField",
            ir.FieldTypeKind.ENUM: "CharField",  # ENUMs map to CharField with choices
        }

        return type_map.get(field_type.kind, "CharField")

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

    def _get_string_field(self, entity: ir.EntitySpec) -> str:
        """Get best field for __str__ representation."""
        # Prefer: name, title, email, then first non-id field
        priority_fields = ["name", "title", "email", "label"]

        for field_name in priority_fields:
            if any(f.name == field_name for f in entity.fields):
                return field_name

        # Return first non-id field
        for field in entity.fields:
            if field.name != "id":
                return field.name

        return "id"

    def _has_soft_delete_pattern(self, entity: ir.EntitySpec) -> bool:
        """
        Detect if entity uses soft_delete_behavior pattern.

        Pattern detected by presence of deleted_at field (datetime optional).
        This field is created by vocabulary expansion of @use soft_delete_behavior().
        """
        for field in entity.fields:
            if field.name == "deleted_at" and field.type.kind == ir.FieldTypeKind.DATETIME:
                return True
        return False

    def _generate_soft_delete_manager(self) -> list[str]:
        """
        Generate SoftDeleteManager class for soft delete pattern.

        This manager excludes soft-deleted records from default queries.
        """
        return [
            "class SoftDeleteManager(models.Manager):",
            '    """Manager that excludes soft-deleted records from default queries."""',
            "",
            "    def get_queryset(self):",
            '        """Return queryset excluding deleted records."""',
            "        return super().get_queryset().filter(deleted_at__isnull=True)",
        ]

    def _generate_soft_delete_methods(self, entity: ir.EntitySpec) -> str:
        """
        Generate soft delete and hard delete methods.

        Implements soft_delete_behavior pattern:
        - delete() method marks record as deleted
        - hard_delete() method permanently removes record
        """
        # Check if entity has deleted_by field
        has_deleted_by = any(f.name == "deleted_by" for f in entity.fields)

        lines = [
            "    def delete(self, *args, **kwargs):",
            '        """Soft delete: mark as deleted without removing from database."""',
            "        self.deleted_at = timezone.now()",
        ]

        # Only set deleted_by if the field exists
        if has_deleted_by:
            lines.append(
                "        # Note: deleted_by should be set by the caller if user context available"
            )

        lines.extend(
            [
                "        self.save()",
                "",
                "    def hard_delete(self):",
                '        """Permanently delete record from database."""',
                "        super().delete()",
            ]
        )

        return "\n".join(lines)

    def _get_workflow_field(self, entity: ir.EntitySpec) -> ir.FieldSpec | None:
        """
        Detect if entity uses status_workflow_pattern and return the workflow field.

        Pattern detected by finding an enum field with a corresponding
        {field_name}_changed_at datetime field (from vocabulary expansion).
        """
        for field in entity.fields:
            if field.type.kind == ir.FieldTypeKind.ENUM:
                # Check if there's a corresponding _changed_at field
                changed_at_field = f"{field.name}_changed_at"
                if any(
                    f.name == changed_at_field and f.type.kind == ir.FieldTypeKind.DATETIME
                    for f in entity.fields
                ):
                    return field
        return None

    def _generate_status_workflow_methods(
        self, entity: ir.EntitySpec, workflow_field: ir.FieldSpec
    ) -> str:
        """
        Generate status workflow validation and transition tracking methods.

        Implements status_workflow_pattern:
        - validate_status_transition() validates state changes
        - change_status() method updates status with tracking
        """
        field_name = workflow_field.name
        changed_at_field = f"{field_name}_changed_at"
        changed_by_field = f"{field_name}_changed_by"

        # Check if entity has changed_by field
        has_changed_by = any(f.name == changed_by_field for f in entity.fields)

        # Get the TextChoices class name
        choices_class = f"{entity.name}{self._to_pascal_case(field_name)}Choices"

        lines = [
            f"    def validate_{field_name}_transition(self, new_status):",
            '        """',
            f"        Validate {field_name} transition.",
            "        ",
            "        Override this method to add custom transition validation logic.",
            "        Raise ValidationError if transition is not allowed.",
            '        """',
            "        # Basic validation: ensure new_status is a valid choice",
            f"        valid_statuses = [choice[0] for choice in {choices_class}.choices]",
            "        if new_status not in valid_statuses:",
            "            raise ValidationError(",
            '                f"Invalid status: {new_status}. Must be one of: {valid_statuses}"',
            "            )",
            "",
            f"    def change_{field_name}(self, new_status, user=None):",
            '        """',
            f"        Change {field_name} with validation and tracking.",
            "        ",
            "        Args:",
            "            new_status: New status value",
            "            user: User making the change (optional)",
            "        ",
            "        Raises:",
            "            ValidationError: If transition is not valid",
            '        """',
            "        # Validate transition",
            f"        self.validate_{field_name}_transition(new_status)",
            "        ",
            "        # Update status",
            f"        old_status = self.{field_name}",
            f"        self.{field_name} = new_status",
            f"        self.{changed_at_field} = timezone.now()",
        ]

        if has_changed_by:
            lines.extend(
                [
                    "        if user:",
                    f"            self.{changed_by_field} = user",
                ]
            )

        lines.extend(
            [
                "        ",
                "        self.save()",
                "        ",
                "        # Hook for post-transition actions (can be overridden)",
                f"        self.on_{field_name}_changed(old_status, new_status, user)",
                "",
                f"    def on_{field_name}_changed(self, old_status, new_status, user=None):",
                '        """',
                f"        Hook called after {field_name} change.",
                "        ",
                "        Override this method to add custom logic like notifications,",
                "        webhooks, or other side effects when status changes.",
                '        """',
                "        pass  # Can be overridden in subclasses or customizations",
            ]
        )

        return "\n".join(lines)

    def _get_tenant_field(self, entity: ir.EntitySpec) -> ir.FieldSpec | None:
        """
        Detect if entity uses multi_tenant_isolation pattern and return the tenant field.

        Pattern detected by finding a required reference field to an Organization
        or other tenant entity (commonly named organization_id).
        """
        # Common tenant field names
        tenant_field_names = ["organization_id", "tenant_id", "account_id", "company_id"]

        for field in entity.fields:
            if (
                field.type.kind == ir.FieldTypeKind.REF
                and field.is_required
                and field.name in tenant_field_names
            ):
                return field

        return None

    def _generate_multi_tenant_helpers(
        self, entity: ir.EntitySpec, tenant_field: ir.FieldSpec
    ) -> str:
        """
        Generate multi-tenant isolation helpers.

        Implements multi_tenant_isolation pattern:
        - Class method for tenant-scoped queries
        - Documentation about tenant isolation
        """
        field_name = tenant_field.name
        tenant_entity = tenant_field.type.ref_entity or "Organization"

        lines = [
            "    @classmethod",
            f"    def for_tenant(cls, {field_name}):",
            '        """',
            "        Get queryset scoped to specific tenant.",
            "        ",
            "        This model uses multi-tenant isolation. All queries should be",
            f"        scoped to a tenant using this method or by filtering on {field_name}.",
            "        ",
            "        Args:",
            f"            {field_name}: The {tenant_entity} to scope queries to",
            "        ",
            "        Returns:",
            "            QuerySet filtered to the specified tenant",
            "        ",
            "        Example:",
            f"            tenant = {tenant_entity}.objects.get(id=tenant_id)",
            f"            items = {entity.name}.for_tenant(tenant)",
            '        """',
            f"        return cls.objects.filter({field_name}={field_name})",
        ]

        return "\n".join(lines)
