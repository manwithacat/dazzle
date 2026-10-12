"""Tests for #979 — `action: surface_name` resolves to entity slug, not slugified surface name.

Background: pre-#979, surface-named actions were slugified
(`/app/cohort-analysis-list`) — but entity routes are registered at the
entity slug (e.g. `/app/cohortanalysis` for entity `CohortAnalysis`), so
every confirm_action_panel revoke/primary/secondary action that referenced
a surface by name 404'd.

Fix: `_confirm_action_to_url` takes an optional `app_spec` and looks up
the named surface to find its `entity_ref`, returning the entity path.
"""

from types import SimpleNamespace

import pytest

from dazzle.page.runtime.action_urls import (
    _confirm_action_to_url,
    fill_row_id_in_url,
)

pytestmark = pytest.mark.gate


def _stub_app_spec(surfaces):
    """Build a minimal app_spec stub with .surfaces."""
    return SimpleNamespace(surfaces=surfaces)


def _stub_surface(name: str, entity_ref: str = ""):
    return SimpleNamespace(name=name, entity_ref=entity_ref)


def test_literal_url_passes_through_unchanged() -> None:
    """Form 1: action starting with `/` — used as-is."""
    assert (
        _confirm_action_to_url("/app/manuscript?status=flagged") == "/app/manuscript?status=flagged"
    )
    assert _confirm_action_to_url("/login") == "/login"


def test_empty_action_returns_empty_string() -> None:
    """Empty input → empty string (informational card)."""
    assert _confirm_action_to_url("") == ""
    assert _confirm_action_to_url("", app_spec=None) == ""


def test_confirm_action_edit_view_keep_id_template() -> None:
    """confirm_action_panel has a source row — EDIT/VIEW keep ``{id}`` (cycle 1402)."""
    from dazzle.core import ir

    spec = _stub_app_spec(
        [
            SimpleNamespace(
                name="system_edit",
                entity_ref="System",
                mode=ir.SurfaceMode.EDIT,
            ),
            SimpleNamespace(
                name="system_detail",
                entity_ref="System",
                mode=ir.SurfaceMode.VIEW,
            ),
            SimpleNamespace(
                name="system_create",
                entity_ref="System",
                mode=ir.SurfaceMode.CREATE,
            ),
        ]
    )
    assert _confirm_action_to_url("system_edit", spec) == "/app/system/{id}/edit"
    assert _confirm_action_to_url("system_detail", spec) == "/app/system/{id}"
    assert _confirm_action_to_url("system_create", spec) == "/app/system/create"
    # action_grid path unchanged


def test_confirm_action_unknown_falls_back_to_source_edit() -> None:
    """ops_dashboard ``integration_enable`` had no surface → dead slugify path.

    With ``source_entity``, fall back to that entity's edit template so the
    consent CTA lands on a real form after ``{id}`` fill (cycle 1402).
    """
    spec = _stub_app_spec([])
    assert (
        _confirm_action_to_url("integration_enable", spec, source_entity="Integration")
        == "/app/integration/{id}/edit"
    )
    assert (
        _confirm_action_to_url(
            "integration_revoke?reason=off",
            spec,
            source_entity="Integration",
        )
        == "/app/integration/{id}/edit?reason=off"
    )


def test_fill_row_id_in_url() -> None:
    rid = "b2000000-0000-4000-8000-000000000099"
    assert fill_row_id_in_url("/app/integration/{id}/edit", rid) == f"/app/integration/{rid}/edit"
    assert fill_row_id_in_url("/app/system/create", rid) == "/app/system/create"
    # Missing row → omit CTA rather than leave a literal ``{id}`` path
    assert fill_row_id_in_url("/app/integration/{id}/edit", "") == ""


def test_region_row_drill_url_honors_edit_and_view_mode() -> None:
    """Workspace ``action: task_edit`` must drill to edit, not detail (cycle 1403).

    Fleet regions (simple_task, ops_dashboard, contact_manager) author
    EDIT surfaces as row actions; pre-fix always used VIEW detail.
    """
    from dazzle.core import ir
    from dazzle.page.runtime.action_urls import region_row_drill_url

    spec = _stub_app_spec(
        [
            SimpleNamespace(
                name="task_edit",
                entity_ref="Task",
                mode=ir.SurfaceMode.EDIT,
            ),
            SimpleNamespace(
                name="task_detail",
                entity_ref="Task",
                mode=ir.SurfaceMode.VIEW,
            ),
            SimpleNamespace(
                name="system_create",
                entity_ref="System",
                mode=ir.SurfaceMode.CREATE,
            ),
            SimpleNamespace(
                name="task_list",
                entity_ref="Task",
                mode=ir.SurfaceMode.LIST,
            ),
            # Missing mode (stub surfaces) → detail with {id}, not list
            SimpleNamespace(name="task_legacy", entity_ref="Task"),
        ]
    )
    # Workspaces on the stub for name-collision path
    spec.workspaces = [SimpleNamespace(name="ops_dashboard")]

    assert region_row_drill_url("task_edit", spec) == "/app/task/{id}/edit"
    assert region_row_drill_url("task_detail", spec) == "/app/task/{id}"
    assert region_row_drill_url("system_create", spec) == "/app/system/create"
    assert region_row_drill_url("task_list", spec) == "/app/task"
    assert region_row_drill_url("task_legacy", spec) == "/app/task/{id}"
    assert (
        region_row_drill_url("ops_dashboard", spec)
        == "/app/workspaces/ops_dashboard?context_id={id}"
    )
    assert region_row_drill_url("ghost", spec) == ""
    assert region_row_drill_url("task_edit", None) == ""
