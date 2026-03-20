"""
Unit tests for scope predicate validation in the semantic validator.

Tests that validate_scope_predicates catches invalid field references,
broken FK paths, and non-existent entities in compiled scope predicates.
"""

from dazzle.core import ir
from dazzle.core.ir.fk_graph import FKGraph
from dazzle.core.ir.predicates import (
    BoolComposite,
    BoolOp,
    ColumnCheck,
    CompOp,
    ExistsBinding,
    ExistsCheck,
    PathCheck,
    Tautology,
    UserAttrCheck,
    ValueRef,
)
from dazzle.core.validator import validate_scope_predicates

# =============================================================================
# Helpers
# =============================================================================


def _id_field() -> ir.FieldSpec:
    return ir.FieldSpec(
        name="id",
        type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
        modifiers=[ir.FieldModifier.PK],
    )


def _ref_field(name: str, target: str) -> ir.FieldSpec:
    return ir.FieldSpec(
        name=name,
        type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity=target),
    )


def _str_field(name: str) -> ir.FieldSpec:
    return ir.FieldSpec(
        name=name,
        type=ir.FieldType(kind=ir.FieldTypeKind.STR, max_length=200),
    )


def _make_scope_rule(predicate: object) -> ir.ScopeRule:
    return ir.ScopeRule(
        operation=ir.PermissionKind.READ,
        personas=["*"],
        predicate=predicate,
    )


def _build_appspec(
    entities: list[ir.EntitySpec],
    fk_graph: FKGraph | None = None,
) -> ir.AppSpec:
    if fk_graph is None:
        fk_graph = FKGraph.from_entities(entities)
    return ir.AppSpec(
        name="Test",
        domain=ir.DomainSpec(entities=entities),
        fk_graph=fk_graph,
    )


# =============================================================================
# Tests — valid predicates (no errors)
# =============================================================================


