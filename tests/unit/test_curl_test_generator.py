"""Unit tests for CurlTestGenerator — bash/curl smoke test generation."""

from __future__ import annotations

import pytest

from dazzle.core.ir import (
    AppSpec,
    DomainSpec,
    EntitySpec,
    FieldModifier,
    FieldSpec,
    FieldType,
    FieldTypeKind,
    PersonaSpec,
    StateMachineSpec,
    StateTransition,
)
from dazzle.testing.curl_test_generator import ALL_SUITES, CurlTestGenerator

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def simple_entity() -> EntitySpec:
    return EntitySpec(
        name="Task",
        title="Task",
        fields=[
            FieldSpec(
                name="id",
                type=FieldType(kind=FieldTypeKind.UUID),
                modifiers=[FieldModifier.PK],
            ),
            FieldSpec(
                name="title",
                type=FieldType(kind=FieldTypeKind.STR, max_length=200),
                modifiers=[FieldModifier.REQUIRED],
            ),
            FieldSpec(
                name="completed",
                type=FieldType(kind=FieldTypeKind.BOOL),
                default=False,
            ),
        ],
    )


@pytest.fixture
def entity_with_money() -> EntitySpec:
    return EntitySpec(
        name="Invoice",
        title="Invoice",
        fields=[
            FieldSpec(
                name="id",
                type=FieldType(kind=FieldTypeKind.UUID),
                modifiers=[FieldModifier.PK],
            ),
            FieldSpec(
                name="amount",
                type=FieldType(kind=FieldTypeKind.MONEY, currency_code="GBP"),
                modifiers=[FieldModifier.REQUIRED],
            ),
            FieldSpec(
                name="label",
                type=FieldType(kind=FieldTypeKind.STR, max_length=100),
                modifiers=[FieldModifier.REQUIRED],
            ),
        ],
    )


@pytest.fixture
def parent_entity() -> EntitySpec:
    return EntitySpec(
        name="Project",
        title="Project",
        fields=[
            FieldSpec(
                name="id",
                type=FieldType(kind=FieldTypeKind.UUID),
                modifiers=[FieldModifier.PK],
            ),
            FieldSpec(
                name="name",
                type=FieldType(kind=FieldTypeKind.STR, max_length=100),
                modifiers=[FieldModifier.REQUIRED],
            ),
        ],
    )


@pytest.fixture
def child_entity() -> EntitySpec:
    """Entity with a required ref to Project."""
    return EntitySpec(
        name="Task",
        title="Task",
        fields=[
            FieldSpec(
                name="id",
                type=FieldType(kind=FieldTypeKind.UUID),
                modifiers=[FieldModifier.PK],
            ),
            FieldSpec(
                name="title",
                type=FieldType(kind=FieldTypeKind.STR, max_length=200),
                modifiers=[FieldModifier.REQUIRED],
            ),
            FieldSpec(
                name="project_id",
                type=FieldType(kind=FieldTypeKind.REF, ref_entity="Project"),
                modifiers=[FieldModifier.REQUIRED],
            ),
        ],
    )


@pytest.fixture
def entity_with_state() -> EntitySpec:
    return EntitySpec(
        name="Order",
        title="Order",
        fields=[
            FieldSpec(
                name="id",
                type=FieldType(kind=FieldTypeKind.UUID),
                modifiers=[FieldModifier.PK],
            ),
            FieldSpec(
                name="total",
                type=FieldType(kind=FieldTypeKind.DECIMAL),
                modifiers=[FieldModifier.REQUIRED],
            ),
            FieldSpec(
                name="status",
                type=FieldType(
                    kind=FieldTypeKind.ENUM,
                    enum_values=["draft", "pending", "shipped"],
                ),
                default="draft",
            ),
        ],
        state_machine=StateMachineSpec(
            status_field="status",
            states=["draft", "pending", "shipped"],
            transitions=[
                StateTransition(from_state="draft", to_state="pending"),
                StateTransition(from_state="pending", to_state="shipped"),
            ],
        ),
    )


@pytest.fixture
def simple_appspec(simple_entity: EntitySpec) -> AppSpec:
    return AppSpec(
        name="TestApp",
        title="Test Application",
        domain=DomainSpec(entities=[simple_entity]),
    )


@pytest.fixture
def appspec_with_personas(simple_entity: EntitySpec) -> AppSpec:
    return AppSpec(
        name="TestApp",
        title="Test Application",
        domain=DomainSpec(entities=[simple_entity]),
        personas=[
            PersonaSpec(id="admin", label="Admin"),
            PersonaSpec(id="viewer", label="Viewer"),
        ],
    )


