"""#1626 — current_user filters must use auth principal id, not stale email rows."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from dazzle.http.runtime.workspace_user import _resolve_workspace_user


@pytest.mark.asyncio
async def test_prefers_auth_id_over_stale_email_row() -> None:
    auth_id = "a1000000-0000-4000-8000-000000000001"
    stale_id = "95995ad4-a97d-45ce-8b9b-df32426ee586"
    auth_user = SimpleNamespace(id=auth_id, email="member@demo.dazzle.local")
    auth_ctx = SimpleNamespace(is_authenticated=True, user=auth_user)
    middleware = MagicMock()
    middleware.get_auth_context.return_value = auth_ctx

    repo = MagicMock()
    # id lookup misses; email hits a stale domain row
    repo.list = AsyncMock(
        side_effect=[
            {"items": []},  # by id
            {"items": [{"id": stale_id, "email": "member@demo.dazzle.local"}]},  # by email
        ]
    )
    uid, entity = await _resolve_workspace_user(
        request=object(),
        auth_middleware=middleware,
        repositories={"User": repo},
        user_entity_name="User",
    )
    assert uid == auth_id
    # Stale email row must not override auth principal for filters.
    assert entity is None or str(entity.get("id")) == auth_id


@pytest.mark.asyncio
async def test_id_match_returns_entity_attrs() -> None:
    auth_id = "a1000000-0000-4000-8000-000000000001"
    auth_user = SimpleNamespace(id=auth_id, email="member@demo.dazzle.local")
    auth_ctx = SimpleNamespace(is_authenticated=True, user=auth_user)
    middleware = MagicMock()
    middleware.get_auth_context.return_value = auth_ctx
    repo = MagicMock()
    repo.list = AsyncMock(
        return_value={
            "items": [{"id": auth_id, "email": "member@demo.dazzle.local", "role": "member"}]
        }
    )
    uid, entity = await _resolve_workspace_user(
        request=object(),
        auth_middleware=middleware,
        repositories={"User": repo},
        user_entity_name="User",
    )
    assert uid == auth_id
    assert entity is not None
    assert entity["role"] == "member"
