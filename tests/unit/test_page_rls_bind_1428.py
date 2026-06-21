"""#1428: the page in-process read path must bind the per-request RLS GUCs.

#1422 removed the page→REST loopback self-fetch and made page detail/edit reads
(and list / create / update) run in-process. The REST auth dependency
(``dependencies.get_optional_user``) calls ``_bind_rls_tenant_id`` to set the
``dazzle.tenant_id`` / ``dazzle.user_<attr>`` contextvars the leased Postgres
connection reads at lease time; the page auth seam (``_resolve_auth_context``)
did not. On a ``shared_schema`` / RLS app the unbound connection then denied
every row to the in-process page read → ``RecordNotFound`` → 404, even though
the same row returned 200 over REST.

These tests pin the fix: ``_resolve_auth_context`` invokes ``_bind_rls_tenant_id``
with the resolved auth context (the binding helper itself is proven to set the
GUCs in ``test_bind_rls_from_membership.py``). The regression was the *missing
call* at the page seam, so asserting the call is made is the precise guard.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import dazzle.http.runtime.auth.dependencies as _deps
from dazzle.http.runtime.page_routes import _resolve_auth_context


@pytest.mark.asyncio
async def test_resolve_auth_context_binds_rls_gucs(monkeypatch: pytest.MonkeyPatch) -> None:
    """The page seam must call _bind_rls_tenant_id with the resolved context —
    the bind the REST dependency does and #1422 dropped from the page path."""
    calls: list[object] = []
    monkeypatch.setattr(_deps, "_bind_rls_tenant_id", lambda ctx: calls.append(ctx))

    resolved = SimpleNamespace(is_authenticated=True)

    def _resolver(_req: object) -> SimpleNamespace:
        return resolved

    result = await _resolve_auth_context(_resolver, MagicMock())

    assert result is resolved
    assert calls == [resolved], "page seam did not bind the RLS GUCs (#1428 regression)"


@pytest.mark.asyncio
async def test_resolve_auth_context_async_resolver_also_binds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The bind happens after the coroutine is awaited (async auth stacks)."""
    calls: list[object] = []
    monkeypatch.setattr(_deps, "_bind_rls_tenant_id", lambda ctx: calls.append(ctx))

    resolved = SimpleNamespace(is_authenticated=True)

    async def _resolver(_req: object) -> SimpleNamespace:
        return resolved

    await _resolve_auth_context(_resolver, MagicMock())

    assert calls == [resolved]


@pytest.mark.asyncio
async def test_resolve_auth_context_no_resolver_does_not_bind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No auth configured → nothing to bind (no crash, no call)."""
    calls: list[object] = []
    monkeypatch.setattr(_deps, "_bind_rls_tenant_id", lambda ctx: calls.append(ctx))

    assert await _resolve_auth_context(None, MagicMock()) is None
    assert calls == []
