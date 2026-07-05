"""Tests for bulk-action endpoints (#785)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.ir import BulkActionSpec


class _Repo:
    """Minimal async repo: stores dict rows by id."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = {str(r["id"]): r for r in rows}

    async def update(self, id: str, data: dict[str, Any]) -> dict[str, Any] | None:
        row = self._rows.get(str(id))
        if row is None:
            return None
        row.update(data)
        return row


class _Service:
    """Minimal async service: serves scope-aware reads from dict rows."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = {str(r["id"]): r for r in rows}

    async def execute(
        self,
        *,
        operation: str,
        id: Any = None,
        filters: dict[str, Any] | None = None,
        **_kw: Any,
    ) -> Any:
        if operation == "read":
            return self._rows.get(str(id))
        if operation == "list":
            rid = str((filters or {}).get("id"))
            row = self._rows.get(rid)
            return {"items": [row] if row else []}
        return None


def _auth_ctx(*, authenticated: bool, roles: list[str] | None = None) -> Any:
    """Build a stand-in AuthContext (route helpers read it via getattr)."""
    user = (
        SimpleNamespace(id="u1", roles=roles or [], is_superuser=False, email="u@example.test")
        if authenticated
        else None
    )
    return SimpleNamespace(is_authenticated=authenticated, user=user)


def _auth_dep_returning(ctx: Any) -> Any:
    """A FastAPI dependency that always resolves to ``ctx``."""

    async def _dep() -> Any:
        return ctx

    return _dep


def _mount(router: Any) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _surface_with_bulk(
    *,
    entity: str = "InsertionPoint",
    actions: list[BulkActionSpec] | None = None,
    mode: str = "list",
) -> Any:
    return SimpleNamespace(
        entity_ref=entity,
        mode=mode,
        ux=SimpleNamespace(
            bulk_actions=actions
            or [
                BulkActionSpec(name="accept", field="status", target_value="active"),
                BulkActionSpec(name="reject", field="status", target_value="rejected"),
            ]
        ),
    )


class TestCreateBulkRoutes:
    @pytest.mark.parametrize(
        ("surfaces", "repositories"),
        [
            ([], {}),
            (
                [
                    SimpleNamespace(
                        entity_ref="Task", mode="list", ux=SimpleNamespace(bulk_actions=[])
                    )
                ],
                {"Task": _Repo([])},
            ),
            (
                [_surface_with_bulk(mode="edit")],
                {"InsertionPoint": _Repo([])},
            ),
            (
                [_surface_with_bulk()],
                {},
            ),
        ],
        ids=[
            "test_no_surfaces_returns_none",
            "test_no_bulk_actions_returns_none",
            "test_non_list_surfaces_ignored",
            "test_missing_repository_skips_entity",
        ],
    )
    def test_returns_none(self, surfaces: list, repositories: dict) -> None:
        from dazzle.http.runtime.bulk_routes import create_bulk_routes

        assert (
            create_bulk_routes(
                surfaces,
                repositories=repositories,
                services={},
                cedar_access_specs={},
                fk_graph=None,
                optional_auth_dep=None,
            )
            is None
        )


class TestBulkEndpointHandler:
    def _build(self, rows: list[dict[str, Any]]) -> TestClient:
        from dazzle.http.runtime.bulk_routes import create_bulk_routes

        # optional_auth_dep=None — exercises the no-auth-app path.
        router = create_bulk_routes(
            [_surface_with_bulk()],
            repositories={"InsertionPoint": _Repo(rows)},
            services={},
            cedar_access_specs={},
            fk_graph=None,
            optional_auth_dep=None,
        )
        assert router is not None
        return _mount(router)

    def test_applies_action_to_multiple_ids(self) -> None:
        rows = [
            {"id": "i1", "status": "pending"},
            {"id": "i2", "status": "pending"},
            {"id": "i3", "status": "pending"},
        ]
        client = self._build(rows)
        resp = client.post(
            "/api/insertionpoints/bulk",
            json={"action": "accept", "ids": ["i1", "i2", "i3"]},
        )
        assert resp.status_code == 200
        body = json.loads(resp.content)
        assert body["succeeded"] == 3
        assert body["action"] == "accept"
        assert body["field"] == "status"
        assert body["target_value"] == "active"
        for row in rows:
            assert row["status"] == "active"

    def test_unknown_action_returns_422(self) -> None:
        client = self._build([{"id": "i1", "status": "pending"}])
        resp = client.post(
            "/api/insertionpoints/bulk",
            json={"action": "mystery", "ids": ["i1"]},
        )
        assert resp.status_code == 422
        body = json.loads(resp.content)
        assert "mystery" in body["error"]
        assert "accept" in body["actions"]
        assert "reject" in body["actions"]

    def test_missing_ids_returns_422(self) -> None:
        client = self._build([])
        resp = client.post("/api/insertionpoints/bulk", json={"action": "accept", "ids": []})
        assert resp.status_code == 422
        assert "non-empty list" in json.loads(resp.content)["error"]

    def test_invalid_body_returns_400(self) -> None:
        client = self._build([])
        resp = client.post(
            "/api/insertionpoints/bulk",
            content="not json",
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 400

    def test_per_item_not_found_reported(self) -> None:
        client = self._build([{"id": "i1", "status": "pending"}])
        resp = client.post(
            "/api/insertionpoints/bulk",
            json={"action": "accept", "ids": ["i1", "missing"]},
        )
        body = json.loads(resp.content)
        assert body["total"] == 2
        assert body["succeeded"] == 1
        by_id = {r["id"]: r for r in body["results"]}
        assert by_id["i1"]["ok"] is True
        assert by_id["missing"]["ok"] is False
        assert by_id["missing"]["error"] == "not_found"

    def test_reject_action_uses_target_value(self) -> None:
        rows = [{"id": "i1", "status": "pending"}]
        client = self._build(rows)
        resp = client.post(
            "/api/insertionpoints/bulk",
            json={"action": "reject", "ids": ["i1"]},
        )
        body = json.loads(resp.content)
        assert body["target_value"] == "rejected"
        assert rows[0]["status"] == "rejected"


class TestDSLParserBulkActions:
    """ux: bulk_actions: block parses into BulkActionSpec list."""

    def _parse_first_surface(self, dsl: str) -> Any:
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("t.dsl"))
        return fragment.surfaces[0]

    def test_basic_parse(self) -> None:
        dsl = """
