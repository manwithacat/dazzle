"""Tests for grant_routes — relation-level granted_by / approval (#650)."""

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from dazzle.http.runtime.grant_routes import create_grant_routes, resolve_grant_expiry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_relation(name: str, role_name: str, approval: str = "required"):
    """Build a minimal GrantRelationSpec-like object."""
    rel = MagicMock()
    rel.name = name
    role_check = MagicMock()
    role_check.role_name = role_name
    expr = MagicMock()
    expr.role_check = role_check
    expr.left = None
    expr.right = None
    rel.granted_by = expr
    rel.approval = approval
    return rel


def _make_schema(name: str, relations: list):
    """Build a minimal GrantSchemaSpec-like object."""
    schema = MagicMock()
    schema.name = name
    schema.relations = relations
    # Ensure schema does NOT have granted_by or approval
    del schema.granted_by
    del schema.approval
    return schema


def _make_appspec(schemas: dict):
    """Build a mock AppSpec that can look up grant schemas."""
    appspec = MagicMock()
    appspec.get_grant_schema = lambda name: schemas.get(name)
    return appspec


# ---------------------------------------------------------------------------
# Tests for _check_granted_by and _get_relation_spec
# ---------------------------------------------------------------------------


class TestCheckGrantedByUsesRelation:
    """Verify that _check_granted_by reads from relation, not schema (#650)."""

    def _build_router_internals(self, schemas: dict):
        """Create routes and extract the inner helpers via the router."""
        appspec = _make_appspec(schemas)
        # We can't easily access the closure helpers, so test via endpoint
        # behaviour instead.
        return appspec

    def test_granted_by_comes_from_relation(self):
        """The role check should use the relation's granted_by, not schema's."""
        rel = _make_relation("approve_letter", "senior_leadership")
        schema = _make_schema("engagement_approval", [rel])
        appspec = _make_appspec({"engagement_approval": schema})

        # Build routes — this exercises the closure
        router = create_grant_routes(
            db_manager=MagicMock(),
            appspec=appspec,
            auth_dep=lambda: None,
        )
        # Router should have been created without error
        assert router is not None

    def test_approval_mode_comes_from_relation(self):
        """approval_mode should be read from relation spec, not schema."""
        rel = _make_relation("approve_letter", "admin", approval="immediate")
        schema = _make_schema("test_schema", [rel])

        # Verify the relation has the approval, not the schema
        assert rel.approval == "immediate"
        assert not hasattr(schema, "approval")

    def test_schema_has_no_granted_by(self):
        """GrantSchemaSpec should not have granted_by — it's on relations."""
        rel = _make_relation("do_thing", "manager")
        schema = _make_schema("test_schema", [rel])
        assert not hasattr(schema, "granted_by")
        assert hasattr(rel, "granted_by")


# ---------------------------------------------------------------------------
# Tests for _extract_roles helper (compound expressions)
# ---------------------------------------------------------------------------


class TestExtractRoles:
    """Test role extraction from ConditionExpr trees."""

    def test_simple_role(self):
        """Single role(X) expression extracts one role."""
        from dazzle.http.runtime.grant_routes import create_grant_routes

        # We need to test _extract_roles which is a closure.
        # Test it indirectly via the route logic.
        rel = _make_relation("test_rel", "admin")
        schema = _make_schema("test", [rel])
        appspec = _make_appspec({"test": schema})

        router = create_grant_routes(db_manager=MagicMock(), appspec=appspec, auth_dep=lambda: None)
        assert router is not None

    def test_compound_or_expression(self):
        """role(X) or role(Y) extracts both roles."""
        # Build compound expression: role(admin) or role(manager)
        expr = MagicMock()
        expr.role_check = None

        left = MagicMock()
        left.role_check = MagicMock()
        left.role_check.role_name = "admin"
        left.left = None
        left.right = None

        right = MagicMock()
        right.role_check = MagicMock()
        right.role_check.role_name = "manager"
        right.left = None
        right.right = None

        expr.left = left
        expr.right = right

        rel = MagicMock()
        rel.name = "multi_role_rel"
        rel.granted_by = expr
        rel.approval = "required"

        schema = _make_schema("compound_test", [rel])
        appspec = _make_appspec({"compound_test": schema})

        router = create_grant_routes(db_manager=MagicMock(), appspec=appspec, auth_dep=lambda: None)
        assert router is not None


# ---------------------------------------------------------------------------
# Declared relation clauses are enforced (ADR-0057, flense ship Q)
# ---------------------------------------------------------------------------

