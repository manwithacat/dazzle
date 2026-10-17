"""Tests for `# dazzle:implements` annotation parsing + handler wrapping (#1126).

Two surfaces under test:

1. `discover_route_overrides` populates `implements_entity` /
   `implements_op` / `implements_via` on the descriptor when the
   annotation is present.
2. A route mounted by `build_override_router` runs the permit + scope
   gate against the path-param row id BEFORE the override handler; on
   denial the handler body is never reached.
"""

import textwrap
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dazzle.http.runtime.policy import (
    EntityPolicyInfo,
    PolicyRegistry,
)
from dazzle.http.runtime.route_overrides import (
    build_override_router,
    discover_route_overrides,
)

# ---------------------------------------------------------------------------
# Annotation parsing
# ---------------------------------------------------------------------------


def _write_override(tmp_path: Path, body: str) -> Path:
    routes_dir = tmp_path / "routes"
    routes_dir.mkdir()
    py = routes_dir / "task_delete.py"
    py.write_text(textwrap.dedent(body))
    return routes_dir


def test_discover_populates_implements_fields(tmp_path: Path) -> None:
    routes_dir = _write_override(
        tmp_path,
        """
        # dazzle:route-override POST /api/task/{task_id}/delete
        # dazzle:implements Task.delete via task_id

        async def handler(request, task_id: str):
            return {"ok": True}
        """,
    )
    overrides = discover_route_overrides(routes_dir)
    assert len(overrides) == 1
    o = overrides[0]
    assert o.implements_entity == "Task"
    assert o.implements_op == "delete"
    assert o.implements_via == "task_id"


def test_discover_leaves_implements_none_when_annotation_absent(tmp_path: Path) -> None:
    """Legacy overrides without the annotation must keep working —
    the new fields default to None and the wrapping path is skipped."""
    routes_dir = _write_override(
        tmp_path,
        """
        # dazzle:route-override GET /custom/endpoint

        async def handler(request):
            return {"ok": True}
        """,
    )
    overrides = discover_route_overrides(routes_dir)
    assert len(overrides) == 1
    o = overrides[0]
    assert o.implements_entity is None
    assert o.implements_op is None
    assert o.implements_via is None


def test_discover_ignores_invalid_op(tmp_path: Path) -> None:
    """An unknown op (e.g. `Task.nuke`) is ignored — the descriptor's
    implements_* fields stay None, the legacy unguarded path is used."""
    routes_dir = _write_override(
        tmp_path,
        """
        # dazzle:route-override POST /api/task/{task_id}/nuke
        # dazzle:implements Task.nuke via task_id

        async def handler(request, task_id: str):
            return {"ok": True}
        """,
    )
    overrides = discover_route_overrides(routes_dir)
    assert overrides[0].implements_entity is None


# ---------------------------------------------------------------------------
# Policy gate — through build_override_router on a live app
# ---------------------------------------------------------------------------


class _TaskService:
    async def execute(self, **kwargs: Any) -> Any:
        return {"id": kwargs.get("id"), "title": "t"}


class _SessionStore:
    """``AuthStore.validate_session`` for one session id: ``s-1`` → ``roles``, in tenant ``t-1``."""

    def __init__(self, roles: list[str]) -> None:
        self._roles = roles

    def validate_session(self, session_id: str) -> Any:
        from dazzle.http.runtime.auth.models import AuthContext, MembershipRecord, UserRecord

        if session_id != "s-1":
            return AuthContext()
        return AuthContext(
            user=UserRecord(email="u@test.local", password_hash="x", roles=self._roles),
            is_authenticated=True,
            roles=self._roles,
            active_membership=MembershipRecord(
                id="m-1", tenant_id="t-1", identity_id="u-1", roles=self._roles
            ),
        )


