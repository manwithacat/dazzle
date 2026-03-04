"""
Tests for circular FK migration handling.

Verifies that the migration planner correctly handles circular foreign key
references by deferring FK constraints to ALTER TABLE statements.
"""

from __future__ import annotations

from dazzle_back.runtime.migrations import MigrationAction, MigrationPlanner
from dazzle_back.runtime.relation_loader import (
    RelationRegistry,
    get_foreign_key_constraints,
)
from dazzle_back.specs.entity import EntitySpec, FieldSpec, FieldType, ScalarType

# =============================================================================
# Helpers
# =============================================================================


def _entity(name: str, fields: list[FieldSpec]) -> EntitySpec:
    """Shorthand for creating an EntitySpec."""
    return EntitySpec(name=name, fields=fields)


def _field(name: str, kind: str = "scalar", scalar_type: ScalarType | None = None, **kwargs):
    """Shorthand for creating a FieldSpec."""
    ft_kwargs: dict = {"kind": kind}
    if scalar_type:
        ft_kwargs["scalar_type"] = scalar_type
    ft_kwargs.update({k: v for k, v in kwargs.items() if k in ("ref_entity", "enum_values")})
    field_kwargs = {k: v for k, v in kwargs.items() if k not in ("ref_entity", "enum_values")}
    return FieldSpec(name=name, type=FieldType(**ft_kwargs), **field_kwargs)


# =============================================================================
# Deferred FK Constraint Generation
# =============================================================================


class TestDeferredFKConstraints:
    """Test MigrationPlanner._plan_deferred_fk_constraints()."""

    def _make_planner(self):
        """Create a planner with a dummy db_manager (won't be used for these tests)."""
        return MigrationPlanner(db_manager=None)

    def test_generates_alter_table_for_circular_refs(self):
        """Circular FK edges produce ADD_CONSTRAINT steps."""
        entities = [
            _entity(
                "Department",
                [
                    _field("id", scalar_type=ScalarType.UUID),
                    _field("head", kind="ref", ref_entity="User"),
                ],
            ),
            _entity(
                "User",
                [
                    _field("id", scalar_type=ScalarType.UUID),
                    _field("department", kind="ref", ref_entity="Department"),
                ],
            ),
        ]
        circular_edges = {("Department", "User"), ("User", "Department")}
        entity_map = {e.name: e for e in entities}

        planner = self._make_planner()
        steps = planner._plan_deferred_fk_constraints(entities, circular_edges, entity_map)

        assert len(steps) == 2

        # All steps should be ADD_CONSTRAINT
        assert all(s.action == MigrationAction.ADD_CONSTRAINT for s in steps)

        # Check SQL contains ALTER TABLE and FOREIGN KEY
        for step in steps:
            assert step.sql is not None
            assert "ALTER TABLE" in step.sql
            assert "FOREIGN KEY" in step.sql
            assert "REFERENCES" in step.sql
            # Idempotent via DO block
            assert "DO $$" in step.sql
            assert "duplicate_object" in step.sql

    def test_no_steps_for_non_circular_refs(self):
        """Non-circular FK refs don't produce deferred constraint steps."""
        entities = [
            _entity("Client", [_field("id", scalar_type=ScalarType.UUID)]),
            _entity(
                "Invoice",
                [
                    _field("id", scalar_type=ScalarType.UUID),
                    _field("client", kind="ref", ref_entity="Client"),
                ],
            ),
        ]
        circular_edges: set[tuple[str, str]] = set()  # No cycles
        entity_map = {e.name: e for e in entities}

        planner = self._make_planner()
        steps = planner._plan_deferred_fk_constraints(entities, circular_edges, entity_map)

        assert len(steps) == 0

    def test_constraint_names_are_deterministic(self):
        """Constraint names follow the pattern fk_{entity}_{field}_{ref}."""
        entities = [
            _entity(
                "Department",
                [
                    _field("id", scalar_type=ScalarType.UUID),
                    _field("head", kind="ref", ref_entity="User"),
                ],
            ),
            _entity(
                "User",
                [
                    _field("id", scalar_type=ScalarType.UUID),
                    _field("department", kind="ref", ref_entity="Department"),
                ],
            ),
        ]
        circular_edges = {("Department", "User"), ("User", "Department")}
        entity_map = {e.name: e for e in entities}

        planner = self._make_planner()
        steps = planner._plan_deferred_fk_constraints(entities, circular_edges, entity_map)

        constraint_names = set()
        for step in steps:
            assert step.sql is not None
            # Extract constraint name from SQL
            if "fk_Department_head_User" in step.sql:
                constraint_names.add("fk_Department_head_User")
            if "fk_User_department_Department" in step.sql:
                constraint_names.add("fk_User_department_Department")

        assert "fk_Department_head_User" in constraint_names
        assert "fk_User_department_Department" in constraint_names

    def test_only_circular_edges_get_deferred(self):
        """In mixed scenario, only circular edges produce deferred steps."""
        entities = [
            _entity(
                "Department",
                [
                    _field("id", scalar_type=ScalarType.UUID),
                    _field("head", kind="ref", ref_entity="User"),
                ],
            ),
            _entity(
                "User",
                [
                    _field("id", scalar_type=ScalarType.UUID),
                    _field("department", kind="ref", ref_entity="Department"),
                ],
            ),
            _entity(
                "Invoice",
                [
                    _field("id", scalar_type=ScalarType.UUID),
                    _field("user", kind="ref", ref_entity="User"),
                ],
            ),
        ]
        circular_edges = {("Department", "User"), ("User", "Department")}
        entity_map = {e.name: e for e in entities}

        planner = self._make_planner()
        steps = planner._plan_deferred_fk_constraints(entities, circular_edges, entity_map)

        # Only Department.head->User and User.department->Department
        # Invoice.user->User is NOT circular, so no deferred step for it
        tables_with_steps = {s.table for s in steps}
        assert "Invoice" not in tables_with_steps
        assert "Department" in tables_with_steps
        assert "User" in tables_with_steps


