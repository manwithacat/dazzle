"""
Utility functions for FastAPI adapter.

Contains type mappings and string conversion utilities.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dazzle.core.ir import FieldType


# Type mappings from DSL to Python
TYPE_MAPPING = {
    "str": "str",
    "text": "str",
    "int": "int",
    "decimal": "Decimal",
    "bool": "bool",
    "date": "date",
    "datetime": "datetime",
    "uuid": "UUID",
    "email": "EmailStr",
    "ref": "UUID",  # Foreign key
    "has_many": "list",  # Will be customized
    "has_one": "Optional",
    "embeds": "dict",  # Embedded object
    "belongs_to": "UUID",
}


def snake_case(name: str) -> str:
    """Convert PascalCase to snake_case."""
    result = []
    for i, char in enumerate(name):
        if char.isupper() and i > 0:
            result.append("_")
        result.append(char.lower())
    return "".join(result)


def pascal_case(name: str) -> str:
    """Convert snake_case to PascalCase."""
    return "".join(word.capitalize() for word in name.split("_"))


def get_column_type(field_type: "FieldType") -> str:
    """Get SQLAlchemy column type."""
    kind = field_type.kind.value

    if kind == "str":
        max_len = field_type.max_length or 255
        return f"String({max_len})"
    elif kind == "text":
        return "Text"
    elif kind == "int":
        return "Integer"
    elif kind == "decimal":
        precision = field_type.precision or 10
        scale = field_type.scale or 2
        return f"Numeric({precision}, {scale})"
    elif kind == "bool":
        return "Boolean"
    elif kind == "date":
        return "Date"
    elif kind == "datetime":
        return "DateTime"
    elif kind == "uuid":
        return "PGUUID(as_uuid=True)"
    elif kind == "email":
        return "String(255)"
    else:
        return "String(255)"
