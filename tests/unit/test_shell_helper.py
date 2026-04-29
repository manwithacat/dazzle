"""Tests for #951 — `render_in_app_shell` public helper.

Pins:
- `ShellState` dataclass + defaults
- `build_shell_state()` extracts nav from an AppSpec
- `register_shell_state()` attaches to `app.state`
- `get_shell_state()` returns the registered state, or an empty
  default when nothing is registered (so the helper still works
  in unit-test contexts)
- `render_in_app_shell()` returns a TemplateResponse that the
  app shell can extend
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest


def _make_appspec(workspaces: list[Any] | None = None, title: str = "Test App"):
    """Minimal AppSpec stand-in for unit testing."""
    spec = MagicMock()
    spec.title = title
    spec.name = "test_app"
    spec.workspaces = workspaces or []
    spec.personas = []
    return spec


def _make_workspace(name: str, title: str = ""):
    ws = MagicMock()
    ws.name = name
    ws.title = title or ""
    ws.access = None
    return ws


class TestShellState:
    def test_default_app_name(self) -> None:
        from dazzle_back.runtime.shell import ShellState

        s = ShellState()
        assert s.app_name == "Dazzle"

    def test_default_nav_is_empty(self) -> None:
        from dazzle_back.runtime.shell import ShellState

        s = ShellState()
        assert s.nav_items == []
        assert s.nav_groups == []
        assert s.nav_by_persona == {}

    def test_explicit_fields_round_trip(self) -> None:
        from dazzle_back.runtime.shell import ShellState

        nav = [{"label": "Home", "route": "/app"}]
        s = ShellState(app_name="My App", nav_items=nav, app_prefix="/app")
        assert s.app_name == "My App"
        assert s.nav_items == nav
        assert s.app_prefix == "/app"


class TestBuildShellState:
    def test_extracts_app_name_from_title(self) -> None:
        from dazzle_back.runtime.shell import build_shell_state

        spec = _make_appspec(title="My Cool App")
        s = build_shell_state(spec)
        assert s.app_name == "My Cool App"

    def test_falls_back_to_name_when_no_title(self) -> None:
        from dazzle_back.runtime.shell import build_shell_state

        spec = _make_appspec()
        spec.title = ""
        spec.name = "my_app"
        s = build_shell_state(spec)
        assert s.app_name == "My App"

    def test_nav_items_built_from_workspaces(self) -> None:
        from dazzle_back.runtime.shell import build_shell_state

        spec = _make_appspec(
            workspaces=[
                _make_workspace("teacher_workspace", "Teacher Workspace"),
                _make_workspace("admin_workspace"),
            ]
        )
        s = build_shell_state(spec)
        labels = [item["label"] for item in s.nav_items]
        routes = [item["route"] for item in s.nav_items]
        assert labels == ["Teacher Workspace", "Admin Workspace"]
        assert routes == [
            "/app/workspaces/teacher_workspace",
            "/app/workspaces/admin_workspace",
        ]

    def test_app_prefix_is_threaded_into_routes(self) -> None:
        from dazzle_back.runtime.shell import build_shell_state

        spec = _make_appspec(workspaces=[_make_workspace("ws1")])
        s = build_shell_state(spec, app_prefix="/portal")
        assert s.nav_items[0]["route"] == "/portal/workspaces/ws1"

    def test_get_auth_context_threaded_through(self) -> None:
        from dazzle_back.runtime.shell import build_shell_state

        sentinel: Any = object()
        spec = _make_appspec()
        s = build_shell_state(spec, get_auth_context=sentinel)
        assert s.get_auth_context is sentinel


class TestRegisterAndGetShellState:
    def test_register_attaches_to_app_state(self) -> None:
        from dazzle_back.runtime.shell import (
            ShellState,
            register_shell_state,
        )

        app = MagicMock()
        app.state = MagicMock()
        state = ShellState(app_name="X")
        register_shell_state(app, state)
        assert app.state.shell_state is state

    def test_get_shell_state_returns_registered(self) -> None:
        from dazzle_back.runtime.shell import (
            ShellState,
            get_shell_state,
            register_shell_state,
        )

        app = MagicMock()
        app.state = MagicMock(spec=[])  # no attrs by default
        state = ShellState(app_name="Registered")
        register_shell_state(app, state)

        request = MagicMock()
        request.app = app
        result = get_shell_state(request)
        assert result is state

    def test_get_shell_state_returns_empty_default_when_unregistered(
        self,
    ) -> None:
        """When nothing is registered (e.g. a bare FastAPI app in a
        unit test), the helper should still return a usable empty
        `ShellState` rather than raising."""
        from dazzle_back.runtime.shell import ShellState, get_shell_state

        request = MagicMock()
        request.app = MagicMock()
        # app.state has no shell_state attribute
        request.app.state = MagicMock(spec=[])

        result = get_shell_state(request)
        assert isinstance(result, ShellState)
        assert result.app_name == "Dazzle"
        assert result.nav_items == []


class TestRenderInAppShell:
    @pytest.fixture
    def request_with_state(self) -> Any:
        """Build a minimal request with a registered shell state."""
        from dazzle_back.runtime.shell import (
            ShellState,
            register_shell_state,
        )

        request = MagicMock()
        request.url.path = "/test/path"
        app = MagicMock()
        app.state = MagicMock(spec=[])
        register_shell_state(
            app,
            ShellState(
                app_name="Render Test",
                nav_items=[{"label": "Home", "route": "/app"}],
            ),
        )
        request.app = app
        return request

    def test_returns_a_response(self, request_with_state, tmp_path) -> None:
        """The helper returns a Starlette Response (TemplateResponse).
        We render against a tiny project-side template that doesn't
        actually extend app_shell (to keep the test independent of
        the full shell chrome)."""
        # Inject a stub template into the env's loader chain. Using
        # a DictLoader merged via ChoiceLoader is the cleanest way.
        from jinja2 import ChoiceLoader, DictLoader

        from dazzle_ui.runtime.template_renderer import get_jinja_env

        env = get_jinja_env()
        original_loader = env.loader
        env.loader = ChoiceLoader(
            [
                DictLoader(
                    {
                        "_test_shell_render.html": (
                            "<title>{{ page_title }}</title>"
                            "<nav>{% for item in nav_items %}"
                            '<a href="{{ item.route }}">{{ item.label }}</a>'
                            "{% endfor %}</nav>"
                            "<main>{{ purpose_msg | default('') }}</main>"
                        )
                    }
                ),
                original_loader,
            ]
        )
        try:
            from dazzle_back.runtime.shell import render_in_app_shell

            response = render_in_app_shell(
                request_with_state,
                template="_test_shell_render.html",
                title="Hello",
                context={"purpose_msg": "Welcome back"},
            )
            assert response.status_code == 200
            body = response.body.decode()
            assert "<title>Hello</title>" in body
            assert '<a href="/app">Home</a>' in body
            assert "<main>Welcome back</main>" in body
        finally:
            env.loader = original_loader

    def test_active_nav_route_falls_back_to_request_url(self, request_with_state) -> None:
        """When `active_nav_route` is unset, the helper uses
        `request.url.path` so nav highlighting works without the
        project handler having to know which sidebar entry maps to
        it."""
        from jinja2 import ChoiceLoader, DictLoader

        from dazzle_back.runtime.shell import render_in_app_shell
        from dazzle_ui.runtime.template_renderer import get_jinja_env

        env = get_jinja_env()
        original = env.loader
        env.loader = ChoiceLoader(
            [
                DictLoader({"_test_route.html": "current={{ current_route }}"}),
                original,
            ]
        )
        try:
            response = render_in_app_shell(request_with_state, template="_test_route.html")
            assert "current=/test/path" in response.body.decode()
        finally:
            env.loader = original

    def test_explicit_active_nav_route_overrides_request(self, request_with_state) -> None:
        from jinja2 import ChoiceLoader, DictLoader

        from dazzle_back.runtime.shell import render_in_app_shell
        from dazzle_ui.runtime.template_renderer import get_jinja_env

        env = get_jinja_env()
        original = env.loader
        env.loader = ChoiceLoader(
            [
                DictLoader({"_test_route.html": "current={{ current_route }}"}),
                original,
            ]
        )
        try:
            response = render_in_app_shell(
                request_with_state,
                template="_test_route.html",
                active_nav_route="/app/workspaces/foo",
            )
            assert "current=/app/workspaces/foo" in response.body.decode()
        finally:
            env.loader = original
