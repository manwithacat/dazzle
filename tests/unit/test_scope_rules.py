"""
Unit tests for ScopeRule IR type and AccessSpec.scopes field,
plus parser tests for scope: blocks and permit: field-condition rejection.
Includes converter tests for _convert_scope_rule (Task 3).
Includes linker integration tests for FK graph and predicate compilation (Task 5).
"""

import os
import tempfile
from pathlib import Path
from typing import Any

import pytest

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.errors import ParseError
from dazzle.core.ir.conditions import (
    Comparison,
    ComparisonOperator,
    ConditionExpr,
    ConditionValue,
)
from dazzle.core.ir.domain import AccessSpec, PermissionKind, ScopeRule
from dazzle.http.converters.entity_converter import _convert_scope_rule
from dazzle.http.specs.auth import AccessOperationKind, ScopeRuleSpec


def _make_condition() -> ConditionExpr:
    """Helper: build a simple field condition (owner_id = current_user)."""
    return ConditionExpr(
        comparison=Comparison(
            field="owner_id",
            operator=ComparisonOperator.EQUALS,
            value=ConditionValue(literal="current_user"),
        )
    )


def _parse(dsl: str):
    """Parse DSL text and return the ModuleFragment."""
    _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
    return fragment


class TestScopeRule:
    """Tests for ScopeRule dataclass / Pydantic model."""

    @pytest.mark.parametrize(
        ("kwargs", "condition", "personas"),
        [
            pytest.param(
                {"operation": PermissionKind.READ, "personas": ["manager"]},
                _make_condition(),
                ["manager"],
                id="field-condition",
            ),
            # condition=None means 'all records' — no row filter applied.
            pytest.param(
                {"operation": PermissionKind.LIST, "personas": ["admin"]},
                None,
                ["admin"],
                id="condition-none-means-all",
            ),
            # personas=['*'] means all authorized roles.
            pytest.param(
                {"operation": PermissionKind.READ, "personas": ["*"]},
                _make_condition(),
                ["*"],
                id="wildcard-personas",
            ),
            # personas defaults to empty list when not supplied; every kind accepted.
            *[
                pytest.param({"operation": kind}, None, [], id=f"default-personas-{kind.value}")
                for kind in PermissionKind
            ],
        ],
    )
    def test_scope_rule_stores_operation_condition_and_personas(
        self, kwargs: dict[str, Any], condition: ConditionExpr | None, personas: list[str]
    ) -> None:
        rule = ScopeRule(**kwargs, condition=condition)

        assert rule.operation == kwargs["operation"]
        assert rule.condition == condition
        assert rule.personas == personas


class TestAccessSpecScopes:
    """Tests for the scopes field on AccessSpec."""

    def test_access_spec_scopes_defaults_to_empty_list(self):
        """AccessSpec.scopes must default to an empty list."""
        spec = AccessSpec()

        assert spec.scopes == []

    def test_access_spec_scopes_accepts_scope_rule_list(self):
        """AccessSpec.scopes accepts a list of ScopeRule instances."""
        rules = [
            ScopeRule(operation=PermissionKind.READ, personas=["*"]),
            ScopeRule(
                operation=PermissionKind.LIST,
                condition=_make_condition(),
                personas=["manager"],
            ),
        ]
        spec = AccessSpec(scopes=rules)

        assert len(spec.scopes) == 2
        assert spec.scopes[0].operation == PermissionKind.READ
        assert spec.scopes[1].operation == PermissionKind.LIST
        assert spec.scopes[1].personas == ["manager"]

    def test_access_spec_existing_fields_unaffected(self):
        """Adding scopes does not disturb visibility or permissions fields."""
        spec = AccessSpec()

        assert spec.visibility == []
        assert spec.permissions == []
        assert spec.scopes == []


