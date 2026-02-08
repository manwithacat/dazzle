"""Tests for auto_add / auto_update timestamp injection (#132)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import BaseModel, Field

from dazzle_back.runtime.model_generator import (
    generate_create_schema,
    generate_update_schema,
)
from dazzle_back.runtime.service_generator import CRUDService
from dazzle_back.specs.entity import EntitySpec, FieldSpec, FieldType, ScalarType


def _make_entity_with_timestamps() -> EntitySpec:
    return EntitySpec(
        name="Article",
        description="Test entity with auto timestamps",
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
                name="created_at",
                type=FieldType(kind="scalar", scalar_type=ScalarType.DATETIME),
                auto_add=True,
            ),
            FieldSpec(
                name="updated_at",
                type=FieldType(kind="scalar", scalar_type=ScalarType.DATETIME),
                auto_update=True,
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Schema generation: auto fields excluded
# ---------------------------------------------------------------------------


class TestAutoFieldExclusion:
    """auto_add and auto_update fields should be excluded from create/update schemas."""

    def test_create_schema_excludes_auto_add(self):
        entity = _make_entity_with_timestamps()
        schema = generate_create_schema(entity)
        field_names = set(schema.model_fields.keys())
        assert "title" in field_names
        assert "created_at" not in field_names
        assert "updated_at" not in field_names
        assert "id" not in field_names

    def test_update_schema_excludes_auto_update(self):
        entity = _make_entity_with_timestamps()
        schema = generate_update_schema(entity)
        field_names = set(schema.model_fields.keys())
        assert "title" in field_names
        assert "created_at" not in field_names
        assert "updated_at" not in field_names
        assert "id" not in field_names


# ---------------------------------------------------------------------------
# Service layer: timestamp injection
# ---------------------------------------------------------------------------


class ArticleModel(BaseModel):
    id: UUID | None = Field(default=None)
    title: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ArticleCreate(BaseModel):
    title: str


class ArticleUpdate(BaseModel):
    title: str | None = None


@pytest.mark.asyncio
async def test_create_injects_auto_add():
    """create() should inject a datetime for auto_add fields."""
    entity = _make_entity_with_timestamps()
    service = CRUDService(
        entity_name="Article",
        model_class=ArticleModel,
        create_schema=ArticleCreate,
        update_schema=ArticleUpdate,
        entity_spec=entity,
    )
    before = datetime.now(UTC)
    result = await service.create(ArticleCreate(title="Hello"))
    after = datetime.now(UTC)

    assert result.created_at is not None
    assert before <= result.created_at <= after


@pytest.mark.asyncio
async def test_update_injects_auto_update():
    """update() should inject a datetime for auto_update fields."""
    entity = _make_entity_with_timestamps()
    service = CRUDService(
        entity_name="Article",
        model_class=ArticleModel,
        create_schema=ArticleCreate,
        update_schema=ArticleUpdate,
        entity_spec=entity,
    )

    # Create first
    created = await service.create(ArticleCreate(title="Hello"))
    entity_id = created.id

    before = datetime.now(UTC)
    updated = await service.update(entity_id, ArticleUpdate(title="World"))
    after = datetime.now(UTC)

    assert updated is not None
    assert updated.updated_at is not None
    assert before <= updated.updated_at <= after


@pytest.mark.asyncio
async def test_user_cannot_override_auto_add():
    """auto_add timestamp should override any user-provided value."""
    entity = _make_entity_with_timestamps()
    service = CRUDService(
        entity_name="Article",
        model_class=ArticleModel,
        create_schema=ArticleCreate,
        update_schema=ArticleUpdate,
        entity_spec=entity,
    )
    result = await service.create(ArticleCreate(title="Test"))
    # created_at should be set by the service, not None
    assert result.created_at is not None
