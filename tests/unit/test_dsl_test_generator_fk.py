"""Tests for recursive FK dependency chain resolution (issue #237)."""

from __future__ import annotations

from dazzle.core.ir import AppSpec
from dazzle.core.ir.domain import DomainSpec, EntitySpec
from dazzle.core.ir.fields import FieldModifier, FieldSpec, FieldType, FieldTypeKind
from dazzle.core.ir.state_machine import StateMachineSpec, StateTransition
from dazzle.testing.dsl_test_generator import DSLTestGenerator


def _field(name: str, kind: FieldTypeKind = FieldTypeKind.STR, **kwargs) -> FieldSpec:
    """Shorthand field builder."""
    modifiers = kwargs.pop("modifiers", [])
    ft_kwargs: dict = {"kind": kind}
    if kind == FieldTypeKind.STR:
        ft_kwargs["max_length"] = kwargs.pop("max_length", 200)
    if kind == FieldTypeKind.REF:
        ft_kwargs["ref_entity"] = kwargs.pop("ref_entity", None)
    return FieldSpec(name=name, type=FieldType(**ft_kwargs), modifiers=modifiers)


def _pk_field() -> FieldSpec:
    return _field("id", FieldTypeKind.UUID, modifiers=[FieldModifier.PK])


def _ref_field(name: str, target: str, required: bool = True) -> FieldSpec:
    mods = [FieldModifier.REQUIRED] if required else []
    return _field(name, FieldTypeKind.REF, ref_entity=target, modifiers=mods)


def _str_field(name: str, required: bool = True) -> FieldSpec:
    mods = [FieldModifier.REQUIRED] if required else []
    return _field(name, FieldTypeKind.STR, modifiers=mods)


def _make_appspec(*entities: EntitySpec) -> AppSpec:
    return AppSpec(
        name="test",
        title="Test",
        domain=DomainSpec(entities=list(entities)),
        surfaces=[],
        views=[],
        enums=[],
        processes=[],
        ledgers=[],
        transactions=[],
        workspaces=[],
        experiences=[],
        personas=[],
        stories=[],
        webhooks=[],
        approvals=[],
        slas=[],
        islands=[],
    )


# ---------------------------------------------------------------------------
# Entities used across tests
# ---------------------------------------------------------------------------

_LEVEL1 = EntitySpec(
    name="Level1",
    title="Level 1",
    fields=[_pk_field(), _str_field("name")],
)

_LEVEL2 = EntitySpec(
    name="Level2",
    title="Level 2",
    fields=[_pk_field(), _ref_field("parent", "Level1"), _str_field("name")],
)

_LEVEL3 = EntitySpec(
    name="Level3",
    title="Level 3",
    fields=[_pk_field(), _ref_field("parent", "Level2"), _str_field("name")],
)

_LEVEL4 = EntitySpec(
    name="Level4",
    title="Level 4",
    fields=[_pk_field(), _ref_field("parent", "Level3"), _str_field("name")],
)


