"""Entity-card quick_actions must use authored surface titles (oral #158)."""

from __future__ import annotations

from pathlib import Path

from dazzle.core.ir.workspaces import (
    EntityCardConfig,
    EntityCardSection,
    EntityCardSectionMode,
)
from dazzle.core.project import load_project
from dazzle.http.runtime.workspace_card_fetchers import _build_entity_card_sections
from dazzle.render.filters import clerk_quick_action_label
from dazzle.render.fragment.region.workspace_card_bodies import _render_quick_actions_body


def _ops_surface_titles() -> dict[str, str]:
    spec = load_project(Path("examples/ops_dashboard"))
    titles: dict[str, str] = {}
    for surf in spec.surfaces:
        name = str(getattr(surf, "name", "") or "")
        title = str(getattr(surf, "title", "") or "").strip()
        if name and title:
            titles[name] = title
    return titles


def test_ops_dashboard_alert_360_quick_actions_are_surface_ids() -> None:
    spec = load_project(Path("examples/ops_dashboard"))
    found = False
    for ws in spec.workspaces:
        for region in ws.regions:
            if region.name != "alert_360":
                continue
            found = True
            cfg = region.entity_card_config
            assert cfg is not None
            ops = next(
                s for s in (cfg.sections or []) if s.mode == EntityCardSectionMode.QUICK_ACTIONS
            )
            assert "alert_create" in list(ops.actions or [])
            assert "alert_list" in list(ops.actions or [])
    assert found


def test_clerk_quick_action_label_uses_authored_surface_title() -> None:
    titles = _ops_surface_titles()
    assert titles["alert_create"] == "Create Alert"
    assert titles["alert_list"] == "Alerts"
    assert clerk_quick_action_label("alert_create", titles) == "Create Alert"
    assert clerk_quick_action_label("alert_list", titles) == "Alerts"


def test_clerk_quick_action_label_leftover_stays_put() -> None:
    titles = _ops_surface_titles()
    assert clerk_quick_action_label("zzz", titles) == "zzz"
    assert clerk_quick_action_label("ghost", titles) == "ghost"
    assert clerk_quick_action_label("2abc", titles) == "2abc"


def test_clerk_quick_action_label_without_catalog_humanizes() -> None:
    assert clerk_quick_action_label("log_behaviour") == "Log Behaviour"
    assert clerk_quick_action_label("zzz") == "zzz"


def test_quick_actions_html_uses_surface_titles_not_slug_title_case() -> None:
    titles = _ops_surface_titles()
    body = _render_quick_actions_body(["alert_create", "alert_list", "zzz"], titles=titles)
    assert ">Create Alert<" in body
    assert ">Alerts<" in body
    assert ">zzz<" in body
    assert 'data-dz-action="alert_create"' in body
    assert ">Alert Create<" not in body
    assert ">Alert List<" not in body


def test_quick_actions_section_live_ops_dashboard() -> None:
    spec = load_project(Path("examples/ops_dashboard"))
    titles = _ops_surface_titles()
    cfg = None
    for ws in spec.workspaces:
        for region in ws.regions:
            if region.name == "alert_360":
                cfg = region.entity_card_config
                break
    assert cfg is not None
    out = _build_entity_card_sections(
        items=[{"id": "a1", "message": "CPU spike"}],
        config=cfg,
        action_titles=titles,
    )
    ops = next(s for s in out if s["mode"] == "quick_actions")
    body = ops["body"]
    assert ">Create Alert<" in body
    assert ">Alerts<" in body
    assert ">Alert Create<" not in body


def test_quick_actions_unknown_id_with_catalog_stays_put() -> None:
    cfg = EntityCardConfig(
        sections=[
            EntityCardSection(
                name="ops",
                mode=EntityCardSectionMode.QUICK_ACTIONS,
                actions=["alert_create", "ghost"],
            )
        ]
    )
    out = _build_entity_card_sections(
        items=[{"id": "a1"}],
        config=cfg,
        action_titles={"alert_create": "Create Alert"},
    )
    body = out[0]["body"]
    assert ">Create Alert<" in body
    assert ">ghost<" in body
    assert ">Ghost<" not in body
