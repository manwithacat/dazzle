# tests/unit/test_parse_has_grant.py
"""Tests for has_grant() condition parsing."""

from pathlib import Path

from dazzle.core.dsl_parser_impl import parse_dsl


def _parse_access_condition(dsl_text: str):
    """Parse a minimal entity with an access rule and return the read condition."""
    full = f"""module test_mod
entity Thing "Thing":
  id: uuid pk
  department: ref Department
  access:
    read: {dsl_text}
"""
    _, _, _, _, _, fragment = parse_dsl(full, Path("test.dsl"))
    entity = fragment.entities[0]
    read_rules = [r for r in entity.access.permissions if r.operation.value == "read"]
    assert read_rules, f"No read rule found for: {dsl_text}"
    return read_rules[0].condition


class TestHasGrantParsing:
    def test_simple_has_grant(self):
        cond = _parse_access_condition('has_grant("acting_hod", department)')
        assert cond.grant_check is not None
        assert cond.grant_check.relation == "acting_hod"
        assert cond.grant_check.scope_field == "department"

    def test_has_grant_or_role(self):
        cond = _parse_access_condition('role(hod) or has_grant("acting_hod", department)')
        assert cond.is_compound
        assert cond.left.is_role_check
        assert cond.right.grant_check is not None
        assert cond.right.grant_check.relation == "acting_hod"

    def test_has_grant_and_comparison(self):
        cond = _parse_access_condition('has_grant("observer", department) and status = active')
        assert cond.is_compound
        assert cond.left.grant_check is not None
        assert cond.right.comparison is not None

    def test_has_grant_in_parentheses(self):
        cond = _parse_access_condition('(has_grant("acting_hod", department)) or role(admin)')
        assert cond.is_compound
        assert cond.left.grant_check is not None
        assert cond.right.is_role_check