module testapp
app testapp "Test"

entity InsertionPoint "Point":
  id: uuid pk
  status: str(20) required

surface review "Review":
  uses entity InsertionPoint
  mode: list
  section main:
    field status "Status"
  ux:
    bulk_actions:
      accept: status -> active
      reject: status -> rejected
"""
        surface = self._parse_first_surface(dsl)
        actions = surface.ux.bulk_actions
        assert len(actions) == 2
        assert actions[0].name == "accept"
        assert actions[0].field == "status"
        assert actions[0].target_value == "active"
        assert actions[1].name == "reject"
        assert actions[1].target_value == "rejected"

    def test_quoted_target_value(self) -> None:
        dsl = """
module testapp
app testapp "Test"

entity InsertionPoint "Point":
  id: uuid pk
  status: str(20) required

surface review "Review":
  uses entity InsertionPoint
  mode: list
  section main:
    field status "Status"
  ux:
    bulk_actions:
      archive: status -> "archived and locked"
"""
        surface = self._parse_first_surface(dsl)
        assert surface.ux.bulk_actions[0].target_value == "archived and locked"

    def test_bool_target_value(self) -> None:
        dsl = """
module testapp
app testapp "Test"

entity Task "Task":
  id: uuid pk
  completed: bool=false

surface review "Review":
  uses entity Task
  mode: list
  section main:
    field completed "Done"
  ux:
    bulk_actions:
      finish: completed -> true
      reopen: completed -> false
"""
        surface = self._parse_first_surface(dsl)
        actions = surface.ux.bulk_actions
        assert actions[0].target_value == "true"
        assert actions[1].target_value == "false"

    def test_bulk_actions_coexist_with_other_ux_keys(self) -> None:
        dsl = """
module testapp
app testapp "Test"

entity Task "Task":
  id: uuid pk
  status: str(20)

surface review "Review":
  uses entity Task
  mode: list
  section main:
    field status "Status"
  ux:
    filter: status
    bulk_actions:
      accept: status -> active
