"""
Tests for relationship handling and nested data loading.

Tests relation registry, relation loader, and foreign key handling.
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from dazzle_back.runtime.relation_loader import (
    RelationInfo,
    RelationLoader,
    RelationRegistry,
    build_foreign_key_constraint,
    get_foreign_key_constraints,
    get_foreign_key_indexes,
)
from dazzle_back.specs.entity import (
    EntitySpec,
    FieldSpec,
    FieldType,
    OnDeleteAction,
    RelationKind,
    RelationSpec,
    ScalarType,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def user_entity() -> Any:
    """Create a User entity spec."""
    return EntitySpec(
        name="User",
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
            FieldSpec(
                name="email",
                type=FieldType(kind="scalar", scalar_type=ScalarType.EMAIL),
                required=True,
            ),
        ],
    )


@pytest.fixture
def task_entity() -> Any:
    """Create a Task entity spec with owner relation."""
    return EntitySpec(
        name="Task",
        fields=[
            FieldSpec(
                name="id",
                type=FieldType(kind="scalar", scalar_type=ScalarType.UUID),
                required=True,
            ),
            FieldSpec(
                name="title",
                type=FieldType(kind="scalar", scalar_type=ScalarType.STR),
                required=True,
            ),
            FieldSpec(
                name="owner_id",
                type=FieldType(kind="ref", ref_entity="User"),
                required=True,
            ),
        ],
        relations=[
            RelationSpec(
                name="owner",
                from_entity="Task",
                to_entity="User",
                kind=RelationKind.MANY_TO_ONE,
                on_delete=OnDeleteAction.CASCADE,
            ),
        ],
    )


@pytest.fixture
def comment_entity() -> Any:
    """Create a Comment entity spec."""
    return EntitySpec(
        name="Comment",
        fields=[
            FieldSpec(
                name="id",
                type=FieldType(kind="scalar", scalar_type=ScalarType.UUID),
                required=True,
            ),
            FieldSpec(
                name="text",
                type=FieldType(kind="scalar", scalar_type=ScalarType.TEXT),
                required=True,
            ),
            FieldSpec(
                name="task_id",
                type=FieldType(kind="ref", ref_entity="Task"),
                required=True,
            ),
        ],
    )


@pytest.fixture
def all_entities(user_entity: Any, task_entity: Any, comment_entity: Any) -> Any:
    """Get all test entities."""
    return [user_entity, task_entity, comment_entity]


@pytest.fixture
def test_db() -> Any:
    """Create a test database with tables."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Create tables
    conn.execute("""
        CREATE TABLE User (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE Task (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            owner_id TEXT NOT NULL,
            FOREIGN KEY (owner_id) REFERENCES User(id)
        )
    """)

    conn.execute("""
        CREATE TABLE Comment (
            id TEXT PRIMARY KEY,
            text TEXT NOT NULL,
            task_id TEXT NOT NULL,
            FOREIGN KEY (task_id) REFERENCES Task(id)
        )
    """)

    # Insert test data
    user_id = str(uuid4())
    task_id = str(uuid4())
    comment_id = str(uuid4())

    conn.execute(
        "INSERT INTO User (id, name, email) VALUES (?, ?, ?)",
        (user_id, "John Doe", "john@example.com"),
    )
    conn.execute(
        "INSERT INTO Task (id, title, owner_id) VALUES (?, ?, ?)",
        (task_id, "Test Task", user_id),
    )
    conn.execute(
        "INSERT INTO Comment (id, text, task_id) VALUES (?, ?, ?)",
        (comment_id, "Test comment", task_id),
    )

    conn.commit()

    yield conn, {"user_id": user_id, "task_id": task_id, "comment_id": comment_id}

    conn.close()
    Path(db_path).unlink(missing_ok=True)


# =============================================================================
# RelationInfo Tests
# =============================================================================


