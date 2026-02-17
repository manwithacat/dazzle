"""Tests for the route override system (v0.29.0).

Covers:
- Route override discovery from declaration headers
- Handler loading from Python files
- Router building from discovered overrides
"""

from __future__ import annotations

from pathlib import Path


class TestDiscoverRouteOverrides:
    """discover_route_overrides() parses declaration headers."""

    def test_discovers_get_override(self, tmp_path: Path) -> None:
        from dazzle_back.runtime.route_overrides import discover_route_overrides

        routes_dir = tmp_path / "routes"
        routes_dir.mkdir()
        (routes_dir / "custom_wizard.py").write_text(
            "# dazzle:route-override GET /app/tasks/create\n"
            "async def handler(request):\n"
            "    return {'custom': True}\n"
        )
        result = discover_route_overrides(routes_dir)
        assert len(result) == 1
        assert result[0].method == "GET"
        assert result[0].path == "/app/tasks/create"
        assert callable(result[0].handler)

    def test_discovers_post_override(self, tmp_path: Path) -> None:
        from dazzle_back.runtime.route_overrides import discover_route_overrides

        routes_dir = tmp_path / "routes"
        routes_dir.mkdir()
        (routes_dir / "custom_submit.py").write_text(
            "# dazzle:route-override POST /api/tasks\n"
            "async def handler(request):\n"
            "    return {'submitted': True}\n"
        )
        result = discover_route_overrides(routes_dir)
        assert len(result) == 1
        assert result[0].method == "POST"
        assert result[0].path == "/api/tasks"

    def test_case_insensitive_method(self, tmp_path: Path) -> None:
        from dazzle_back.runtime.route_overrides import discover_route_overrides

        routes_dir = tmp_path / "routes"
        routes_dir.mkdir()
        (routes_dir / "test.py").write_text(
            "# dazzle:route-override get /test\nasync def handler(): return {}\n"
        )
        result = discover_route_overrides(routes_dir)
        assert len(result) == 1
        assert result[0].method == "GET"

    def test_ignores_files_without_declaration(self, tmp_path: Path) -> None:
        from dazzle_back.runtime.route_overrides import discover_route_overrides

        routes_dir = tmp_path / "routes"
        routes_dir.mkdir()
        (routes_dir / "helper.py").write_text("def utility(): pass\n")
        result = discover_route_overrides(routes_dir)
        assert result == []

    def test_ignores_underscore_files(self, tmp_path: Path) -> None:
        from dazzle_back.runtime.route_overrides import discover_route_overrides

        routes_dir = tmp_path / "routes"
        routes_dir.mkdir()
        (routes_dir / "__init__.py").write_text(
            "# dazzle:route-override GET /test\nasync def handler(): return {}\n"
        )
        result = discover_route_overrides(routes_dir)
        assert result == []

    def test_warns_on_missing_handler(self, tmp_path: Path) -> None:
        from dazzle_back.runtime.route_overrides import discover_route_overrides

        routes_dir = tmp_path / "routes"
        routes_dir.mkdir()
        (routes_dir / "no_handler.py").write_text(
            "# dazzle:route-override GET /test\ndef not_handler(): pass\n"
        )
        result = discover_route_overrides(routes_dir)
        assert result == []

    def test_nonexistent_dir_returns_empty(self) -> None:
        from dazzle_back.runtime.route_overrides import discover_route_overrides

        result = discover_route_overrides(Path("/nonexistent"))
        assert result == []

    def test_multiple_overrides(self, tmp_path: Path) -> None:
        from dazzle_back.runtime.route_overrides import discover_route_overrides

        routes_dir = tmp_path / "routes"
        routes_dir.mkdir()
        (routes_dir / "a.py").write_text(
            "# dazzle:route-override GET /a\nasync def handler(): return {}\n"
        )
        (routes_dir / "b.py").write_text(
            "# dazzle:route-override POST /b\nasync def handler(): return {}\n"
        )
        result = discover_route_overrides(routes_dir)
        assert len(result) == 2


class TestBuildOverrideRouter:
    """build_override_router() creates a FastAPI router from overrides."""

    def test_returns_none_for_empty_dir(self, tmp_path: Path) -> None:
        from dazzle_back.runtime.route_overrides import build_override_router

        routes_dir = tmp_path / "routes"
        routes_dir.mkdir()
        result = build_override_router(routes_dir)
        assert result is None

    def test_builds_router_with_routes(self, tmp_path: Path) -> None:
        from dazzle_back.runtime.route_overrides import build_override_router

        routes_dir = tmp_path / "routes"
        routes_dir.mkdir()
        (routes_dir / "custom.py").write_text(
            "# dazzle:route-override GET /custom\n"
            "async def handler():\n"
            "    return {'custom': True}\n"
        )
        router = build_override_router(routes_dir)
        assert router is not None
        # Router should have one route registered
        assert len(router.routes) == 1

    def test_supports_all_http_methods(self, tmp_path: Path) -> None:
        from dazzle_back.runtime.route_overrides import build_override_router

        routes_dir = tmp_path / "routes"
        routes_dir.mkdir()
        for i, method in enumerate(["GET", "POST", "PUT", "PATCH", "DELETE"]):
            (routes_dir / f"route_{i}.py").write_text(
                f"# dazzle:route-override {method} /test_{i}\nasync def handler(): return {{}}\n"
            )
        router = build_override_router(routes_dir)
        assert router is not None
        assert len(router.routes) == 5

    def test_returns_none_for_nonexistent_dir(self) -> None:
        from dazzle_back.runtime.route_overrides import build_override_router

        result = build_override_router(Path("/nonexistent"))
        assert result is None
