"""#1466: workspace region / batch / stats endpoints must bind the per-request RLS GUCs.

These three handlers self-authenticate via ``auth_middleware.get_auth_context``
(the routes register with plain ``app.get`` and gate personas inline — no FastAPI
auth dependency), so ``dependencies._bind_rls_tenant_id`` — which sets the
``dazzle.tenant_id`` / ``dazzle.user_<attr>`` contextvars the leased Postgres
connection reads at lease time — was never called. On a ``shared_schema`` / RLS app
the unbound connection then fenced every row → each region rendered its empty-state
(and stats resolved to 0) under the non-bypass ``dazzle_app`` role.

This is the same regression #1428 fixed on the page in-process path; these tests pin
the equivalent fix on the workspace-region paths. The binding helper itself is proven
in ``test_bind_rls_from_membership.py``; the regression was the *missing call*, so
asserting the call is made with the resolved auth context is the precise guard.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

import dazzle.http.runtime.workspace_handlers as _handlers
import dazzle.http.runtime.workspace_region_prelude as _prelude
from dazzle.http.runtime.workspace_context import WorkspaceRegionContext


def _auth_ctx() -> SimpleNamespace:
    """A minimal authenticated context (persona gate skipped via ws_access=None)."""
    return SimpleNamespace(is_authenticated=True, user=None, roles=[], preferences=None)


def _region_ctx(mw: Any, *, require_auth: bool = True) -> WorkspaceRegionContext:
    return WorkspaceRegionContext(
        ctx_region=SimpleNamespace(
            aggregates={}, name="r", endpoint="/api/workspaces/ws/regions/r"
        ),
        ir_region=None,
        source="Task",
        entity_spec=None,
        attention_signals=[],
        ws_access=None,  # no persona gate
        repositories={},
        require_auth=require_auth,
        auth_middleware=mw,
    )


def _record_bind(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    calls: list[object] = []
    # _bind_rls_tenant_id is imported at module top in both consumer modules (the
    # binding is module-level, not a call-time source import), so patch it in each
    # consumer namespace — patching the source `_deps` would miss the bound name.
    recorder = lambda ctx: calls.append(ctx)  # noqa: E731
    monkeypatch.setattr(_prelude, "_bind_rls_tenant_id", recorder)
    monkeypatch.setattr(_handlers, "_bind_rls_tenant_id", recorder)
    return calls


@pytest.mark.asyncio
async def test_region_prelude_binds_rls_gucs(monkeypatch: pytest.MonkeyPatch) -> None:
    """resolve_request_user_context (region path) binds the GUCs with the resolved ctx."""
    calls = _record_bind(monkeypatch)

    async def _no_user(*_a: Any, **_k: Any) -> tuple[None, None]:
        return None, None

    monkeypatch.setattr(_prelude, "_resolve_workspace_user", _no_user)

    auth = _auth_ctx()
    mw = SimpleNamespace(get_auth_context=lambda _req: auth)
    ctx = _region_ctx(mw, require_auth=False)  # skip the 401 gate; still resolves auth for filters

    await _prelude.resolve_request_user_context(SimpleNamespace(query_params={}), ctx)

    assert calls == [auth], "region prelude did not bind the RLS GUCs (#1466)"


@pytest.mark.asyncio
async def test_batch_handler_binds_rls_gucs(monkeypatch: pytest.MonkeyPatch) -> None:
    """_workspace_batch_handler binds before the concurrent region reads."""
    calls = _record_bind(monkeypatch)

    async def _no_user(*_a: Any, **_k: Any) -> tuple[None, None]:
        return None, None

    async def _empty_region(*_a: Any, **_k: Any) -> dict[str, Any]:
        return {}

    monkeypatch.setattr(_handlers, "_resolve_workspace_user", _no_user)
    monkeypatch.setattr(_handlers, "_fetch_region_json", _empty_region)

    auth = _auth_ctx()
    mw = SimpleNamespace(get_auth_context=lambda _req: auth)
    ctxs = [_region_ctx(mw)]

    await _handlers._workspace_batch_handler(SimpleNamespace(query_params={}), 1, 50, ctxs)

    assert calls == [auth], "batch handler did not bind the RLS GUCs (#1466)"


@pytest.mark.asyncio
async def test_stats_handler_binds_rls_gucs(monkeypatch: pytest.MonkeyPatch) -> None:
    """_workspace_stats_handler binds before the scope-aware aggregate queries."""
    calls = _record_bind(monkeypatch)

    auth = _auth_ctx()
    mw = SimpleNamespace(get_auth_context=lambda _req: auth)
    ctxs = [_region_ctx(mw)]  # aggregates={} → no aggregate compute

    await _handlers._workspace_stats_handler(SimpleNamespace(query_params={}), ctxs)

    assert calls == [auth], "stats handler did not bind the RLS GUCs (#1466)"


@pytest.mark.asyncio
async def test_no_auth_context_does_not_bind(monkeypatch: pytest.MonkeyPatch) -> None:
    """No middleware → nothing to bind (no crash, no call) — fail-closed, not a crash."""
    calls = _record_bind(monkeypatch)
    ctxs = [_region_ctx(None, require_auth=False)]
    await _handlers._workspace_stats_handler(SimpleNamespace(query_params={}), ctxs)
    assert calls == []
