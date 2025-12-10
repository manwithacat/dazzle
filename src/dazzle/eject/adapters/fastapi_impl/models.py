"""
FastAPI model generation.

Generates SQLAlchemy models from entity specifications.
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent
from typing import TYPE_CHECKING

from dazzle.eject.generator import GeneratorResult

from .utils import get_column_type, pascal_case, snake_case

if TYPE_CHECKING:
    from dazzle.core.ir import EntitySpec, FieldSpec


def generate_base_model() -> str:
    """Generate base model with common fields."""
    return dedent('''
        """
        Base model with common functionality.
        Generated from DSL - DO NOT EDIT.
        """
        from datetime import UTC, datetime
        from uuid import UUID, uuid4

        from sqlalchemy import Column, DateTime, String
        from sqlalchemy.dialects.postgresql import UUID as PGUUID
        from sqlalchemy.ext.declarative import declarative_base

        Base = declarative_base()


        def _utcnow() -> datetime:
            """Return current UTC datetime (timezone-aware)."""
            return datetime.now(UTC)


        class TimestampMixin:
            """Mixin for created_at and updated_at fields."""

            created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
            updated_at = Column(
                DateTime(timezone=True),
                default=_utcnow,
                onupdate=_utcnow,
                nullable=False,
            )


        class UUIDMixin:
            """Mixin for UUID primary key."""

            id = Column(
                PGUUID(as_uuid=True),
                primary_key=True,
                default=uuid4,
            )
    ''').strip()


def generate_entity_model(entity: "EntitySpec") -> str:
    """Generate SQLAlchemy model for an entity."""
    lines = [
        '"""',
        f"{entity.name} entity model.",
        "Generated from DSL - DO NOT EDIT.",
        '"""',
        "from datetime import date, datetime",
        "from decimal import Decimal",
        "from enum import Enum",
        "from typing import Optional",
        "from uuid import UUID",
        "",
        "from sqlalchemy import Column, String, Integer, Boolean, Date, DateTime, Numeric, Text, ForeignKey, Enum as SQLEnum",
        "from sqlalchemy.dialects.postgresql import UUID as PGUUID",
        "from sqlalchemy.orm import relationship",
        "",
        "from .base import Base, TimestampMixin",
        "",
    ]

    # Generate enums
    for field in entity.fields:
        if field.type.kind.value == "enum" and field.type.enum_values:
            enum_name = f"{entity.name}{pascal_case(field.name)}"
            lines.append(f"class {enum_name}(str, Enum):")
            for val in field.type.enum_values:
                lines.append(f'    {val.upper()} = "{val}"')
            lines.append("")

    # Generate model class
    has_timestamps = any(
        f.name in ("created_at", "updated_at") for f in entity.fields
    )
    mixins = ", TimestampMixin" if has_timestamps else ""

    # Add intent as docstring if present
    if entity.intent:
        lines.append(f'class {entity.name}(Base{mixins}):')
        lines.append(f'    """')
        lines.append(f'    {entity.intent}')
        lines.append(f'    """')
    else:
        lines.append(f'class {entity.name}(Base{mixins}):')
        lines.append(f'    """{entity.title or entity.name} entity."""')

    lines.append(f'    __tablename__ = "{snake_case(entity.name)}s"')
    lines.append("")

    # Generate columns
    for field in entity.fields:
        # Skip timestamp fields if using mixin
        if has_timestamps and field.name in ("created_at", "updated_at"):
            continue

        column_def = _generate_column(field, entity)
        if column_def:
            lines.append(f"    {column_def}")

    return "\n".join(lines)


def _generate_column(field: "FieldSpec", entity: "EntitySpec") -> str:
    """Generate SQLAlchemy column definition."""
    kind = field.type.kind.value

    # Handle primary key
    if field.is_primary_key:
        return f'{field.name} = Column(PGUUID(as_uuid=True), primary_key=True)'

    # Handle relationships
    if kind == "ref":
        ref_entity = field.type.ref_entity
        ref_table = snake_case(ref_entity) + "s"
        nullable = "False" if field.is_required else "True"
        return f'{field.name}_id = Column(PGUUID(as_uuid=True), ForeignKey("{ref_table}.id"), nullable={nullable})'

    if kind in ("has_many", "has_one", "belongs_to"):
        # These are relationship fields, handled separately
        ref_entity = field.type.ref_entity
        if kind == "has_many":
            return f'{field.name} = relationship("{ref_entity}", back_populates="{snake_case(entity.name)}")'
        elif kind == "belongs_to":
            return f'{field.name} = relationship("{ref_entity}", back_populates="{snake_case(entity.name)}s")'
        return ""

    # Handle enums
    if kind == "enum":
        enum_name = f"{entity.name}{pascal_case(field.name)}"
        nullable = "False" if field.is_required else "True"
        default = f', default={enum_name}.{field.default.upper()}' if field.default else ""
        return f'{field.name} = Column(SQLEnum({enum_name}), nullable={nullable}{default})'

    # Handle basic types
    col_type = get_column_type(field.type)
    nullable = "False" if field.is_required else "True"
    default = f", default={repr(field.default)}" if field.default is not None else ""

    return f'{field.name} = Column({col_type}, nullable={nullable}{default})'


class ModelGenerator:
    """Generates SQLAlchemy models for FastAPI adapter."""

    def __init__(self, spec, output_dir: Path, write_file_fn, ensure_dir_fn):
        self.spec = spec
        self.output_dir = output_dir
        self.backend_dir = output_dir / "backend"
        self._write_file = write_file_fn
        self._ensure_dir = ensure_dir_fn

    def generate_models(self) -> GeneratorResult:
        """Generate entity models."""
        result = GeneratorResult()

        models_dir = self.backend_dir / "models"
        self._ensure_dir(models_dir)

        # Generate base model
        base_content = generate_base_model()
        base_path = models_dir / "base.py"
        self._write_file(base_path, base_content)
        result.add_file(base_path)

        # Generate model for each entity
        imports = ['"""Entity models."""\n']
        for entity in self.spec.domain.entities:
            model_content = generate_entity_model(entity)
            model_path = models_dir / f"{snake_case(entity.name)}.py"
            self._write_file(model_path, model_content)
            result.add_file(model_path)
            imports.append(
                f"from .{snake_case(entity.name)} import {entity.name}"
            )

        # Generate __init__.py
        init_content = "\n".join(imports) + "\n"
        init_path = models_dir / "__init__.py"
        self._write_file(init_path, init_content)
        result.add_file(init_path)

        return result
