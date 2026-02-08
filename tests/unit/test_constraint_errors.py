"""Tests for constraint violation error handling (#133 + #134 + #146)."""

from __future__ import annotations

from unittest.mock import MagicMock
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
# _parse_constraint_error — string inputs (backwards-compatible)
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

    def test_postgres_foreign_key_no_detail(self):
        """FK error without DETAIL still returns foreign_key type."""
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
# _parse_constraint_error — exception objects (psycopg-style)
# ---------------------------------------------------------------------------


class TestParseConstraintErrorPsycopg:
    """Test FK/unique parsing from psycopg exception objects with pgerror/diag."""

    @staticmethod
    def _make_pg_exc(
        pgerror: str | None = None,
        detail: str | None = None,
        str_repr: str = "",
    ) -> Exception:
        """Build a mock psycopg-style exception."""
        exc = Exception(str_repr)
        if pgerror is not None:
            exc.pgerror = pgerror  # type: ignore[attr-defined]
        diag = MagicMock()
        diag.detail = detail
        exc.diag = diag  # type: ignore[attr-defined]
        return exc

    def test_pg_unique_via_pgerror(self):
        exc = self._make_pg_exc(
            pgerror=(
                'ERROR:  duplicate key value violates unique constraint "task_slug_key"\n'
                "DETAIL:  Key (slug)=(my-slug) already exists.\n"
            ),
            detail="Key (slug)=(my-slug) already exists.",
        )
        ctype, field = _parse_constraint_error(exc, "Task")
        assert ctype == "unique"
        assert field == "slug"

    def test_pg_fk_with_detail_extracts_field(self):
        """FK error with DETAIL extracts field name and referenced table."""
        exc = self._make_pg_exc(
            pgerror=(
                'ERROR:  insert or update on table "task" violates foreign key constraint '
                '"task_assigned_to_fkey"\n'
                "DETAIL:  Key (assigned_to)=(550e8400-e29b-41d4-a716-446655440000) "
                'is not present in table "User".\n'
            ),
            detail=(
                "Key (assigned_to)=(550e8400-e29b-41d4-a716-446655440000) "
                'is not present in table "User".'
            ),
        )
        ctype, field = _parse_constraint_error(exc, "Task")
        assert ctype == "foreign_key"
        assert field == "assigned_to"

    def test_pg_fk_detail_only_on_diag(self):
        """When pgerror is missing, fall back to str(exc) + diag.detail."""
        exc = self._make_pg_exc(
            pgerror=None,
            detail='Key (project_id)=(abc) is not present in table "Project".',
            str_repr=(
                'insert or update on table "task" violates foreign key constraint '
                '"task_project_id_fkey"'
            ),
        )
        ctype, field = _parse_constraint_error(exc, "Task")
        assert ctype == "foreign_key"
        assert field == "project_id"

    def test_pg_fk_no_detail_at_all(self):
        """FK error with no DETAIL still returns foreign_key with field=None."""
        exc = self._make_pg_exc(
            pgerror=(
                'ERROR:  insert or update on table "task" violates foreign key constraint '
                '"task_project_id_fkey"\n'
            ),
            detail=None,
        )
        ctype, field = _parse_constraint_error(exc, "Task")
        assert ctype == "foreign_key"
        assert field is None

    def test_pg_unique_detail_from_diag_only(self):
        """Unique error where Key() is only in diag.detail, not in str(exc)."""
        exc = self._make_pg_exc(
            pgerror=None,
            detail="Key (email)=(a@b.com) already exists.",
            str_repr='duplicate key value violates unique constraint "user_email_key"',
        )
        ctype, field = _parse_constraint_error(exc, "User")
        assert ctype == "unique"
        assert field == "email"


# ---------------------------------------------------------------------------
# Repository integration — unique constraints
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


# ---------------------------------------------------------------------------
# Repository integration — FK constraints (SQLite with PRAGMA foreign_keys)
# ---------------------------------------------------------------------------


def _make_parent_child_specs() -> tuple[EntitySpec, EntitySpec]:
    """Create parent (Team) and child (Player) entity specs with an FK relation."""
    team = EntitySpec(
        name="Team",
        description="Team entity",
        fields=[
            FieldSpec(
                name="id",
                type=FieldType(kind="scalar", scalar_type=ScalarType.UUID),
                required=True,
            ),
            FieldSpec(
                name="name",
                type=FieldType(kind="scalar", scalar_type=ScalarType.STR),
                required=True,
            ),
        ],
    )
    player = EntitySpec(
        name="Player",
        description="Player entity",
        fields=[
            FieldSpec(
                name="id",
                type=FieldType(kind="scalar", scalar_type=ScalarType.UUID),
                required=True,
            ),
            FieldSpec(
                name="team_id",
                type=FieldType(kind="ref", ref_entity="Team"),
                required=True,
            ),
            FieldSpec(
                name="name",
                type=FieldType(kind="scalar", scalar_type=ScalarType.STR),
                required=True,
            ),
        ],
    )
    return team, player


