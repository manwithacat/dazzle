"""Tests for assemble_post_build_routes() — unified route assembly.

Uses AST inspection (like test_url_consistency.py) and mock-based integration
tests to verify the shared route assembly function.
"""

from __future__ import annotations

import ast
import inspect
from typing import Any
from unittest.mock import MagicMock

import pytest

from dazzle.core.ir.process import ScheduleSpec
from dazzle_back.runtime.app_factory import assemble_post_build_routes

pytest.importorskip("fastapi")

from fastapi import FastAPI  # noqa: E402

from dazzle.core.ir import (  # noqa: E402
    AppSpec,
    DomainSpec,
    EntitySpec,
    FieldModifier,
    FieldSpec,
    FieldType,
    FieldTypeKind,
    SurfaceElement,
    SurfaceMode,
    SurfaceSection,
    SurfaceSpec,
    WorkspaceSpec,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _entity() -> EntitySpec:
    return EntitySpec(
        name="Task",
        title="Task",
        fields=[
            FieldSpec(
                name="id", type=FieldType(kind=FieldTypeKind.UUID), modifiers=[FieldModifier.PK]
            ),
            FieldSpec(
                name="title",
                type=FieldType(kind=FieldTypeKind.STR, max_length=200),
                modifiers=[FieldModifier.REQUIRED],
            ),
        ],
    )


def _appspec(**overrides: Any) -> AppSpec:
    defaults: dict[str, Any] = {
        "name": "test_app",
        "title": "Test App",
        "domain": DomainSpec(entities=[_entity()]),
        "surfaces": [
            SurfaceSpec(
                name="task_list",
                title="Tasks",
                entity_ref="Task",
                mode=SurfaceMode.LIST,
                sections=[
                    SurfaceSection(
                        name="main",
                        title="Main",
                        elements=[SurfaceElement(field_name="title", label="Title")],
                    )
                ],
            )
        ],
        "workspaces": [WorkspaceSpec(name="main", title="Main")],
    }
    defaults.update(overrides)
    return AppSpec(**defaults)


def _mock_builder() -> MagicMock:
    builder = MagicMock()
    builder.auth_middleware = None
    builder.auth_store = None
    builder.services = {}
    builder.process_adapter = None
    return builder


def _find_calls(source: str, func_name: str) -> list[ast.Call]:
    """Find all calls to func_name in source AST."""
    tree = ast.parse(source)
    calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = ""
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            if name == func_name:
                calls.append(node)
    return calls


# ---------------------------------------------------------------------------
# AST-based structural tests
# ---------------------------------------------------------------------------


class TestAssembleRoutesStructure:
    """Verify assemble_post_build_routes has correct structure via AST."""

    _source = inspect.getsource(assemble_post_build_routes)

    def test_passes_app_prefix_to_create_page_routes(self) -> None:
        calls = _find_calls(self._source, "create_page_routes")
        assert calls, "create_page_routes call not found"
        kw_names = [kw.arg for kw in calls[0].keywords]
        assert "app_prefix" in kw_names

    def test_passes_app_prefix_to_create_experience_routes(self) -> None:
        calls = _find_calls(self._source, "create_experience_routes")
        assert calls, "create_experience_routes call not found"
        kw_names = [kw.arg for kw in calls[0].keywords]
        assert "app_prefix" in kw_names

    def test_passes_project_root_to_auth_page_routes(self) -> None:
        calls = _find_calls(self._source, "create_auth_page_routes")
        assert calls, "create_auth_page_routes call not found"
        kw_names = [kw.arg for kw in calls[0].keywords]
        assert "project_root" in kw_names

    def test_calls_validate_routes(self) -> None:
        calls = _find_calls(self._source, "validate_routes")
        assert calls, "validate_routes call not found"

    def test_calls_register_site_404_handler(self) -> None:
        calls = _find_calls(self._source, "register_site_404_handler")
        assert calls, "register_site_404_handler call not found"

    def test_calls_sync_schedules_from_appspec(self) -> None:
        calls = _find_calls(self._source, "sync_schedules_from_appspec")
        assert calls, "sync_schedules_from_appspec call not found"


# ---------------------------------------------------------------------------
# Behavioral tests
# ---------------------------------------------------------------------------


class TestAssembleRoutesBehavior:
    def test_mounts_bundled_css_route_when_css_non_empty(self) -> None:
        app = FastAPI()
        assemble_post_build_routes(
            app, _appspec(), _mock_builder(), bundled_css="body { color: red; }"
        )
        route_paths = [r.path for r in app.routes if hasattr(r, "path")]
        assert "/static/css/dazzle-bundle.css" in route_paths

    def test_no_bundled_css_route_when_empty(self) -> None:
        app = FastAPI()
        assemble_post_build_routes(app, _appspec(), _mock_builder(), bundled_css="")
        route_paths = [r.path for r in app.routes if hasattr(r, "path")]
        assert "/static/css/dazzle-bundle.css" not in route_paths

    def test_mounts_app_pages_at_app_prefix(self) -> None:
        app = FastAPI()
        assemble_post_build_routes(app, _appspec(), _mock_builder())
        route_paths = [r.path for r in app.routes if hasattr(r, "path")]
        app_routes = [p for p in route_paths if p.startswith("/app/")]
        assert app_routes, "No /app/* routes found"

    def test_syncs_schedules_to_process_adapter(self) -> None:
        builder = _mock_builder()
        adapter = MagicMock()
        adapter.sync_schedules_from_appspec.return_value = 2
        builder.process_adapter = adapter
        appspec = _appspec(schedules=[ScheduleSpec(name="daily", cron="0 8 * * *")])
        app = FastAPI()
        assemble_post_build_routes(app, appspec, builder)
        adapter.sync_schedules_from_appspec.assert_called_once_with(appspec)

    def test_does_not_sync_schedules_without_adapter(self) -> None:
        builder = _mock_builder()
        builder.process_adapter = None
        appspec = _appspec(schedules=[ScheduleSpec(name="daily", cron="0 8 * * *")])
        app = FastAPI()
        # Should not raise
        assemble_post_build_routes(app, appspec, builder)