class TestRecursiveParentSetup:
    """_generate_parent_setup_steps creates ancestors in topological order."""

    def test_single_level_still_works(self) -> None:
        """A → B: B is created first (no regression)."""
        child = EntitySpec(
            name="Child",
            fields=[_pk_field(), _ref_field("owner", "Parent"), _str_field("label")],
        )
        parent = EntitySpec(
            name="Parent",
            fields=[_pk_field(), _str_field("name")],
        )
        gen = DSLTestGenerator(_make_appspec(parent, child))
        refs = gen._get_required_refs(child)
        steps = gen._generate_parent_setup_steps(refs)

        assert len(steps) == 1
        assert steps[0]["target"] == "entity:Parent"
        assert steps[0]["store_result"] == "parent_parent"

    def test_two_level_chain(self) -> None:
        """C → B → A: A created first, then B with ref to A."""
        gen = DSLTestGenerator(_make_appspec(_LEVEL1, _LEVEL2, _LEVEL3))
        refs = gen._get_required_refs(_LEVEL3)
        steps = gen._generate_parent_setup_steps(refs)

        assert len(steps) == 2
        # Level1 must be created before Level2
        assert steps[0]["target"] == "entity:Level1"
        assert steps[1]["target"] == "entity:Level2"
        # Level2's data should include a $ref to Level1
        assert steps[1]["data"]["parent"] == "$ref:parent_level1.id"

    def test_three_level_chain(self) -> None:
        """D → C → B → A: all ancestors created in order."""
        gen = DSLTestGenerator(_make_appspec(_LEVEL1, _LEVEL2, _LEVEL3, _LEVEL4))
        refs = gen._get_required_refs(_LEVEL4)
        steps = gen._generate_parent_setup_steps(refs)

        assert len(steps) == 3
        targets = [s["target"] for s in steps]
        assert targets == ["entity:Level1", "entity:Level2", "entity:Level3"]
        # Each level should ref the previous
        assert steps[1]["data"]["parent"] == "$ref:parent_level1.id"
        assert steps[2]["data"]["parent"] == "$ref:parent_level2.id"

    def test_diamond_dependency_deduplicates(self) -> None:
        """Entity with two refs to entities that share a common ancestor."""
        base = EntitySpec(name="Base", fields=[_pk_field(), _str_field("name")])
        left = EntitySpec(
            name="Left",
            fields=[_pk_field(), _ref_field("base", "Base"), _str_field("name")],
        )
        right = EntitySpec(
            name="Right",
            fields=[_pk_field(), _ref_field("base", "Base"), _str_field("name")],
        )
        child = EntitySpec(
            name="Child",
            fields=[
                _pk_field(),
                _ref_field("left", "Left"),
                _ref_field("right", "Right"),
                _str_field("name"),
            ],
        )
        gen = DSLTestGenerator(_make_appspec(base, left, right, child))
        refs = gen._get_required_refs(child)
        steps = gen._generate_parent_setup_steps(refs)

        # Base should appear exactly once, despite being needed by both Left and Right
        targets = [s["target"] for s in steps]
        assert targets.count("entity:Base") == 1
        # Order: Base first, then Left and Right (both after Base)
        base_idx = targets.index("entity:Base")
        left_idx = targets.index("entity:Left")
        right_idx = targets.index("entity:Right")
        assert base_idx < left_idx
        assert base_idx < right_idx

    def test_circular_dependency_skipped(self) -> None:
        """Circular A → B → A should not infinite-loop."""
        a = EntitySpec(
            name="A",
            fields=[_pk_field(), _ref_field("b_ref", "B"), _str_field("name")],
        )
        b = EntitySpec(
            name="B",
            fields=[_pk_field(), _ref_field("a_ref", "A"), _str_field("name")],
        )
        gen = DSLTestGenerator(_make_appspec(a, b))
        refs = gen._get_required_refs(a)
        # Should not raise or infinite-loop
        steps = gen._generate_parent_setup_steps(refs)
        # At least B should be created (A is the child, not a parent here)
        targets = [s["target"] for s in steps]
        assert "entity:B" in targets

    def test_no_refs_returns_empty(self) -> None:
        """Entity with no refs produces no setup steps."""
        simple = EntitySpec(name="Simple", fields=[_pk_field(), _str_field("name")])
        gen = DSLTestGenerator(_make_appspec(simple))
        refs = gen._get_required_refs(simple)
        steps = gen._generate_parent_setup_steps(refs)
        assert steps == []

    def test_optional_refs_not_included(self) -> None:
        """Optional ref fields should not trigger parent creation."""
        parent = EntitySpec(name="Parent", fields=[_pk_field(), _str_field("name")])
        child = EntitySpec(
            name="Child",
            fields=[_pk_field(), _ref_field("owner", "Parent", required=False), _str_field("name")],
        )
        gen = DSLTestGenerator(_make_appspec(parent, child))
        refs = gen._get_required_refs(child)
        steps = gen._generate_parent_setup_steps(refs)
        assert steps == []


class TestEntityTestsTransitiveDeps:
    """_generate_entity_tests includes transitive parent setup."""

    def test_crud_includes_grandparent_setup(self) -> None:
        """CRUD create for Level3 should have setup steps for Level1 and Level2."""
        gen = DSLTestGenerator(_make_appspec(_LEVEL1, _LEVEL2, _LEVEL3))
        tests = gen._generate_entity_tests(_LEVEL3)

        # Find the create test
        create_test = next(t for t in tests if "CREATE" in t["test_id"])
        steps = create_test["steps"]

        # First two steps should create Level1 and Level2
        assert steps[0]["target"] == "entity:Level1"
        assert steps[1]["target"] == "entity:Level2"
        # Third step creates Level3 itself
        assert steps[2]["target"] == "entity:Level3"
        # Level3's data should ref Level2
        assert steps[2]["data"]["parent"] == "$ref:parent_level2.id"

    def test_related_entities_includes_transitive(self) -> None:
        """related_entities should include all transitive dependencies."""
        gen = DSLTestGenerator(_make_appspec(_LEVEL1, _LEVEL2, _LEVEL3))
        tests = gen._generate_entity_tests(_LEVEL3)

        create_test = next(t for t in tests if "CREATE" in t["test_id"])
        entities = create_test["entities"]
        assert "Level3" in entities
        assert "Level2" in entities
        assert "Level1" in entities