@pytest.fixture()
def fk_db_and_repos(tmp_path):
    """Create DB with FK-constrained tables and repos for Team + Player."""
    from uuid import UUID as UUIDType

    from pydantic import BaseModel, Field

    class TeamModel(BaseModel):
        id: UUIDType | None = Field(default=None)
        name: str

    class PlayerModel(BaseModel):
        id: UUIDType | None = Field(default=None)
        team_id: UUIDType | None = Field(default=None)
        name: str

    db = DatabaseManager(db_path=tmp_path / "fk_test.db")
    team_spec, player_spec = _make_parent_child_specs()

    # Use create_all_tables which builds a registry with FK constraints
    db.create_all_tables([team_spec, player_spec])

    team_repo: SQLiteRepository = SQLiteRepository(  # type: ignore[type-arg]
        db_manager=db, entity_spec=team_spec, model_class=TeamModel
    )
    player_repo: SQLiteRepository = SQLiteRepository(  # type: ignore[type-arg]
        db_manager=db, entity_spec=player_spec, model_class=PlayerModel
    )
    return db, team_repo, player_repo


@pytest.mark.asyncio
async def test_fk_violation_on_create(fk_db_and_repos):
    """Inserting a child with a non-existent parent FK raises ConstraintViolationError."""
    _, _team_repo, player_repo = fk_db_and_repos
    fake_team_id = uuid4()

    with pytest.raises(ConstraintViolationError) as exc_info:
        await player_repo.create({"id": uuid4(), "team_id": fake_team_id, "name": "Ghost Player"})

    assert exc_info.value.constraint_type == "foreign_key"


@pytest.mark.asyncio
async def test_fk_valid_reference_succeeds(fk_db_and_repos):
    """Inserting a child with a valid parent FK works fine."""
    _, team_repo, player_repo = fk_db_and_repos
    team_id = uuid4()
    await team_repo.create({"id": team_id, "name": "Red Team"})

    result = await player_repo.create({"id": uuid4(), "team_id": team_id, "name": "Alice"})
    assert result.name == "Alice"


# ---------------------------------------------------------------------------
# psycopg subclass detection via MRO (#151)
# ---------------------------------------------------------------------------


class TestPsycopgSubclassDetection:
    """Verify that psycopg IntegrityError subclasses are caught via MRO check.

    psycopg raises ForeignKeyViolation and UniqueViolation which inherit from
    IntegrityError but whose __name__ does NOT contain 'IntegrityError'.
    The MRO-based check must walk the inheritance chain.
    """

    @staticmethod
    def _make_subclass(name: str, base_name: str = "IntegrityError") -> type:
        """Create a fake exception class hierarchy mimicking psycopg."""
        # psycopg.errors.IntegrityError → DatabaseError → Error → Exception
        pg_error = type("Error", (Exception,), {})
        db_error = type("DatabaseError", (pg_error,), {})
        integrity = type(base_name, (db_error,), {})
        subclass = type(name, (integrity,), {})
        return subclass

    def test_foreign_key_violation_detected(self):
        """ForeignKeyViolation (subclass of IntegrityError) is caught."""
        FKV = self._make_subclass("ForeignKeyViolation")
        exc = FKV("FOREIGN KEY constraint failed")
        assert any("IntegrityError" in cls.__name__ for cls in type(exc).__mro__)

    def test_unique_violation_detected(self):
        """UniqueViolation (subclass of IntegrityError) is caught."""
        UV = self._make_subclass("UniqueViolation")
        exc = UV("UNIQUE constraint failed: Task.slug")
        assert any("IntegrityError" in cls.__name__ for cls in type(exc).__mro__)

    def test_direct_integrity_error_detected(self):
        """Direct IntegrityError (not a subclass) is still caught."""
        IE = self._make_subclass("IntegrityError", base_name="DatabaseError")
        # IE itself is named IntegrityError
        IE = type("IntegrityError", (Exception,), {})
        exc = IE("some error")
        assert any("IntegrityError" in cls.__name__ for cls in type(exc).__mro__)

    def test_unrelated_exception_not_detected(self):
        """A normal Exception should NOT match the IntegrityError check."""
        exc = ValueError("not an integrity error")
        assert not any("IntegrityError" in cls.__name__ for cls in type(exc).__mro__)

    def test_parse_constraint_error_with_subclass(self):
        """_parse_constraint_error works with psycopg-style subclass exceptions."""
        FKV = self._make_subclass("ForeignKeyViolation")
        exc = FKV("FOREIGN KEY constraint failed")
        ctype, field = _parse_constraint_error(exc, "Task")
        assert ctype == "foreign_key"

    def test_parse_constraint_error_unique_subclass(self):
        """_parse_constraint_error parses unique violations from subclass."""
        UV = self._make_subclass("UniqueViolation")
        exc = UV("UNIQUE constraint failed: Task.slug")
        ctype, field = _parse_constraint_error(exc, "Task")
        assert ctype == "unique"
        assert field == "slug"
