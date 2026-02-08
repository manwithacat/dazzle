"""
Mock data generator for static preview pages.

Generates realistic-looking sample data from entity specifications
for use in preview HTML files that work without a server.
"""

from __future__ import annotations

import random
import uuid
from datetime import date, datetime, timedelta
from typing import Any

from dazzle.core import ir
from dazzle.core.ir import FieldTypeKind

# Sample data pools
_NAMES = ["Alice Johnson", "Bob Smith", "Carol Williams", "David Brown", "Eve Davis"]
_TITLES = [
    "Fix login page CSS",
    "Add unit tests",
    "Deploy to staging",
    "Review PR #42",
    "Update documentation",
    "Refactor auth module",
    "Add search feature",
    "Fix memory leak",
]
_DESCRIPTIONS = [
    "This needs to be done before the next release.",
    "High priority item from the last sprint review.",
    "Follow up from customer feedback.",
    "",
    "Blocked by upstream dependency.",
]


def _generate_field_value(field: ir.FieldSpec, index: int) -> Any:
    """Generate a realistic mock value for a field."""
    if not field.type:
        return f"sample_{index}"

    kind = field.type.kind

    if kind == FieldTypeKind.UUID:
        return str(uuid.uuid4())
    elif kind == FieldTypeKind.STR:
        if "name" in field.name.lower():
            return _NAMES[index % len(_NAMES)]
        if "title" in field.name.lower():
            return _TITLES[index % len(_TITLES)]
        if "email" in field.name.lower():
            return f"user{index}@example.com"
        return f"{field.name}_{index}"
    elif kind == FieldTypeKind.TEXT:
        return _DESCRIPTIONS[index % len(_DESCRIPTIONS)]
    elif kind == FieldTypeKind.INT:
        return random.randint(1, 100)  # noqa: S311
    elif kind == FieldTypeKind.DECIMAL:
        return round(random.uniform(10.0, 1000.0), 2)  # noqa: S311
    elif kind == FieldTypeKind.BOOL:
        return index % 3 != 0
    elif kind == FieldTypeKind.DATE:
        return (date.today() + timedelta(days=random.randint(-30, 30))).isoformat()  # noqa: S311
    elif kind == FieldTypeKind.DATETIME:
        return (datetime.now() + timedelta(hours=random.randint(-72, 72))).isoformat()  # noqa: S311
    elif kind == FieldTypeKind.ENUM:
        if field.type.enum_values:
            return field.type.enum_values[index % len(field.type.enum_values)]
        return "unknown"
    elif kind == FieldTypeKind.EMAIL:
        return f"user{index}@example.com"
    elif kind == FieldTypeKind.URL:
        return f"https://example.com/{field.name}/{index}"
    elif kind == FieldTypeKind.REF:
        return str(uuid.uuid4())

    return f"mock_{index}"


def generate_mock_records(entity: ir.EntitySpec, count: int = 5) -> list[dict[str, Any]]:
    """
    Generate mock records for an entity.

    Args:
        entity: Entity specification to generate data for.
        count: Number of records to generate.

    Returns:
        List of dictionaries representing mock records.
    """
    records: list[dict[str, Any]] = []

    for i in range(count):
        record: dict[str, Any] = {}
        for field in entity.fields:
            if field.is_primary_key:
                record[field.name] = str(uuid.uuid4())
            elif field.type and field.type.kind == FieldTypeKind.MONEY:
                # Money fields expand to _minor (int) + _currency (str)
                record[f"{field.name}_minor"] = random.randint(1000, 100000)  # noqa: S311
                record[f"{field.name}_currency"] = field.type.currency_code or "GBP"
            else:
                record[field.name] = _generate_field_value(field, i)

        # If entity has a state machine, add status from states
        if entity.state_machine and "status" not in record:
            states = entity.state_machine.states
            record["status"] = states[i % len(states)]

        records.append(record)

    return records