# =============================================================================
# Relation Loader: exclude_edges
# =============================================================================


class TestGetForeignKeyConstraintsExcludeEdges:
    """Test get_foreign_key_constraints() with exclude_edges parameter."""

    def _make_registry(self, entities):
        """Build a RelationRegistry from entities."""
        return RelationRegistry.from_entities(entities)

    def test_exclude_edges_skips_circular_fk(self):
        """Circular FK constraints are excluded when exclude_edges is set."""
        entities = [
            _entity(
                "Department",
                [
                    _field("id", scalar_type=ScalarType.UUID),
                    _field("head", kind="ref", ref_entity="User"),
                ],
            ),
            _entity(
                "User",
                [
                    _field("id", scalar_type=ScalarType.UUID),
                    _field("department", kind="ref", ref_entity="Department"),
                ],
            ),
        ]
        registry = self._make_registry(entities)
        exclude = {("Department", "User"), ("User", "Department")}

        # Department's FK to User should be excluded
        dept_fks = get_foreign_key_constraints(entities[0], registry, exclude_edges=exclude)
        assert len(dept_fks) == 0

        # User's FK to Department should be excluded
        user_fks = get_foreign_key_constraints(entities[1], registry, exclude_edges=exclude)
        assert len(user_fks) == 0

    def test_no_exclude_includes_all_fks(self):
        """Without exclude_edges, all FK constraints are included."""
        entities = [
            _entity(
                "Department",
                [
                    _field("id", scalar_type=ScalarType.UUID),
                    _field("head", kind="ref", ref_entity="User"),
                ],
            ),
            _entity(
                "User",
                [
                    _field("id", scalar_type=ScalarType.UUID),
                    _field("department", kind="ref", ref_entity="Department"),
                ],
            ),
        ]
        registry = self._make_registry(entities)

        dept_fks = get_foreign_key_constraints(entities[0], registry)
        assert len(dept_fks) == 1
        assert "FOREIGN KEY" in dept_fks[0]

    def test_exclude_only_affects_specified_edges(self):
        """Only edges in exclude_edges are skipped; others remain."""
        entities = [
            _entity(
                "Department",
                [
                    _field("id", scalar_type=ScalarType.UUID),
                    _field("head", kind="ref", ref_entity="User"),
                ],
            ),
            _entity(
                "User",
                [
                    _field("id", scalar_type=ScalarType.UUID),
                    _field("department", kind="ref", ref_entity="Department"),
                ],
            ),
            _entity(
                "Invoice",
                [
                    _field("id", scalar_type=ScalarType.UUID),
                    _field("user", kind="ref", ref_entity="User"),
                ],
            ),
        ]
        registry = self._make_registry(entities)
        exclude = {("Department", "User"), ("User", "Department")}

        # Invoice's FK to User is NOT in exclude_edges, so it stays
        invoice_fks = get_foreign_key_constraints(entities[2], registry, exclude_edges=exclude)
        assert len(invoice_fks) == 1
        assert "FOREIGN KEY" in invoice_fks[0]


# =============================================================================
# CREATE TABLE SQL Exclusion
# =============================================================================


class TestCreateTableSQLExclusion:
    """Test that _generate_create_table_sql excludes circular FKs."""

    def _make_planner(self):
        return MigrationPlanner(db_manager=None)

    def test_create_table_excludes_circular_fk(self):
        """CREATE TABLE SQL should not contain FK for circular edges."""
        entities = [
            _entity(
                "Department",
                [
                    _field("id", scalar_type=ScalarType.UUID),
                    _field("head", kind="ref", ref_entity="User"),
                ],
            ),
            _entity(
                "User",
                [
                    _field("id", scalar_type=ScalarType.UUID),
                    _field("department", kind="ref", ref_entity="Department"),
                ],
            ),
        ]
        registry = RelationRegistry.from_entities(entities)
        circular_edges = {("Department", "User"), ("User", "Department")}

        planner = self._make_planner()
        sql = planner._generate_create_table_sql(
            entities[0],
            registry=registry,
            circular_edges=circular_edges,
        )

        # Should have CREATE TABLE and columns, but NO FOREIGN KEY clause
        assert "CREATE TABLE" in sql
        assert '"head"' in sql
        assert "FOREIGN KEY" not in sql

    def test_create_table_includes_non_circular_fk(self):
        """CREATE TABLE SQL should include FK for non-circular refs."""
        entities = [
            _entity("Client", [_field("id", scalar_type=ScalarType.UUID)]),
            _entity(
                "Invoice",
                [
                    _field("id", scalar_type=ScalarType.UUID),
                    _field("client", kind="ref", ref_entity="Client"),
                ],
            ),
        ]
        registry = RelationRegistry.from_entities(entities)

        planner = self._make_planner()
        sql = planner._generate_create_table_sql(
            entities[1],
            registry=registry,
            circular_edges=set(),
        )

        assert "CREATE TABLE" in sql
        assert "FOREIGN KEY" in sql
        assert "Client" in sql
