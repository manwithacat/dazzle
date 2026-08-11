"""agent_acceptance cycle 1918 — Staff Directory open lands Person hub.

Workspace must not share the name ``person_detail`` with surface person_detail:
region ``action: person_detail`` prefers workspace → context_id desk, which was
showing company-wide employment timelines instead of the clicked person's hub.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from dazzle.core.ir.surfaces import SurfaceMode
from dazzle.page.runtime.action_urls import region_row_drill_url

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "examples/hr_records/dsl/app.dsl"


def _workspace_block(name: str) -> str:
    text = APP.read_text()
    marker = f'workspace {name} "'
    assert marker in text, f"missing workspace {name}"
    block = text.split(marker, 1)[1]
    # next workspace or EOF
    if "\nworkspace " in block:
        block = block.split("\nworkspace ", 1)[0]
    return block


def test_no_workspace_named_person_detail_shadowing_surface() -> None:
    text = APP.read_text()
    assert 'surface person_detail "Person"' in text
    assert "workspace person_detail" not in text
    assert 'workspace career_desk "' in text


def test_staff_directory_person_actions_target_person_detail() -> None:
    block = _workspace_block("staff_directory")
    for region in ("media_shelf:", "current_staff:", "recent_starters:"):
        assert region in block
    assert block.count("action: person_detail") >= 3


def test_region_action_person_detail_resolves_to_entity_hub() -> None:
    """With career_desk only, action: person_detail is the Person VIEW surface."""
    app_spec = SimpleNamespace(
        workspaces=[SimpleNamespace(name="career_desk")],
        surfaces=[
            SimpleNamespace(
                name="person_detail",
                entity_ref="Person",
                mode=SurfaceMode.VIEW,
            )
        ],
    )
    url = region_row_drill_url("person_detail", app_spec)
    assert "workspaces/person_detail" not in url
    assert "{id}" in url
    assert "person" in url.lower()
    # Collision regression: if a workspace steals the name, we get context_id desk.
    collided = SimpleNamespace(
        workspaces=[SimpleNamespace(name="person_detail")],
        surfaces=app_spec.surfaces,
    )
    bad = region_row_drill_url("person_detail", collided)
    assert bad == "/app/workspaces/person_detail?context_id={id}"