class TestParseScopeBlock:
    """Parser tests for scope: blocks in entity definitions."""

    def test_parse_scope_block_basic(self):
        """scope: block with a field condition and a for: clause is parsed correctly."""
        dsl = """\
module test

entity School "School":
  id: uuid pk
  school: ref School optional

  permit:
    list: role(teacher)
    read: role(teacher)

  scope:
    list: school = current_user.school
      as: teacher, school_admin
"""
        fragment = _parse(dsl)
        entity = fragment.entities[0]
        assert entity.access is not None
        scopes = entity.access.scopes
        assert len(scopes) == 1
        rule = scopes[0]
        assert rule.operation == PermissionKind.LIST
        assert rule.condition is not None
        assert rule.condition.comparison is not None
        assert rule.condition.comparison.field == "school"
        assert rule.personas == ["teacher", "school_admin"]

    def test_parse_scope_all(self):
        """scope: list: all for: admin produces condition=None."""
        dsl = """\
module test

entity Report "Report":
  id: uuid pk

  permit:
    list: role(admin)

  scope:
    list: all
      as: admin
"""
        fragment = _parse(dsl)
        entity = fragment.entities[0]
        assert entity.access is not None
        scopes = entity.access.scopes
        assert len(scopes) == 1
        rule = scopes[0]
        assert rule.operation == PermissionKind.LIST
        assert rule.condition is None
        assert rule.personas == ["admin"]

    def test_parse_scope_wildcard_for(self):
        """scope: read: owner = current_user for: * is parsed correctly."""
        dsl = """\
module test

entity Note "Note":
  id: uuid pk

  permit:
    read: authenticated

  scope:
    read: owner = current_user
      as: *
"""
        fragment = _parse(dsl)
        entity = fragment.entities[0]
        assert entity.access is not None
        scopes = entity.access.scopes
        assert len(scopes) == 1
        assert scopes[0].personas == ["*"]

    def test_parse_scope_multiple_for_roles(self):
        """scope: for: with multiple roles parses all of them."""
        dsl = """\
module test

entity Document "Document":
  id: uuid pk

  permit:
    list: role(sovereign)

  scope:
    list: realm = current_user.realm
      as: sovereign, architect, witness
"""
        fragment = _parse(dsl)
        entity = fragment.entities[0]
        assert entity.access is not None
        scopes = entity.access.scopes
        assert len(scopes) == 1
        assert scopes[0].personas == ["sovereign", "architect", "witness"]

    def test_parse_scope_multiple_rules(self):
        """Multiple rules in a scope: block are all parsed."""
        dsl = """\
module test

entity Item "Item":
  id: uuid pk

  permit:
    read: role(viewer)
    list: role(viewer)

  scope:
    list: school = current_user.school
      as: teacher
    read: owner = current_user
      as: *
"""
        fragment = _parse(dsl)
        entity = fragment.entities[0]
        assert entity.access is not None
        scopes = entity.access.scopes
        assert len(scopes) == 2
        assert scopes[0].operation == PermissionKind.LIST
        assert scopes[0].personas == ["teacher"]
        assert scopes[1].operation == PermissionKind.READ
        assert scopes[1].personas == ["*"]

    def test_scope_stored_in_access_spec(self):
        """scope: rules are stored in entity.access.scopes."""
        dsl = """\
module test

entity Task "Task":
  id: uuid pk

  scope:
    list: all
      as: oracle
"""
        fragment = _parse(dsl)
        entity = fragment.entities[0]
        assert entity.access is not None
        assert len(entity.access.scopes) == 1
        # permissions and visibility are still empty
        assert entity.access.permissions == []
        assert entity.access.visibility == []


