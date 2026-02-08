"""Tests for constraint violation error handling (#133 + #134)."""

from __future__ import annotations

from uuid import uuid4

import pytest

from dazzle_back.runtime.repository import (
    ConstraintViolationError,
    DatabaseManager,
    SQLiteRepository,
    _parse_constraint_error,
)
from dazzle_back.specs.entity import EntitySpec, FieldSpec, FieldType, ScalarType

# ---------------------------------------------------------------------------
# _parse_constraint_error
# ---------------------------------------------------------------------------


class TestParseConstraintError:
    """Test error message parsing for SQLite and PostgreSQL patterns."""

    def test_sqlite_unique_with_field(self):
        ctype, field = _parse_constraint_error("UNIQUE constraint failed: Task.slug", "Task")
        assert ctype == "unique"
        assert field == "slug"

    def test_sqlite_unique_no_table_prefix(self):
        ctype, field = _parse_constraint_error("UNIQUE constraint failed: slug", "Task")
        assert ctype == "unique"
        assert field == "slug"

    def test_sqlite_foreign_key(self):
        ctype, field = _parse_constraint_error("FOREIGN KEY constraint failed", "Task")
        assert ctype == "foreign_key"
        assert field is None

    def test_postgres_unique(self):
        ctype, field = _parse_constraint_error(
            'duplicate key value violates unique constraint "task_slug_key" '
            "DETAIL: Key (slug)=(my-slug) already exists.",
            "Task",
        )
        assert ctype == "unique"
        assert field == "slug"

    def test_postgres_foreign_key(self):
        ctype, field = _parse_constraint_error(
            'insert or update on table "task" violates foreign key constraint '
            '"task_project_id_fkey"',
            "Task",
        )
        assert ctype == "foreign_key"
        assert field is None

    def test_unknown_error(self):
        ctype, field = _parse_constraint_error("some other error", "Task")
        assert ctype == "integrity"
        assert field is None


# ---------------------------------------------------------------------------
# Repository integration
# ---------------------------------------------------------------------------


def _make_entity_spec() -> EntitySpec:
    return EntitySpec(
        name="Widget",
        description="Test entity",
        fields=[
            FieldSpec(
                name="id",
                type=FieldType(kind="scalar", scalar_type=ScalarType.UUID),
                required=True,
                unique=True,
            ),
            FieldSpec(
                name="slug",
                type=FieldType(kind="scalar", scalar_type=ScalarType.STR),
                required=True,
                unique=True,
            ),
            FieldSpec(
                name="title",
                type=FieldType(kind="scalar", scalar_type=ScalarType.STR),
                required=False,
            ),
        ],
    )


@pytest.fixture()
def db_and_repo(tmp_path):
    """Create a DB manager, table, and repository."""
    from uuid import UUID as UUIDType

    from pydantic import BaseModel, Field

    class WidgetModel(BaseModel):
        id: UUIDType | None = Field(default=None)
        slug: str
        title: str | None = None

    db = DatabaseManager(db_path=tmp_path / "test.db")
    entity = _make_entity_spec()
    db.create_table(entity)
    repo: SQLiteRepository = SQLiteRepository(  # type: ignore[type-arg]
        db_manager=db, entity_spec=entity, model_class=WidgetModel
    )
    return db, repo


@pytest.mark.asyncio
async def test_unique_violation_on_create(db_and_repo):
    """Inserting a duplicate unique value raises ConstraintViolationError."""
    _, repo = db_and_repo
    id1 = uuid4()
    id2 = uuid4()
    await repo.create({"id": id1, "slug": "hello", "title": "A"})

    with pytest.raises(ConstraintViolationError) as exc_info:
        await repo.create({"id": id2, "slug": "hello", "title": "B"})

    assert exc_info.value.constraint_type == "unique"
    assert exc_info.value.field == "slug"
    assert "already exists" in str(exc_info.value)


@pytest.mark.asyncio
async def test_unique_violation_on_update(db_and_repo):
    """Updating to a duplicate unique value raises ConstraintViolationError."""
    _, repo = db_and_repo
    id1 = uuid4()
    id2 = uuid4()
    await repo.create({"id": id1, "slug": "first", "title": "A"})
    await repo.create({"id": id2, "slug": "second", "title": "B"})

    with pytest.raises(ConstraintViolationError) as exc_info:
        await repo.update(id2, {"slug": "first"})

    assert exc_info.value.constraint_type == "unique"


@pytest.mark.asyncio
async def test_normal_create_succeeds(db_and_repo):
    """Normal create without constraint issues works fine."""
    _, repo = db_and_repo
    result = await repo.create({"id": uuid4(), "slug": "ok", "title": "Fine"})
    assert result.slug == "ok"