class TestRelationInfo:
    """Tests for RelationInfo."""

    def test_is_to_one_many_to_one(self) -> None:
        """Test is_to_one for many-to-one relation."""
        info = RelationInfo(
            name="owner",
            from_entity="Task",
            to_entity="User",
            kind="many_to_one",
            foreign_key_field="owner_id",
        )

        assert info.is_to_one is True
        assert info.is_to_many is False

    def test_is_to_one_one_to_one(self) -> None:
        """Test is_to_one for one-to-one relation."""
        info = RelationInfo(
            name="profile",
            from_entity="User",
            to_entity="Profile",
            kind="one_to_one",
            foreign_key_field="profile_id",
        )

        assert info.is_to_one is True
        assert info.is_to_many is False

    def test_is_to_many_one_to_many(self) -> None:
        """Test is_to_many for one-to-many relation."""
        info = RelationInfo(
            name="tasks",
            from_entity="User",
            to_entity="Task",
            kind="one_to_many",
            foreign_key_field="owner_id",
        )

        assert info.is_to_many is True
        assert info.is_to_one is False

    def test_is_to_many_many_to_many(self) -> None:
        """Test is_to_many for many-to-many relation."""
        info = RelationInfo(
            name="tags",
            from_entity="Task",
            to_entity="Tag",
            kind="many_to_many",
            foreign_key_field="task_id",
        )

        assert info.is_to_many is True
        assert info.is_to_one is False


# =============================================================================
# RelationRegistry Tests
# =============================================================================


class TestRelationRegistry:
    """Tests for RelationRegistry."""

    def test_register_and_get(self) -> None:
        """Test registering and retrieving relations."""
        registry = RelationRegistry()
        info = RelationInfo(
            name="owner",
            from_entity="Task",
            to_entity="User",
            kind="many_to_one",
            foreign_key_field="owner_id",
        )
        registry.register("Task", info)

        assert registry.has_relation("Task", "owner")
        assert registry.get_relation("Task", "owner") == info

    def test_get_relations(self) -> None:
        """Test getting all relations for an entity."""
        registry = RelationRegistry()
        info1 = RelationInfo(
            name="owner",
            from_entity="Task",
            to_entity="User",
            kind="many_to_one",
            foreign_key_field="owner_id",
        )
        info2 = RelationInfo(
            name="project",
            from_entity="Task",
            to_entity="Project",
            kind="many_to_one",
            foreign_key_field="project_id",
        )
        registry.register("Task", info1)
        registry.register("Task", info2)

        relations = registry.get_relations("Task")
        assert len(relations) == 2

    def test_has_relation_false(self) -> None:
        """Test has_relation returns False for non-existent relation."""
        registry = RelationRegistry()

        assert registry.has_relation("Task", "nonexistent") is False

    def test_from_entities(self, all_entities: Any) -> None:
        """Test building registry from entity specs."""
        registry = RelationRegistry.from_entities(all_entities)

        # Task should have owner relation
        assert registry.has_relation("Task", "owner")
        owner_rel = registry.get_relation("Task", "owner")
        assert owner_rel is not None
        assert owner_rel.to_entity == "User"

        # Comment should have implicit task relation from ref field
        assert registry.has_relation("Comment", "task")


# =============================================================================
# RelationLoader Tests
# =============================================================================


