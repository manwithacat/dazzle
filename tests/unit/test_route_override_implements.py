"""Tests for `# dazzle:implements` annotation parsing + handler wrapping (#1126).

Two surfaces under test:

1. `discover_route_overrides` populates `implements_entity` /
   `implements_op` / `implements_via` on the descriptor when the
   annotation is present.
2. `_wrap_with_policy_gate` invokes `check_entity_op` against the
   path-param row id BEFORE the underlying handler runs; on denial
   the handler body is never reached.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, Request

from dazzle.http.runtime.policy import (
    EntityPolicyInfo,
    PolicyRegistry,
)
from dazzle.http.runtime.route_overrides import (
    _wrap_with_policy_gate,
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
# Wrapper — _wrap_with_policy_gate
# ---------------------------------------------------------------------------


def _request_with_registry(
    registry: PolicyRegistry,
    auth_user_id: str = "u-1",
    auth_roles: list[str] | None = None,
    path_kwargs: dict | None = None,
) -> Request:
    """Build the minimal Request shape `check_entity_op` reads off."""
    user = SimpleNamespace(id=auth_user_id, roles=auth_roles or ["role_admin"])
    auth_ctx = SimpleNamespace(is_authenticated=True, user=user)
    app_state = SimpleNamespace(policy_registry=registry)
    return SimpleNamespace(
        app=SimpleNamespace(state=app_state),
        state=SimpleNamespace(auth_context=auth_ctx),
    )  # type: ignore[return-value]


def _registry_with_spec(spec: object, service: object | None = None) -> PolicyRegistry:
    return PolicyRegistry(
        entities={
            "Task": EntityPolicyInfo(
                entity_name="Task",
                cedar_access_spec=spec,  # type: ignore[arg-type]
                fk_graph=MagicMock(),
                service=service,  # type: ignore[arg-type]
            )
        }
    )


def _permit_spec() -> object:
    from dazzle.core.ir.domain import (
        AccessSpec,
        PermissionKind,
        PermissionRule,
        PolicyEffect,
    )

    return AccessSpec(
        permissions=[
            PermissionRule(
                operation=PermissionKind.UPDATE,
                effect=PolicyEffect.PERMIT,
                personas=["admin"],
            )
        ]
    )


@pytest.mark.asyncio
async def test_wrapper_invokes_underlying_handler_on_pass() -> None:
    """Happy path — permit + scope pass → underlying handler runs and
    its result is returned."""
    service = MagicMock()
    service.execute = AsyncMock(return_value={"id": "row-1"})
    registry = _registry_with_spec(_permit_spec(), service=service)

    inner = AsyncMock(return_value={"ok": True})
    wrapped = _wrap_with_policy_gate(inner, entity="Task", op="update", via="task_id")

    req = _request_with_registry(registry)
    result = await wrapped(request=req, task_id="row-1")

    assert result == {"ok": True}
    inner.assert_awaited_once()


@pytest.mark.asyncio
async def test_wrapper_short_circuits_when_check_denies() -> None:
    """Permit denies (no admin role) → wrapper raises 403 BEFORE the
    underlying handler runs."""
    registry = _registry_with_spec(_permit_spec())

    inner = AsyncMock(return_value={"ok": True})
    wrapped = _wrap_with_policy_gate(inner, entity="Task", op="update", via="task_id")

    req = _request_with_registry(registry, auth_roles=["role_member"])
    with pytest.raises(HTTPException) as exc:
        await wrapped(request=req, task_id="row-1")
    assert exc.value.status_code == 403
    inner.assert_not_awaited()


@pytest.mark.asyncio
async def test_wrapper_raises_500_when_request_arg_missing() -> None:
    """Wrapper can't reach app.state.policy_registry without a Request —
    defensive 500 with diagnostic detail rather than silent skip."""
    inner = AsyncMock(return_value={"ok": True})
    wrapped = _wrap_with_policy_gate(inner, entity="Task", op="update", via="task_id")

    with pytest.raises(HTTPException) as exc:
        await wrapped(task_id="row-1")
    assert exc.value.status_code == 500
    assert "policy_gate_missing_request" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_wrapper_raises_500_when_via_param_missing() -> None:
    """The path-param named by `via` must appear in kwargs; if it
    doesn't, the wrapper surfaces a 500 with diagnostic detail."""
    registry = _registry_with_spec(_permit_spec())
    inner = AsyncMock(return_value={"ok": True})
    wrapped = _wrap_with_policy_gate(inner, entity="Task", op="update", via="task_id")

    req = _request_with_registry(registry)
    with pytest.raises(HTTPException) as exc:
        await wrapped(request=req)  # no task_id kwarg
    assert exc.value.status_code == 500
    assert "policy_gate_missing_path_param" in str(exc.value.detail)


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
