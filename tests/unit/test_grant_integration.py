# tests/unit/test_grant_integration.py
"""Integration test: DSL parse → IR → grant store → condition evaluation."""

import sqlite3
from pathlib import Path
from uuid import uuid4

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle_back.runtime.condition_evaluator import evaluate_condition
from dazzle_back.runtime.grant_store import GrantStore


class TestGrantPipelineIntegration:
    def test_parse_to_evaluation_pipeline(self):
        """Parse grant_schema DSL, create grant in store, evaluate condition."""
        # 1. Parse DSL with grant_schema and has_grant()
        dsl = """module test_mod

entity Department "Department":
  id: uuid pk
  name: str(200)

entity AssessmentEvent "Assessment Event":
  id: uuid pk
  department: ref Department
  access:
    read: role(hod) or has_grant("acting_hod", department)
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        # Verify has_grant parsed correctly
        entity = [e for e in fragment.entities if e.name == "AssessmentEvent"][0]
        read_rules = [r for r in entity.access.permissions if r.operation.value == "read"]
        assert read_rules
        cond = read_rules[0].condition
        assert cond.is_compound  # role(hod) or has_grant(...)
        assert cond.right.grant_check is not None
        assert cond.right.grant_check.relation == "acting_hod"
        assert cond.right.grant_check.scope_field == "department"

        # 2. Create grant in store
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        store = GrantStore(conn)

        user_id = str(uuid4())
        dept_id = str(uuid4())

        store.create_grant(
            schema_name="dept_delegation",
            relation="acting_hod",
            principal_id=user_id,
            scope_entity="Department",
            scope_id=dept_id,
            granted_by_id=str(uuid4()),
            approval_mode="none",
        )

        # 3. Evaluate condition with pre-fetched grants
        active_grants = store.list_grants(principal_id=user_id, status="active")

        # Serialize condition to dict (as it would be at runtime)
        condition_dict = cond.model_dump()

        record = {"department": dept_id}
        context = {
            "user_roles": [],  # Not an HoD
            "active_grants": active_grants,
        }

        result = evaluate_condition(condition_dict, record, context)
        assert result is True, "User with active grant should pass has_grant() check"

    def test_parse_to_evaluation_no_grant(self):
        """User without grant fails has_grant() check."""
        dsl = """module test_mod

entity Department "Department":
  id: uuid pk
  name: str(200)

entity AssessmentEvent "Assessment Event":
  id: uuid pk
  department: ref Department
  access:
    read: has_grant("acting_hod", department)
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        entity = [e for e in fragment.entities if e.name == "AssessmentEvent"][0]
        read_rules = [r for r in entity.access.permissions if r.operation.value == "read"]
        cond = read_rules[0].condition
        condition_dict = cond.model_dump()

        record = {"department": str(uuid4())}
        context = {"active_grants": []}

        result = evaluate_condition(condition_dict, record, context)
        assert result is False
