"""#1140: framework auto-route suppression when a project override or
CRUD list already serves the same path.

Three patterns exercised:

1. Workspace auto-handler is suppressed when a project override is
   already mounted at ``/app/workspaces/<name>``.
2. Plural redirect is suppressed when the CRUD list endpoint already
   serves the plural path (e.g. AssessmentEvent → /assessmentevents).
3. Without ``claimed_paths``, the framework registers both as before
   — so the new arg is the opt-in, not a behaviour change.
"""

from __future__ import annotations

from typing import Any

import pytest

pytest.importorskip("fastapi")

from dazzle.back.runtime.page_routes import create_page_routes  # noqa: E402
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


def _appspec_with_workspace_and_entity() -> AppSpec:
    """Two-route fixture: one workspace + one entity with a
    plural-canonical route shape (``AssessmentEvent`` → ``/assessmentevents``).
    """
    entity = EntitySpec(
        name="AssessmentEvent",
        title="Assessment Event",
        fields=[
            FieldSpec(
                name="id",
                type=FieldType(kind=FieldTypeKind.UUID),
                modifiers=[FieldModifier.PK],
            ),
        ],
    )
    surface = SurfaceSpec(
        name="event_list",
        title="Events",
        entity_ref="AssessmentEvent",
        mode=SurfaceMode.LIST,
        sections=[
            SurfaceSection(
                name="main",
                title="Main",
                elements=[SurfaceElement(field_name="id", label="ID")],
            )
        ],
    )
    return AppSpec(
        name="test_app",
        title="Test",
        domain=DomainSpec(entities=[entity]),
        surfaces=[surface],
        workspaces=[WorkspaceSpec(name="teacher_workspace", title="Teacher")],
    )


def _route_paths(router: Any) -> set[tuple[str, str]]:
    """Return the (method, path) pairs registered on a router."""
    out: set[tuple[str, str]] = set()
    for route in router.routes:
        methods = getattr(route, "methods", None)
        path = getattr(route, "path", None)
        if not methods or not path:
            continue
        for method in methods:
            out.add((method, path))
    return out


# ---------------------------------------------------------------------------
# Pattern 1 — workspace override suppression
# ---------------------------------------------------------------------------


def test_workspace_handler_registered_when_no_override() -> None:
    """Sanity: without claimed_paths the auto-route is registered as
    before. Establishes the baseline the next test contrasts."""
    appspec = _appspec_with_workspace_and_entity()
    router = create_page_routes(appspec, app_prefix="/app")
    assert ("GET", "/workspaces/teacher_workspace") in _route_paths(router)


def test_workspace_handler_skipped_when_override_claimed() -> None:
    """When the project's override is already mounted at the same
    path, the framework auto-handler is dead weight — skip it."""
    appspec = _appspec_with_workspace_and_entity()
    router = create_page_routes(
        appspec,
        app_prefix="/app",
        claimed_paths={("GET", "/workspaces/teacher_workspace")},
    )
    assert ("GET", "/workspaces/teacher_workspace") not in _route_paths(router)


# ---------------------------------------------------------------------------
# Pattern 2 — plural-redirect collision suppression
# ---------------------------------------------------------------------------


def test_plural_redirect_skipped_when_crud_list_claims_plural_path() -> None:
    """AssessmentEvent's canonical CRUD path IS the plural
    (``/assessmentevents``). The plural redirect would register on
    top of the list endpoint — claimed_paths suppresses it."""
    appspec = _appspec_with_workspace_and_entity()
    router = create_page_routes(
        appspec,
        app_prefix="/app",
        claimed_paths={("GET", "/assessmentevents")},
    )
    paths = _route_paths(router)
    # Surface page is at /assessmentevent (singular slug); redirect
    # would have been at /assessmentevents but is now suppressed.
    plural_get = ("GET", "/assessmentevents")
    assert plural_get not in paths


def test_plural_redirect_registered_when_path_free() -> None:
    """Without a claim, the redirect registers as before — the gate
    is opt-in, not a behaviour change for projects that don't mount
    a CRUD-conflicting plural canonical."""
    appspec = _appspec_with_workspace_and_entity()
    router = create_page_routes(appspec, app_prefix="/app")
    paths = _route_paths(router)
    # The plural redirect lands at /assessmentevents (relative to the
    # /app prefix) when no CRUD list claims it.
    assert ("GET", "/assessmentevents") in paths
