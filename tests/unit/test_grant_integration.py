# tests/unit/test_grant_integration.py
"""Integration test: DSL parse → IR → grant store → condition evaluation (PostgreSQL)."""

import os
from pathlib import Path
from uuid import uuid4

import pytest

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.http.runtime.condition_evaluator import evaluate_condition
from dazzle.http.runtime.grant_store import GrantStore

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

    def test_store_row_with_expiry_evaluates(self, pg_integration_conn):
        """Flense ship AC: a stored grant's `expires_at` is a datetime; the check
        compared it with an ISO string and raised TypeError."""
        from datetime import UTC, datetime, timedelta

        store = GrantStore(pg_integration_conn)
        user_id, dept_id = uuid4(), uuid4()
        store.create_grant(
            schema_name="dept_delegation",
            relation="acting_hod",
            principal_id=user_id,
            scope_entity="Department",
            scope_id=dept_id,
            granted_by_id=uuid4(),
            approval_mode="none",
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
        active_grants = store.list_grants(principal_id=user_id, status="active")
        assert isinstance(active_grants[0]["expires_at"], datetime)
        condition = {"grant_check": {"relation": "acting_hod", "scope_field": "department"}}
        context = {"active_grants": active_grants}
        assert evaluate_condition(condition, {"department": str(dept_id)}, context) is True


class TestDeclaredGrantClausesOverRoutes:
    """ADR-0057 ship Q: expiry / max_duration / approved_by enforced through the real routes."""

    def test_create_and_approve_respect_declared_clauses(self, pg_integration_conn):
        from contextlib import contextmanager
        from datetime import UTC, datetime, timedelta
        from types import SimpleNamespace
        from unittest.mock import MagicMock

        from fastapi import FastAPI, Request
        from fastapi.testclient import TestClient

        from dazzle.http.runtime.grant_routes import create_grant_routes

        dsl = """module test_mod

grant_schema department_delegation "Department Delegation":
  scope: Department
  relation acting_hod "Assign Acting Head of Department":
    granted_by: role(school_admin)
    approved_by: role(senior_leader)
    approval: required
    expiry: required
    max_duration: 90d
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        schema = fragment.grant_schemas[0]
        appspec = MagicMock()
        appspec.get_grant_schema = lambda n: schema if n == schema.name else None

        @contextmanager
        def _conn():
            yield pg_integration_conn

        db = MagicMock()
        db.connection = _conn

        def auth_dep(request: Request):
            return SimpleNamespace(
                is_authenticated=True,
                user_id=request.headers["x-user"],
                user=SimpleNamespace(roles=[request.headers["x-role"]]),
            )

        app = FastAPI()
        app.include_router(create_grant_routes(db_manager=db, appspec=appspec, auth_dep=auth_dep))
        client = TestClient(app)
        admin = {"x-user": str(uuid4()), "x-role": "school_admin"}
        leader = {"x-user": str(uuid4()), "x-role": "senior_leader"}
        body = {
            "schema_name": "department_delegation",
            "relation": "acting_hod",
            "principal_id": str(uuid4()),
            "scope_entity": "Department",
            "scope_id": str(uuid4()),
        }

        assert client.post("/_dazzle/grants", json=body, headers=admin).status_code == 422
        too_long = (datetime.now(UTC) + timedelta(days=91)).isoformat()
        resp = client.post("/_dazzle/grants", json={**body, "expires_at": too_long}, headers=admin)
        assert resp.status_code == 422
        assert GrantStore(pg_integration_conn).list_grants() == []

        ok = (datetime.now(UTC) + timedelta(days=30)).isoformat()
        resp = client.post("/_dazzle/grants", json={**body, "expires_at": ok}, headers=admin)
        assert resp.status_code == 201, resp.text
        grant = resp.json()["grant"]
        assert grant["status"] == "pending_approval"
        assert grant["expires_at"] is not None

        gid = grant["id"]
        assert client.post(f"/_dazzle/grants/{gid}/approve", headers=admin).status_code == 403
        resp = client.post(f"/_dazzle/grants/{gid}/approve", headers=leader)
        assert resp.status_code == 200, resp.text
        assert resp.json()["grant"]["status"] == "active"
        assert str(resp.json()["grant"]["approved_by_id"]) == leader["x-user"]


class TestGrantListingOverRoutes:
    """Flense ship AC: `GET /_dazzle/grants` is authorised against the real store."""

    def test_listing_is_scoped_to_the_caller(self, pg_integration_conn):
        from contextlib import contextmanager
        from types import SimpleNamespace
        from unittest.mock import MagicMock

        from fastapi import FastAPI, Request
        from fastapi.testclient import TestClient

        from dazzle.http.runtime.grant_routes import create_grant_routes

        dsl = """module test_mod

grant_schema department_delegation "Department Delegation":
  scope: Department
  relation observer "Assign Observer":
    granted_by: role(school_admin)
    approval: none
    expiry: optional
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        schema = fragment.grant_schemas[0]
        appspec = MagicMock()
        appspec.get_grant_schema = lambda n: schema if n == schema.name else None

        @contextmanager
        def _conn():
            yield pg_integration_conn

        db = MagicMock()
        db.connection = _conn

        def auth_dep(request: Request):
            return SimpleNamespace(
                is_authenticated=True,
                user_id=request.headers["x-user"],
                user=SimpleNamespace(
                    roles=[request.headers["x-role"]],
                    is_superuser=request.headers.get("x-superuser") == "1",
                ),
            )

        app = FastAPI()
        app.include_router(create_grant_routes(db_manager=db, appspec=appspec, auth_dep=auth_dep))
        client = TestClient(app)
        admin = {"x-user": str(uuid4()), "x-role": "school_admin"}
        holder, bystander = str(uuid4()), str(uuid4())
        created = set()
        for principal in (holder, str(uuid4())):
            body = {
                "schema_name": "department_delegation",
                "relation": "observer",
                "principal_id": principal,
                "scope_entity": "Department",
                "scope_id": str(uuid4()),
            }
            resp = client.post("/_dazzle/grants", json=body, headers=admin)
            assert resp.status_code == 201, resp.text
            created.add(str(resp.json()["grant"]["id"]))

        def listed(headers: dict[str, str]) -> set[str]:
            resp = client.get("/_dazzle/grants", headers=headers)
            assert resp.status_code == 200, resp.text
            return {str(g["id"]) for g in resp.json()["grants"]}

        assert listed({"x-user": bystander, "x-role": "teacher"}) == set()
        holder_view = listed({"x-user": holder, "x-role": "teacher"})
        assert len(holder_view) == 1 and holder_view < created
        assert listed({"x-user": str(uuid4()), "x-role": "school_admin"}) == created
        su = {"x-user": bystander, "x-role": "teacher", "x-superuser": "1"}
        assert listed(su) == created
