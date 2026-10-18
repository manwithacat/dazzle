"""`GET /_dazzle/fts/{entity}` applies the list path's permit + scope (ship P).

Before ship P the route read ``AppSpec.cedar_access_specs`` — an attribute
``AppSpec`` does not have — so every search ran unscoped. These tests build a
real AppSpec from DSL (one scoped entity, one without access rules), wire the
access specs the way ``server.py`` does, and assert what reaches
``Repository.fts_search``. The Postgres proof is
``tests/integration/test_search_scope_pg.py``.
"""

import os
import tempfile
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI
from starlette.testclient import TestClient

_DSL = """
module fts_scope
app fts_scope "FTS Scope"

persona member "Member":
  description: "Sees own notes"

persona guest "Guest":
  description: "May not list notes"

entity User "User":
  id: uuid pk
  email: email required

entity Note "Note":
  id: uuid pk
  title: str(200) required
  owner: ref User required

  permit:
    list: role(member)

  scope:
    list: owner = current_user
      as: member

entity Memo "Memo":
  id: uuid pk
  title: str(200) required

search on Note:
  fields: title

search on Memo:
  fields: title
"""


def _appspec() -> Any:
    from dazzle.core.linker import build_appspec
    from dazzle.core.parser import parse_modules

    with tempfile.NamedTemporaryFile(mode="w", suffix=".dsl", delete=False) as f:
        f.write(_DSL)
        path = Path(f.name)
    try:
        modules = parse_modules([path])
        return build_appspec(modules, modules[0].name)
    finally:
        os.unlink(path)


class _RecordingRepo:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def fts_search(self, spec: Any, q: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {"items": [], "total": 0, "page": 1, "page_size": 20}


def _client(role: str) -> tuple[TestClient, dict[str, _RecordingRepo], str]:
    """Mount the FTS router for a caller holding *role*; returns the client, the
    recording repos and the caller's domain-user id."""
    from dazzle.http.converters.entity_converter import convert_entities
    from dazzle.http.runtime.auth.models import AuthContext, UserRecord
    from dazzle.http.runtime.fts_routes import create_fts_routes

    appspec = _appspec()
    # Mirrors server.py's `cedar_access_specs` construction.
    cedar_access_specs = {
        e.name: e.access for e in convert_entities(appspec.domain.entities) if e.access
    }
    user = UserRecord(id=uuid4(), email="u@example.test", password_hash="x", roles=[role])
    # The runtime merges the matching domain `User` row's id into preferences;
    # `owner = current_user` binds that id.
    domain_user_id = str(uuid4())

    async def _auth() -> AuthContext:
        return AuthContext(
            user=user,
            is_authenticated=True,
            roles=[role],
            preferences={"entity_id": domain_user_id},
        )

    repos = {"Note": _RecordingRepo(), "Memo": _RecordingRepo()}
    router = create_fts_routes(
        appspec=appspec,
        repositories=repos,
        fk_graph=appspec.fk_graph,
        auth_dep=_auth,
        cedar_access_specs=cedar_access_specs,
    )
    assert router is not None
    app = FastAPI()
    app.include_router(router)
    return TestClient(app), repos, domain_user_id


def test_scoped_entity_search_carries_the_scope_predicate() -> None:
    client, repos, domain_user_id = _client("member")
    resp = client.get("/_dazzle/fts/Note", params={"q": "hello"})
    assert resp.status_code == 200
    (call,) = repos["Note"].calls
    sql, params = call["filters"]["__scope_predicate"]
    assert '"Note"."owner" = ' in sql
    assert params == [domain_user_id]


def test_entity_without_access_rules_is_unaffected() -> None:
    client, repos, _ = _client("member")
    resp = client.get("/_dazzle/fts/Memo", params={"q": "hello"})
    assert resp.status_code == 200
    (call,) = repos["Memo"].calls
    assert call["filters"] == {}


def test_role_the_list_permit_denies_gets_403_and_no_query() -> None:
    client, repos, _ = _client("guest")
    resp = client.get("/_dazzle/fts/Note", params={"q": "hello"})
    assert resp.status_code == 403
    assert repos["Note"].calls == []


def test_cleared_search_box_gets_nothing_to_swap() -> None:
    """#1821: a cleared box's late request (empty ``q``) must not land an error
    body in the results panel — the html form answers 204 (htmx swaps nothing,
    the box has restored its coaching line); the JSON API still rejects it."""
    client, repos, _ = _client("member")
    assert client.get("/_dazzle/fts/Note", params={"q": " ", "html": 1}).status_code == 204
    assert client.get("/_dazzle/fts/Note", params={"q": ""}).status_code == 422
    assert repos["Note"].calls == []