"""
        surface = self._parse_first_surface(dsl)
        assert surface.ux.filter == ["status"]
        assert len(surface.ux.bulk_actions) == 1
        assert surface.ux.bulk_actions[0].name == "accept"


class TestBulkEndpointRBAC:
    """RBAC permit gate + row-level scope enforcement on the bulk endpoint (#1170).

    Before #1170 the bulk endpoint mounted with no auth dependency and
    called ``repo.update`` directly with a bare ``WHERE id = ?`` — any
    caller could mutate any row of the entity, cross-tenant. These tests
    pin the enforced behaviour.
    """

    def _cedar(self, *, permit_update: bool, scopes: list[Any] | None = None) -> Any:
        from dazzle.core.access import (
            AccessOperationKind,
            AccessPolicyEffect,
            EntityAccessSpec,
            PermissionRuleSpec,
        )

        # personas=[] => "any authenticated user". When permit_update is
        # False the only permit covers CREATE, so UPDATE default-denies.
        permit_op = AccessOperationKind.UPDATE if permit_update else AccessOperationKind.CREATE
        return EntityAccessSpec(
            permissions=[
                PermissionRuleSpec(
                    operation=permit_op,
                    personas=[],
                    effect=AccessPolicyEffect.PERMIT,
                )
            ],
            scopes=scopes or [],
        )

    def _build(
        self,
        *,
        rows: list[dict[str, Any]],
        cedar_spec: Any,
        auth_context: Any,
        fk_graph: Any = None,
    ) -> tuple[TestClient, _Repo]:
        from dazzle.http.runtime.bulk_routes import create_bulk_routes

        repo = _Repo(rows)
        router = create_bulk_routes(
            [_surface_with_bulk()],
            repositories={"InsertionPoint": repo},
            services={"InsertionPoint": _Service(rows)},
            cedar_access_specs={"InsertionPoint": cedar_spec},
            fk_graph=fk_graph,
            optional_auth_dep=_auth_dep_returning(auth_context),
        )
        assert router is not None
        return _mount(router), repo

    def test_unauthenticated_request_is_denied(self) -> None:
        rows = [{"id": "i1", "status": "pending"}]
        client, _repo = self._build(
            rows=rows,
            cedar_spec=self._cedar(permit_update=True),
            auth_context=_auth_ctx(authenticated=False),
        )
        resp = client.post("/api/insertionpoints/bulk", json={"action": "accept", "ids": ["i1"]})
        assert resp.status_code == 403
        assert rows[0]["status"] == "pending"  # not mutated

    def test_role_without_update_permit_is_denied(self) -> None:
        rows = [{"id": "i1", "status": "pending"}]
        client, _repo = self._build(
            rows=rows,
            cedar_spec=self._cedar(permit_update=False),  # only CREATE permitted
            auth_context=_auth_ctx(authenticated=True, roles=["viewer"]),
        )
        resp = client.post("/api/insertionpoints/bulk", json={"action": "accept", "ids": ["i1"]})
        assert resp.status_code == 403
        assert rows[0]["status"] == "pending"

    def test_scope_denied_ids_reported_not_found(self) -> None:
        # The core #1170 regression: an authenticated, update-permitted
        # caller must NOT mutate rows outside their scope. The scope rule
        # grants `admin` only; an `editor` caller matches no rule and is
        # default-denied per id (reported as not_found, IDOR-safe).
        from dazzle.core.access import AccessOperationKind, ScopeRuleSpec

        rows = [
            {"id": "i1", "status": "pending"},
            {"id": "i2", "status": "pending"},
        ]
        client, _repo = self._build(
            rows=rows,
            cedar_spec=self._cedar(
                permit_update=True,
                scopes=[ScopeRuleSpec(operation=AccessOperationKind.UPDATE, personas=["admin"])],
            ),
            auth_context=_auth_ctx(authenticated=True, roles=["editor"]),
            fk_graph=object(),  # non-None: exercises the scope resolver
        )
        resp = client.post(
            "/api/insertionpoints/bulk",
            json={"action": "accept", "ids": ["i1", "i2"]},
        )
        assert resp.status_code == 200
        body = json.loads(resp.content)
        assert body["succeeded"] == 0
        assert all(r["error"] == "not_found" for r in body["results"])
        assert all(row["status"] == "pending" for row in rows)  # untouched

    def test_in_scope_update_succeeds(self) -> None:
        from dazzle.core.access import AccessOperationKind, ScopeRuleSpec

        rows = [{"id": "i1", "status": "pending"}]
        client, _repo = self._build(
            rows=rows,
            cedar_spec=self._cedar(
                permit_update=True,
                scopes=[ScopeRuleSpec(operation=AccessOperationKind.UPDATE, personas=["*"])],
            ),
            auth_context=_auth_ctx(authenticated=True, roles=["editor"]),
            fk_graph=object(),
        )
        resp = client.post("/api/insertionpoints/bulk", json={"action": "accept", "ids": ["i1"]})
        assert resp.status_code == 200
        body = json.loads(resp.content)
        assert body["succeeded"] == 1
        assert rows[0]["status"] == "active"


class _ListService:
    """Fake service with a real-ish LIST op (filters + search + paging) plus
    read/delete — enough for the grid-primitive all-matching path (C0b)."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    async def execute(
        self,
        *,
        operation: str,
        id: Any = None,
        filters: dict[str, Any] | None = None,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
        search_fields: list[str] | None = None,
        **_kw: Any,
    ) -> Any:
        if operation == "read":
            return next((r for r in self.rows if str(r["id"]) == str(id)), None)
        if operation == "list":
            rows = self.rows
            for k, v in (filters or {}).items():
                rows = [r for r in rows if str(r.get(k)) == str(v)]
            if search:
                fields = search_fields or []
                rows = [
                    r
                    for r in rows
                    if any(search.lower() in str(r.get(f, "")).lower() for f in fields)
                ]
            total = len(rows)
            start = (page - 1) * page_size
            return {
                "items": rows[start : start + page_size],
                "total": total,
                "page": page,
                "page_size": page_size,
            }
        if operation == "delete":
            before = len(self.rows)
            self.rows[:] = [r for r in self.rows if str(r["id"]) != str(id)]
            return {"deleted": len(self.rows) < before}
        return None


