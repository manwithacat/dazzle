"""Tests for the FK graph used in scope path validation."""

import pytest

from dazzle.core import ir
from dazzle.core.ir.fields import FieldModifier, FieldSpec, FieldType, FieldTypeKind
from dazzle.core.ir.fk_graph import FKGraph

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _entity(name: str, fields: list[FieldSpec]) -> ir.EntitySpec:
    return ir.EntitySpec(name=name, title=name, fields=fields)


def _field(
    name: str,
    kind: FieldTypeKind = FieldTypeKind.STR,
    ref: str | None = None,
) -> FieldSpec:
    return FieldSpec(name=name, type=FieldType(kind=kind, ref_entity=ref))


def _pk() -> FieldSpec:
    return FieldSpec(
        name="id",
        type=FieldType(kind=FieldTypeKind.UUID),
        modifiers=[FieldModifier.PK],
    )


# ---------------------------------------------------------------------------
# TestFKGraphConstruction
# ---------------------------------------------------------------------------


class TestFKGraphConstruction:
    def test_build_from_entities_with_ref_fields_has_edge(self) -> None:
        """Entities with ref fields produce edges in the graph."""
        author = _entity("Author", [_pk(), _field("name")])
        book = _entity(
            "Book",
            [_pk(), _field("author_id", FieldTypeKind.REF, ref="Author")],
        )
        graph = FKGraph.from_entities([author, book])

        assert graph.has_edge("Book", "author_id") is True
        assert graph.resolve_target("Book", "author_id") == "Author"

    def test_no_edge_for_non_ref_field(self) -> None:
        """Non-ref fields do not produce edges."""
        entity = _entity("Task", [_pk(), _field("title")])
        graph = FKGraph.from_entities([entity])

        assert graph.has_edge("Task", "title") is False

    def test_empty_entities_produces_empty_entity_names(self) -> None:
        """Empty entity list results in empty entity_names set."""
        graph = FKGraph.from_entities([])
        assert graph.entity_names() == set()

    def test_self_referential_fk(self) -> None:
        """Self-referential FK (e.g. Employee.manager_id → Employee) is handled."""
        employee = _entity(
            "Employee",
            [
                _pk(),
                _field("name"),
                _field("manager_id", FieldTypeKind.REF, ref="Employee"),
            ],
        )
        graph = FKGraph.from_entities([employee])

        assert graph.has_edge("Employee", "manager_id") is True
        assert graph.resolve_target("Employee", "manager_id") == "Employee"

    def test_belongs_to_produces_edge(self) -> None:
        """belongs_to relationship fields are treated as FK edges."""
        order = _entity("Order", [_pk()])
        item = _entity(
            "OrderItem",
            [_pk(), _field("order_id", FieldTypeKind.BELONGS_TO, ref="Order")],
        )
        graph = FKGraph.from_entities([order, item])

        assert graph.has_edge("OrderItem", "order_id") is True
        assert graph.resolve_target("OrderItem", "order_id") == "Order"

    def test_entity_names_includes_all_entities(self) -> None:
        """entity_names returns all entity names, including those with no FKs."""
        school = _entity("School", [_pk()])
        dept = _entity(
            "Department",
            [_pk(), _field("school_id", FieldTypeKind.REF, ref="School")],
        )
        graph = FKGraph.from_entities([school, dept])
        assert graph.entity_names() == {"School", "Department"}


# ---------------------------------------------------------------------------
# TestPathResolution
# ---------------------------------------------------------------------------