class TestPermitFieldConditionRejection:
    """Tests that field conditions in permit: blocks are rejected."""

    @pytest.mark.parametrize(
        "dsl",
        [
            pytest.param(
                """\
module test

entity Shape "Shape":
  id: uuid pk
  school: ref School optional

  permit:
    list: school = current_user.school
""",
                id="field-comparison",
            ),
            # role(x) or field = value is rejected because of the comparison.
            pytest.param(
                """\
module test

entity Thing "Thing":
  id: uuid pk
  realm: str(100) optional

  permit:
    list: role(teacher) or realm = current_user.realm
""",
                id="mixed-or-with-comparison",
            ),
        ],
    )
    def test_field_condition_in_permit_raises_error(self, dsl: str) -> None:
        with pytest.raises(ParseError, match="Field condition in permit: block"):
            _parse(dsl)

    @pytest.mark.parametrize(
        ("dsl", "permission_count"),
        [
            pytest.param(
                """\
module test

entity Shape "Shape":
  id: uuid pk

  permit:
    list: role(teacher)
    read: role(teacher) or role(admin)
    create: role(admin)
""",
                3,
                id="role-check",
            ),
            pytest.param(
                """\
module test

entity Log "Log":
  id: uuid pk

  permit:
    read: authenticated
""",
                1,
                id="authenticated",
            ),
            # Only permit: rejects field conditions; forbid: keeps them (pra example).
            # Count is permit read + forbid delete.
            pytest.param(
                """\
module test

entity Resource "Resource":
  id: uuid pk
  classification: enum[public,restricted]=public

  permit:
    read: role(admin)

  forbid:
    delete: classification = restricted
""",
                2,
                id="forbid-with-field-condition",
            ),
            pytest.param(
                """\
module test

entity Record "Record":
  id: uuid pk
  department: str(50) optional

  permit:
    read: has_grant("observer", department)
""",
                1,
                id="grant-check",
            ),
        ],
    )
    def test_authorization_checks_are_allowed(self, dsl: str, permission_count: int) -> None:
        """Role, authenticated and grant checks in permit:, and field conditions in
        forbid:, are not rejected."""
        entity = _parse(dsl).entities[0]
        assert entity.access is not None
        assert len(entity.access.permissions) == permission_count


# =============================================================================
# Task 3: Converter tests — _convert_scope_rule
# =============================================================================


class TestConvertScopeRule:
    """Tests for the _convert_scope_rule converter function."""

    def test_convert_scope_rule_with_field_condition(self):
        """_convert_scope_rule converts a ScopeRule with a field condition."""
        condition = _make_condition()
        ir_rule = ScopeRule(
            operation=PermissionKind.READ,
            condition=condition,
            personas=["manager"],
        )

        result = _convert_scope_rule(ir_rule)

        assert isinstance(result, ScopeRuleSpec)
        assert result.operation == AccessOperationKind.READ
        assert result.condition is not None
        assert result.condition.kind == "comparison"
        assert result.condition.field == "owner_id"
        assert result.condition.value == "current_user"
        assert result.personas == ["manager"]

    @pytest.mark.parametrize(
        ("ir_rule", "operation", "personas"),
        [
            # condition=None produces condition=None in the spec.
            pytest.param(
                ScopeRule(operation=PermissionKind.LIST, condition=None, personas=["admin"]),
                AccessOperationKind.LIST,
                ["admin"],
                id="condition-none",
            ),
            pytest.param(
                ScopeRule(operation=PermissionKind.READ, personas=["*"]),
                AccessOperationKind.READ,
                ["*"],
                id="wildcard-personas",
            ),
            # Every PermissionKind maps to its AccessOperationKind; empty personas kept.
            *[
                pytest.param(ScopeRule(operation=ir_kind), op, [], id=f"operation-{op.value}")
                for ir_kind, op in (
                    (PermissionKind.CREATE, AccessOperationKind.CREATE),
                    (PermissionKind.READ, AccessOperationKind.READ),
                    (PermissionKind.UPDATE, AccessOperationKind.UPDATE),
                    (PermissionKind.DELETE, AccessOperationKind.DELETE),
                    (PermissionKind.LIST, AccessOperationKind.LIST),
                )
            ],
        ],
    )
    def test_convert_scope_rule_maps_operation_and_preserves_personas(
        self, ir_rule: ScopeRule, operation: AccessOperationKind, personas: list[str]
    ) -> None:
        result = _convert_scope_rule(ir_rule)

        assert isinstance(result, ScopeRuleSpec)
        assert result.operation == operation
        assert result.condition is None
        assert result.personas == personas


# =============================================================================
# Task 5: Linker integration — FK graph building and predicate compilation
# =============================================================================


