"""
Tests for grant_schemas registration on ModuleFragment and AppSpec (v0.42.0).

Verifies that GrantSchemaSpec flows through the IR container types correctly.
"""

from dazzle.core.ir.appspec import AppSpec
from dazzle.core.ir.conditions import ConditionExpr, RoleCheck
from dazzle.core.ir.domain import DomainSpec
from dazzle.core.ir.grants import (
    GrantApprovalMode,
    GrantExpiryMode,
    GrantRelationSpec,
    GrantSchemaSpec,
)
from dazzle.core.ir.module import ModuleFragment

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_condition(role: str) -> ConditionExpr:
    """Build a minimal role() condition expression."""
    return ConditionExpr(role_check=RoleCheck(role_name=role))


def _make_relation(name: str = "acting_hod", label: str = "Acting HoD") -> GrantRelationSpec:
    return GrantRelationSpec(
        name=name,
        label=label,
        granted_by=_make_condition("senior_leadership"),
        approval=GrantApprovalMode.REQUIRED,
        expiry=GrantExpiryMode.REQUIRED,
    )


def _make_grant_schema(
    name: str = "dept_delegation",
    label: str = "Department Delegation",
    scope: str = "Department",
) -> GrantSchemaSpec:
    return GrantSchemaSpec(
        name=name,
        label=label,
        scope=scope,
        relations=[_make_relation()],
    )


def _make_appspec(grant_schemas: list[GrantSchemaSpec] | None = None) -> AppSpec:
    """Build a minimal AppSpec."""
    return AppSpec(
        name="test_app",
        domain=DomainSpec(entities=[]),
        grant_schemas=grant_schemas or [],
    )


# ---------------------------------------------------------------------------
# ModuleFragment
# ---------------------------------------------------------------------------


class TestModuleFragmentGrantSchemas:
    def test_defaults_to_empty_list(self) -> None:
        fragment = ModuleFragment()
        assert fragment.grant_schemas == []

    def test_can_hold_grant_schemas(self) -> None:
        schema = _make_grant_schema()
        fragment = ModuleFragment(grant_schemas=[schema])
        assert len(fragment.grant_schemas) == 1
        assert fragment.grant_schemas[0].name == "dept_delegation"

    def test_can_hold_multiple_grant_schemas(self) -> None:
        schemas = [
            _make_grant_schema("schema_a", "Schema A", "EntityA"),
            _make_grant_schema("schema_b", "Schema B", "EntityB"),
        ]
        fragment = ModuleFragment(grant_schemas=schemas)
        assert len(fragment.grant_schemas) == 2
        names = {s.name for s in fragment.grant_schemas}
        assert names == {"schema_a", "schema_b"}


# ---------------------------------------------------------------------------
# AppSpec
# ---------------------------------------------------------------------------


class TestAppSpecGrantSchemas:
    def test_defaults_to_empty_list(self) -> None:
        app = _make_appspec()
        assert app.grant_schemas == []

    def test_can_hold_grant_schemas(self) -> None:
        schema = _make_grant_schema()
        app = _make_appspec(grant_schemas=[schema])
        assert len(app.grant_schemas) == 1

    def test_get_grant_schema_finds_by_name(self) -> None:
        schema = _make_grant_schema("dept_delegation")
        app = _make_appspec(grant_schemas=[schema])
        result = app.get_grant_schema("dept_delegation")
        assert result is not None
        assert result.name == "dept_delegation"

    def test_get_grant_schema_returns_none_when_missing(self) -> None:
        app = _make_appspec()
        assert app.get_grant_schema("nonexistent") is None

    def test_get_grant_schema_returns_none_for_wrong_name(self) -> None:
        schema = _make_grant_schema("dept_delegation")
        app = _make_appspec(grant_schemas=[schema])
        assert app.get_grant_schema("other_schema") is None

    def test_get_grant_schemas_by_scope_filters_correctly(self) -> None:
        dept_schema = _make_grant_schema("dept_delegation", scope="Department")
        team_schema = _make_grant_schema("team_delegation", scope="Team")
        app = _make_appspec(grant_schemas=[dept_schema, team_schema])

        dept_results = app.get_grant_schemas_by_scope("Department")
        assert len(dept_results) == 1
        assert dept_results[0].name == "dept_delegation"

        team_results = app.get_grant_schemas_by_scope("Team")
        assert len(team_results) == 1
        assert team_results[0].name == "team_delegation"

    def test_get_grant_schemas_by_scope_returns_empty_list_for_unknown_entity(self) -> None:
        schema = _make_grant_schema(scope="Department")
        app = _make_appspec(grant_schemas=[schema])
        assert app.get_grant_schemas_by_scope("NonExistentEntity") == []

    def test_get_grant_schemas_by_scope_returns_multiple(self) -> None:
        schema_a = _make_grant_schema("schema_a", scope="Department")
        schema_b = _make_grant_schema("schema_b", scope="Department")
        app = _make_appspec(grant_schemas=[schema_a, schema_b])
        results = app.get_grant_schemas_by_scope("Department")
        assert len(results) == 2