class TestValidPredicates:
    """Ensure valid scope predicates produce no errors."""

    def test_tautology_produces_no_errors(self) -> None:
        entity = ir.EntitySpec(
            name="Task",
            fields=[_id_field()],
            access=ir.AccessSpec(
                scopes=[_make_scope_rule(Tautology())],
            ),
        )
        appspec = _build_appspec([entity])
        errors, warnings = validate_scope_predicates(appspec)
        assert errors == []

    def test_column_check_valid_field(self) -> None:
        entity = ir.EntitySpec(
            name="Task",
            fields=[_id_field(), _str_field("owner_id")],
            access=ir.AccessSpec(
                scopes=[
                    _make_scope_rule(
                        ColumnCheck(
                            field="owner_id",
                            op=CompOp.EQ,
                            value=ValueRef(current_user=True),
                        )
                    )
                ],
            ),
        )
        appspec = _build_appspec([entity])
        errors, _ = validate_scope_predicates(appspec)
        assert errors == []

    def test_user_attr_check_valid_field(self) -> None:
        entity = ir.EntitySpec(
            name="Task",
            fields=[_id_field(), _str_field("org_id")],
            access=ir.AccessSpec(
                scopes=[
                    _make_scope_rule(
                        UserAttrCheck(
                            field="org_id",
                            op=CompOp.EQ,
                            user_attr="org_id",
                        )
                    )
                ],
            ),
        )
        appspec = _build_appspec([entity])
        errors, _ = validate_scope_predicates(appspec)
        assert errors == []

    def test_path_check_valid_fk_path(self) -> None:
        department = ir.EntitySpec(
            name="Department",
            fields=[_id_field(), _str_field("org_id")],
        )
        task = ir.EntitySpec(
            name="Task",
            fields=[_id_field(), _ref_field("department", "Department")],
            access=ir.AccessSpec(
                scopes=[
                    _make_scope_rule(
                        PathCheck(
                            path=["department", "org_id"],
                            op=CompOp.EQ,
                            value=ValueRef(user_attr="org_id"),
                        )
                    )
                ],
            ),
        )
        appspec = _build_appspec([department, task])
        errors, _ = validate_scope_predicates(appspec)
        assert errors == []

    def test_exists_check_valid_entity(self) -> None:
        membership = ir.EntitySpec(
            name="TeamMembership",
            fields=[
                _id_field(),
                _ref_field("user", "User"),
                _ref_field("team", "Team"),
            ],
        )
        user = ir.EntitySpec(name="User", fields=[_id_field()])
        team = ir.EntitySpec(name="Team", fields=[_id_field()])
        task = ir.EntitySpec(
            name="Task",
            fields=[_id_field(), _ref_field("team", "Team")],
            access=ir.AccessSpec(
                scopes=[
                    _make_scope_rule(
                        ExistsCheck(
                            target_entity="TeamMembership",
                            bindings=[
                                ExistsBinding(junction_field="user", target="current_user"),
                                ExistsBinding(junction_field="team", target="id"),
                            ],
                        )
                    )
                ],
            ),
        )
        appspec = _build_appspec([membership, user, team, task])
        errors, _ = validate_scope_predicates(appspec)
        assert errors == []

    def test_bool_composite_valid(self) -> None:
        entity = ir.EntitySpec(
            name="Task",
            fields=[_id_field(), _str_field("owner_id"), _str_field("org_id")],
            access=ir.AccessSpec(
                scopes=[
                    _make_scope_rule(
                        BoolComposite(
                            op=BoolOp.OR,
                            children=[
                                ColumnCheck(
                                    field="owner_id",
                                    op=CompOp.EQ,
                                    value=ValueRef(current_user=True),
                                ),
                                UserAttrCheck(
                                    field="org_id",
                                    op=CompOp.EQ,
                                    user_attr="org_id",
                                ),
                            ],
                        )
                    )
                ],
            ),
        )
        appspec = _build_appspec([entity])
        errors, _ = validate_scope_predicates(appspec)
        assert errors == []

    def test_no_scopes_produces_no_errors(self) -> None:
        entity = ir.EntitySpec(name="Task", fields=[_id_field()])
        appspec = _build_appspec([entity])
        errors, _ = validate_scope_predicates(appspec)
        assert errors == []

    def test_no_fk_graph_produces_no_errors(self) -> None:
        entity = ir.EntitySpec(name="Task", fields=[_id_field()])
        appspec = ir.AppSpec(
            name="Test",
            domain=ir.DomainSpec(entities=[entity]),
            fk_graph=None,
        )
        errors, _ = validate_scope_predicates(appspec)
        assert errors == []


# =============================================================================
# Tests — invalid predicates (errors detected)
# =============================================================================