def _build_appspec(dsl: str):
    """Parse DSL text and link into an AppSpec via build_appspec."""
    from dazzle.core.linker import build_appspec
    from dazzle.core.parser import parse_modules

    with tempfile.NamedTemporaryFile(mode="w", suffix=".dsl", delete=False) as f:
        f.write(dsl)
        f.flush()
        fpath = Path(f.name)
    try:
        modules = parse_modules([fpath])
        return build_appspec(modules, modules[0].name)
    finally:
        os.unlink(fpath)


class TestLinkerFKGraphAndPredicates:
    """Integration tests: FK graph built and predicates compiled at link time."""

    def test_fk_graph_populated_on_appspec(self):
        """AppSpec.fk_graph is not None after build_appspec."""
        dsl = """\
module test
app test_app "Test App"

entity School "School":
  id: uuid pk
  name: str(200) required

  permit:
    list: role(teacher)

  scope:
    list: all
      as: teacher
"""
        appspec = _build_appspec(dsl)
        assert appspec.fk_graph is not None

    def test_scope_all_produces_tautology(self):
        """scope: all compiles to a Tautology predicate at link time."""
        from dazzle.core.ir.predicates import Tautology

        dsl = """\
module test
app test_app "Test App"

entity Report "Report":
  id: uuid pk

  permit:
    list: role(admin)

  scope:
    list: all
      as: admin
"""
        appspec = _build_appspec(dsl)
        entity = appspec.get_entity("Report")
        assert entity is not None
        assert entity.access is not None
        scope_rules = entity.access.scopes
        assert len(scope_rules) == 1
        rule = scope_rules[0]
        assert rule.predicate is not None
        assert isinstance(rule.predicate, Tautology)

    def test_user_attr_check_predicate(self):
        """scope: school_id = current_user.school compiles to UserAttrCheck."""
        from dazzle.core.ir.predicates import UserAttrCheck

        dsl = """\
module test
app test_app "Test App"

entity Student "Student":
  id: uuid pk
  school_id: str(100) required

  permit:
    list: role(teacher)

  scope:
    list: school_id = current_user.school
      as: teacher
"""
        appspec = _build_appspec(dsl)
        entity = appspec.get_entity("Student")
        assert entity is not None
        assert entity.access is not None
        scope_rules = entity.access.scopes
        assert len(scope_rules) == 1
        rule = scope_rules[0]
        assert rule.predicate is not None
        assert isinstance(rule.predicate, UserAttrCheck)
        assert rule.predicate.field == "school_id"
        assert rule.predicate.user_attr == "school"

    def test_entity_without_scopes_unaffected(self):
        """Entity with no scope block has no predicates; fk_graph is still built."""
        dsl = """\
module test
app test_app "Test App"

entity Task "Task":
  id: uuid pk
  title: str(200) required

  permit:
    read: authenticated
"""
        appspec = _build_appspec(dsl)
        assert appspec.fk_graph is not None
        entity = appspec.get_entity("Task")
        assert entity is not None
        # No scopes → no predicates to check, but access may be present
        if entity.access is not None:
            assert entity.access.scopes == []

    def test_multiple_scope_rules_all_compiled(self):
        """Multiple scope rules on one entity each get a predicate."""
        from dazzle.core.ir.predicates import Tautology, UserAttrCheck

        dsl = """\
module test
app test_app "Test App"

entity Note "Note":
  id: uuid pk
  owner_id: str(100) required

  permit:
    list: role(teacher)
    read: role(admin)

  scope:
    list: owner_id = current_user.id
      as: teacher
    read: all
      as: admin
"""
        appspec = _build_appspec(dsl)
        entity = appspec.get_entity("Note")
        assert entity is not None
        assert entity.access is not None
        scopes = entity.access.scopes
        assert len(scopes) == 2

        list_rule = next(r for r in scopes if r.operation == PermissionKind.LIST)
        read_rule = next(r for r in scopes if r.operation == PermissionKind.READ)

        assert isinstance(list_rule.predicate, UserAttrCheck)
        assert list_rule.predicate.user_attr == "id"

        assert isinstance(read_rule.predicate, Tautology)


