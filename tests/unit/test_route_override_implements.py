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
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI, Request
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


def _override_client(tmp_path: Path, route: str, signature: str, roles: list[str]) -> TestClient:
    """Mount a discovered ``# dazzle:implements Task.update via task_id`` override.

    The handler records every call on ``app.state.calls``; the request carries an
    authenticated user holding ``roles``.
    """
    from dazzle.core.ir.domain import AccessSpec, PermissionKind, PermissionRule, PolicyEffect
    from dazzle.core.ir.fk_graph import FKGraph

    record = 'request.app.state.calls.append("ran")' if "request" in signature else "pass"
    routes_dir = _write_override(
        tmp_path,
        f"""
        # dazzle:route-override POST {route}
        # dazzle:implements Task.update via task_id
        from fastapi import Request

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

    @app.middleware("http")
    async def _authenticate(request: Request, call_next: Any) -> Any:
        user = SimpleNamespace(id="u-1", roles=roles)
        request.state.auth_context = SimpleNamespace(is_authenticated=True, user=user)
        return await call_next(request)

    router = build_override_router(routes_dir)
    assert router is not None
    app.include_router(router)
    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize(
    ("route", "signature", "roles", "status", "detail_error", "handler_ran"),
    [
        pytest.param(
            "/api/task/{task_id}/touch",
            "request: Request, task_id: str",
            ["role_admin"],
            200,
            None,
            True,
            id="permit-passes-handler-runs",
        ),
        pytest.param(
            "/api/task/{task_id}/touch",
            "request: Request, task_id: str",
            ["role_member"],
            403,
            None,
            False,
            id="permit-denies-before-handler-runs",
        ),
        pytest.param(
            "/api/task/{task_id}/touch",
            "task_id: str",
            ["role_admin"],
            500,
            "policy_gate_missing_request",
            False,
            id="handler-without-request-is-500",
        ),
        pytest.param(
            "/api/task/touch",
            "request: Request",
            ["role_admin"],
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
    status: int,
    detail_error: str | None,
    handler_ran: bool,
) -> None:
    client = _override_client(tmp_path, route, signature, roles)

    response = client.post(route.replace("{task_id}", "row-1"))

    assert response.status_code == status
    if detail_error is not None:
        assert response.json()["detail"]["error"] == detail_error
    assert client.app.state.calls == (["ran"] if handler_ran else [])


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
