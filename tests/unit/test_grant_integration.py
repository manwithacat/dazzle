# tests/unit/test_grant_integration.py
"""Integration test: DSL parse → IR → grant store → condition evaluation (PostgreSQL)."""

import os
from pathlib import Path
from uuid import uuid4

import pytest

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle_back.runtime.condition_evaluator import evaluate_condition
from dazzle_back.runtime.grant_store import GrantStore

pytestmark = pytest.mark.postgres


@pytest.fixture
def pg_integration_conn():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set")
    import psycopg
    from psycopg.rows import dict_row

    conn = psycopg.connect(url, row_factory=dict_row)
    conn.execute("DROP TABLE IF EXISTS _grant_events, _grants")
    conn.commit()
    yield conn
    conn.close()


class TestGrantPipelineIntegration:
    def test_parse_to_evaluation_pipeline(self, pg_integration_conn):
        """Parse grant_schema DSL, create grant in store, evaluate condition."""
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

        entity = [e for e in fragment.entities if e.name == "AssessmentEvent"][0]
        read_rules = [r for r in entity.access.permissions if r.operation.value == "read"]
        assert read_rules
        cond = read_rules[0].condition
        assert cond.is_compound
        assert cond.right.grant_check is not None
        assert cond.right.grant_check.relation == "acting_hod"
        assert cond.right.grant_check.scope_field == "department"

        store = GrantStore(pg_integration_conn)
        user_id = uuid4()
        dept_id = uuid4()

        store.create_grant(
            schema_name="dept_delegation",
            relation="acting_hod",
            principal_id=user_id,
            scope_entity="Department",
            scope_id=dept_id,
            granted_by_id=uuid4(),
            approval_mode="none",
        )

        active_grants = store.list_grants(principal_id=user_id, status="active")
        condition_dict = cond.model_dump()
        record = {"department": str(dept_id)}
        context = {"user_roles": [], "active_grants": active_grants}

        result = evaluate_condition(condition_dict, record, context)
        assert result is True, "User with active grant should pass has_grant() check"

    def test_parse_to_evaluation_no_grant(self, pg_integration_conn):
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

        # Ensure tables exist
        GrantStore(pg_integration_conn)

        record = {"department": str(uuid4())}
        context = {"active_grants": []}

        result = evaluate_condition(condition_dict, record, context)
        assert result is False