# =============================================================================
# Task 6: Runtime predicate pipeline integration tests
# =============================================================================


class TestResolvePredicateFilters:
    """Tests for _resolve_predicate_filters — predicate → SQL at request time."""

    def test_tautology_returns_empty(self):
        """Tautology predicate produces empty filters (no filtering needed)."""
        pytest.importorskip("fastapi")
        from dazzle.core.ir.fk_graph import FKGraph
        from dazzle.core.ir.predicates import Tautology
        from dazzle.http.runtime.route_generator import _resolve_predicate_filters

        result = _resolve_predicate_filters(Tautology(), "Task", FKGraph(), "user-1", None)
        assert result == {}

    def test_user_attr_check_produces_scope_predicate(self):
        """UserAttrCheck produces __scope_predicate with resolved SQL."""
        pytest.importorskip("fastapi")
        from dazzle.core.ir.fk_graph import FKGraph
        from dazzle.core.ir.predicates import CompOp, UserAttrCheck
        from dazzle.http.runtime.route_generator import _resolve_predicate_filters

        pred = UserAttrCheck(field="school_id", user_attr="school", op=CompOp.EQ)

        class FakeUser:
            school = "school-uuid-abc"

        class FakeAuth:
            user = FakeUser()
            preferences = {}

        result = _resolve_predicate_filters(pred, "Student", FKGraph(), "user-1", FakeAuth())
        assert "__scope_predicate" in result
        sql, params = result["__scope_predicate"]
        assert '"school_id"' in sql
        assert "=" in sql
        assert params == ["school-uuid-abc"]

    def test_current_user_ref_resolved(self):
        """CurrentUserRef in predicate params resolves to entity_id or user_id."""
        pytest.importorskip("fastapi")
        from dazzle.core.ir.fk_graph import FKGraph
        from dazzle.core.ir.predicates import ColumnCheck, CompOp, ValueRef
        from dazzle.http.runtime.route_generator import _resolve_predicate_filters

        pred = ColumnCheck(
            field="owner_id",
            op=CompOp.EQ,
            value=ValueRef(current_user=True),
        )
        result = _resolve_predicate_filters(pred, "Task", FKGraph(), "user-123", None)
        assert "__scope_predicate" in result
        sql, params = result["__scope_predicate"]
        assert '"owner_id"' in sql
        # No auth_context → falls back to user_id
        assert params == ["user-123"]

    def test_contradiction_produces_false(self):
        """Contradiction predicate produces SQL 'FALSE'."""
        pytest.importorskip("fastapi")
        from dazzle.core.ir.fk_graph import FKGraph
        from dazzle.core.ir.predicates import Contradiction
        from dazzle.http.runtime.route_generator import _resolve_predicate_filters

        result = _resolve_predicate_filters(Contradiction(), "Task", FKGraph(), "user-1", None)
        assert "__scope_predicate" in result
        sql, params = result["__scope_predicate"]
        assert sql == "FALSE"
        assert params == []