def _override_client(tmp_path: Path, route: str, signature: str, roles: list[str]) -> TestClient:
    """Mount a discovered ``# dazzle:implements Task.update via task_id`` override.

    The handler records the RLS tenant bound when it runs on ``app.state.calls``.
    Sign-in is a session cookie resolved against ``app.state.auth_store`` — the gate
    must resolve it itself, as the CRUD routes' auth dependency does (#1801): a
    test that handed the gate a ready-made ``request.state.auth_context`` passed
    while every real signed-in request got 401.
    """
    from dazzle.core.ir.domain import AccessSpec, PermissionKind, PermissionRule, PolicyEffect
    from dazzle.core.ir.fk_graph import FKGraph

    record = (
        "request.app.state.calls.append(get_current_tenant_id())"
        if "request" in signature
        else "pass"
    )
    routes_dir = _write_override(
        tmp_path,
        f"""
        # dazzle:route-override POST {route}
        # dazzle:implements Task.update via task_id
        from fastapi import Request

        from dazzle.http.runtime.tenant_isolation import get_current_tenant_id

        async def handler({signature}):
            {record}
            return {{"ok": True}}
        """,
    )
    app = FastAPI()
    app.state.calls = []
    app.state.policy_registry = PolicyRegistry(
        entities={
            "Task": EntityPolicyInfo(
                entity_name="Task",
                cedar_access_spec=AccessSpec(
                    permissions=[
                        PermissionRule(
                            operation=PermissionKind.UPDATE,
                            effect=PolicyEffect.PERMIT,
                            personas=["admin"],
                        )
                    ]
                ),
                fk_graph=FKGraph(),
                service=_TaskService(),  # type: ignore[arg-type]
            )
        }
    )

    app.state.auth_store = _SessionStore(roles)

    router = build_override_router(routes_dir)
    assert router is not None
    app.include_router(router)
    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize(
    ("route", "signature", "roles", "session", "status", "detail_error", "handler_ran"),
    [
        pytest.param(
            "/api/task/{task_id}/touch",
            "request: Request, task_id: str",
            ["role_admin"],
            "s-1",
            200,
            None,
            True,
            id="signed-in-permit-passes-handler-runs-in-tenant",
        ),
        pytest.param(
            "/api/task/{task_id}/touch",
            "request: Request, task_id: str",
            ["role_member"],
            "s-1",
            403,
            None,
            False,
            id="permit-denies-before-handler-runs",
        ),
        pytest.param(
            "/api/task/{task_id}/touch",
            "request: Request, task_id: str",
            ["role_admin"],
            None,
            401,
            None,
            False,
            id="anonymous-is-401",
        ),
        pytest.param(
            "/api/task/{task_id}/touch",
            "request: Request, task_id: str",
            ["role_admin"],
            "expired",
            401,
            None,
            False,
            id="unknown-session-is-401",
        ),
        pytest.param(
            "/api/task/{task_id}/touch",
            "task_id: str",
            ["role_admin"],
            "s-1",
            500,
            "policy_gate_missing_request",
            False,
            id="handler-without-request-is-500",
        ),
        pytest.param(
            "/api/task/touch",
            "request: Request",
            ["role_admin"],
            "s-1",
            500,
            "policy_gate_missing_path_param",
            False,
            id="route-without-via-param-is-500",
        ),
    ],
)
def test_implements_override_runs_the_policy_gate_first(
    tmp_path: Path,
    route: str,
    signature: str,
    roles: list[str],
    session: str | None,
    status: int,
    detail_error: str | None,
    handler_ran: bool,
) -> None:
    client = _override_client(tmp_path, route, signature, roles)
    if session is not None:
        client.cookies.set("dazzle_session", session)

    response = client.post(route.replace("{task_id}", "row-1"))

    assert response.status_code == status
    if detail_error is not None:
        assert response.json()["detail"]["error"] == detail_error
    # The handler ran with the session's tenant bound for RLS, as the CRUD routes bind it.
    assert client.app.state.calls == (["t-1"] if handler_ran else [])


def test_discover_populates_emits_paths(tmp_path: Path) -> None:
    # #1392 item 3 — `# dazzle:emits <path>` headers parse into emits_paths.
    routes_dir = _write_override(
        tmp_path,
        """
        # dazzle:route-override GET /app/board
        # dazzle:emits /app/tasks/{id}
        # dazzle:emits /app/tasks/create

        async def handler(request):
            return {"ok": True}
        """,
    )
    overrides = discover_route_overrides(routes_dir)
    o = next(o for o in overrides if o.path == "/app/board")
    assert o.emits_paths == ("/app/tasks/{id}", "/app/tasks/create")


def test_no_emits_header_is_empty(tmp_path: Path) -> None:
    routes_dir = _write_override(
        tmp_path,
        """
        # dazzle:route-override GET /app/plain

        async def handler(request):
            return {"ok": True}
        """,
    )
    overrides = discover_route_overrides(routes_dir)
    assert overrides[0].emits_paths == ()
