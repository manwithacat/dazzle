"""Tests for route conflict detection."""

import logging

import pytest
from fastapi import FastAPI
from starlette.routing import Mount

from dazzle.http.runtime.route_validator import validate_routes


def _make_app_with_routes(*routes: tuple[str, list[str]]) -> FastAPI:
    """Build a FastAPI app with the given (path, methods) pairs."""
    app = FastAPI()
    for path, methods in routes:
        for method in methods:
            getattr(app, method.lower())(path)(lambda: None)
    return app


def _build_app_no_conflicts() -> FastAPI:
    return _make_app_with_routes(
        ("/users", ["GET"]),
        ("/users", ["POST"]),
        ("/users/{id}", ["GET"]),
    )


def _build_app_multiple_conflicts() -> FastAPI:
    app = FastAPI()

    @app.get("/a")
    async def a1() -> None: ...

    @app.get("/a")
    async def a2() -> None: ...

    @app.post("/b")
    async def b1() -> None: ...

    @app.post("/b")
    async def b2() -> None: ...

    return app


def _build_app_different_methods_same_path() -> FastAPI:
    app = FastAPI()

    @app.get("/resource")
    async def get_resource() -> None: ...

    @app.post("/resource")
    async def create_resource() -> None: ...

    return app


def _build_app_with_mount() -> FastAPI:
    app = FastAPI()

    @app.get("/api")
    async def api() -> None: ...

    app.routes.append(Mount("/static", routes=[]))
    return app


def _build_empty_app() -> FastAPI:
    return FastAPI()


class TestValidateRoutes:
    @pytest.mark.parametrize(
        ("builder", "expected_count"),
        [
            (_build_app_no_conflicts, 0),
            (_build_app_multiple_conflicts, 2),
            (_build_app_different_methods_same_path, 0),
            (_build_app_with_mount, 0),
            (_build_empty_app, 0),
        ],
        ids=[
            "test_no_conflicts_returns_empty",
            "test_detects_multiple_conflicts",
            "test_different_methods_same_path_no_conflict",
            "test_ignores_mount_routes",
            "test_empty_app_returns_empty",
        ],
    )
    def test_conflict_count(self, builder, expected_count) -> None:
        assert len(validate_routes(builder())) == expected_count

    def test_detects_duplicate_get(self) -> None:
        app = FastAPI()

        @app.get("/items")
        async def items_v1() -> dict[str, str]:
            return {"v": "1"}

        @app.get("/items")
        async def items_v2() -> dict[str, str]:
            return {"v": "2"}

        conflicts = validate_routes(app)
        assert len(conflicts) == 1
        assert "GET" in conflicts[0]
        assert "/items" in conflicts[0]
        assert "2 times" in conflicts[0]

    def test_strict_raises_on_conflict(self) -> None:
        app = FastAPI()

        @app.get("/dup")
        async def dup1() -> None: ...

        @app.get("/dup")
        async def dup2() -> None: ...

        with pytest.raises(RuntimeError, match="Route conflicts detected"):
            validate_routes(app, strict=True)

    def test_strict_no_raise_when_clean(self) -> None:
        app = _make_app_with_routes(("/x", ["GET"]), ("/y", ["POST"]))
        validate_routes(app, strict=True)  # should not raise

    def test_logs_warnings(self, caplog: pytest.LogCaptureFixture) -> None:
        app = FastAPI()

        @app.get("/warn")
        async def w1() -> None: ...

        @app.get("/warn")
        async def w2() -> None: ...

        with caplog.at_level(logging.WARNING, logger="dazzle.routes"):
            validate_routes(app)

        assert any("Route conflict" in r.message for r in caplog.records)