class TestResolveScopeFiltersPredicatePath:
    """Tests for _resolve_scope_filters using the new predicate pipeline."""

    def _make_scope_spec_with_predicate(self, predicate, personas=None):
        """Build a minimal cedar_access_spec with a scope rule carrying a predicate."""
        from types import SimpleNamespace

        scope_rule = SimpleNamespace(
            operation=SimpleNamespace(value="list"),
            condition=SimpleNamespace(kind="comparison", field="x", value="y"),
            personas=personas or ["*"],
            predicate=predicate,
        )
        return SimpleNamespace(scopes=[scope_rule])

    def test_predicate_path_used_when_available(self):
        """When predicate and fk_graph are available, predicate pipeline is used."""
        pytest.importorskip("fastapi")
        from dazzle.core.ir.fk_graph import FKGraph
        from dazzle.core.ir.predicates import CompOp, UserAttrCheck
        from dazzle.http.runtime.route_generator import _resolve_scope_filters

        pred = UserAttrCheck(field="school_id", user_attr="school", op=CompOp.EQ)

        class FakeUser:
            school = "school-42"

        class FakeAuth:
            user = FakeUser()
            preferences = {}

        spec = self._make_scope_spec_with_predicate(pred)
        result = _resolve_scope_filters(
            spec,
            "list",
            {"*"},
            "user-1",
            auth_context=FakeAuth(),
            entity_name="Student",
            fk_graph=FKGraph(),
        )
        assert result is not None
        assert "__scope_predicate" in result

    def test_legacy_fallback_when_no_fk_graph(self):
        """Without fk_graph, falls back to legacy condition extraction."""
        pytest.importorskip("fastapi")
        from dazzle.core.ir.predicates import CompOp, UserAttrCheck
        from dazzle.http.runtime.route_generator import _resolve_scope_filters

        pred = UserAttrCheck(field="school_id", user_attr="school", op=CompOp.EQ)
        spec = self._make_scope_spec_with_predicate(pred)
        result = _resolve_scope_filters(
            spec,
            "list",
            {"*"},
            "user-1",
            fk_graph=None,  # no fk_graph → legacy path
        )
        assert result is not None
        # Legacy path uses condition extraction, not __scope_predicate
        assert "__scope_predicate" not in result

    @staticmethod
    def _user_without(attr: str) -> Any:
        """An auth context whose user record and preferences lack ``attr``."""
        from types import SimpleNamespace

        return SimpleNamespace(
            user=SimpleNamespace(id="user-1", email="t@example.com"),
            preferences={},
            active_membership=None,
        )

    def test_unresolved_user_attribute_denies_without_raising(self, caplog):
        """Flense ship AA: a rule whose `current_user.<attr>` does not resolve used
        to append `None` to the union and raise TypeError (a 500 on list, search
        and read). It is now an always-false rule: no rows, the same `None` as
        "no scope rule matched", and a WARNING naming entity, verb and attribute."""
        pytest.importorskip("fastapi")
        from dazzle.core.ir.fk_graph import FKGraph
        from dazzle.core.ir.predicates import CompOp, UserAttrCheck
        from dazzle.http.runtime.route_generator import _resolve_scope_filters

        pred = UserAttrCheck(field="department_id", user_attr="department", op=CompOp.EQ)
        spec = self._make_scope_spec_with_predicate(pred, personas=["teacher"])

        with caplog.at_level("WARNING"):
            result = _resolve_scope_filters(
                spec,
                "list",
                {"teacher"},
                "user-1",
                auth_context=self._user_without("department"),
                entity_name="Assessment",
                fk_graph=FKGraph(),
            )

        assert result is None
        assert "Assessment list" in caplog.text
        assert "current_user.department" in caplog.text

    def test_unresolved_rule_leaves_the_other_roles_scope_in_force(self):
        """Union semantics: the unresolvable rule contributes no rows, the
        resolvable rule of the caller's other role still applies."""
        pytest.importorskip("fastapi")
        from types import SimpleNamespace

        from dazzle.core.ir.fk_graph import FKGraph
        from dazzle.core.ir.predicates import ColumnCheck, CompOp, UserAttrCheck, ValueRef
        from dazzle.http.runtime.route_generator import _resolve_scope_filters

        dept_rule = SimpleNamespace(
            operation=SimpleNamespace(value="list"),
            condition=None,
            personas=["teacher"],
            predicate=UserAttrCheck(field="department_id", user_attr="department", op=CompOp.EQ),
        )
        own_rule = SimpleNamespace(
            operation=SimpleNamespace(value="list"),
            condition=None,
            personas=["author"],
            predicate=ColumnCheck(
                field="owner_id", op=CompOp.EQ, value=ValueRef(current_user=True)
            ),
        )
        spec = SimpleNamespace(scopes=[dept_rule, own_rule])

        result = _resolve_scope_filters(
            spec,
            "list",
            {"teacher", "author"},
            "user-1",
            auth_context=self._user_without("department"),
            entity_name="Assessment",
            fk_graph=FKGraph(),
        )

        assert result is not None
        sql, params = result["__scope_predicate"]
        assert '"owner_id"' in sql and "department_id" not in sql
        assert params == ["user-1"]


