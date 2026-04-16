"""Tests for bulk-action endpoints (#785)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from fastapi import FastAPI
from starlette.testclient import TestClient

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.ir import BulkActionSpec


class _Repo:
    """Minimal async repo: stores dict rows by id."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = {str(r["id"]): r for r in rows}

    async def update(self, id: str, data: dict[str, Any]) -> dict[str, Any] | None:
        row = self._rows.get(str(id))
        if row is None:
            return None
        row.update(data)
        return row


def _mount(router: Any) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _surface_with_bulk(
    *,
    entity: str = "InsertionPoint",
    actions: list[BulkActionSpec] | None = None,
    mode: str = "list",
) -> Any:
    return SimpleNamespace(
        entity_ref=entity,
        mode=mode,
        ux=SimpleNamespace(
            bulk_actions=actions
            or [
                BulkActionSpec(name="accept", field="status", target_value="active"),
                BulkActionSpec(name="reject", field="status", target_value="rejected"),
            ]
        ),
    )


class TestCreateBulkRoutes:
    def test_no_surfaces_returns_none(self) -> None:
        from dazzle_back.runtime.bulk_routes import create_bulk_routes

        assert create_bulk_routes(surfaces=[], repositories={}) is None

    def test_no_bulk_actions_returns_none(self) -> None:
        from dazzle_back.runtime.bulk_routes import create_bulk_routes

        plain = SimpleNamespace(entity_ref="Task", mode="list", ux=SimpleNamespace(bulk_actions=[]))
        result = create_bulk_routes(surfaces=[plain], repositories={"Task": _Repo([])})
        assert result is None

    def test_non_list_surfaces_ignored(self) -> None:
        from dazzle_back.runtime.bulk_routes import create_bulk_routes

        edit_surface = _surface_with_bulk(mode="edit")
        assert (
            create_bulk_routes(
                surfaces=[edit_surface],
                repositories={"InsertionPoint": _Repo([])},
            )
            is None
        )

    def test_missing_repository_skips_entity(self) -> None:
        from dazzle_back.runtime.bulk_routes import create_bulk_routes

        # Repo map omits the entity, so the router has nothing to mount.
        assert create_bulk_routes(surfaces=[_surface_with_bulk()], repositories={}) is None


class TestBulkEndpointHandler:
    def _build(self, rows: list[dict[str, Any]]) -> TestClient:
        from dazzle_back.runtime.bulk_routes import create_bulk_routes

        router = create_bulk_routes(
            surfaces=[_surface_with_bulk()],
            repositories={"InsertionPoint": _Repo(rows)},
        )
        assert router is not None
        return _mount(router)

    def test_applies_action_to_multiple_ids(self) -> None:
        rows = [
            {"id": "i1", "status": "pending"},
            {"id": "i2", "status": "pending"},
            {"id": "i3", "status": "pending"},
        ]
        client = self._build(rows)
        resp = client.post(
            "/api/insertionpoints/bulk",
            json={"action": "accept", "ids": ["i1", "i2", "i3"]},
        )
        assert resp.status_code == 200
        body = json.loads(resp.content)
        assert body["succeeded"] == 3
        assert body["action"] == "accept"
        assert body["field"] == "status"
        assert body["target_value"] == "active"
        for row in rows:
            assert row["status"] == "active"

    def test_unknown_action_returns_422(self) -> None:
        client = self._build([{"id": "i1", "status": "pending"}])
        resp = client.post(
            "/api/insertionpoints/bulk",
            json={"action": "mystery", "ids": ["i1"]},
        )
        assert resp.status_code == 422
        body = json.loads(resp.content)
        assert "mystery" in body["error"]
        assert "accept" in body["actions"]
        assert "reject" in body["actions"]

    def test_missing_ids_returns_422(self) -> None:
        client = self._build([])
        resp = client.post("/api/insertionpoints/bulk", json={"action": "accept", "ids": []})
        assert resp.status_code == 422
        assert "non-empty list" in json.loads(resp.content)["error"]

    def test_invalid_body_returns_400(self) -> None:
        client = self._build([])
        resp = client.post(
            "/api/insertionpoints/bulk",
            content="not json",
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 400

    def test_per_item_not_found_reported(self) -> None:
        client = self._build([{"id": "i1", "status": "pending"}])
        resp = client.post(
            "/api/insertionpoints/bulk",
            json={"action": "accept", "ids": ["i1", "missing"]},
        )
        body = json.loads(resp.content)
        assert body["total"] == 2
        assert body["succeeded"] == 1
        by_id = {r["id"]: r for r in body["results"]}
        assert by_id["i1"]["ok"] is True
        assert by_id["missing"]["ok"] is False
        assert by_id["missing"]["error"] == "not_found"

    def test_reject_action_uses_target_value(self) -> None:
        rows = [{"id": "i1", "status": "pending"}]
        client = self._build(rows)
        resp = client.post(
            "/api/insertionpoints/bulk",
            json={"action": "reject", "ids": ["i1"]},
        )
        body = json.loads(resp.content)
        assert body["target_value"] == "rejected"
        assert rows[0]["status"] == "rejected"


class TestDSLParserBulkActions:
    """ux: bulk_actions: block parses into BulkActionSpec list."""

    def _parse_first_surface(self, dsl: str) -> Any:
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("t.dsl"))
        return fragment.surfaces[0]

    def test_basic_parse(self) -> None:
        dsl = """
module testapp
app testapp "Test"

entity InsertionPoint "Point":
  id: uuid pk
  status: str(20) required

surface review "Review":
  uses entity InsertionPoint
  mode: list
  section main:
    field status "Status"
  ux:
    bulk_actions:
      accept: status -> active
      reject: status -> rejected
"""
        surface = self._parse_first_surface(dsl)
        actions = surface.ux.bulk_actions
        assert len(actions) == 2
        assert actions[0].name == "accept"
        assert actions[0].field == "status"
        assert actions[0].target_value == "active"
        assert actions[1].name == "reject"
        assert actions[1].target_value == "rejected"

    def test_quoted_target_value(self) -> None:
        dsl = """
module testapp
app testapp "Test"

entity InsertionPoint "Point":
  id: uuid pk
  status: str(20) required

surface review "Review":
  uses entity InsertionPoint
  mode: list
  section main:
    field status "Status"
  ux:
    bulk_actions:
      archive: status -> "archived and locked"
"""
        surface = self._parse_first_surface(dsl)
        assert surface.ux.bulk_actions[0].target_value == "archived and locked"

    def test_bool_target_value(self) -> None:
        dsl = """
module testapp
app testapp "Test"

entity Task "Task":
  id: uuid pk
  completed: bool=false

surface review "Review":
  uses entity Task
  mode: list
  section main:
    field completed "Done"
  ux:
    bulk_actions:
      finish: completed -> true
      reopen: completed -> false
"""
        surface = self._parse_first_surface(dsl)
        actions = surface.ux.bulk_actions
        assert actions[0].target_value == "true"
        assert actions[1].target_value == "false"

    def test_bulk_actions_coexist_with_other_ux_keys(self) -> None:
        dsl = """
module testapp
app testapp "Test"

entity Task "Task":
  id: uuid pk
  status: str(20)

surface review "Review":
  uses entity Task
  mode: list
  section main:
    field status "Status"
  ux:
    filter: status
    bulk_actions:
      accept: status -> active
"""
        surface = self._parse_first_surface(dsl)
        assert surface.ux.filter == ["status"]
        assert len(surface.ux.bulk_actions) == 1
        assert surface.ux.bulk_actions[0].name == "accept"
