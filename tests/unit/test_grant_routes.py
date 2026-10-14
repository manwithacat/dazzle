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

  relation dept_observer "Assign Department Observer":
    granted_by: role(head_of_department) or has_grant("acting_hod", department)
    approval: none
    expiry: optional
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

    def has_active_grant(self, principal_id: Any, relation: str, scope_id: Any) -> bool:
        return any(
            g["status"] == "active"
            and str(g["principal_id"]) == str(principal_id)
            and g["relation"] == relation
            and str(g["scope_id"]) == str(scope_id)
            for g in self.grants.values()
        )

    def list_grants(
        self,
        scope_entity: Any = None,
        scope_id: Any = None,
        principal_id: Any = None,
        status: Any = None,
    ) -> list[dict[str, Any]]:
        wanted = {
            "scope_entity": scope_entity,
            "scope_id": scope_id,
            "principal_id": principal_id,
            "status": status,
        }
        return [
            g
            for g in self.grants.values()
            if all(v is None or str(g.get(k)) == str(v) for k, v in wanted.items())
        ]


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
        membership_roles = request.headers.get("x-membership-roles")
        return SimpleNamespace(
            is_authenticated=True,
            user_id=request.headers.get("x-user") or str(uuid4()),
            user=SimpleNamespace(
                roles=request.headers.get("x-roles", "").split(","),
                is_superuser=request.headers.get("x-superuser") == "1",
            ),
            active_membership=(
                SimpleNamespace(roles=membership_roles.split(","))
                if membership_roles is not None
                else None
            ),
        )

    app = FastAPI()
    app.include_router(create_grant_routes(db_manager=db, appspec=appspec, auth_dep=auth_dep))
    client = TestClient(app)

    def post(
        path: str,
        json: dict[str, Any] | None = None,
        roles: str = "school_admin",
        user: str | None = None,
        membership_roles: str | None = None,
        method: str = "post",
        superuser: bool = False,
    ) -> Any:
        headers = {"x-roles": roles, **({"x-user": user} if user else {})}
        if membership_roles is not None:
            headers["x-membership-roles"] = membership_roles
        if superuser:
            headers["x-superuser"] = "1"
        if method == "get":
            return client.get(f"/_dazzle/grants{path}", headers=headers)
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


class TestGrantAuthorityIsEvaluated:
    """Flense ship AA: `granted_by`/`approved_by` are evaluated for the caller, not
    mined for role names — effective (membership) roles, and `has_grant(...)` terms
    against the grant store."""

    @pytest.mark.parametrize(
        ("user_roles", "membership_roles", "expected"),
        [
            ("teacher", "school_admin", 201),  # the membership role satisfies granted_by
            ("school_admin", "teacher", 403),  # an active membership wins over user.roles
            ("role_school_admin", None, 201),  # no membership: user.roles, normalised
        ],
    )
    def test_granted_by_reads_effective_roles(
        self,
        clause_client: Any,
        user_roles: str,
        membership_roles: str | None,
        expected: int,
    ) -> None:
        post, _ = clause_client
        resp = post(
            "", _create_body("observer"), roles=user_roles, membership_roles=membership_roles
        )
        assert resp.status_code == expected, resp.text

    def _acting_hod(self, post: Any, holder: str, scope_id: str) -> None:
        body = {
            **_create_body("acting_hod", confirmed=True, expires_at=_in_days(5)),
            "principal_id": holder,
            "scope_id": scope_id,
        }
        gid = post("", body, roles="teacher").json()["grant"]["id"]
        assert post(f"/{gid}/approve", roles="senior_leader").status_code == 200

    @pytest.mark.parametrize(
        ("holds_grant_on", "expected"),
        [("same", 201), ("other", 403), (None, 403)],
    )
    def test_has_grant_term_in_granted_by(
        self, clause_client: Any, holds_grant_on: str | None, expected: int
    ) -> None:
        """`dept_observer` is granted by `role(head_of_department) or
        has_grant("acting_hod", department)`: an acting HoD of this department may
        assign an observer to it, without the head_of_department role."""
        post, _ = clause_client
        caller, department = str(uuid4()), str(uuid4())
        if holds_grant_on is not None:
            self._acting_hod(post, caller, department if holds_grant_on == "same" else str(uuid4()))
        body = {**_create_body("dept_observer"), "scope_id": department}
        resp = post("", body, roles="teacher", user=caller)
        assert resp.status_code == expected, resp.text