@pytest.fixture
def appspec_with_state(entity_with_state: EntitySpec) -> AppSpec:
    return AppSpec(
        name="TestApp",
        title="Test Application",
        domain=DomainSpec(entities=[entity_with_state]),
    )


@pytest.fixture
def appspec_with_refs(parent_entity: EntitySpec, child_entity: EntitySpec) -> AppSpec:
    return AppSpec(
        name="TestApp",
        title="Test Application",
        domain=DomainSpec(entities=[child_entity, parent_entity]),
    )


@pytest.fixture
def appspec_with_money(entity_with_money: EntitySpec) -> AppSpec:
    return AppSpec(
        name="TestApp",
        title="Test Application",
        domain=DomainSpec(entities=[entity_with_money]),
    )


# =============================================================================
# Tests
# =============================================================================


class TestScriptStructure:
    """Test that generated scripts have valid bash structure."""

    def test_shebang(self, simple_appspec: AppSpec) -> None:
        gen = CurlTestGenerator(simple_appspec)
        script = gen.generate()
        assert script.startswith("#!/usr/bin/env bash")

    def test_helper_functions_present(self, simple_appspec: AppSpec) -> None:
        gen = CurlTestGenerator(simple_appspec)
        script = gen.generate()
        assert "assert_status()" in script
        assert "extract_json()" in script
        assert "section_header()" in script
        assert "report()" in script

    def test_set_euo_pipefail(self, simple_appspec: AppSpec) -> None:
        gen = CurlTestGenerator(simple_appspec)
        script = gen.generate()
        assert "set -euo pipefail" in script

    def test_suite_runner(self, simple_appspec: AppSpec) -> None:
        gen = CurlTestGenerator(simple_appspec)
        script = gen.generate()
        assert "run_suites()" in script
        assert 'case "$SUITE" in' in script

    def test_cleanup_trap(self, simple_appspec: AppSpec) -> None:
        gen = CurlTestGenerator(simple_appspec)
        script = gen.generate()
        assert "trap cleanup EXIT" in script

    def test_custom_base_url(self, simple_appspec: AppSpec) -> None:
        gen = CurlTestGenerator(simple_appspec, base_url="http://myhost:9000")
        script = gen.generate()
        assert "http://myhost:9000" in script


class TestCrudTests:
    """Test CRUD test generation."""

    def test_pluralized_endpoints(self, simple_appspec: AppSpec) -> None:
        gen = CurlTestGenerator(simple_appspec)
        script = gen.generate(suites=["crud"])
        assert "/api/tasks" in script

    def test_crud_operations(self, simple_appspec: AppSpec) -> None:
        gen = CurlTestGenerator(simple_appspec)
        script = gen.generate(suites=["crud"])
        assert '"Create Task"' in script
        assert '"List Task"' in script
        assert '"Get Task"' in script
        assert '"Delete Task"' in script

    def test_create_payload_has_required_fields(self, simple_appspec: AppSpec) -> None:
        gen = CurlTestGenerator(simple_appspec)
        script = gen.generate(suites=["crud"])
        # title is required
        assert '"title"' in script

    def test_update_payload(self, simple_appspec: AppSpec) -> None:
        gen = CurlTestGenerator(simple_appspec)
        script = gen.generate(suites=["crud"])
        assert "Updated value" in script

    def test_id_variable_extraction(self, simple_appspec: AppSpec) -> None:
        gen = CurlTestGenerator(simple_appspec)
        script = gen.generate(suites=["crud"])
        assert "ID_TASK=$(extract_json" in script


class TestMoneyFields:
    """Test money field expansion in payloads."""

    def test_money_minor_and_currency(self, appspec_with_money: AppSpec) -> None:
        gen = CurlTestGenerator(appspec_with_money)
        script = gen.generate(suites=["crud"])
        assert '"amount_minor"' in script
        assert '"amount_currency"' in script
        assert '"GBP"' in script

    def test_money_minor_is_integer(self, appspec_with_money: AppSpec) -> None:
        gen = CurlTestGenerator(appspec_with_money)
        script = gen.generate(suites=["crud"])
        assert '"amount_minor": 10000' in script


class TestDependencyOrdering:
    """Test that entities with ref dependencies are ordered correctly."""

    def test_parent_before_child(self, appspec_with_refs: AppSpec) -> None:
        gen = CurlTestGenerator(appspec_with_refs)
        script = gen.generate(suites=["crud"])
        # Project should appear before Task in the script
        project_pos = script.index("Create Project")
        task_pos = script.index("Create Task")
        assert project_pos < task_pos

    def test_ref_field_uses_parent_id_variable(self, appspec_with_refs: AppSpec) -> None:
        gen = CurlTestGenerator(appspec_with_refs)
        script = gen.generate(suites=["crud"])
        assert "${ID_PROJECT}" in script