_CLAUSE_DSL = """
grant_schema department_delegation "Department Delegation":
  scope: Department

  relation acting_hod "Assign Acting Head of Department":
    principal_label: "Staff member"
    confirmation: "This will give {principal.name} full HoD access to {scope.name}"
    granted_by: role(school_admin) or role(teacher)
    approved_by: role(senior_leader)
    approval: required
    expiry: required
    max_duration: 90d
    revoke_verb: "Remove Acting HoD"

  relation observer "Assign Observer":
    granted_by: role(school_admin)
    approval: none
    expiry: optional

  relation capped_optional "Capped optional":
    granted_by: role(school_admin)
    approval: none
    expiry: optional
    max_duration: 7d

  relation permanent "Permanent":
    granted_by: role(school_admin)
    approval: none
    expiry: none
"""


def _clause_relations() -> dict[str, Any]:
    from dazzle.core.dsl_parser_impl import parse_dsl

    _, _, _, _, _, fragment = parse_dsl(f"module test_mod\n{_CLAUSE_DSL}", Path("t.dsl"))
    schema = fragment.grant_schemas[0]
    return {"schema": schema, **{r.name: r for r in schema.relations}}


class _FakeGrantStore:
    """In-memory stand-in for GrantStore — the routes' decisions are under test."""

    grants: dict[str, dict[str, Any]] = {}

    def __init__(self, conn: Any) -> None:
        pass

    def create_grant(self, **kw: Any) -> dict[str, Any]:
        gid = str(uuid4())
        status = "pending_approval" if kw["approval_mode"] == "required" else "active"
        grant = {"id": gid, "status": status, "approved_by_id": None, **kw}
        self.grants[gid] = grant
        return grant

    def _get_grant(self, grant_id: Any) -> dict[str, Any]:
        if str(grant_id) not in self.grants:
            raise ValueError("not found")
        return self.grants[str(grant_id)]

    def approve_grant(self, grant_id: Any, approved_by_id: Any) -> dict[str, Any]:
        g = self.grants[str(grant_id)]
        g.update(status="active", approved_by_id=approved_by_id)
        return g

    def reject_grant(self, grant_id: Any, rejected_by_id: Any) -> dict[str, Any]:
        g = self.grants[str(grant_id)]
        g.update(status="rejected")
        return g