class TestQueryBuilderScopePredicate:
    """Tests for QueryBuilder handling of __scope_predicate."""

    def test_scope_predicate_injected_into_where(self):
        """__scope_predicate key is extracted and injected into WHERE clause."""
        from dazzle.http.runtime.query_builder import QueryBuilder

        builder = QueryBuilder(table_name="Task")
        builder.add_filters(
            {
                "__scope_predicate": ('"school_id" = %s', ["school-42"]),
                "status": "active",
            }
        )

        where_clause, params = builder.build_where_clause()
        assert '"school_id" = %s' in where_clause
        assert '"status"' in where_clause
        assert "school-42" in params
        assert "active" in params

    def test_scope_predicate_alone(self):
        """Scope predicate works as the only filter."""
        from dazzle.http.runtime.query_builder import QueryBuilder

        builder = QueryBuilder(table_name="Student")
        builder.add_filters({"__scope_predicate": ('"owner" = %s', ["u1"])})

        where_clause, params = builder.build_where_clause()
        assert "WHERE" in where_clause
        assert '"owner" = %s' in where_clause
        assert params == ["u1"]

    def test_empty_scope_predicate_ignored(self):
        """Empty scope predicate SQL does not add a WHERE fragment."""
        from dazzle.http.runtime.query_builder import QueryBuilder

        builder = QueryBuilder(table_name="Task")
        builder.add_filters({"__scope_predicate": ("", [])})

        where_clause, params = builder.build_where_clause()
        assert where_clause == ""
        assert params == []


class TestScopeRuleSpecPredicate:
    """Tests for ScopeRuleSpec carrying predicate through conversion."""

    def test_scope_rule_spec_carries_predicate(self):
        """ScopeRuleSpec.predicate is set when converting from IR ScopeRule."""
        from dazzle.core.ir.predicates import CompOp, UserAttrCheck
        from dazzle.http.converters.entity_converter import _convert_scope_rule

        pred = UserAttrCheck(field="school_id", user_attr="school", op=CompOp.EQ)
        ir_rule = ScopeRule(
            operation=PermissionKind.LIST,
            condition=_make_condition(),
            personas=["teacher"],
            predicate=pred,
        )

        result = _convert_scope_rule(ir_rule)
        assert result.predicate is pred

    def test_scope_rule_spec_predicate_none_by_default(self):
        """ScopeRuleSpec.predicate defaults to None."""
        from dazzle.http.converters.entity_converter import _convert_scope_rule

        ir_rule = ScopeRule(
            operation=PermissionKind.LIST,
            condition=None,
            personas=["admin"],
        )
        result = _convert_scope_rule(ir_rule)
        assert result.predicate is None


