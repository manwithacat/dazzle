"""
Mock data generator for static preview pages.

Generates realistic-looking sample data from entity specifications
for use in preview HTML files that work without a server.
"""

from __future__ import annotations

import random
import uuid
from typing import Any

from dazzle.core import ir
from dazzle.core.ir import FieldTypeKind
from dazzle.testing.field_value_gen import generate_field_value


def _generate_field_value(field: ir.FieldSpec, index: int) -> Any:
    """Generate a realistic mock value for a field."""
    return generate_field_value(field, index=index, realistic=True)


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
