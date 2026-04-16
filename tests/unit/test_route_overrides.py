"""Tests for the route override system (v0.29.0).

Covers:
- Route override discovery from declaration headers
- Handler loading from Python files
- Router building from discovered overrides
"""

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


class TestLoadExtensionRouters:
    """load_extension_routers() imports APIRouters declared in dazzle.toml (#786)."""

    def test_empty_spec_list_returns_empty(self, tmp_path: Path) -> None:
        from dazzle_back.runtime.route_overrides import load_extension_routers

        assert load_extension_routers(tmp_path, []) == []

    def test_loads_valid_router(self, tmp_path: Path) -> None:
        from dazzle_back.runtime.route_overrides import load_extension_routers

        pkg = tmp_path / "ext_pkg_valid"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "routes.py").write_text(
            "from fastapi import APIRouter\n"
            "router = APIRouter()\n"
            "@router.get('/ext/ping')\n"
            "async def ping(): return {'ok': True}\n"
        )

        routers = load_extension_routers(tmp_path, ["ext_pkg_valid.routes:router"])
        assert len(routers) == 1
        assert any(r.path == "/ext/ping" for r in routers[0].routes)

    def test_skips_invalid_spec_format(self, tmp_path: Path) -> None:
        from dazzle_back.runtime.route_overrides import load_extension_routers

        # No colon separator
        assert load_extension_routers(tmp_path, ["app.routes.router"]) == []
        # Empty attr
        assert load_extension_routers(tmp_path, ["app.routes:"]) == []
        # Empty module
        assert load_extension_routers(tmp_path, [":router"]) == []

    def test_rejects_path_traversal_in_module(self, tmp_path: Path) -> None:
        from dazzle_back.runtime.route_overrides import load_extension_routers

        # Slashes, dashes, semicolons — all rejected by the whitelist regex.
        specs = [
            "../escape:router",
            "app/routes:router",
            "app.routes;print('x'):router",
            "app-routes:router",
        ]
        assert load_extension_routers(tmp_path, specs) == []

    def test_skips_missing_module(self, tmp_path: Path) -> None:
        from dazzle_back.runtime.route_overrides import load_extension_routers

        assert load_extension_routers(tmp_path, ["nonexistent_pkg_xyz.mod:router"]) == []

    def test_skips_missing_attribute(self, tmp_path: Path) -> None:
        from dazzle_back.runtime.route_overrides import load_extension_routers

        pkg = tmp_path / "ext_pkg_missing_attr"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "routes.py").write_text("from fastapi import APIRouter\nother = APIRouter()\n")

        routers = load_extension_routers(tmp_path, ["ext_pkg_missing_attr.routes:router"])
        assert routers == []

    def test_skips_non_router_attribute(self, tmp_path: Path) -> None:
        from dazzle_back.runtime.route_overrides import load_extension_routers

        pkg = tmp_path / "ext_pkg_wrong_type"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "routes.py").write_text("router = 'not an APIRouter'\n")

        routers = load_extension_routers(tmp_path, ["ext_pkg_wrong_type.routes:router"])
        assert routers == []

    def test_loads_multiple_routers(self, tmp_path: Path) -> None:
        from dazzle_back.runtime.route_overrides import load_extension_routers

        pkg = tmp_path / "ext_multi"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "a.py").write_text(
            "from fastapi import APIRouter\nrouter = APIRouter()\n"
            "@router.get('/a')\nasync def a(): return {}\n"
        )
        (pkg / "b.py").write_text(
            "from fastapi import APIRouter\nrouter = APIRouter()\n"
            "@router.get('/b')\nasync def b(): return {}\n"
        )

        routers = load_extension_routers(tmp_path, ["ext_multi.a:router", "ext_multi.b:router"])
        assert len(routers) == 2

    def test_one_broken_spec_doesnt_block_others(self, tmp_path: Path) -> None:
        from dazzle_back.runtime.route_overrides import load_extension_routers

        pkg = tmp_path / "ext_mixed"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "good.py").write_text("from fastapi import APIRouter\nrouter = APIRouter()\n")

        specs = ["does_not_exist_xyz:router", "ext_mixed.good:router"]
        routers = load_extension_routers(tmp_path, specs)
        assert len(routers) == 1
