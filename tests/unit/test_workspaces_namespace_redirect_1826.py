"""Cycle 1826 — bare ``/app/workspaces`` is a path namespace, not a page.

Smoke crawl auto_seed: breadcrumb parent link → HTTP 404 on Workspaces.
Framework registers GET ``/workspaces`` as the same persona redirect as
app root so agents / typed URLs land on a real workspace.
"""

from __future__ import annotations

from typing import Any

import pytest

pytest.importorskip("fastapi")

from dazzle.core.ir import (  # noqa: E402
    AppSpec,
    DomainSpec,
    EntitySpec,
    FieldModifier,
    FieldSpec,
    FieldType,
    FieldTypeKind,
    WorkspaceSpec,
)
from dazzle.http.runtime.page_routes import create_page_routes  # noqa: E402


def _appspec_with_workspace() -> AppSpec:
    entity = EntitySpec(
        name="Task",
        title="Task",
        fields=[
            FieldSpec(
                name="id",
                type=FieldType(kind=FieldTypeKind.UUID),
                modifiers=[FieldModifier.PK],
            ),
        ],
    )
    return AppSpec(
        name="test_app",
        title="Test",
        domain=DomainSpec(entities=[entity]),
        surfaces=[],
        workspaces=[
            WorkspaceSpec(name="admin_dashboard", title="Admin Dashboard"),
            WorkspaceSpec(name="team_overview", title="Team Overview"),
        ],
    )


def _route_paths(router: Any) -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for route in router.routes:
        methods = getattr(route, "methods", None)
        path = getattr(route, "path", None)
        if not methods or not path:
            continue
        for method in methods:
            out.add((method, path))
    return out


def test_bare_workspaces_namespace_redirect_registered() -> None:
    """GET /workspaces is registered when workspaces exist and path free."""
    router = create_page_routes(_appspec_with_workspace(), app_prefix="/app")
    paths = _route_paths(router)
    assert ("GET", "/workspaces") in paths
    assert ("GET", "/workspaces/admin_dashboard") in paths
    assert ("GET", "/") in paths  # root redirect when no page at /


def test_bare_workspaces_skipped_when_claimed() -> None:
    """Do not double-register when an override already claimed /workspaces."""
    router = create_page_routes(
        _appspec_with_workspace(),
        app_prefix="/app",
        claimed_paths={("GET", "/workspaces")},
    )
    # named workspaces still auto-register; bare namespace does not
    paths = _route_paths(router)
    assert ("GET", "/workspaces") not in paths
    assert ("GET", "/workspaces/admin_dashboard") in paths


def test_no_workspaces_no_namespace_redirect() -> None:
    """Apps without workspaces do not get a bare /workspaces route."""
    entity = EntitySpec(
        name="Task",
        title="Task",
        fields=[
            FieldSpec(
                name="id",
                type=FieldType(kind=FieldTypeKind.UUID),
                modifiers=[FieldModifier.PK],
            ),
        ],
    )
    appspec = AppSpec(
        name="list_only",
        title="List Only",
        domain=DomainSpec(entities=[entity]),
        surfaces=[],
        workspaces=[],
    )
    paths = _route_paths(create_page_routes(appspec, app_prefix="/app"))
    assert ("GET", "/workspaces") not in paths