class TestGridBulkPayload:
    """C0b: the /bulk route accepts the HM grid primitive's FORM payload —
    per-id parity, all-matching re-scope (§15), fail-closed echo rules, and
    the built-in `delete` action (the mounted route the primitive posts to)."""

    _ROWS = [
        {"id": "r1", "status": "new", "plan": "Pro", "name": "Amir"},
        {"id": "r2", "status": "new", "plan": "Pro", "name": "Noah"},
        {"id": "r3", "status": "new", "plan": "Free", "name": "Sofia"},
    ]

    def _build(
        self,
        rows: list[dict[str, Any]],
        *,
        search_fields: list[str] | None = None,
        filter_fields: list[str] | None = None,
        cap: int = 10_000,
    ) -> tuple[TestClient, _ListService]:
        from dazzle.http.runtime.bulk_routes import create_bulk_routes

        svc = _ListService(rows)
        router = create_bulk_routes(
            [_surface_with_bulk()],
            repositories={"InsertionPoint": _Repo(rows)},
            services={"InsertionPoint": svc},
            cedar_access_specs={},
            fk_graph=None,
            optional_auth_dep=None,
            entity_search_fields={"InsertionPoint": search_fields or []},
            entity_filter_fields={"InsertionPoint": filter_fields or []},
            all_matching_cap=cap,
        )
        assert router is not None
        return _mount(router), svc

    def test_form_encoded_per_id_parity(self) -> None:
        rows = [dict(r) for r in self._ROWS]
        client, _svc = self._build(rows)
        resp = client.post(
            "/api/insertionpoints/bulk",
            data={
                "action": "accept",
                "selected_ids": ["r1", "r2"],
                "all_matching_selected": "false",
                "excluded_ids": [],
            },
        )
        assert resp.status_code == 200
        assert json.loads(resp.content)["succeeded"] == 2
        assert rows[0]["status"] == "active" and rows[1]["status"] == "active"
        assert rows[2]["status"] == "new"

    def test_all_matching_applies_query_minus_exclusions_and_strips_paging(self) -> None:
        rows = [dict(r) for r in self._ROWS]
        client, _svc = self._build(rows)
        resp = client.post(
            "/api/insertionpoints/bulk",
            data={
                "action": "accept",
                "selected_ids": ["r1"],  # informational (visible state) only
                "all_matching_selected": "true",
                "excluded_ids": ["r2"],
                "filter[plan]": "Pro",
                # windowing params MUST be stripped — a verbatim re-run would
                # apply the action to one display page only
                "page": "2",
                "page_size": "1",
                "sort": "name",
                "dir": "desc",
            },
        )
        assert resp.status_code == 200
        body = json.loads(resp.content)
        assert body["succeeded"] == 1
        assert rows[0]["status"] == "active", "matched (Pro) and not excluded"
        assert rows[1]["status"] == "new", "excluded id is spared"
        assert rows[2]["status"] == "new", "Free row never matched"

    def test_all_matching_unconsumable_bare_key_rejected(self) -> None:
        rows = [dict(r) for r in self._ROWS]
        client, _svc = self._build(rows)
        resp = client.post(
            "/api/insertionpoints/bulk",
            data={
                "action": "accept",
                "all_matching_selected": "true",
                "bogus": "x",
            },
        )
        assert resp.status_code == 422, "an unconsumable narrowing param must fail closed"
        assert all(r["status"] == "new" for r in rows)

    def test_all_matching_search_without_search_fields_rejected(self) -> None:
        rows = [dict(r) for r in self._ROWS]
        client, _svc = self._build(rows)  # no search_fields
        resp = client.post(
            "/api/insertionpoints/bulk",
            data={"action": "accept", "all_matching_selected": "true", "q": "amir"},
        )
        assert resp.status_code == 422
        assert all(r["status"] == "new" for r in rows)

    def test_all_matching_search_narrows_with_search_fields(self) -> None:
        rows = [dict(r) for r in self._ROWS]
        client, _svc = self._build(rows, search_fields=["name"])
        resp = client.post(
            "/api/insertionpoints/bulk",
            data={"action": "accept", "all_matching_selected": "true", "q": "amir"},
        )
        assert resp.status_code == 200
        assert rows[0]["status"] == "active"
        assert rows[1]["status"] == "new" and rows[2]["status"] == "new"

    def test_all_matching_bare_key_allowed_when_declared(self) -> None:
        rows = [dict(r) for r in self._ROWS]
        client, _svc = self._build(rows, filter_fields=["plan"])
        resp = client.post(
            "/api/insertionpoints/bulk",
            data={"action": "accept", "all_matching_selected": "true", "plan": "Free"},
        )
        assert resp.status_code == 200
        assert rows[2]["status"] == "active"
        assert rows[0]["status"] == "new" and rows[1]["status"] == "new"

    def test_all_matching_cap_rejects_oversize_sets(self) -> None:
        rows = [dict(r) for r in self._ROWS]
        client, _svc = self._build(rows, cap=2)
        resp = client.post(
            "/api/insertionpoints/bulk",
            data={"action": "accept", "all_matching_selected": "true"},
        )
        assert resp.status_code == 422, "3 matched > cap 2 — narrow the query"
        assert all(r["status"] == "new" for r in rows)

    def test_builtin_delete_action_per_id(self) -> None:
        rows = [dict(r) for r in self._ROWS]
        client, svc = self._build(rows)
        resp = client.post(
            "/api/insertionpoints/bulk",
            data={
                "action": "delete",
                "selected_ids": ["r2"],
                "all_matching_selected": "false",
            },
        )
        assert resp.status_code == 200
        assert json.loads(resp.content)["succeeded"] == 1
        assert [r["id"] for r in svc.rows] == ["r1", "r3"], "the selected row is deleted"

    def test_builtin_delete_all_matching(self) -> None:
        rows = [dict(r) for r in self._ROWS]
        client, svc = self._build(rows)
        resp = client.post(
            "/api/insertionpoints/bulk",
            data={
                "action": "delete",
                "all_matching_selected": "true",
                "excluded_ids": ["r1"],
                "filter[plan]": "Pro",
            },
        )
        assert resp.status_code == 200
        assert [r["id"] for r in svc.rows] == ["r1", "r3"], (
            "Pro rows delete EXCEPT the excluded one; Free never matched"
        )

    def test_declared_action_shadows_builtin_delete(self) -> None:
        """A DSL-declared action NAMED `delete` wins over the built-in."""
        rows = [dict(r) for r in self._ROWS]
        from dazzle.http.runtime.bulk_routes import create_bulk_routes

        svc = _ListService(rows)
        router = create_bulk_routes(
            [
                _surface_with_bulk(
                    actions=[BulkActionSpec(name="delete", field="status", target_value="gone")]
                )
            ],
            repositories={"InsertionPoint": _Repo(rows)},
            services={"InsertionPoint": svc},
            cedar_access_specs={},
            fk_graph=None,
            optional_auth_dep=None,
        )
        assert router is not None
        client = _mount(router)
        resp = client.post(
            "/api/insertionpoints/bulk",
            data={"action": "delete", "selected_ids": ["r1"], "all_matching_selected": "false"},
        )
        assert resp.status_code == 200
        assert rows[0]["status"] == "gone", "the declared transition ran"
        assert len(svc.rows) == 3, "nothing was deleted"