class TestPathResolution:
    @pytest.fixture()
    def chain_graph(self) -> FKGraph:
        """4-entity chain: School → Department → Teacher → Manuscript."""
        school = _entity("School", [_pk(), _field("name")])
        department = _entity(
            "Department",
            [_pk(), _field("school_id", FieldTypeKind.REF, ref="School")],
        )
        teacher = _entity(
            "Teacher",
            [_pk(), _field("department_id", FieldTypeKind.REF, ref="Department")],
        )
        manuscript = _entity(
            "Manuscript",
            [_pk(), _field("teacher_id", FieldTypeKind.REF, ref="Teacher")],
        )
        return FKGraph.from_entities([school, department, teacher, manuscript])

    def test_resolve_segment_by_relation_name(self, chain_graph: FKGraph) -> None:
        """resolve_segment with relation name 'teacher' returns FK field + target."""
        fk_field, target = chain_graph.resolve_segment("Manuscript", "teacher")
        assert fk_field == "teacher_id"
        assert target == "Teacher"

    def test_resolve_segment_by_fk_field_name(self, chain_graph: FKGraph) -> None:
        """resolve_segment with explicit FK field name returns same result."""
        fk_field, target = chain_graph.resolve_segment("Manuscript", "teacher_id")
        assert fk_field == "teacher_id"
        assert target == "Teacher"

    def test_resolve_path_three_deep(self, chain_graph: FKGraph) -> None:
        """resolve_path through 3 FK hops returns 3 PathSteps."""

        steps = chain_graph.resolve_path("Manuscript", ["teacher", "department", "school_id"])
        assert len(steps) == 3

        assert steps[0].from_entity == "Manuscript"
        assert steps[0].fk_field == "teacher_id"
        assert steps[0].target_entity == "Teacher"
        assert steps[0].terminal_field is None

        assert steps[1].from_entity == "Teacher"
        assert steps[1].fk_field == "department_id"
        assert steps[1].target_entity == "Department"
        assert steps[1].terminal_field is None

        assert steps[2].from_entity == "Department"
        assert steps[2].fk_field == "school_id"
        assert steps[2].target_entity == "School"
        assert steps[2].terminal_field == "school_id"

    def test_resolve_path_single_hop(self, chain_graph: FKGraph) -> None:
        """Single-hop path returns one PathStep with terminal_field set."""
        steps = chain_graph.resolve_path("Manuscript", ["teacher_id"])
        assert len(steps) == 1
        assert steps[0].from_entity == "Manuscript"
        assert steps[0].target_entity == "Teacher"
        assert steps[0].terminal_field == "teacher_id"

    def test_invalid_segment_raises_value_error(self, chain_graph: FKGraph) -> None:
        """Invalid segment name raises ValueError mentioning 'has no FK'."""
        with pytest.raises(ValueError, match="has no FK"):
            chain_graph.resolve_segment("Manuscript", "nonexistent")

    def test_field_exists_true(self, chain_graph: FKGraph) -> None:
        """field_exists returns True for known fields."""
        assert chain_graph.field_exists("Manuscript", "teacher_id") is True
        assert chain_graph.field_exists("Manuscript", "id") is True

    def test_field_exists_false(self, chain_graph: FKGraph) -> None:
        """field_exists returns False for unknown fields."""
        assert chain_graph.field_exists("Manuscript", "nonexistent") is False

    def test_resolve_segment_belongs_to_same_as_ref(self) -> None:
        """belongs_to FK resolved identically to ref FK."""
        order = _entity("Order", [_pk()])
        item = _entity(
            "OrderItem",
            [_pk(), _field("order_id", FieldTypeKind.BELONGS_TO, ref="Order")],
        )
        graph = FKGraph.from_entities([order, item])
        fk_field, target = graph.resolve_segment("OrderItem", "order")
        assert fk_field == "order_id"
        assert target == "Order"

    def test_resolve_path_empty_raises(self, chain_graph: FKGraph) -> None:
        """resolve_path with empty list raises ValueError."""
        with pytest.raises(ValueError):
            chain_graph.resolve_path("Manuscript", [])

    def test_resolve_target_returns_none_for_missing(self, chain_graph: FKGraph) -> None:
        """resolve_target returns None for non-existent FK field."""
        assert chain_graph.resolve_target("Manuscript", "bogus_id") is None
