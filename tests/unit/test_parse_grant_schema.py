# tests/unit/test_parse_grant_schema.py
"""Tests for grant_schema DSL construct parsing."""

from pathlib import Path

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.ir.grants import GrantApprovalMode, GrantExpiryMode


def _parse_grant_schemas(dsl_text: str):
    """Parse DSL text and return grant_schemas from the fragment."""
    full = f"module test_mod\n{dsl_text}"
    _, _, _, _, _, fragment = parse_dsl(full, Path("test.dsl"))
    return fragment.grant_schemas


class TestGrantSchemaBasicParsing:
    def test_minimal_grant_schema(self):
        schemas = _parse_grant_schemas("""
grant_schema dept_delegation "Department Delegation":
  scope: Department

  relation acting_hod "Assign covering HoD":
    granted_by: role(senior_leadership)
""")
        assert len(schemas) == 1
        s = schemas[0]
        assert s.name == "dept_delegation"
        assert s.label == "Department Delegation"
        assert s.scope == "Department"
        assert len(s.relations) == 1
        r = s.relations[0]
        assert r.name == "acting_hod"
        assert r.label == "Assign covering HoD"
        assert r.granted_by.is_role_check
        assert r.granted_by.role_check.role_name == "senior_leadership"
        # Defaults
        assert r.approval == GrantApprovalMode.REQUIRED
        assert r.expiry == GrantExpiryMode.REQUIRED

    def test_full_grant_schema(self):
        schemas = _parse_grant_schemas("""
grant_schema dept_delegation "Department Delegation":
  description: "Delegation of department-level responsibilities"
  scope: Department

  relation acting_hod "Assign covering HoD":
    description: "Temporarily assign HoD responsibilities"
    principal_label: "Staff member"
    confirmation: "This will give {principal.name} full HoD access to {scope.name}"
    granted_by: role(senior_leadership)
    approved_by: role(principal)
    approval: required
    expiry: required
    max_duration: 90d
    revoke_verb: "Remove covering HoD"
""")
        assert len(schemas) == 1
        s = schemas[0]
        assert s.description == "Delegation of department-level responsibilities"
        r = s.relations[0]
        assert r.description == "Temporarily assign HoD responsibilities"
        assert r.principal_label == "Staff member"
        assert r.confirmation == "This will give {principal.name} full HoD access to {scope.name}"
        assert r.max_duration == "90d"
        assert r.revoke_verb == "Remove covering HoD"
        assert r.approved_by is not None
        assert r.approved_by.is_role_check

    def test_multiple_relations(self):
        schemas = _parse_grant_schemas("""
grant_schema dept_delegation "Department Delegation":
  scope: Department

  relation acting_hod "Assign covering HoD":
    granted_by: role(senior_leadership)
    approval: required
    expiry: required
    max_duration: 90d

  relation observer "Assign department observer":
    granted_by: role(hod) or has_grant("acting_hod", department)
    approval: none
    expiry: optional
""")
        assert len(schemas) == 1
        assert len(schemas[0].relations) == 2
        r1, r2 = schemas[0].relations
        assert r1.name == "acting_hod"
        assert r2.name == "observer"
        assert r2.approval == GrantApprovalMode.NONE
        assert r2.expiry == GrantExpiryMode.OPTIONAL
        # r2 granted_by should be a compound expression
        assert r2.granted_by.is_compound

    def test_approval_immediate(self):
        schemas = _parse_grant_schemas("""
grant_schema x "X":
  scope: Thing

  relation r "R":
    granted_by: role(admin)
    approval: immediate
    expiry: none
""")
        r = schemas[0].relations[0]
        assert r.approval == GrantApprovalMode.IMMEDIATE
        assert r.expiry == GrantExpiryMode.NONE


class TestMultipleGrantSchemas:
    def test_two_schemas_in_module(self):
        schemas = _parse_grant_schemas("""
grant_schema dept_delegation "Department Delegation":
  scope: Department
  relation acting_hod "Assign covering HoD":
    granted_by: role(admin)

grant_schema account_access "Account Access":
  scope: ClientAccount
  relation accountant "Assign accountant":
    granted_by: role(manager)
    approval: none
    expiry: none
""")
        assert len(schemas) == 2
        assert schemas[0].name == "dept_delegation"
        assert schemas[1].name == "account_access"
        assert schemas[1].scope == "ClientAccount"
