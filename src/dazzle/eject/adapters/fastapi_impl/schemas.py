"""
FastAPI schema generation.

Generates Pydantic request/response schemas from entity specifications.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from dazzle.eject.generator import GeneratorResult

from .utils import pascal_case, snake_case

if TYPE_CHECKING:
    from dazzle.core.ir import AppSpec, EntitySpec, FieldSpec


def generate_entity_schemas(entity: EntitySpec) -> str:
    """Generate Pydantic schemas for an entity."""
    lines = [
        '"""',
        f"Pydantic schemas for {entity.name}.",
        "Generated from DSL - DO NOT EDIT.",
        '"""',
        "from datetime import date, datetime",
        "from decimal import Decimal",
        "from enum import Enum",
        "from typing import Optional",
        "from uuid import UUID",
        "",
        "from pydantic import BaseModel, Field, EmailStr, ConfigDict",
        "",
    ]

    # Generate enums (same as models)
    for field in entity.fields:
        if field.type.kind.value == "enum" and field.type.enum_values:
            enum_name = f"{entity.name}{pascal_case(field.name)}"
            lines.append(f"class {enum_name}(str, Enum):")
            for val in field.type.enum_values:
                lines.append(f'    {val.upper()} = "{val}"')
            lines.append("")

    # Base schema (shared fields)
    lines.append(f"class {entity.name}Base(BaseModel):")
    if entity.intent:
        lines.append(f'    """{entity.intent}"""')
    lines.append("")

    writable_fields = [
        f
        for f in entity.fields
        if not f.is_primary_key
        and f.name not in ("created_at", "updated_at")
        and f.type.kind.value not in ("has_many", "has_one", "belongs_to")
    ]

    for field in writable_fields:
        field_def = _generate_pydantic_field(field, entity)
        lines.append(f"    {field_def}")

    if not writable_fields:
        lines.append("    pass")

    lines.append("")

    # Create schema
    lines.append(f"class {entity.name}Create({entity.name}Base):")
    lines.append('    """Schema for creating a new record."""')
    lines.append("    pass")
    lines.append("")

    # Update schema (all optional)
    lines.append(f"class {entity.name}Update(BaseModel):")
    lines.append('    """Schema for updating a record."""')
    for field in writable_fields:
        field_def = _generate_pydantic_field(field, entity, optional=True)
        lines.append(f"    {field_def}")
    if not writable_fields:
        lines.append("    pass")
    lines.append("")

    # Read schema (includes all fields)
    lines.append(f"class {entity.name}Read({entity.name}Base):")
    lines.append('    """Schema for reading a record."""')
    lines.append("    model_config = ConfigDict(from_attributes=True)")
    lines.append("")
    lines.append("    id: UUID")

    # Add computed fields as read-only
    for cf in entity.computed_fields:
        # Infer type from expression (simplified)
        lines.append(f"    {cf.name}: Optional[str] = None  # Computed field")

    # Add timestamps if present
    has_created = any(f.name == "created_at" for f in entity.fields)
    has_updated = any(f.name == "updated_at" for f in entity.fields)
    if has_created:
        lines.append("    created_at: datetime")
    if has_updated:
        lines.append("    updated_at: datetime")

    return "\n".join(lines)


def _generate_pydantic_field(
    field: FieldSpec,
    entity: EntitySpec,
    optional: bool = False,
) -> str:
    """Generate Pydantic field definition."""
    kind = field.type.kind.value
    py_type = _get_python_type(field, entity)

    if optional or not field.is_required:
        py_type = f"Optional[{py_type}]"

    default = ""
    if field.default is not None:
        if kind == "enum":
            enum_name = f"{entity.name}{pascal_case(field.name)}"
            default = f" = {enum_name}.{str(field.default).upper()}"
        elif kind == "bool":
            default = f" = {field.default}"
        elif kind == "str" or kind == "text":
            default = f' = "{field.default}"'
        else:
            default = f" = {field.default}"
    elif optional or not field.is_required:
        default = " = None"

    return f"{field.name}: {py_type}{default}"


def _get_python_type(field: FieldSpec, entity: EntitySpec) -> str:
    """Get Python type annotation for a field."""
    kind = field.type.kind.value

    if kind == "enum":
        return f"{entity.name}{pascal_case(field.name)}"
    elif kind == "str":
        return "str"
    elif kind == "text":
        return "str"
    elif kind == "int":
        return "int"
    elif kind == "decimal":
        return "Decimal"
    elif kind == "bool":
        return "bool"
    elif kind == "date":
        return "date"
    elif kind == "datetime":
        return "datetime"
    elif kind == "uuid":
        return "UUID"
    elif kind == "email":
        return "EmailStr"
    elif kind == "ref":
        return "UUID"
    else:
        return "str"


class SchemaGenerator:
    """Generates Pydantic schemas for FastAPI adapter."""

    def __init__(
        self,
        spec: AppSpec,
        output_dir: Path,
        write_file_fn: Callable[[Path, str], None],
        ensure_dir_fn: Callable[[Path], None],
    ) -> None:
        self.spec = spec
        self.output_dir = output_dir
        self.backend_dir = output_dir / "backend"
        self._write_file = write_file_fn
        self._ensure_dir = ensure_dir_fn

    def generate_schemas(self) -> GeneratorResult:
        """Generate Pydantic request/response schemas."""
        result = GeneratorResult()

        schemas_dir = self.backend_dir / "schemas"
        self._ensure_dir(schemas_dir)

        imports = ['"""Request/response schemas."""\n']

        for entity in self.spec.domain.entities:
            schema_content = generate_entity_schemas(entity)
            schema_path = schemas_dir / f"{snake_case(entity.name)}.py"
            self._write_file(schema_path, schema_content)
            result.add_file(schema_path)

            name = entity.name
            imports.append(
                f"from .{snake_case(name)} import {name}Base, {name}Create, {name}Update, {name}Read"
            )

        # Generate __init__.py
        init_content = "\n".join(imports) + "\n"
        init_path = schemas_dir / "__init__.py"
        self._write_file(init_path, init_content)
        result.add_file(init_path)

        return result
