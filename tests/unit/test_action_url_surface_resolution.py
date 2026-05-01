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

from dazzle_ui.runtime.workspace_renderer import _action_to_url


def _stub_app_spec(surfaces):
    """Build a minimal app_spec stub with .surfaces."""
    return SimpleNamespace(surfaces=surfaces)


def _stub_surface(name: str, entity_ref: str = ""):
    return SimpleNamespace(name=name, entity_ref=entity_ref)


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
    spec = _stub_app_spec(
        [
            _stub_surface("cohort_analysis_list", entity_ref="CohortAnalysis"),
            _stub_surface("manuscript_detail", entity_ref="Manuscript"),
        ]
    )
    # CohortAnalysis → cohortanalysis (lower + no underscores)
    assert _action_to_url("cohort_analysis_list", spec) == "/app/cohortanalysis"
    # Manuscript → manuscript
    assert _action_to_url("manuscript_detail", spec) == "/app/manuscript"


def test_surface_name_with_underscored_entity_ref() -> None:
    """Multi-word entity_ref slugifies via lower + underscore→hyphen."""
    spec = _stub_app_spec([_stub_surface("the_thing_list", entity_ref="My_Big_Entity")])
    assert _action_to_url("the_thing_list", spec) == "/app/my-big-entity"


def test_surface_lookup_preserves_query_string() -> None:
    """Query string survives surface lookup unchanged."""
    spec = _stub_app_spec([_stub_surface("cohort_analysis_list", entity_ref="CohortAnalysis")])
    assert (
        _action_to_url("cohort_analysis_list?status=flagged", spec)
        == "/app/cohortanalysis?status=flagged"
    )


def test_unknown_action_falls_back_to_slugify() -> None:
    """Form 3: no matching surface → legacy slugify behaviour."""
    spec = _stub_app_spec([])
    assert _action_to_url("parents_evening_create", spec) == "/app/parents-evening-create"
    # Same fallback when app_spec is None entirely.
    assert _action_to_url("parents_evening_create", None) == "/app/parents-evening-create"


def test_surface_without_entity_ref_falls_back() -> None:
    """A surface registered with no entity_ref falls back to slugify."""
    spec = _stub_app_spec([_stub_surface("orphan_surface", entity_ref="")])
    assert _action_to_url("orphan_surface", spec) == "/app/orphan-surface"


def test_empty_action_with_app_spec() -> None:
    """Empty + app_spec — still empty."""
    spec = _stub_app_spec([_stub_surface("x", entity_ref="X")])
    assert _action_to_url("", spec) == ""
