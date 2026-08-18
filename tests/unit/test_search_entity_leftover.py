"""Search leftover ?entity= must not invent the unfiltered fleet (cycle 2247).

leftover-honest catalog stay-put already exists (oral #69 /
leftover_honest_auth_error). GET ``/_dazzle/search`` still treated
leftover ``zzz`` / ``ghost`` / ``MysteryEntity`` as absent and
invented the fleet (``test_unknown_entity_param_falls_back_to_all``).
Valid declared searchable entity names ride; leftover stays put
(400, no fleet). Absent / blank still first-visit (all entities).
Live ``hx-get="/_dazzle/search"`` + contact_manager
``patterns: searchable``. Oral #117 — not leftover catalog picker
(oral #69), not leftover search-box ``q``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from dazzle.http.runtime.search_routes import (
    create_search_routes,
    leftover_honest_search_entity,
)

_ROUTES = (
    Path(__file__).resolve().parents[2] / "src" / "dazzle" / "http" / "runtime" / "search_routes.py"
)
_LIVE_DSL = Path(__file__).resolve().parents[2] / "examples" / "contact_manager" / "dsl" / "app.dsl"
_LIVE_DOCS = Path(__file__).resolve().parents[2] / "docs" / "reference" / "frontend.md"


class _FakeRepo:
    def __init__(self, items: list[dict[str, object]]) -> None:
        self._items = items
        self.calls = 0

    async def list(self, **_: object) -> dict[str, object]:
        self.calls += 1
        return {"items": self._items, "total": len(self._items)}


def _mount() -> tuple[TestClient, _FakeRepo, _FakeRepo]:
    work = _FakeRepo([{"id": "w1", "title": "Hello"}])
    node = _FakeRepo([{"id": "n1", "title": "Hello"}])
    router = create_search_routes(
        repositories={"Work": work, "Node": node},
        entity_search_fields={"Work": ["title"], "Node": ["title"]},
    )
    assert router is not None
    app = FastAPI()
    app.include_router(router)
    return TestClient(app), work, node


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Work", "Work"),
        ("Node", "Node"),
        ("  Work  ", "Work"),
        ("", ""),
        (None, ""),
        ("   ", ""),
        ("zzz", None),
        ("ghost", None),
        ("MysteryEntity", None),
        ("work", None),
        ("Contact", None),
        (["Work"], None),
        ({"entity": "Work"}, None),
        (1, None),
        (True, None),
    ],
    ids=[
        "work-rides",
        "node-rides",
        "strip",
        "empty-default",
        "none-default",
        "blank-default",
        "leftover-zzz",
        "leftover-ghost",
        "leftover-mystery",
        "leftover-case",
        "leftover-other-entity",
        "leftover-list",
        "leftover-dict",
        "leftover-int",
        "leftover-true",
    ],
)
def test_leftover_honest_search_entity_does_not_invent(raw: object, expected: str | None) -> None:
    declared = ("Work", "Node")
    assert leftover_honest_search_entity(raw, declared) == expected


def test_leftover_entity_zzz_does_not_invent_fleet() -> None:
    client, work, node = _mount()
    resp = client.get("/_dazzle/search", params={"q": "hello", "entity": "zzz"})
    assert resp.status_code == 400
    assert resp.json() == {"error": "invalid entity"}
    assert work.calls == 0
    assert node.calls == 0


def test_leftover_entity_ghost_does_not_invent_fleet() -> None:
    client, work, node = _mount()
    resp = client.get("/_dazzle/search", params={"q": "hello", "entity": "ghost"})
    assert resp.status_code == 400
    assert resp.json()["error"] == "invalid entity"
    assert work.calls == 0
    assert node.calls == 0


def test_leftover_entity_mystery_does_not_invent_fleet() -> None:
    client, work, node = _mount()
    resp = client.get("/_dazzle/search", params={"q": "hello", "entity": "MysteryEntity"})
    assert resp.status_code == 400
    assert work.calls == 0
    assert node.calls == 0


def test_valid_entity_restricts_scope() -> None:
    client, work, node = _mount()
    resp = client.get("/_dazzle/search", params={"q": "hello", "entity": "Work"})
    assert resp.status_code == 200
    body = resp.json()
    assert [r["entity"] for r in body["results"]] == ["Work"]
    assert work.calls == 1
    assert node.calls == 0


def test_absent_entity_still_first_visit_fleet() -> None:
    client, work, node = _mount()
    resp = client.get("/_dazzle/search", params={"q": "hello"})
    assert resp.status_code == 200
    assert [r["entity"] for r in resp.json()["results"]] == ["Work", "Node"]
    assert work.calls == 1
    assert node.calls == 1


def test_helper_source_pins_search_entity_leftover() -> None:
    routes = _ROUTES.read_text()
    assert "def leftover_honest_search_entity" in routes
    assert "leftover_honest_auth_error" in routes
    assert 'return JSONResponse(content={"error": "invalid entity"}, status_code=400)' in routes
    assert "Response(\n            status_code=400,\n            content=" not in routes


def test_live_search_surface_and_contact_searchable() -> None:
    assert 'hx-get="/_dazzle/search"' in _LIVE_DOCS.read_text()
    assert "patterns: profile, searchable" in _LIVE_DSL.read_text()
