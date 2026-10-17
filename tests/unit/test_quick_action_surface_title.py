"""Entity-card quick_actions must use authored surface titles (oral #158)."""

from __future__ import annotations

from dazzle.core.ir.workspaces import (
    EntityCardAction,
    EntityCardConfig,
    EntityCardSection,
    EntityCardSectionMode,
)
from dazzle.http.runtime.workspace_card_fetchers import _build_entity_card_sections
from dazzle.render.filters import clerk_quick_action_label


def test_clerk_quick_action_label_without_catalog_humanizes() -> None:
    assert clerk_quick_action_label("log_behaviour") == "Log behaviour"
    assert clerk_quick_action_label("zzz") == "zzz"


def test_quick_actions_unknown_id_with_catalog_stays_put() -> None:
    cfg = EntityCardConfig(
        sections=[
            EntityCardSection(
                name="ops",
                mode=EntityCardSectionMode.QUICK_ACTIONS,
                actions=[EntityCardAction(id="alert_create"), EntityCardAction(id="ghost")],
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