class TestRelationLoader:
    """Tests for RelationLoader."""

    def test_load_to_one_relation(self, all_entities: Any, test_db: Any) -> None:
        """Test loading a to-one relation."""
        conn, ids = test_db
        registry = RelationRegistry.from_entities(all_entities)
        loader = RelationLoader(registry, all_entities)

        # Create task rows
        rows = [{"id": ids["task_id"], "title": "Test Task", "owner_id": ids["user_id"]}]

        # Load owner relation
        result = loader.load_relations("Task", rows, ["owner"], conn)

        assert len(result) == 1
        assert result[0]["owner"] is not None
        assert result[0]["owner"]["name"] == "John Doe"
        assert result[0]["owner"]["email"] == "john@example.com"

    def test_load_to_one_null_relation(self, all_entities: Any, test_db: Any) -> None:
        """Test loading to-one relation with null FK."""
        conn, ids = test_db
        registry = RelationRegistry.from_entities(all_entities)
        loader = RelationLoader(registry, all_entities)

        # Create task row with no owner_id
        rows = [{"id": str(uuid4()), "title": "Orphan Task", "owner_id": None}]

        result = loader.load_relations("Task", rows, ["owner"], conn)

        assert len(result) == 1
        assert result[0]["owner"] is None

    def test_load_to_many_relation(self, all_entities: Any, test_db: Any) -> None:
        """Test loading a to-many relation."""
        conn, ids = test_db
        registry = RelationRegistry()

        # Register a one-to-many relation from Task to Comment
        registry.register(
            "Task",
            RelationInfo(
                name="comments",
                from_entity="Task",
                to_entity="Comment",
                kind="one_to_many",
                foreign_key_field="task_id",
            ),
        )

        loader = RelationLoader(registry, all_entities)

        rows = [{"id": ids["task_id"], "title": "Test Task"}]
        result = loader.load_relations("Task", rows, ["comments"], conn)

        assert len(result) == 1
        assert "comments" in result[0]
        assert len(result[0]["comments"]) == 1
        assert result[0]["comments"][0]["text"] == "Test comment"

    def test_load_to_many_empty(self, all_entities: Any, test_db: Any) -> None:
        """Test loading to-many relation with no related items."""
        conn, ids = test_db
        registry = RelationRegistry()

        # Register comments relation
        registry.register(
            "Task",
            RelationInfo(
                name="comments",
                from_entity="Task",
                to_entity="Comment",
                kind="one_to_many",
                foreign_key_field="task_id",
            ),
        )

        loader = RelationLoader(registry, all_entities)

        # Create a task with no comments
        new_task_id = str(uuid4())
        conn.execute(
            "INSERT INTO Task (id, title, owner_id) VALUES (?, ?, ?)",
            (new_task_id, "New Task", ids["user_id"]),
        )
        conn.commit()

        rows = [{"id": new_task_id, "title": "New Task"}]
        result = loader.load_relations("Task", rows, ["comments"], conn)

        assert result[0]["comments"] == []

    def test_load_multiple_relations(self, all_entities: Any, test_db: Any) -> None:
        """Test loading multiple relations at once."""
        conn, ids = test_db
        registry = RelationRegistry.from_entities(all_entities)

        # Add comments relation
        registry.register(
            "Task",
            RelationInfo(
                name="comments",
                from_entity="Task",
                to_entity="Comment",
                kind="one_to_many",
                foreign_key_field="task_id",
            ),
        )

        loader = RelationLoader(registry, all_entities)

        rows = [{"id": ids["task_id"], "title": "Test Task", "owner_id": ids["user_id"]}]
        result = loader.load_relations("Task", rows, ["owner", "comments"], conn)

        assert result[0]["owner"] is not None
        assert result[0]["comments"] is not None

    def test_load_unknown_relation(self, all_entities: Any, test_db: Any) -> None:
        """Test loading unknown relation is ignored."""
        conn, ids = test_db
        registry = RelationRegistry.from_entities(all_entities)
        loader = RelationLoader(registry, all_entities)

        rows = [{"id": ids["task_id"], "title": "Test Task"}]
        result = loader.load_relations("Task", rows, ["nonexistent"], conn)

        # Should not modify rows
        assert "nonexistent" not in result[0]

    def test_load_empty_rows(self, all_entities: Any, test_db: Any) -> None:
        """Test loading relations on empty rows list."""
        conn, ids = test_db
        registry = RelationRegistry.from_entities(all_entities)
        loader = RelationLoader(registry, all_entities)

        result = loader.load_relations("Task", [], ["owner"], conn)

        assert result == []

    def test_batch_loading(self, all_entities: Any, test_db: Any) -> None:
        """Test that multiple rows are batch-loaded efficiently."""
        conn, ids = test_db
        registry = RelationRegistry.from_entities(all_entities)
        loader = RelationLoader(registry, all_entities)

        # Create another task for the same user
        task2_id = str(uuid4())
        conn.execute(
            "INSERT INTO Task (id, title, owner_id) VALUES (?, ?, ?)",
            (task2_id, "Task 2", ids["user_id"]),
        )
        conn.commit()

        rows = [
            {"id": ids["task_id"], "title": "Task 1", "owner_id": ids["user_id"]},
            {"id": task2_id, "title": "Task 2", "owner_id": ids["user_id"]},
        ]

        result = loader.load_relations("Task", rows, ["owner"], conn)

        # Both should have the same owner loaded
        assert result[0]["owner"]["id"] == result[1]["owner"]["id"]
        assert result[0]["owner"]["name"] == "John Doe"


# =============================================================================
# Foreign Key Tests
# =============================================================================


