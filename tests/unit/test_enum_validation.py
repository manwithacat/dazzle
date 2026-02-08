"""Tests for enum field validation (#130)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from dazzle_back.runtime.model_generator import (
    generate_create_schema,
    generate_entity_model,
    generate_update_schema,
)
from dazzle_back.specs.entity import EntitySpec, FieldSpec, FieldType, ScalarType


def _make_entity_with_enum() -> EntitySpec:
    return EntitySpec(
        name="Ticket",
        description="Test entity with enum field",
        fields=[
            FieldSpec(
                name="id",
                type=FieldType(kind="scalar", scalar_type=ScalarType.UUID),
                required=True,
                unique=True,
            ),
            FieldSpec(
                name="title",
                type=FieldType(kind="scalar", scalar_type=ScalarType.STR),
                required=True,
            ),
            FieldSpec(
                name="priority",
                type=FieldType(kind="enum", enum_values=["low", "medium", "high"]),
                required=True,
            ),
            FieldSpec(
                name="status",
                type=FieldType(kind="enum", enum_values=["open", "closed"]),
                default="open",
            ),
        ],
    )


class TestEnumEntityModel:
    """Test enum validation on the full entity model."""

    def test_valid_enum_accepted(self):
        from uuid import uuid4

        entity = _make_entity_with_enum()
        Model = generate_entity_model(entity)
        instance = Model(id=uuid4(), title="Bug", priority="high")
        assert instance.priority == "high"

    def test_invalid_enum_rejected(self):
        from uuid import uuid4

        entity = _make_entity_with_enum()
        Model = generate_entity_model(entity)
        with pytest.raises(ValidationError) as exc_info:
            Model(id=uuid4(), title="Bug", priority="critical")
        assert "Invalid value 'critical' for 'priority'" in str(exc_info.value)
        assert "Allowed: low, medium, high" in str(exc_info.value)

    def test_default_enum_value(self):
        from uuid import uuid4

        entity = _make_entity_with_enum()
        Model = generate_entity_model(entity)
        instance = Model(id=uuid4(), title="Bug", priority="low")
        assert instance.status == "open"


class TestEnumCreateSchema:
    """Test enum validation on create schema."""

    def test_valid_enum_in_create(self):
        entity = _make_entity_with_enum()
        Schema = generate_create_schema(entity)
        instance = Schema(title="Bug", priority="medium")
        assert instance.priority == "medium"

    def test_invalid_enum_in_create(self):
        entity = _make_entity_with_enum()
        Schema = generate_create_schema(entity)
        with pytest.raises(ValidationError):
            Schema(title="Bug", priority="urgent")


class TestEnumUpdateSchema:
    """Test enum validation on update schema."""

    def test_valid_enum_in_update(self):
        entity = _make_entity_with_enum()
        Schema = generate_update_schema(entity)
        instance = Schema(priority="high")
        assert instance.priority == "high"

    def test_invalid_enum_in_update(self):
        entity = _make_entity_with_enum()
        Schema = generate_update_schema(entity)
        with pytest.raises(ValidationError):
            Schema(priority="urgent")

    def test_none_enum_in_update(self):
        """Optional enum fields should accept None in update schema."""
        entity = _make_entity_with_enum()
        Schema = generate_update_schema(entity)
        instance = Schema()
        assert instance.priority is None