class TestStateMachineWithRefs:
    """State machine tests include parent setup for entities with required refs."""

    def _entity_with_sm(self) -> EntitySpec:
        """Entity with both a state machine and a required ref."""
        return EntitySpec(
            name="Order",
            title="Order",
            fields=[
                _pk_field(),
                _ref_field("customer", "Customer"),
                _str_field("description"),
                _field(
                    "status",
                    FieldTypeKind.ENUM,
                    modifiers=[FieldModifier.REQUIRED],
                ),
            ],
            state_machine=StateMachineSpec(
                status_field="status",
                states=["pending", "active", "completed"],
                transitions=[
                    StateTransition(from_state="pending", to_state="active"),
                    StateTransition(from_state="active", to_state="completed"),
                ],
            ),
        )

    def test_valid_transition_has_parent_setup(self) -> None:
        customer = EntitySpec(name="Customer", fields=[_pk_field(), _str_field("name")])
        order = self._entity_with_sm()
        gen = DSLTestGenerator(_make_appspec(customer, order))
        tests = gen._generate_state_machine_tests(order)

        # Find a valid transition test
        valid_test = next(t for t in tests if "INVALID" not in t["test_id"])
        steps = valid_test["steps"]

        # First step should create Customer parent
        assert steps[0]["action"] == "create"
        assert steps[0]["target"] == "entity:Customer"
        assert steps[0]["store_result"] == "parent_customer"

        # Second step should create Order with ref to Customer
        assert steps[1]["target"] == "entity:Order"
        assert steps[1]["data"]["customer"] == "$ref:parent_customer.id"

    def test_invalid_transition_has_parent_setup(self) -> None:
        customer = EntitySpec(name="Customer", fields=[_pk_field(), _str_field("name")])
        order = self._entity_with_sm()
        gen = DSLTestGenerator(_make_appspec(customer, order))
        tests = gen._generate_state_machine_tests(order)

        # Find an invalid transition test
        invalid_tests = [t for t in tests if "INVALID" in t["test_id"]]
        assert len(invalid_tests) > 0
        steps = invalid_tests[0]["steps"]

        # First step should create Customer parent
        assert steps[0]["action"] == "create"
        assert steps[0]["target"] == "entity:Customer"

    def test_sm_related_entities_includes_parents(self) -> None:
        customer = EntitySpec(name="Customer", fields=[_pk_field(), _str_field("name")])
        order = self._entity_with_sm()
        gen = DSLTestGenerator(_make_appspec(customer, order))
        tests = gen._generate_state_machine_tests(order)

        valid_test = next(t for t in tests if "INVALID" not in t["test_id"])
        assert "Customer" in valid_test["entities"]
        assert "Order" in valid_test["entities"]

    def test_sm_no_refs_still_works(self) -> None:
        """State machine entity without refs produces tests without setup steps."""
        entity = EntitySpec(
            name="Task",
            fields=[
                _pk_field(),
                _str_field("title"),
                _field("status", FieldTypeKind.ENUM, modifiers=[FieldModifier.REQUIRED]),
            ],
            state_machine=StateMachineSpec(
                status_field="status",
                states=["open", "closed"],
                transitions=[StateTransition(from_state="open", to_state="closed")],
            ),
        )
        gen = DSLTestGenerator(_make_appspec(entity))
        tests = gen._generate_state_machine_tests(entity)
        assert len(tests) > 0

        valid_test = next(t for t in tests if "INVALID" not in t["test_id"])
        # First step should be the entity create (no parent setup)
        assert valid_test["steps"][0]["target"] == "entity:Task"
        assert valid_test["steps"][0]["action"] == "create"

    def test_sm_transitive_chain(self) -> None:
        """State machine entity at end of a FK chain gets full ancestor setup."""
        level1 = EntitySpec(name="Org", fields=[_pk_field(), _str_field("name")])
        level2 = EntitySpec(
            name="Team",
            fields=[_pk_field(), _ref_field("org", "Org"), _str_field("name")],
        )
        entity = EntitySpec(
            name="Ticket",
            fields=[
                _pk_field(),
                _ref_field("team", "Team"),
                _str_field("title"),
                _field("status", FieldTypeKind.ENUM, modifiers=[FieldModifier.REQUIRED]),
            ],
            state_machine=StateMachineSpec(
                status_field="status",
                states=["open", "closed"],
                transitions=[StateTransition(from_state="open", to_state="closed")],
            ),
        )
        gen = DSLTestGenerator(_make_appspec(level1, level2, entity))
        tests = gen._generate_state_machine_tests(entity)
        valid_test = next(t for t in tests if "INVALID" not in t["test_id"])
        steps = valid_test["steps"]

        # Org first, then Team, then Ticket
        assert steps[0]["target"] == "entity:Org"
        assert steps[1]["target"] == "entity:Team"
        assert steps[1]["data"]["org"] == "$ref:parent_org.id"
        assert steps[2]["target"] == "entity:Ticket"
        assert steps[2]["data"]["team"] == "$ref:parent_team.id"
