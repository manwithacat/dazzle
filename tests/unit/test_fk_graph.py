"""Tests for the FK graph used in scope path validation."""

from collections.abc import Callable

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


def _ref(name: str, target: str, kind: FieldTypeKind = FieldTypeKind.REF) -> FieldSpec:
    return _field(name, kind, ref=target)


def _chain_graph() -> FKGraph:
    """4-entity chain: School → Department → Teacher → Manuscript."""
    return FKGraph.from_entities(
        [
            _entity("School", [_pk(), _field("name")]),
            _entity("Department", [_pk(), _ref("school_id", "School")]),
            _entity("Teacher", [_pk(), _ref("department_id", "Department")]),
            _entity("Manuscript", [_pk(), _ref("teacher_id", "Teacher")]),
        ]
    )


def _order_item_graph() -> FKGraph:
    """OrderItem.order_id is a belongs_to FK to Order."""
    return FKGraph.from_entities(
        [
            _entity("Order", [_pk()]),
            _entity("OrderItem", [_pk(), _ref("order_id", "Order", FieldTypeKind.BELONGS_TO)]),
        ]
    )


def _invoice_graph() -> FKGraph:
    """Invoice (root) ← Order(invoice) ← LineItem(order); plus an independent Tag."""
    return FKGraph.from_entities(
        [
            _entity("Invoice", [_pk()]),
            _entity("Order", [_pk(), _ref("invoice_id", "Invoice")]),
            _entity("LineItem", [_pk(), _ref("order_id", "Order")]),
            _entity("Tag", [_pk()]),
        ]
    )


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("entities", "source", "field", "expected_target"),
    [
        pytest.param(
            [
                _entity("Author", [_pk(), _field("name")]),
                _entity("Book", [_pk(), _ref("author_id", "Author")]),
            ],
            "Book",
            "author_id",
            "Author",
            id="ref-field-has-edge",
        ),
        pytest.param(
            [_entity("Employee", [_pk(), _field("name"), _ref("manager_id", "Employee")])],
            "Employee",
            "manager_id",
            "Employee",
            id="self-referential-fk",
        ),
        pytest.param(
            [
                _entity("Order", [_pk()]),
                _entity("OrderItem", [_pk(), _ref("order_id", "Order", FieldTypeKind.BELONGS_TO)]),
            ],
            "OrderItem",
            "order_id",
            "Order",
            id="belongs-to-is-edge",
        ),
        pytest.param(
            [_entity("Task", [_pk(), _field("title")])],
            "Task",
            "title",
            None,
            id="non-ref-field-no-edge",
        ),
    ],
)
def test_fk_edge(
    entities: list[ir.EntitySpec], source: str, field: str, expected_target: str | None
) -> None:
    """Ref and belongs_to fields (incl. self-refs) become edges; other fields don't."""
    graph = FKGraph.from_entities(entities)
    assert graph.has_edge(source, field) is (expected_target is not None)
    assert graph.resolve_target(source, field) == expected_target


@pytest.mark.parametrize(
    ("entities", "expected"),
    [
        pytest.param([], set(), id="empty"),
        pytest.param(
            [
                _entity("School", [_pk()]),
                _entity("Department", [_pk(), _ref("school_id", "School")]),
            ],
            {"School", "Department"},
            id="includes-entities-without-fks",
        ),
    ],
)
def test_entity_names(entities: list[ir.EntitySpec], expected: set[str]) -> None:
    assert FKGraph.from_entities(entities).entity_names() == expected


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("graph_factory", "entity", "segment", "expected"),
    [
        pytest.param(
            _chain_graph, "Manuscript", "teacher", ("teacher_id", "Teacher"), id="relation-name"
        ),
        pytest.param(
            _chain_graph, "Manuscript", "teacher_id", ("teacher_id", "Teacher"), id="fk-field-name"
        ),
        pytest.param(
            _order_item_graph, "OrderItem", "order", ("order_id", "Order"), id="belongs-to-as-ref"
        ),
    ],
)
def test_resolve_segment(
    graph_factory: Callable[[], FKGraph], entity: str, segment: str, expected: tuple[str, str]
) -> None:
    """resolve_segment accepts the relation name or the FK field name -> (fk_field, target)."""
    assert graph_factory().resolve_segment(entity, segment) == expected


class TestPathResolution:
    @pytest.fixture()
    def chain_graph(self) -> FKGraph:
        return _chain_graph()

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

    def test_resolve_path_empty_raises(self, chain_graph: FKGraph) -> None:
        """resolve_path with empty list raises ValueError."""
        with pytest.raises(ValueError):
            chain_graph.resolve_path("Manuscript", [])

    def test_resolve_target_returns_none_for_missing(self, chain_graph: FKGraph) -> None:
        """resolve_target returns None for non-existent FK field."""
        assert chain_graph.resolve_target("Manuscript", "bogus_id") is None


# ---------------------------------------------------------------------------
# #1315 — creation_order (FK-topological parent-before-child sort)
# ---------------------------------------------------------------------------


def _self_ref_graph() -> FKGraph:
    return FKGraph.from_entities([_entity("Employee", [_pk(), _ref("manager_id", "Employee")])])


def _cycle_graph() -> FKGraph:
    return FKGraph.from_entities(
        [
            _entity("A", [_pk(), _ref("b_id", "B")]),
            _entity("B", [_pk(), _ref("a_id", "A")]),
        ]
    )


@pytest.mark.parametrize(
    ("graph_factory", "entities", "expected"),
    [
        # Declared child-first; parents are placed before children.
        pytest.param(
            _invoice_graph,
            ["LineItem", "Order", "Invoice"],
            ["Invoice", "Order", "LineItem"],
            id="parents-before-children-1315",
        ),
        pytest.param(
            _invoice_graph,
            ["Invoice", "Order", "LineItem"],
            ["Invoice", "Order", "LineItem"],
            id="already-ordered-is-stable",
        ),
        # No FK between Invoice and Tag -> declared order preserved.
        pytest.param(
            _invoice_graph, ["Tag", "Invoice"], ["Tag", "Invoice"], id="independent-keep-order"
        ),
        # Order's FK target Invoice is outside the set -> no constraint.
        pytest.param(_invoice_graph, ["Order"], ["Order"], id="fk-outside-set-unconstrained"),
        pytest.param(_self_ref_graph, ["Employee"], None, id="self-referential-fk-none"),
        pytest.param(_cycle_graph, ["A", "B"], None, id="cycle-none"),
        pytest.param(_invoice_graph, ["Invoice", "Invoice"], None, id="duplicates-none"),
    ],
)
def test_creation_order(
    graph_factory: Callable[[], FKGraph], entities: list[str], expected: list[str] | None
) -> None:
    assert graph_factory().creation_order(entities) == expected