class TestStateMachineTests:
    """Test state machine test generation."""

    def test_state_tests_generated(self, appspec_with_state: AppSpec) -> None:
        gen = CurlTestGenerator(appspec_with_state)
        script = gen.generate(suites=["state"])
        assert "suite_state()" in script
        assert "transition" in script

    def test_transition_direction(self, appspec_with_state: AppSpec) -> None:
        gen = CurlTestGenerator(appspec_with_state)
        script = gen.generate(suites=["state"])
        assert "draft -> pending" in script

    def test_no_state_suite_without_state_machines(self, simple_appspec: AppSpec) -> None:
        gen = CurlTestGenerator(simple_appspec)
        script = gen.generate(suites=["state"])
        # No suite_state function should be generated
        assert "suite_state()" not in script


class TestPersonaTests:
    """Test persona auth and access tests."""

    def test_persona_auth_generated(self, appspec_with_personas: AppSpec) -> None:
        gen = CurlTestGenerator(appspec_with_personas)
        script = gen.generate(suites=["auth"])
        assert "suite_auth()" in script
        assert "Authenticate as admin" in script
        assert "Authenticate as viewer" in script

    def test_persona_token_variables(self, appspec_with_personas: AppSpec) -> None:
        gen = CurlTestGenerator(appspec_with_personas)
        script = gen.generate(suites=["auth"])
        assert "TOKEN_ADMIN" in script
        assert "TOKEN_VIEWER" in script

    def test_persona_crud_access(self, appspec_with_personas: AppSpec) -> None:
        gen = CurlTestGenerator(appspec_with_personas)
        script = gen.generate(suites=["persona"])
        assert "suite_persona()" in script
        assert "admin: list Task" in script
        assert "viewer: list Task" in script

    def test_no_persona_suite_without_personas(self, simple_appspec: AppSpec) -> None:
        gen = CurlTestGenerator(simple_appspec)
        script = gen.generate(suites=["persona"])
        assert "suite_persona()" not in script

    def test_no_auth_suite_without_personas(self, simple_appspec: AppSpec) -> None:
        gen = CurlTestGenerator(simple_appspec)
        script = gen.generate(suites=["auth"])
        assert "suite_auth()" not in script


class TestValidationTests:
    """Test validation test generation."""

    def test_empty_body_sent(self, simple_appspec: AppSpec) -> None:
        gen = CurlTestGenerator(simple_appspec)
        script = gen.generate(suites=["validation"])
        assert "suite_validation()" in script
        assert "'{}'" in script

    def test_expects_422(self, simple_appspec: AppSpec) -> None:
        gen = CurlTestGenerator(simple_appspec)
        script = gen.generate(suites=["validation"])
        assert "422" in script


class TestSecurityTests:
    """Test security test generation."""

    def test_unauthenticated_access(self, simple_appspec: AppSpec) -> None:
        gen = CurlTestGenerator(simple_appspec)
        script = gen.generate(suites=["security"])
        assert "suite_security()" in script
        assert "Unauthenticated Task list" in script
        assert "401" in script

    def test_no_auth_header(self, simple_appspec: AppSpec) -> None:
        gen = CurlTestGenerator(simple_appspec)
        script = gen.generate(suites=["security"])
        # Security tests should only use GET with no auth header
        # The assert_status call should have no auth param (5th/6th arg)
        lines = [line for line in script.splitlines() if "Unauthenticated" in line]
        for line in lines:
            # Should only have 4 positional args (label, method, url, expected)
            assert "Bearer" not in line


class TestSmokeTests:
    """Test smoke test generation."""

    def test_health_check(self, simple_appspec: AppSpec) -> None:
        gen = CurlTestGenerator(simple_appspec)
        script = gen.generate(suites=["smoke"])
        assert "suite_smoke()" in script
        assert "Health check" in script
        assert "/health" in script


class TestSuiteSelection:
    """Test that suite selection filters output."""

    def test_single_suite(self, simple_appspec: AppSpec) -> None:
        gen = CurlTestGenerator(simple_appspec)
        script = gen.generate(suites=["smoke"])
        assert "suite_smoke()" in script
        assert "suite_crud()" not in script

    def test_multiple_suites(self, simple_appspec: AppSpec) -> None:
        gen = CurlTestGenerator(simple_appspec)
        script = gen.generate(suites=["smoke", "crud"])
        assert "suite_smoke()" in script
        assert "suite_crud()" in script
        assert "suite_security()" not in script

    def test_all_suites(self, simple_appspec: AppSpec) -> None:
        gen = CurlTestGenerator(simple_appspec)
        script = gen.generate()
        for suite_name in ALL_SUITES:
            # At minimum, the runner case entry should exist
            assert f"    {suite_name})" in script