class TestGridBulkPayloadFixes:
    """C0b review fixes: search/q precedence parity + AccessForbidden → 403."""

    _ROWS = [
        {"id": "r1", "status": "new", "name": "Amir"},
        {"id": "r2", "status": "new", "name": "Noah"},
    ]

    def test_search_wins_over_q_when_both_echoed(self) -> None:
        """The list route resolves `search or q` (#596) — the all-matching
        resolver must use the SAME precedence, or a crafted POST carrying both
        applies the action to a different set than the view showed."""
        rows = [dict(r) for r in self._ROWS]
        client, _svc = TestGridBulkPayload()._build(rows, search_fields=["name"])
        resp = client.post(
            "/api/insertionpoints/bulk",
            data={
                "action": "accept",
                "all_matching_selected": "true",
                "search": "amir",  # what the list view used (wins on the list route)
                "q": "o",  # broader — matches Noah too; must NOT win here
            },
        )
        assert resp.status_code == 200
        assert rows[0]["status"] == "active", "the `search` term's match applies"
        assert rows[1]["status"] == "new", "the broader `q` term must not widen the action"

    def test_all_matching_list_permit_denied_maps_to_403(self) -> None:
        """A caller with UPDATE permit but NO LIST permit: gated_list's permit
        gate raises AccessForbidden — the route must map it to 403, not 500."""
        from dazzle.core.access import (
            AccessOperationKind,
            AccessPolicyEffect,
            EntityAccessSpec,
            PermissionRuleSpec,
        )
        from dazzle.http.runtime.bulk_routes import create_bulk_routes

        rows = [dict(r) for r in self._ROWS]
        svc = _ListService(rows)
        # UPDATE permitted to any authenticated user; LIST permitted ONLY to
        # `admin` (a pure-role rule) — the caller is `editor`, so gated_list's
        # permit gate raises AccessForbidden.
        cedar = EntityAccessSpec(
            permissions=[
                PermissionRuleSpec(
                    operation=AccessOperationKind.UPDATE,
                    personas=[],
                    effect=AccessPolicyEffect.PERMIT,
                ),
                PermissionRuleSpec(
                    operation=AccessOperationKind.LIST,
                    personas=["admin"],
                    effect=AccessPolicyEffect.PERMIT,
                ),
            ],
            scopes=[],
        )
        router = create_bulk_routes(
            [_surface_with_bulk()],
            repositories={"InsertionPoint": _Repo(rows)},
            services={"InsertionPoint": svc},
            cedar_access_specs={"InsertionPoint": cedar},
            fk_graph=None,
            optional_auth_dep=_auth_dep_returning(_auth_ctx(authenticated=True, roles=["editor"])),
        )
        assert router is not None
        client = _mount(router)
        resp = client.post(
            "/api/insertionpoints/bulk",
            data={"action": "accept", "all_matching_selected": "true"},
        )
        assert resp.status_code == 403, f"AccessForbidden must map to 403: {resp.status_code}"
        assert all(r["status"] == "new" for r in rows)
