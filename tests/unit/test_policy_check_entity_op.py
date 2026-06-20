"""Tests for `dazzle.http.runtime.policy.check_entity_op` (#1126).

The public policy gate for route overrides + arbitrary project code.
Mirrors the framework's CRUD-route enforcement so overrides can opt
back into permit/scope without re-encoding the DSL declaration.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from dazzle.http.runtime.policy import (
    EntityPolicyInfo,
    PolicyRegistry,
    check_entity_op,
)


def _make_request(
    *,
    policy_registry: PolicyRegistry | None,
    auth_context: object | None = None,
) -> SimpleNamespace:
    """Build a stand-in Request — `check_entity_op` only reads
    `request.app.state.policy_registry` and `request.state.auth_context`."""
    app_state = SimpleNamespace(policy_registry=policy_registry)
    return SimpleNamespace(
        app=SimpleNamespace(state=app_state),
        state=SimpleNamespace(auth_context=auth_context),
    )


def _auth(user_id: str = "u-1", roles: list[str] | None = None, **attrs: object) -> object:
    user = SimpleNamespace(id=user_id, roles=roles or ["role_admin"], **attrs)
    return SimpleNamespace(is_authenticated=True, user=user)


# ---------------------------------------------------------------------------
# Wiring guards — clear errors when the framework hasn't built the registry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_raises_runtime_error_when_no_policy_registry() -> None:
    """A bare FastAPI app built outside `create_app` doesn't have
    a policy registry. Fail closed with a framework-bug message
    rather than silently bypassing the check."""
    req = _make_request(policy_registry=None)
    with pytest.raises(RuntimeError, match="no policy_registry"):
        await check_entity_op(req, "Task", "update", row_id="row-1")


@pytest.mark.asyncio
async def test_raises_401_when_unauthenticated() -> None:
    registry = PolicyRegistry(entities={})
    req = _make_request(policy_registry=registry, auth_context=None)
    with pytest.raises(HTTPException) as exc:
        await check_entity_op(req, "Task", "update", row_id="row-1")
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_returns_none_when_entity_has_no_access_spec() -> None:
    """Unprotected entities (no permit:/scope: rules) pass through —
    matches the framework's "permissive by default" stance and lets
    intentionally-tutorial entities (`unprotected_entity` warning
    territory) work without raising."""
    registry = PolicyRegistry(
        entities={
            "Task": EntityPolicyInfo(
                entity_name="Task",
                cedar_access_spec=None,
                fk_graph=None,
            )
        }
    )
    req = _make_request(policy_registry=registry, auth_context=_auth())
    result = await check_entity_op(req, "Task", "update", row_id="row-1")
    assert result is None


# ---------------------------------------------------------------------------
# Permit gate
# ---------------------------------------------------------------------------


def _spec_permits(op: str, personas: list[str]) -> object:
    """Build a minimal access spec stand-in: one permit rule for the
    given (op, personas) pair, no scope rules. `policy._permit_passes`
    calls `evaluate_permission`, which reads `.permissions`."""
    from dazzle.core.ir.domain import (
        AccessSpec,
        PermissionKind,
        PermissionRule,
        PolicyEffect,
    )

    op_kind = getattr(PermissionKind, op.upper())
    rule = PermissionRule(
        operation=op_kind,
        effect=PolicyEffect.PERMIT,
        personas=list(personas),
    )
    return AccessSpec(permissions=[rule])


@pytest.mark.asyncio
async def test_raises_403_on_permit_denied() -> None:
    """Permit rule allows admin only; member-role user gets 403."""
    spec = _spec_permits("update", ["admin"])
    registry = PolicyRegistry(
        entities={
            "Task": EntityPolicyInfo(entity_name="Task", cedar_access_spec=spec, fk_graph=None)
        }
    )
    req = _make_request(policy_registry=registry, auth_context=_auth(roles=["role_member"]))
    with pytest.raises(HTTPException) as exc:
        await check_entity_op(req, "Task", "update", row_id="row-1")
    assert exc.value.status_code == 403


# ---------------------------------------------------------------------------
# Scope gate — read/update/delete (scoped pre-read)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_returns_row_on_pass(monkeypatch) -> None:
    """Happy path: permit passes, scope passes (no scope rules → all
    rows visible), the row dict comes back to the caller."""
    spec = _spec_permits("update", ["admin"])
    service = MagicMock()
    service.execute = AsyncMock(return_value={"id": "row-1", "title": "T"})

    registry = PolicyRegistry(
        entities={
            "Task": EntityPolicyInfo(
                entity_name="Task",
                cedar_access_spec=spec,
                fk_graph=MagicMock(),
                service=service,
            )
        }
    )
    req = _make_request(policy_registry=registry, auth_context=_auth(roles=["role_admin"]))
    row = await check_entity_op(req, "Task", "update", row_id="row-1")
    assert row == {"id": "row-1", "title": "T"}


@pytest.mark.asyncio
async def test_raises_404_when_scope_rejects_row(monkeypatch) -> None:
    """Permit passes but scoped pre-read returns None (row doesn't
    exist OR scope predicate rejects it) → 404 default-deny."""
    spec = _spec_permits("delete", ["admin"])
    service = MagicMock()
    service.execute = AsyncMock(return_value=None)  # not found / scope-rejected

    registry = PolicyRegistry(
        entities={
            "Task": EntityPolicyInfo(
                entity_name="Task",
                cedar_access_spec=spec,
                fk_graph=MagicMock(),
                service=service,
            )
        }
    )
    req = _make_request(policy_registry=registry, auth_context=_auth(roles=["role_admin"]))
    with pytest.raises(HTTPException) as exc:
        await check_entity_op(req, "Task", "delete", row_id="missing")
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_raises_value_error_when_row_id_missing_on_update() -> None:
    spec = _spec_permits("update", ["admin"])
    registry = PolicyRegistry(
        entities={
            "Task": EntityPolicyInfo(
                entity_name="Task",
                cedar_access_spec=spec,
                fk_graph=MagicMock(),
                service=MagicMock(),
            )
        }
    )
    req = _make_request(policy_registry=registry, auth_context=_auth(roles=["role_admin"]))
    with pytest.raises(ValueError, match="row_id required"):
        await check_entity_op(req, "Task", "update")


# ---------------------------------------------------------------------------
# Create op — payload-time predicate check
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_with_no_scope_rules_passes() -> None:
    """Permit passes, no scope: create: rules declared → allow."""
    spec = _spec_permits("create", ["admin"])
    registry = PolicyRegistry(
        entities={
            "Task": EntityPolicyInfo(entity_name="Task", cedar_access_spec=spec, fk_graph=None)
        }
    )
    req = _make_request(policy_registry=registry, auth_context=_auth(roles=["role_admin"]))
    result = await check_entity_op(req, "Task", "create", payload={"title": "X"})
    assert result is None


@pytest.mark.asyncio
async def test_create_requires_payload_kwarg() -> None:
    spec = _spec_permits("create", ["admin"])
    registry = PolicyRegistry(
        entities={
            "Task": EntityPolicyInfo(entity_name="Task", cedar_access_spec=spec, fk_graph=None)
        }
    )
    req = _make_request(policy_registry=registry, auth_context=_auth(roles=["role_admin"]))
    with pytest.raises(ValueError, match="payload required"):
        await check_entity_op(req, "Task", "create")


# ---------------------------------------------------------------------------
# Op validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_raises_value_error_on_unknown_op() -> None:
    registry = PolicyRegistry(entities={})
    req = _make_request(policy_registry=registry, auth_context=_auth())
    with pytest.raises(ValueError, match="unknown op"):
        await check_entity_op(req, "Task", "nuke", row_id="x")