class TestForeignKeyConstraints:
    """Tests for FK constraint generation."""

    def test_build_fk_constraint_cascade(self) -> None:
        """Test FK constraint with CASCADE on delete."""
        info = RelationInfo(
            name="owner",
            from_entity="Task",
            to_entity="User",
            kind="many_to_one",
            foreign_key_field="owner_id",
            on_delete="cascade",
        )

        sql = build_foreign_key_constraint(info, "Task")

        assert "FOREIGN KEY (owner_id)" in sql
        assert "REFERENCES User(id)" in sql
        assert "ON DELETE CASCADE" in sql

    def test_build_fk_constraint_restrict(self) -> None:
        """Test FK constraint with RESTRICT on delete."""
        info = RelationInfo(
            name="owner",
            from_entity="Task",
            to_entity="User",
            kind="many_to_one",
            foreign_key_field="owner_id",
            on_delete="restrict",
        )

        sql = build_foreign_key_constraint(info, "Task")

        assert "ON DELETE RESTRICT" in sql

    def test_build_fk_constraint_set_null(self) -> None:
        """Test FK constraint with SET NULL on delete."""
        info = RelationInfo(
            name="owner",
            from_entity="Task",
            to_entity="User",
            kind="many_to_one",
            foreign_key_field="owner_id",
            on_delete="set_null",
        )

        sql = build_foreign_key_constraint(info, "Task")

        assert "ON DELETE SET NULL" in sql

    def test_get_fk_constraints(self, task_entity: Any, all_entities: Any) -> None:
        """Test getting all FK constraints for an entity.

        Task has both an explicit ``owner`` relation (FK inferred as "owner")
        and an implicit relation from the ``owner_id`` ref field (FK = "owner_id"),
        so two constraints are generated.
        """
        registry = RelationRegistry.from_entities(all_entities)
        constraints = get_foreign_key_constraints(task_entity, registry)

        assert len(constraints) == 2
        combined = " ".join(constraints)
        assert "owner_id" in combined
        assert "REFERENCES User(id)" in combined

    def test_get_fk_indexes(self, task_entity: Any, all_entities: Any) -> None:
        """Test getting FK index statements.

        Both the explicit and implicit owner relations produce indexes.
        """
        registry = RelationRegistry.from_entities(all_entities)
        indexes = get_foreign_key_indexes(task_entity, registry)

        assert len(indexes) == 2
        combined = " ".join(indexes)
        assert "CREATE INDEX" in combined
        assert "owner_id" in combined


# =============================================================================
# Edge Cases
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_self_referential_relation(self) -> None:
        """Test self-referential relation (e.g., parent task)."""
        entity = EntitySpec(
            name="Task",
            fields=[
                FieldSpec(
                    name="id",
                    type=FieldType(kind="scalar", scalar_type=ScalarType.UUID),
                ),
                FieldSpec(
                    name="parent_id",
                    type=FieldType(kind="ref", ref_entity="Task"),
                ),
            ],
        )

        registry = RelationRegistry.from_entities([entity])

        assert registry.has_relation("Task", "parent")

    def test_multiple_refs_to_same_entity(self) -> None:
        """Test multiple refs to same entity."""
        entity = EntitySpec(
            name="Task",
            fields=[
                FieldSpec(
                    name="id",
                    type=FieldType(kind="scalar", scalar_type=ScalarType.UUID),
                ),
                FieldSpec(
                    name="created_by_id",
                    type=FieldType(kind="ref", ref_entity="User"),
                ),
                FieldSpec(
                    name="assigned_to_id",
                    type=FieldType(kind="ref", ref_entity="User"),
                ),
            ],
        )

        registry = RelationRegistry.from_entities([entity])

        # Should have both relations
        relations = registry.get_relations("Task")
        assert len(relations) == 2

    def test_relation_with_backref(self) -> None:
        """Test relation with backref name."""
        entity = EntitySpec(
            name="Task",
            fields=[
                FieldSpec(
                    name="id",
                    type=FieldType(kind="scalar", scalar_type=ScalarType.UUID),
                ),
            ],
            relations=[
                RelationSpec(
                    name="owner",
                    from_entity="Task",
                    to_entity="User",
                    kind=RelationKind.MANY_TO_ONE,
                    backref="tasks",
                ),
            ],
        )

        registry = RelationRegistry.from_entities([entity])
        rel = registry.get_relation("Task", "owner")
        assert rel is not None
        assert rel.backref == "tasks"
