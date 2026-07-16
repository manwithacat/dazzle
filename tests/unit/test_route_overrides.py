"""Tests for the route override system (v0.29.0).

Covers:
- Route override discovery from declaration headers
- Handler loading from Python files
- Router building from discovered overrides
"""

from pathlib import Path

import pytest


class TestDiscoverRouteOverrides:
    """discover_route_overrides() parses declaration headers."""

    def test_discovers_get_override(self, tmp_path: Path) -> None:
        from dazzle.http.runtime.route_overrides import discover_route_overrides

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
        from dazzle.http.runtime.route_overrides import discover_route_overrides

        routes_dir = tmp_path / "routes"
        routes_dir.mkdir()
        (routes_dir / "custom_submit.py").write_text(
            "# dazzle:route-override POST /_dazzle/tasks\n"
            "async def handler(request):\n"
            "    return {'submitted': True}\n"
        )
        result = discover_route_overrides(routes_dir)
        assert len(result) == 1
        assert result[0].method == "POST"
        assert result[0].path == "/_dazzle/tasks"

    def test_case_insensitive_method(self, tmp_path: Path) -> None:
        from dazzle.http.runtime.route_overrides import discover_route_overrides

        routes_dir = tmp_path / "routes"
        routes_dir.mkdir()
        (routes_dir / "test.py").write_text(
            "# dazzle:route-override get /test\nasync def handler(): return {}\n"
        )
        result = discover_route_overrides(routes_dir)
        assert len(result) == 1
        assert result[0].method == "GET"

    @pytest.mark.parametrize(
        ("setup", "expected_len"),
        [
            (
                lambda d: [(d / "helper.py", "def utility(): pass\n")],
                0,
            ),
            (
                lambda d: [
                    (
                        d / "__init__.py",
                        "# dazzle:route-override GET /test\nasync def handler(): return {}\n",
                    )
                ],
                0,
            ),
            (
                lambda d: [
                    (
                        d / "no_handler.py",
                        "# dazzle:route-override GET /test\ndef not_handler(): pass\n",
                    )
                ],
                0,
            ),
            (None, 0),  # nonexistent dir
            (
                lambda d: [
                    (
                        d / "a.py",
                        "# dazzle:route-override GET /a\nasync def handler(): return {}\n",
                    ),
                    (
                        d / "b.py",
                        "# dazzle:route-override POST /b\nasync def handler(): return {}\n",
                    ),
                ],
                2,
            ),
        ],
        ids=[
            "test_ignores_files_without_declaration",
            "test_ignores_underscore_files",
            "test_warns_on_missing_handler",
            "test_nonexistent_dir_returns_empty",
            "test_multiple_overrides",
        ],
    )
    def test_discover_count(self, tmp_path: Path, setup, expected_len) -> None:
        from dazzle.http.runtime.route_overrides import discover_route_overrides

        if setup is None:
            assert discover_route_overrides(Path("/nonexistent")) == []
            return
        routes_dir = tmp_path / "routes"
        routes_dir.mkdir()
        for path, content in setup(routes_dir):
            path.write_text(content)
        result = discover_route_overrides(routes_dir)
        assert len(result) == expected_len


class TestBuildOverrideRouter:
    """build_override_router() creates a FastAPI router from overrides."""

    def test_returns_none_for_empty_dir(self, tmp_path: Path) -> None:
        from dazzle.http.runtime.route_overrides import build_override_router

        routes_dir = tmp_path / "routes"
        routes_dir.mkdir()
        result = build_override_router(routes_dir)
        assert result is None

    def test_builds_router_with_routes(self, tmp_path: Path) -> None:
        from dazzle.http.runtime.route_overrides import build_override_router

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
        from dazzle.http.runtime.route_overrides import build_override_router

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
        from dazzle.http.runtime.route_overrides import build_override_router

        result = build_override_router(Path("/nonexistent"))
        assert result is None


