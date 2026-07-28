"""Tests for #979 — `action: surface_name` resolves to entity slug, not slugified surface name.

Background: pre-#979, `_action_to_url("cohort_analysis_list")` returned
`/app/cohort-analysis-list` — but entity list routes are registered at
`/app/{entity_name.lower().replace("_", "-")}` (e.g. `/app/cohortanalysis`
for entity `CohortAnalysis`). Result: every action_grid card and every
confirm_action_panel revoke/primary/secondary action that referenced a
surface by name 404'd.

Fix: `_action_to_url` now takes an optional `app_spec` and looks up the
named surface to find its `entity_ref`, returning the entity slug. Falls
back to the legacy slugify when no matching surface or entity exists.

The same surface-aware resolution pattern was already in use at
`workspace_renderer.py:481-499` for region-level `action:` — this fix
brings the action_grid card and confirm_action_panel paths into line.
"""

from types import SimpleNamespace
from typing import Any

import pytest

from dazzle.page.runtime.action_urls import (
    _action_to_url,
    _confirm_action_to_url,
    fill_row_id_in_url,
)

pytestmark = pytest.mark.gate


def _stub_app_spec(surfaces):
    """Build a minimal app_spec stub with .surfaces."""
    return SimpleNamespace(surfaces=surfaces)


def _stub_surface(name: str, entity_ref: str = ""):
    return SimpleNamespace(name=name, entity_ref=entity_ref)


def _spec_cohort_manuscript() -> SimpleNamespace:
    return _stub_app_spec(
        [
            _stub_surface("cohort_analysis_list", entity_ref="CohortAnalysis"),
            _stub_surface("manuscript_detail", entity_ref="Manuscript"),
        ]
    )


def _spec_underscored() -> SimpleNamespace:
    return _stub_app_spec([_stub_surface("the_thing_list", entity_ref="My_Big_Entity")])


def _spec_cohort_only() -> SimpleNamespace:
    return _stub_app_spec([_stub_surface("cohort_analysis_list", entity_ref="CohortAnalysis")])


def _spec_orphan() -> SimpleNamespace:
    return _stub_app_spec([_stub_surface("orphan_surface", entity_ref="")])


def _spec_x() -> SimpleNamespace:
    return _stub_app_spec([_stub_surface("x", entity_ref="X")])


def test_literal_url_passes_through_unchanged() -> None:
    """Form 1: action starting with `/` — used as-is."""
    assert _action_to_url("/app/manuscript?status=flagged") == "/app/manuscript?status=flagged"
    assert _action_to_url("/login") == "/login"


def test_empty_action_returns_empty_string() -> None:
    """Empty input → empty string (informational card)."""
    assert _action_to_url("") == ""
    assert _action_to_url("", app_spec=None) == ""


def test_surface_name_resolves_to_entity_slug() -> None:
    """Form 2 (#979): surface name → entity_ref slug."""
    spec = _spec_cohort_manuscript()
    # CohortAnalysis → cohortanalysis (lower + no underscores)
    assert _action_to_url("cohort_analysis_list", spec) == "/app/cohortanalysis"
    # Manuscript → manuscript
    assert _action_to_url("manuscript_detail", spec) == "/app/manuscript"


def test_create_mode_surface_resolves_to_create_path() -> None:
    """CREATE-mode surfaces must land on ``/create`` (cycle 1401).

    Pre-fix, every mode used list_path, so action_grid ``system_create``
    navigated to the list and skipped the cycle-1397 CREATE RBAC gate
    (which keys on the ``/create`` suffix).
    """
    from dazzle.core import ir

    spec = _stub_app_spec(
        [
            SimpleNamespace(
                name="system_create",
                entity_ref="System",
                mode=ir.SurfaceMode.CREATE,
            ),
            SimpleNamespace(
                name="system_list",
                entity_ref="System",
                mode=ir.SurfaceMode.LIST,
            ),
            SimpleNamespace(
                name="system_edit",
                entity_ref="System",
                mode=ir.SurfaceMode.EDIT,
            ),
        ]
    )
    assert _action_to_url("system_create", spec) == "/app/system/create"
    assert _action_to_url("system_list", spec) == "/app/system"
    # EDIT lacks a row id on dashboard CTAs → list browse (not edit template)
    assert _action_to_url("system_edit", spec) == "/app/system"
    assert _action_to_url("system_create?source=ops", spec) == "/app/system/create?source=ops"


@pytest.mark.parametrize(
    ("action", "spec_factory", "expected"),
    [
        ("the_thing_list", _spec_underscored, "/app/my-big-entity"),
        (
            "cohort_analysis_list?status=flagged",
            _spec_cohort_only,
            "/app/cohortanalysis?status=flagged",
        ),
        ("orphan_surface", _spec_orphan, "/app/orphan-surface"),
        ("", _spec_x, ""),
    ],
    ids=[
        "test_surface_name_with_underscored_entity_ref",
        "test_surface_lookup_preserves_query_string",
        "test_surface_without_entity_ref_falls_back",
        "test_empty_action_with_app_spec",
    ],
)
def test_action_to_url_with_spec(action: str, spec_factory: Any, expected: str) -> None:
    assert _action_to_url(action, spec_factory()) == expected


def test_unknown_action_falls_back_to_slugify() -> None:
    """Form 3: no matching surface → legacy slugify behaviour."""
    spec = _stub_app_spec([])
    assert _action_to_url("parents_evening_create", spec) == "/app/parents-evening-create"
    # Same fallback when app_spec is None entirely.
    assert _action_to_url("parents_evening_create", None) == "/app/parents-evening-create"


def test_confirm_action_edit_view_keep_id_template() -> None:
    """confirm_action_panel has a source row — EDIT/VIEW keep ``{id}`` (cycle 1402).

    action_grid still demotes EDIT to list (no row id on dashboard cards).
    """
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
    assert _action_to_url("system_edit", spec) == "/app/system"


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
