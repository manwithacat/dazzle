"""How a workspace region request resolves ``current_user`` (#1626, #483, #484, #486, #588).

Driven through ``resolve_request_user_context`` — the region prelude every
workspace region, batch and stats route runs — with a real ``AuthContext`` and a
User repository that answers by filter. Every case runs with
``require_auth=False``: the user is still resolved when the app does not demand
auth (#483).

- #1626: ``current_user`` filters bind the auth principal id; a stale domain
  row found only by email (pre-rekey mirror, different id) must not override it.
- #484: ``Repository.list`` returns a dict; its ``items`` are read as a key.
- #486: the resolved User row lands in the filter context as
  ``current_user_entity`` and its attrs in the auth preferences, so
  ``current_user.<field>`` resolves.
- #588: the DSL user entity is looked up by its declared name, not ``User``.
"""

from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest

from dazzle.http.runtime.auth.models import AuthContext, UserRecord
from dazzle.http.runtime.workspace_context import WorkspaceRegionContext
from dazzle.http.runtime.workspace_region_prelude import resolve_request_user_context

AUTH_ID = "a1000000-0000-4000-8000-000000000001"
STALE_ID = "95995ad4-a97d-45ce-8b9b-df32426ee586"
EMAIL = "member@demo.dazzle.local"


class _UserRepo:
    """Answers ``list(filters={"id"|"email": ...})`` from a fixed row set."""

    def __init__(self, *rows: dict[str, Any]) -> None:
        self.rows = rows

    async def list(self, *, filters: dict[str, Any], page_size: int) -> dict[str, Any]:
        [(key, value)] = filters.items()
        return {"items": [r for r in self.rows if str(r.get(key)) == value][:page_size]}


async def _resolve(repositories: dict[str, Any], user_entity_name: str = "User") -> Any:
    auth = AuthContext(
        user=UserRecord(id=UUID(AUTH_ID), email=EMAIL, password_hash="x"),
        is_authenticated=True,
    )
    ctx = WorkspaceRegionContext(
        ctx_region=SimpleNamespace(aggregates={}, name="r", endpoint="/api/r"),
        ir_region=None,
        source="Task",
        entity_spec=None,
        attention_signals=[],
        ws_access=None,
        repositories=repositories,
        require_auth=False,
        auth_middleware=SimpleNamespace(get_auth_context=lambda _request: auth),
        user_entity_name=user_entity_name,
    )
    request = SimpleNamespace(query_params={}, state=SimpleNamespace())
    return await resolve_request_user_context(request, ctx)


_MEMBER = {"id": AUTH_ID, "email": EMAIL, "role": "member"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("repositories", "entity_name", "expected_entity"),
    [
        pytest.param({"User": _UserRepo(_MEMBER)}, "User", _MEMBER, id="id-match-#1626"),
        pytest.param(
            {"User": _UserRepo({"id": STALE_ID, "email": EMAIL, "role": "stale"})},
            "User",
            None,
            id="stale-email-row-ignored-#1626",
        ),
        pytest.param(
            {"Student": _UserRepo(_MEMBER), "User": _UserRepo()},
            "Student",
            _MEMBER,
            id="declared-user-entity-name-#588",
        ),
        pytest.param({}, "User", None, id="no-user-repository"),
    ],
)
async def test_region_resolves_current_user_to_the_auth_principal(
    repositories: dict[str, Any], entity_name: str, expected_entity: dict[str, Any] | None
) -> None:
    resolved = await _resolve(repositories, entity_name)

    assert resolved.user_id == AUTH_ID
    assert resolved.filter_context["current_user_id"] == AUTH_ID
    assert resolved.user_entity == expected_entity
    assert resolved.filter_context.get("current_user_entity") == expected_entity


@pytest.mark.asyncio
async def test_resolved_user_attrs_reach_the_filter_auth_preferences_486() -> None:
    resolved = await _resolve({"User": _UserRepo(_MEMBER)})

    assert resolved.auth_ctx_for_filters.preferences == {
        "id": AUTH_ID,
        "email": EMAIL,
        "role": "member",
        "entity_id": AUTH_ID,
    }