class TestDualRoleScopeUnion:
    """#1742 — each role's scope applies.

    Before this, a dual-role user matched several restrictive rules and the
    resolver `return`ed on the **first** one that produced a filter, so what a
    person could see depended on the order of the DSL. No dual-role test existed.

    The union itself is tested as the pure function it is; one test through
    `_resolve_scope_filters` proves the resolver now visits *every* matched rule
    instead of stopping at the first.
    """

    _OWNER = {"__scope_predicate": ('"owner_id" = %s', ["user-1"])}
    _CLASS = {"__scope_predicate": ('"class_id" = %s', ["c-9"])}

    @pytest.mark.parametrize(
        ("rules", "expected"),
        [
            # The acceptance case: a student sees own rows, a teacher sees their
            # class's, and a user holding both sees the union. Each rule keeps its
            # own parentheses so its ANDs cannot leak across; params follow the
            # fragment order.
            pytest.param(
                [_OWNER, _CLASS],
                {
                    "__scope_predicate": (
                        '("owner_id" = %s) OR ("class_id" = %s)',
                        ["user-1", "c-9"],
                    )
                },
                id="two-roles-union-1742",
            ),
            # Swapping the rules changes the order of the fragments, never the set
            # of rows visible — which was the whole defect.
            pytest.param(
                [_CLASS, _OWNER],
                {
                    "__scope_predicate": (
                        '("class_id" = %s) OR ("owner_id" = %s)',
                        ["c-9", "user-1"],
                    )
                },
                id="swapped-order-same-fragments-1742",
            ),
            pytest.param([_OWNER], _OWNER, id="single-rule-passes-through"),
            # A role expressing no row restriction contributes none, which is
            # unconditional access.
            pytest.param(
                [{"__scope_predicate": ('"x" = %s', [1])}, {"__scope_predicate": ("", [])}],
                {},
                id="unrestricted-role-makes-union-unconditional",
            ),
        ],
    )
    def test_union_of_rule_filters(
        self, rules: list[dict[str, Any]], expected: dict[str, Any]
    ) -> None:
        from dazzle.http.runtime.scope_filters import _union_rule_filters

        assert _union_rule_filters(rules, "Doc") == expected

    @pytest.mark.parametrize(
        "rules",
        [
            # The legacy condition path produces column filters, which have no SQL
            # to OR-join. It keeps the pre-#1742 behaviour loudly rather than
            # dropping a role's scope silently.
            pytest.param(
                [{"school": "school-42"}, {"district": "d-7"}], id="legacy-column-filters"
            ),
            pytest.param(
                [{"__scope_predicate": ('"owner_id" = %s', ["u1"])}, {"district": "d-7"}],
                id="mixed-shapes",
            ),
        ],
    )
    def test_unjoinable_filters_keep_first_declared_and_say_so(
        self, rules: list[dict[str, Any]], caplog
    ) -> None:
        from dazzle.http.runtime.scope_filters import _union_rule_filters

        with caplog.at_level("WARNING"):
            result = _union_rule_filters(rules, "Doc")

        assert result == rules[0]
        assert "first-declared rule" in caplog.text

    def test_no_resolved_rules_returns_none_for_the_callers_fail_closed_path(self) -> None:
        """`None` keeps the caller's fall-through: a matched rule that produced no
        filter is a resolution failure, not `scope: all`."""
        from dazzle.http.runtime.scope_filters import _union_rule_filters

        assert _union_rule_filters([], "Doc") is None

    def test_resolver_visits_every_matched_rule_not_just_the_first(self, caplog) -> None:
        """The plumbing half: two matching legacy rules must both be resolved,
        which is what makes the warning above fire — the old code returned on the
        first."""
        from unittest.mock import MagicMock

        from dazzle.http.runtime.route_generator import _resolve_scope_filters
        from dazzle.http.specs.auth import (
            AccessComparisonKind,
            AccessConditionSpec,
            AccessOperationKind,
            EntityAccessSpec,
            ScopeRuleSpec,
        )

        spec = EntityAccessSpec(
            scopes=[
                ScopeRuleSpec(
                    operation=AccessOperationKind.LIST,
                    condition=AccessConditionSpec(
                        kind="comparison",
                        field="school",
                        comparison_op=AccessComparisonKind.EQUALS,
                        value="current_user.school",
                    ),
                    personas=["teacher"],
                ),
                ScopeRuleSpec(
                    operation=AccessOperationKind.LIST,
                    condition=AccessConditionSpec(
                        kind="comparison",
                        field="district",
                        comparison_op=AccessComparisonKind.EQUALS,
                        value="current_user.district",
                    ),
                    personas=["auditor"],
                ),
            ]
        )
        auth_ctx = MagicMock()
        auth_ctx.preferences = {"school": "school-42", "district": "d-7"}

        with caplog.at_level("WARNING"):
            result = _resolve_scope_filters(
                spec, "list", {"teacher", "auditor"}, "user-1", auth_ctx
            )

        # First-declared for the legacy shape (documented), but both rules were
        # visited — which is the behaviour change, visible in the log.
        assert result == {"school": "school-42"}
        assert "first-declared rule" in caplog.text
