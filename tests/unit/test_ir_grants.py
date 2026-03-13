"""Tests for grant schema IR types."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from dazzle.core.ir.conditions import ConditionExpr, RoleCheck
from dazzle.core.ir.grants import (
    GrantApprovalMode,
    GrantExpiryMode,
    GrantRelationSpec,
    GrantSchemaSpec,
)
from dazzle.core.ir.location import SourceLocation

# ---------------------------------------------------------------------------
# Enum values
# ---------------------------------------------------------------------------


def test_grant_approval_mode_values() -> None:
    assert GrantApprovalMode.REQUIRED == "required"
    assert GrantApprovalMode.IMMEDIATE == "immediate"
    assert GrantApprovalMode.NONE == "none"


def test_grant_expiry_mode_values() -> None:
    assert GrantExpiryMode.REQUIRED == "required"
    assert GrantExpiryMode.OPTIONAL == "optional"
    assert GrantExpiryMode.NONE == "none"


# ---------------------------------------------------------------------------
# GrantRelationSpec — minimal
# ---------------------------------------------------------------------------


def _role_condition(role: str = "senior_leadership") -> ConditionExpr:
    return ConditionExpr(role_check=RoleCheck(role_name=role))


def test_grant_relation_spec_minimal() -> None:
    rel = GrantRelationSpec(
        name="acting_hod",
        label="Assign covering HoD",
        granted_by=_role_condition(),
    )
    assert rel.name == "acting_hod"
    assert rel.label == "Assign covering HoD"
    assert rel.description is None
    assert rel.principal_label is None
    assert rel.confirmation is None
    assert rel.revoke_verb is None
    assert rel.approved_by is None
    assert rel.approval == GrantApprovalMode.REQUIRED
    assert rel.expiry == GrantExpiryMode.REQUIRED
    assert rel.max_duration is None
    assert rel.source_location is None


def test_grant_relation_spec_full() -> None:
    loc = SourceLocation(file="test.dsl", line=10, column=4)
    approved_by = _role_condition("hod")
    rel = GrantRelationSpec(
        name="acting_hod",
        label="Assign covering HoD",
        description="Temporarily delegates HoD responsibilities",
        principal_label="Covering HoD",
        confirmation="Are you sure you want to assign {principal} as covering HoD?",
        revoke_verb="Remove covering HoD",
        granted_by=_role_condition("senior_leadership"),
        approved_by=approved_by,
        approval=GrantApprovalMode.REQUIRED,
        expiry=GrantExpiryMode.REQUIRED,
        max_duration="90d",
        source_location=loc,
    )
    assert rel.description == "Temporarily delegates HoD responsibilities"
    assert rel.principal_label == "Covering HoD"
    assert rel.confirmation is not None and "principal" in rel.confirmation
    assert rel.revoke_verb == "Remove covering HoD"
    assert rel.approved_by is not None
    assert rel.approved_by.role_check is not None
    assert rel.approved_by.role_check.role_name == "hod"
    assert rel.approval == GrantApprovalMode.REQUIRED
    assert rel.expiry == GrantExpiryMode.REQUIRED
    assert rel.max_duration == "90d"
    assert rel.source_location == loc


def test_grant_relation_spec_immediate_approval() -> None:
    rel = GrantRelationSpec(
        name="observer",
        label="Grant observer access",
        granted_by=_role_condition("manager"),
        approval=GrantApprovalMode.IMMEDIATE,
        expiry=GrantExpiryMode.OPTIONAL,
    )
    assert rel.approval == GrantApprovalMode.IMMEDIATE
    assert rel.expiry == GrantExpiryMode.OPTIONAL


def test_grant_relation_spec_no_expiry() -> None:
    rel = GrantRelationSpec(
        name="delegate",
        label="Delegate task",
        granted_by=_role_condition("admin"),
        approval=GrantApprovalMode.NONE,
        expiry=GrantExpiryMode.NONE,
    )
    assert rel.approval == GrantApprovalMode.NONE
    assert rel.expiry == GrantExpiryMode.NONE


# ---------------------------------------------------------------------------
# GrantRelationSpec — frozen model
# ---------------------------------------------------------------------------


def test_grant_relation_spec_is_frozen() -> None:
    rel = GrantRelationSpec(
        name="acting_hod",
        label="Assign covering HoD",
        granted_by=_role_condition(),
    )
    with pytest.raises(ValidationError):
        rel.name = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# GrantSchemaSpec — single relation
# ---------------------------------------------------------------------------


def test_grant_schema_spec_single_relation() -> None:
    rel = GrantRelationSpec(
        name="acting_hod",
        label="Assign covering HoD",
        granted_by=_role_condition(),
    )
    schema = GrantSchemaSpec(
        name="department_delegation",
        label="Department Delegation",
        scope="Department",
        relations=[rel],
    )
    assert schema.name == "department_delegation"
    assert schema.label == "Department Delegation"
    assert schema.description is None
    assert schema.scope == "Department"
    assert len(schema.relations) == 1
    assert schema.relations[0].name == "acting_hod"
    assert schema.source_location is None


def test_grant_schema_spec_multiple_relations() -> None:
    rel1 = GrantRelationSpec(
        name="acting_hod",
        label="Assign covering HoD",
        granted_by=_role_condition("senior_leadership"),
        max_duration="90d",
    )
    rel2 = GrantRelationSpec(
        name="observer",
        label="Grant observer access",
        granted_by=_role_condition("hod"),
        approval=GrantApprovalMode.IMMEDIATE,
        expiry=GrantExpiryMode.OPTIONAL,
    )
    schema = GrantSchemaSpec(
        name="department_delegation",
        label="Department Delegation",
        description="Runtime delegation for department hierarchy",
        scope="Department",
        relations=[rel1, rel2],
    )
    assert len(schema.relations) == 2
    assert schema.relations[0].name == "acting_hod"
    assert schema.relations[1].name == "observer"
    assert schema.description == "Runtime delegation for department hierarchy"


def test_grant_schema_spec_empty_relations() -> None:
    schema = GrantSchemaSpec(
        name="placeholder_schema",
        label="Placeholder",
        scope="SomeEntity",
        relations=[],
    )
    assert schema.relations == []


# ---------------------------------------------------------------------------
# GrantSchemaSpec — frozen model
# ---------------------------------------------------------------------------


def test_grant_schema_spec_is_frozen() -> None:
    schema = GrantSchemaSpec(
        name="department_delegation",
        label="Department Delegation",
        scope="Department",
        relations=[],
    )
    with pytest.raises(ValidationError):
        schema.name = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# GrantSchemaSpec — with source location
# ---------------------------------------------------------------------------


def test_grant_schema_spec_with_source_location() -> None:
    loc = SourceLocation(file="test.dsl", line=1, column=0)
    schema = GrantSchemaSpec(
        name="department_delegation",
        label="Department Delegation",
        scope="Department",
        relations=[],
        source_location=loc,
    )
    assert schema.source_location is not None
    assert schema.source_location.line == 1
    assert schema.source_location.column == 0


# ---------------------------------------------------------------------------
# Public IR exports
# ---------------------------------------------------------------------------


def test_ir_init_exports() -> None:
    from dazzle.core import ir

    assert hasattr(ir, "GrantApprovalMode")
    assert hasattr(ir, "GrantExpiryMode")
    assert hasattr(ir, "GrantRelationSpec")
    assert hasattr(ir, "GrantSchemaSpec")
