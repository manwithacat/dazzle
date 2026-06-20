"""#1128: ``get_auth_context`` may be an ``async def`` (FastAPI-idiomatic).

Page routes are FastAPI handlers (always async). Projects on async
auth stacks — async DB sessions, async permission lookup, the
standard ``Depends``-style dependency — used to silently fail at the
``get_auth_context`` seam: the returned coroutine was assigned to
``auth_ctx`` and then read as ``.is_authenticated`` / ``.user``,
raising ``AttributeError: 'coroutine' object has no attribute …``
every page load.

The fix wraps the call in ``_resolve_auth_context`` which awaits
when the result is a coroutine and passes through otherwise. Sync
callables continue to work unchanged (backward-compatible).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from dazzle.http.runtime.page_routes import _inject_auth_context, _resolve_auth_context
from dazzle.render.context import PageContext

# ---------------------------------------------------------------------------
# _resolve_auth_context — pure helper
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_auth_context_returns_sync_result_unchanged() -> None:
    """Existing sync callables work exactly as before — backward-compat."""
    sentinel = SimpleNamespace(is_authenticated=True)

    def _sync(_req: object) -> SimpleNamespace:
        return sentinel

    result = await _resolve_auth_context(_sync, MagicMock())
    assert result is sentinel


@pytest.mark.asyncio
async def test_resolve_auth_context_awaits_coroutine() -> None:
    """``async def`` callables are awaited so the seam returns the
    resolved value, not the raw coroutine."""
    sentinel = SimpleNamespace(is_authenticated=True)

    async def _async(_req: object) -> SimpleNamespace:
        return sentinel

    result = await _resolve_auth_context(_async, MagicMock())
    assert result is sentinel


@pytest.mark.asyncio
async def test_resolve_auth_context_none_callable_returns_none() -> None:
    """``get_auth_context=None`` is the no-auth-configured shape; helper
    must return ``None`` cleanly without calling anything."""
    assert await _resolve_auth_context(None, MagicMock()) is None


# ---------------------------------------------------------------------------
# _inject_auth_context — end-to-end with async resolver
# ---------------------------------------------------------------------------


def _make_prc(get_auth_context: object | None) -> SimpleNamespace:
    """Minimal _PageRequestContext shape _inject_auth_context reads."""
    ctx = PageContext(page_title="x")
    deps = SimpleNamespace(
        get_auth_context=get_auth_context,
        entity_cedar_specs=None,
        route_entity=None,
        # #1324 slice 3b: _inject_auth_context resolves a precomputed NavModel
        # from these. This test only checks auth round-tripping, so empties.
        persona_navs={},
        anon_nav=None,
    )
    return SimpleNamespace(ctx=ctx, deps=deps, request=MagicMock(), auth_ctx=None)


@pytest.mark.asyncio
async def test_inject_auth_context_handles_async_callable() -> None:
    """End-to-end: an async resolver round-trips through ``_inject_auth_context``
    and lands as a usable ``auth_ctx`` (not a stale coroutine that would
    raise AttributeError on the next ``.is_authenticated`` read)."""
    user = SimpleNamespace(email="x@y", username="x", roles=["role_admin"], is_superuser=False)
    expected = SimpleNamespace(is_authenticated=True, user=user, preferences={})

    async def _async_resolver(_req: object) -> SimpleNamespace:
        return expected

    prc = _make_prc(get_auth_context=_async_resolver)
    await _inject_auth_context(prc)

    # The async coroutine was awaited — ``auth_ctx`` is the resolved value.
    assert prc.auth_ctx is expected
    assert prc.ctx.is_authenticated is True
    assert prc.ctx.user_email == "x@y"
    assert prc.ctx.user_name == "x"


@pytest.mark.asyncio
async def test_inject_auth_context_still_handles_sync_callable() -> None:
    """Backward-compat: sync resolvers (current default) continue to work."""
    user = SimpleNamespace(email="s@y", username="s", roles=["role_admin"], is_superuser=False)
    expected = SimpleNamespace(is_authenticated=True, user=user, preferences={})

    def _sync_resolver(_req: object) -> SimpleNamespace:
        return expected

    prc = _make_prc(get_auth_context=_sync_resolver)
    await _inject_auth_context(prc)

    assert prc.auth_ctx is expected
    assert prc.ctx.user_email == "s@y"