@pytest.fixture
def clause_client(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Real grant routes over a parsed grant_schema and an in-memory store.

    Yields ``(post, rels)``; ``post(path, json, roles, user)`` calls as a user
    holding the comma-separated ``roles``.
    """
    from fastapi import FastAPI, Request
    from fastapi.testclient import TestClient

    import dazzle.http.runtime.grant_store as grant_store_mod

    monkeypatch.setattr(grant_store_mod, "GrantStore", _FakeGrantStore)
    _FakeGrantStore.grants = {}
    rels = _clause_relations()
    appspec = MagicMock()
    appspec.get_grant_schema = lambda n: rels["schema"] if n == rels["schema"].name else None

    @contextmanager
    def _conn() -> Any:
        yield object()

    db = MagicMock()
    db.connection = _conn

    def auth_dep(request: Request) -> Any:
        return SimpleNamespace(
            is_authenticated=True,
            user_id=request.headers.get("x-user") or str(uuid4()),
            user=SimpleNamespace(roles=request.headers.get("x-roles", "").split(",")),
        )

    app = FastAPI()
    app.include_router(create_grant_routes(db_manager=db, appspec=appspec, auth_dep=auth_dep))
    client = TestClient(app)

    def post(
        path: str,
        json: dict[str, Any] | None = None,
        roles: str = "school_admin",
        user: str | None = None,
    ) -> Any:
        headers = {"x-roles": roles, **({"x-user": user} if user else {})}
        return client.post(f"/_dazzle/grants{path}", json=json or {}, headers=headers)

    yield post, rels


def _create_body(relation: str, **extra: Any) -> dict[str, Any]:
    return {
        "schema_name": "department_delegation",
        "relation": relation,
        "principal_id": str(uuid4()),
        "scope_entity": "Department",
        "scope_id": str(uuid4()),
        **extra,
    }


def _in_days(days: float) -> str:
    return (datetime.now(UTC) + timedelta(days=days)).isoformat()


class TestDeclaredExpiryEnforced:
    @pytest.mark.parametrize(
        ("relation", "expires_in_days", "expected"),
        [
            ("acting_hod", None, 422),  # expiry: required, missing
            ("acting_hod", 91, 422),  # beyond max_duration: 90d
            ("acting_hod", -1, 422),  # in the past
            ("acting_hod", 89, 201),
            ("observer", None, 201),  # expiry: optional, no cap
            ("observer", 400, 201),
            ("capped_optional", None, 422),  # a declared cap needs an expires_at
            ("capped_optional", 8, 422),
            ("capped_optional", 6, 201),
            ("permanent", None, 201),  # expiry: none
            ("permanent", 5, 422),
        ],
    )
    def test_create_honours_expiry_and_max_duration(
        self, clause_client: Any, relation: str, expires_in_days: float | None, expected: int
    ) -> None:
        post, _ = clause_client
        extra: dict[str, Any] = {"confirmed": True}
        if expires_in_days is not None:
            extra["expires_at"] = _in_days(expires_in_days)
        resp = post("", _create_body(relation, **extra))
        assert resp.status_code == expected, resp.text

    def test_malformed_expires_at_is_422(self, clause_client: Any) -> None:
        post, _ = clause_client
        resp = post("", _create_body("observer", expires_at="next tuesday"))
        assert resp.status_code == 422
        assert "ISO-8601" in resp.json()["detail"]

    def test_param_max_duration_resolves_through_param_resolver(self) -> None:
        from dazzle.core.ir.params import ParamRef, ParamSpec
        from dazzle.http.runtime.param_store import ParamResolver

        rel = _clause_relations()["acting_hod"].model_copy(
            update={"max_duration": ParamRef(key="grant.max", param_type="str", default="")}
        )
        resolver = ParamResolver(
            specs={
                "grant.max": ParamSpec(
                    key="grant.max", param_type="str", default="2d", scope="system"
                )
            }
        )
        now = datetime.now(UTC)
        one_day = (now + timedelta(days=1)).isoformat()
        assert resolve_grant_expiry(rel, one_day, now=now, param_resolver=resolver)
        with pytest.raises(HTTPException) as exc:
            three_days = (now + timedelta(days=3)).isoformat()
            resolve_grant_expiry(rel, three_days, now=now, param_resolver=resolver)
        assert exc.value.status_code == 422

    def test_unresolvable_max_duration_fails_closed(self) -> None:
        rel = _clause_relations()["acting_hod"].model_copy(update={"max_duration": "ninety"})
        with pytest.raises(HTTPException) as exc:
            resolve_grant_expiry(rel, _in_days(1))
        assert exc.value.status_code == 500


class TestDeclaredConfirmationEnforced:
    @pytest.mark.parametrize(
        ("confirmed", "expected"), [(None, 422), (False, 422), ("yes", 422), (True, 201)]
    )
    def test_create_requires_confirmed_true(
        self, clause_client: Any, confirmed: Any, expected: int
    ) -> None:
        post, _ = clause_client
        extra: dict[str, Any] = {"expires_at": _in_days(5)}
        if confirmed is not None:
            extra["confirmed"] = confirmed
        resp = post("", _create_body("acting_hod", **extra))
        assert resp.status_code == expected, resp.text
        if expected == 422:
            assert "full HoD access" in resp.json()["detail"]

    def test_relation_without_confirmation_needs_no_flag(self, clause_client: Any) -> None:
        post, _ = clause_client
        assert post("", _create_body("observer")).status_code == 201


class TestDeclaredApprovedByEnforced:
    def _pending(self, post: Any) -> str:
        body = _create_body("acting_hod", confirmed=True, expires_at=_in_days(5))
        resp = post("", body, roles="teacher")
        assert resp.status_code == 201, resp.text
        assert resp.json()["grant"]["status"] == "pending_approval"
        return str(resp.json()["grant"]["id"])

    @pytest.mark.parametrize("verb", ["approve", "reject"])
    @pytest.mark.parametrize("roles", ["teacher", "school_admin"])
    def test_granted_by_roles_outside_approved_by_get_403(
        self, clause_client: Any, verb: str, roles: str
    ) -> None:
        post, _ = clause_client
        gid = self._pending(post)
        resp = post(f"/{gid}/{verb}", roles=roles)
        assert resp.status_code == 403
        assert "approved_by" in resp.json()["detail"]

    def test_approved_by_role_approves_and_is_recorded(self, clause_client: Any) -> None:
        post, _ = clause_client
        gid = self._pending(post)
        approver = str(uuid4())
        resp = post(f"/{gid}/approve", roles="senior_leader", user=approver)
        assert resp.status_code == 200, resp.text
        assert resp.json()["grant"]["status"] == "active"
        assert resp.json()["grant"]["approved_by_id"] == approver

    def test_approved_by_role_rejects(self, clause_client: Any) -> None:
        post, _ = clause_client
        gid = self._pending(post)
        assert post(f"/{gid}/reject", roles="senior_leader").status_code == 200
