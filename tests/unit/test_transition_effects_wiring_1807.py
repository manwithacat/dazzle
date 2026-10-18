"""``on_transition`` effects run on every update path (#1807, #1824).

#1807 — the executor looks services up by ``effect.entity_name``, so the wiring hands it
the entity-keyed view of the service registry.
#1824 — the runtime held one CRUDService per *service name* (list_/create_/get_/update_/
delete_<entity>); the runner landed on one of them while the policy registry and the PUT
route used others, so the effect never fired. There is now one CRUDService per entity.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.http.runtime.service_generator import CRUDService
from dazzle.http.runtime.subsystems.system_routes import SystemRoutesSubsystem

DSL = """module t
app t "T"

entity Doc "Doc":
  id: uuid pk
  status: enum[draft, sent] = draft

  transitions:
    draft -> sent

  on_transition:
    draft -> sent:
      create Audit:
        note: "sent"

entity Audit "Audit":
  id: uuid pk
  note: str(50)
"""


class _Crud(CRUDService):
    """Service-registry stand-in: CRUD surface only, records creates."""

    def __init__(self, entity_name: str) -> None:
        self.entity_name = entity_name
        self.callbacks: list[Any] = []
        self.created: list[dict[str, Any]] = []
        self.create_schema = lambda **kw: kw

    def on_updated(self, cb: Any) -> None:
        self.callbacks.append(cb)

    async def create(self, data: dict[str, Any], **_: Any) -> Any:  # type: ignore[override]
        self.created.append(data)
        return SimpleNamespace(id="a-1")


@pytest.mark.asyncio
async def test_on_transition_create_effect_runs_against_the_target_entity_service() -> None:
    *_, fragment = parse_dsl(DSL, Path("t.dsl"))
    doc, audit = _Crud("Doc"), _Crud("Audit")
    ctx = SimpleNamespace(
        appspec=SimpleNamespace(domain=SimpleNamespace(entities=fragment.entities)),
        entity_services={"Doc": doc, "Audit": audit},
    )
    SystemRoutesSubsystem._init_transition_effects(
        SystemRoutesSubsystem.__new__(SystemRoutesSubsystem), ctx
    )
    assert len(doc.callbacks) == 1

    await doc.callbacks[0]("Doc", "d-1", {"status": "sent"}, {"status": "draft"})

    assert audit.created == [{"note": "sent"}]


# --- #1824: the real runtime, both update paths (PostgreSQL) -----------------------------

APP_DSL = """module t1824
app t1824 "T1824"

entity Memo1824 "Memo":
  id: uuid pk
  title: str(50) required
  status: enum[draft, sent] = draft

  transitions:
    draft -> sent

  on_transition:
    draft -> sent:
      create MemoTrail1824:
        note: "sent"

entity MemoTrail1824 "Memo trail":
  id: uuid pk
  note: str(50)

surface memo_list "Memos":
  uses entity Memo1824
  mode: list
  section main:
    field title "Title"
    field status "Status"

surface memo_create "New memo":
  uses entity Memo1824
  mode: create
  section main:
    field title "Title"

surface memo_edit "Edit memo":
  uses entity Memo1824
  mode: edit
  section main:
    field title "Title"
    field status "Status"

surface trail_list "Trail":
  uses entity MemoTrail1824
  mode: list
  section main:
    field note "Note"
"""


@pytest.fixture(scope="module")
def memo_app(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[Any, Any, Any]]:
    from fastapi.testclient import TestClient

    from dazzle.core.linker import build_appspec
    from dazzle.core.parser import parse_modules
    from dazzle.http.runtime.app_factory import create_app
    from dazzle.http.runtime.pg_backend import PostgresBackend
    from tests.unit._auth_pg import pg_url_or_skip

    database_url = pg_url_or_skip()
    root = tmp_path_factory.mktemp("t1824")
    (root / "app.dsl").write_text(APP_DSL)
    appspec = build_appspec(parse_modules([root / "app.dsl"]), "t1824")
    app = create_app(appspec, database_url=database_url)
    with TestClient(app) as client:
        db = PostgresBackend(database_url)
        with db.connection() as conn:
            conn.execute('DELETE FROM "MemoTrail1824"')
            conn.execute('DELETE FROM "Memo1824"')
        client.get("/health")  # sets the dazzle_csrf cookie
        yield app, client, db


def _trail_count(db: Any) -> int:
    with db.connection() as conn:
        row = conn.execute('SELECT count(*) AS n FROM "MemoTrail1824"').fetchone()
    return int(row["n"] if isinstance(row, dict) else row[0])


def _draft_memo(client: Any) -> str:
    created = client.post(
        "/memo1824s",
        json={"title": "m", "status": "draft"},
        headers={"X-CSRF-Token": client.cookies.get("dazzle_csrf", "")},
    )
    assert created.status_code == 200, created.text
    return str(created.json()["id"])


@pytest.mark.parametrize("path", ["policy_registry_service", "put_route"])
def test_on_transition_effect_runs_on_every_update_path(
    memo_app: tuple[Any, Any, Any], path: str
) -> None:
    app, client, db = memo_app
    memo_id = _draft_memo(client)
    before = _trail_count(db)

    if path == "policy_registry_service":
        service = app.state.policy_registry.get("Memo1824").service
        asyncio.run(service.update(UUID(memo_id), service.update_schema(status="sent")))
    else:
        updated = client.put(
            f"/memo1824s/{memo_id}",
            json={"title": "m", "status": "sent"},
            headers={"X-CSRF-Token": client.cookies.get("dazzle_csrf", "")},
        )
        assert updated.status_code == 200, updated.text

    assert _trail_count(db) == before + 1