class TestOverrideRegistrationIsolation1601:
    """#1601 — one bad override must not silently kill every host route."""

    @staticmethod
    def _write_good(routes_dir: Path, name: str, path: str) -> None:
        (routes_dir / f"{name}.py").write_text(
            f"# dazzle:route-override GET {path}\n"
            "from fastapi.responses import HTMLResponse\n"
            "async def handler():\n"
            "    return HTMLResponse('<p>ok</p>')\n"
        )

    @staticmethod
    def _write_union_return(routes_dir: Path) -> None:
        # FastAPI rejects Union response annotations at registration time
        # (CyFuture: HTMLResponse | RedirectResponse → all host routes gone).
        (routes_dir / "bad_union.py").write_text(
            "# dazzle:route-override GET /ch/import\n"
            "from fastapi.responses import HTMLResponse, RedirectResponse\n"
            "async def handler() -> HTMLResponse | RedirectResponse:\n"
            "    return HTMLResponse('<p>bad</p>')\n"
        )

    def test_hard_mode_raises_and_names_source(self, tmp_path: Path, monkeypatch) -> None:
        from dazzle.http.runtime.route_overrides import (
            RouteOverrideRegistrationError,
            build_override_router,
        )

        monkeypatch.delenv("DAZZLE_ROUTE_OVERRIDE_SOFT", raising=False)
        routes_dir = tmp_path / "routes"
        routes_dir.mkdir()
        self._write_good(routes_dir, "good", "/gdpr/export")
        self._write_union_return(routes_dir)

        with pytest.raises(RouteOverrideRegistrationError) as ei:
            build_override_router(routes_dir)
        err = str(ei.value)
        assert "bad_union.py" in err or "/ch/import" in err
        assert len(ei.value.failures) >= 1

    def test_soft_mode_keeps_good_routes(self, tmp_path: Path, monkeypatch) -> None:
        from dazzle.http.runtime.route_overrides import build_override_router

        monkeypatch.setenv("DAZZLE_ROUTE_OVERRIDE_SOFT", "1")
        routes_dir = tmp_path / "routes"
        routes_dir.mkdir()
        self._write_good(routes_dir, "good", "/gdpr/export")
        self._write_union_return(routes_dir)

        router = build_override_router(routes_dir)
        assert router is not None
        paths = [getattr(r, "path", None) for r in router.routes]
        assert "/gdpr/export" in paths
        assert "/ch/import" not in paths

    def test_all_good_still_registers(self, tmp_path: Path, monkeypatch) -> None:
        from dazzle.http.runtime.route_overrides import build_override_router

        monkeypatch.delenv("DAZZLE_ROUTE_OVERRIDE_SOFT", raising=False)
        routes_dir = tmp_path / "routes"
        routes_dir.mkdir()
        self._write_good(routes_dir, "a", "/ch/import")
        self._write_good(routes_dir, "b", "/gdpr/export")
        router = build_override_router(routes_dir)
        assert router is not None
        assert len(router.routes) == 2


class TestLoadExtensionRouters:
    """load_extension_routers() imports APIRouters declared in dazzle.toml (#786)."""

    def test_empty_spec_list_returns_empty(self, tmp_path: Path) -> None:
        from dazzle.http.runtime.route_overrides import load_extension_routers

        assert load_extension_routers(tmp_path, []) == []

    def test_loads_valid_router(self, tmp_path: Path) -> None:
        from dazzle.http.runtime.route_overrides import load_extension_routers

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
        from dazzle.http.runtime.route_overrides import load_extension_routers

        # No colon separator
        assert load_extension_routers(tmp_path, ["app.routes.router"]) == []
        # Empty attr
        assert load_extension_routers(tmp_path, ["app.routes:"]) == []
        # Empty module
        assert load_extension_routers(tmp_path, [":router"]) == []

    def test_rejects_path_traversal_in_module(self, tmp_path: Path) -> None:
        from dazzle.http.runtime.route_overrides import load_extension_routers

        # Slashes, dashes, semicolons — all rejected by the whitelist regex.
        specs = [
            "../escape:router",
            "app/routes:router",
            "app.routes;print('x'):router",
            "app-routes:router",
        ]
        assert load_extension_routers(tmp_path, specs) == []

    def test_skips_missing_module(self, tmp_path: Path) -> None:
        from dazzle.http.runtime.route_overrides import load_extension_routers

        assert load_extension_routers(tmp_path, ["nonexistent_pkg_xyz.mod:router"]) == []

    @pytest.mark.parametrize(
        ("pkg_name", "routes_content"),
        [
            (
                "ext_pkg_missing_attr",
                "from fastapi import APIRouter\nother = APIRouter()\n",
            ),
            (
                "ext_pkg_wrong_type",
                "router = 'not an APIRouter'\n",
            ),
        ],
        ids=[
            "test_skips_missing_attribute",
            "test_skips_non_router_attribute",
        ],
    )
    def test_skips_bad_attribute(self, tmp_path: Path, pkg_name: str, routes_content: str) -> None:
        from dazzle.http.runtime.route_overrides import load_extension_routers

        pkg = tmp_path / pkg_name
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "routes.py").write_text(routes_content)

        routers = load_extension_routers(tmp_path, [f"{pkg_name}.routes:router"])
        assert routers == []

    def test_loads_multiple_routers(self, tmp_path: Path) -> None:
        from dazzle.http.runtime.route_overrides import load_extension_routers

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
        from dazzle.http.runtime.route_overrides import load_extension_routers

        pkg = tmp_path / "ext_mixed"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "good.py").write_text("from fastapi import APIRouter\nrouter = APIRouter()\n")

        specs = ["does_not_exist_xyz:router", "ext_mixed.good:router"]
        routers = load_extension_routers(tmp_path, specs)
        assert len(routers) == 1