class TestInvalidPredicates:
    """Ensure invalid scope predicates are caught."""

    def test_column_check_nonexistent_field(self) -> None:
        entity = ir.EntitySpec(
            name="Task",
            fields=[_id_field()],
            access=ir.AccessSpec(
                scopes=[
                    _make_scope_rule(
                        ColumnCheck(
                            field="nonexistent",
                            op=CompOp.EQ,
                            value=ValueRef(literal="x"),
                        )
                    )
                ],
            ),
        )
        appspec = _build_appspec([entity])
        errors, _ = validate_scope_predicates(appspec)
        assert len(errors) == 1
        assert "nonexistent" in errors[0]
        assert "ColumnCheck" in errors[0]

    def test_user_attr_check_nonexistent_field(self) -> None:
        entity = ir.EntitySpec(
            name="Task",
            fields=[_id_field()],
            access=ir.AccessSpec(
                scopes=[
                    _make_scope_rule(
                        UserAttrCheck(
                            field="missing_field",
                            op=CompOp.EQ,
                            user_attr="org_id",
                        )
                    )
                ],
            ),
        )
        appspec = _build_appspec([entity])
        errors, _ = validate_scope_predicates(appspec)
        assert len(errors) == 1
        assert "missing_field" in errors[0]
        assert "UserAttrCheck" in errors[0]

    def test_path_check_broken_fk_path(self) -> None:
        task = ir.EntitySpec(
            name="Task",
            fields=[_id_field(), _str_field("title")],
            access=ir.AccessSpec(
                scopes=[
                    _make_scope_rule(
                        PathCheck(
                            path=["department", "org_id"],
                            op=CompOp.EQ,
                            value=ValueRef(user_attr="org_id"),
                        )
                    )
                ],
            ),
        )
        appspec = _build_appspec([task])
        errors, _ = validate_scope_predicates(appspec)
        assert len(errors) == 1
        assert "PathCheck" in errors[0]
        assert "department.org_id" in errors[0]

    def test_exists_check_nonexistent_entity(self) -> None:
        task = ir.EntitySpec(
            name="Task",
            fields=[_id_field()],
            access=ir.AccessSpec(
                scopes=[
                    _make_scope_rule(
                        ExistsCheck(
                            target_entity="GhostEntity",
                            bindings=[
                                ExistsBinding(junction_field="user", target="current_user"),
                            ],
                        )
                    )
                ],
            ),
        )
        appspec = _build_appspec([task])
        errors, _ = validate_scope_predicates(appspec)
        assert len(errors) == 1
        assert "GhostEntity" in errors[0]
        assert "ExistsCheck" in errors[0]

    def test_bool_composite_with_invalid_child(self) -> None:
        """Errors inside a BoolComposite child are surfaced."""
        entity = ir.EntitySpec(
            name="Task",
            fields=[_id_field(), _str_field("owner_id")],
            access=ir.AccessSpec(
                scopes=[
                    _make_scope_rule(
                        BoolComposite(
                            op=BoolOp.AND,
                            children=[
                                ColumnCheck(
                                    field="owner_id",
                                    op=CompOp.EQ,
                                    value=ValueRef(current_user=True),
                                ),
                                ColumnCheck(
                                    field="bad_field",
                                    op=CompOp.EQ,
                                    value=ValueRef(literal="x"),
                                ),
                            ],
                        )
                    )
                ],
            ),
        )
        appspec = _build_appspec([entity])
        errors, _ = validate_scope_predicates(appspec)
        assert len(errors) == 1
        assert "bad_field" in errors[0]

    def test_empty_path_check(self) -> None:
        entity = ir.EntitySpec(
            name="Task",
            fields=[_id_field()],
            access=ir.AccessSpec(
                scopes=[
                    _make_scope_rule(
                        PathCheck(
                            path=[],
                            op=CompOp.EQ,
                            value=ValueRef(literal="x"),
                        )
                    )
                ],
            ),
        )
        appspec = _build_appspec([entity])
        errors, _ = validate_scope_predicates(appspec)
        assert len(errors) == 1
        assert "empty path" in errors[0]

    def test_multiple_errors_across_entities(self) -> None:
        """Multiple entities with bad predicates each produce errors."""
        task = ir.EntitySpec(
            name="Task",
            fields=[_id_field()],
            access=ir.AccessSpec(
                scopes=[
                    _make_scope_rule(
                        ColumnCheck(
                            field="bad1",
                            op=CompOp.EQ,
                            value=ValueRef(literal="x"),
                        )
                    )
                ],
            ),
        )
        project = ir.EntitySpec(
            name="Project",
            fields=[_id_field()],
            access=ir.AccessSpec(
                scopes=[
                    _make_scope_rule(
                        ColumnCheck(
                            field="bad2",
                            op=CompOp.EQ,
                            value=ValueRef(literal="y"),
                        )
                    )
                ],
            ),
        )
        appspec = _build_appspec([task, project])
        errors, _ = validate_scope_predicates(appspec)
        assert len(errors) == 2
        assert any("bad1" in e for e in errors)
        assert any("bad2" in e for e in errors)