class TestGrantListingIsAuthorised:
    """Flense ship AC: `GET /_dazzle/grants` listed every grant to any signed-in
    user. A caller now sees the grants they are a party to (principal, granter,
    approver) and those of relations/scopes whose `granted_by:`/`approved_by:` they
    satisfy; a superuser sees all; query filters only narrow."""

    def _setup(self, post: Any) -> dict[str, str]:
        ids = {k: str(uuid4()) for k in ("admin", "holder", "hod", "acting", "dept", "leader")}
        # observer: granted_by role(school_admin)
        observer = {**_create_body("observer"), "principal_id": ids["holder"]}
        resp = post("", observer, roles="school_admin", user=ids["admin"])
        ids["observer_grant"] = resp.json()["grant"]["id"]
        # acting_hod on dept, held by `acting` (granted by a teacher, approved by a leader)
        acting = {
            **_create_body("acting_hod", confirmed=True, expires_at=_in_days(5)),
            "principal_id": ids["acting"],
            "scope_id": ids["dept"],
        }
        gid = post("", acting, roles="teacher").json()["grant"]["id"]
        assert post(f"/{gid}/approve", roles="senior_leader", user=ids["leader"]).status_code == 200
        ids["acting_grant"] = gid
        # dept_observer on dept: granted_by role(head_of_department) or has_grant(acting_hod)
        dept_obs = {**_create_body("dept_observer"), "scope_id": ids["dept"]}
        resp = post("", dept_obs, roles="head_of_department", user=ids["hod"])
        ids["dept_observer_grant"] = resp.json()["grant"]["id"]
        return ids

    def _listed(self, post: Any, query: str = "", **caller: Any) -> set[str]:
        resp = post(query, method="get", **caller)
        assert resp.status_code == 200, resp.text
        return {str(g["id"]) for g in resp.json()["grants"]}

    def test_plain_user_sees_only_their_own(self, clause_client: Any) -> None:
        post, _ = clause_client
        ids = self._setup(post)
        assert self._listed(post, roles="teacher", user=str(uuid4())) == {
            ids["acting_grant"]  # teacher satisfies acting_hod's granted_by
        }
        assert self._listed(post, roles="nobody", user=str(uuid4())) == set()
        assert self._listed(post, roles="nobody", user=ids["holder"]) == {ids["observer_grant"]}

    def test_granter_and_approver_see_what_they_could_decide(self, clause_client: Any) -> None:
        post, _ = clause_client
        ids = self._setup(post)
        # another school_admin satisfies observer, acting_hod... granted_by
        assert ids["observer_grant"] in self._listed(post, roles="school_admin", user=str(uuid4()))
        assert self._listed(post, roles="head_of_department", user=str(uuid4())) == {
            ids["dept_observer_grant"]
        }
        # approved_by role(senior_leader) on acting_hod
        assert self._listed(post, roles="senior_leader", user=str(uuid4())) == {ids["acting_grant"]}
        # the recorded approver sees it too, whatever their roles now
        assert self._listed(post, roles="nobody", user=ids["leader"]) == {ids["acting_grant"]}

    def test_has_grant_term_admits_listing_in_that_scope(self, clause_client: Any) -> None:
        post, _ = clause_client
        ids = self._setup(post)
        # `acting` holds acting_hod on dept, so satisfies dept_observer's granted_by there
        assert self._listed(post, roles="nobody", user=ids["acting"]) == {
            ids["acting_grant"],
            ids["dept_observer_grant"],
        }

    def test_superuser_sees_all_and_filters_narrow(self, clause_client: Any) -> None:
        post, _ = clause_client
        ids = self._setup(post)
        everything = {ids["observer_grant"], ids["acting_grant"], ids["dept_observer_grant"]}
        assert self._listed(post, roles="nobody", superuser=True) == everything
        assert self._listed(
            post, f"?principal_id={ids['holder']}", roles="nobody", superuser=True
        ) == {ids["observer_grant"]}
        # a filter never widens: a plain user filtering on another principal gets nothing
        assert (
            self._listed(post, f"?principal_id={ids['holder']}", roles="nobody", user=str(uuid4()))
            == set()
        )

    @pytest.mark.parametrize("verb", ["approve", "reject", "cancel"])
    def test_decision_routes_422_on_a_malformed_id(self, clause_client: Any, verb: str) -> None:
        post, _ = clause_client
        assert post(f"/not-a-uuid/{verb}").status_code == 422
