"""Tests for the cross-entity search endpoint (#782)."""

import json
from typing import Any

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient


class _FakeRepo:
    """In-memory repo that filters items by a substring of any search field."""

    def __init__(self, items: list[dict[str, Any]]) -> None:
        self._items = items

    async def list(
        self,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
        search_fields: list[str] | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        items = self._items
        if search:
            needle = search.lower()
            fields = search_fields or (list(items[0].keys()) if items else [])
            items = [
                row for row in items if any(needle in str(row.get(f, "")).lower() for f in fields)
            ]
        start = (page - 1) * page_size
        return {
            "items": items[start : start + page_size],
            "total": len(items),
            "page": page,
            "page_size": page_size,
        }


def _mount(router: Any) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


class TestCreateSearchRoutes:
    def test_no_searchable_entities_returns_none(self) -> None:
        from dazzle_back.runtime.search_routes import create_search_routes

        assert create_search_routes(repositories={}, entity_search_fields={}) is None

    def test_empty_fields_filtered(self) -> None:
        from dazzle_back.runtime.search_routes import create_search_routes

        router = create_search_routes(
            repositories={"Work": _FakeRepo([])},
            entity_search_fields={"Work": []},
        )
        assert router is None

    def test_returns_router_when_any_entity_searchable(self) -> None:
        from dazzle_back.runtime.search_routes import create_search_routes

        router = create_search_routes(
            repositories={"Work": _FakeRepo([])},
            entity_search_fields={"Work": ["title"]},
        )
        assert router is not None


class TestCrossEntitySearchHandler:
    def test_query_groups_results_by_entity(self) -> None:
        from dazzle_back.runtime.search_routes import create_search_routes

        work_repo = _FakeRepo(
            [
                {"id": "w1", "title": "Hello world", "description": "A greeting"},
                {"id": "w2", "title": "Goodbye", "description": "A farewell"},
            ]
        )
        node_repo = _FakeRepo(
            [
                {"id": "n1", "title": "Hello node", "text": "Node content"},
            ]
        )

        router = create_search_routes(
            repositories={"Work": work_repo, "Node": node_repo},
            entity_search_fields={"Work": ["title"], "Node": ["title", "text"]},
        )
        assert router is not None

        client = _mount(router)
        response = client.get("/api/search", params={"q": "hello"})
        assert response.status_code == 200
        body = json.loads(response.content)
        assert body["query"] == "hello"
        entities = [r["entity"] for r in body["results"]]
        assert entities == ["Work", "Node"]
        work_result = body["results"][0]
        assert work_result["total"] == 1
        assert work_result["items"][0]["id"] == "w1"
        node_result = body["results"][1]
        assert node_result["items"][0]["id"] == "n1"

    def test_entity_param_restricts_scope(self) -> None:
        from dazzle_back.runtime.search_routes import create_search_routes

        router = create_search_routes(
            repositories={
                "Work": _FakeRepo([{"id": "w1", "title": "Hello"}]),
                "Node": _FakeRepo([{"id": "n1", "title": "Hello"}]),
            },
            entity_search_fields={"Work": ["title"], "Node": ["title"]},
        )
        assert router is not None

        client = _mount(router)
        response = client.get("/api/search", params={"q": "hello", "entity": "Work"})
        body = json.loads(response.content)
        assert [r["entity"] for r in body["results"]] == ["Work"]

    def test_unknown_entity_param_falls_back_to_all(self) -> None:
        from dazzle_back.runtime.search_routes import create_search_routes

        router = create_search_routes(
            repositories={"Work": _FakeRepo([{"id": "w1", "title": "Hello"}])},
            entity_search_fields={"Work": ["title"]},
        )
        assert router is not None

        client = _mount(router)
        response = client.get("/api/search", params={"q": "hello", "entity": "MysteryEntity"})
        body = json.loads(response.content)
        assert [r["entity"] for r in body["results"]] == ["Work"]

    def test_repo_failure_does_not_break_other_entities(self) -> None:
        from dazzle_back.runtime.search_routes import create_search_routes

        class BrokenRepo:
            async def list(self, **kwargs: Any) -> Any:
                raise RuntimeError("boom")

        router = create_search_routes(
            repositories={
                "Broken": BrokenRepo(),
                "Work": _FakeRepo([{"id": "w1", "title": "Hello"}]),
            },
            entity_search_fields={"Broken": ["title"], "Work": ["title"]},
        )
        assert router is not None

        client = _mount(router)
        response = client.get("/api/search", params={"q": "hello"})
        body = json.loads(response.content)
        # Broken entity is skipped silently, Work still produces results
        assert [r["entity"] for r in body["results"]] == ["Work"]

    def test_limit_respected(self) -> None:
        from dazzle_back.runtime.search_routes import create_search_routes

        repo = _FakeRepo([{"id": f"w{i}", "title": "match"} for i in range(20)])
        router = create_search_routes(
            repositories={"Work": repo}, entity_search_fields={"Work": ["title"]}
        )
        assert router is not None

        client = _mount(router)
        response = client.get("/api/search", params={"q": "match", "limit": 5})
        body = json.loads(response.content)
        assert body["results"][0]["total"] == 20
        assert len(body["results"][0]["items"]) == 5

    def test_empty_q_rejected(self) -> None:
        from dazzle_back.runtime.search_routes import create_search_routes

        router = create_search_routes(
            repositories={"Work": _FakeRepo([])},
            entity_search_fields={"Work": ["title"]},
        )
        assert router is not None

        client = _mount(router)
        response = client.get("/api/search")
        assert response.status_code == 422  # Missing required q


class TestBuildEntitySearchFieldsFallback:
    """build_entity_search_fields now pulls from IR searchable modifiers too."""

    def test_surface_fields_take_precedence(self) -> None:
        from types import SimpleNamespace

        from dazzle_back.runtime.app_factory import build_entity_search_fields

        surface = SimpleNamespace(entity_ref="Work", search_fields=["title"])
        entity = SimpleNamespace(
            name="Work",
            searchable_fields=[SimpleNamespace(name="description")],
        )
        result = build_entity_search_fields(surfaces=[surface], entities=[entity])
        assert result == {"Work": ["title"]}

    def test_ir_fallback_when_no_surface_declaration(self) -> None:
        from types import SimpleNamespace

        from dazzle_back.runtime.app_factory import build_entity_search_fields

        entity = SimpleNamespace(
            name="Work",
            searchable_fields=[
                SimpleNamespace(name="title"),
                SimpleNamespace(name="description"),
            ],
        )
        result = build_entity_search_fields(surfaces=[], entities=[entity])
        assert result == {"Work": ["title", "description"]}

    def test_entity_without_searchable_fields_omitted(self) -> None:
        from types import SimpleNamespace

        from dazzle_back.runtime.app_factory import build_entity_search_fields

        entity = SimpleNamespace(name="Work", searchable_fields=[])
        result = build_entity_search_fields(surfaces=[], entities=[entity])
        assert result == {}

    def test_no_entities_arg_behaves_as_before(self) -> None:
        from types import SimpleNamespace

        from dazzle_back.runtime.app_factory import build_entity_search_fields

        surface = SimpleNamespace(entity_ref="Work", search_fields=["title"])
        result = build_entity_search_fields(surfaces=[surface])
        assert result == {"Work": ["title"]}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
