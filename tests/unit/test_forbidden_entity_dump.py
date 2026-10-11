"""403 permission speech must not dump EngagementLetter (oral #197)."""

from __future__ import annotations

from pathlib import Path

from dazzle.core.project import load_project
from dazzle.http.runtime.app_error_views import build_app_403_view
from dazzle.render.access_messages import _forbidden_detail
from dazzle.render.fragment.renderer import FragmentRenderer

SUPPORT = Path("examples/support_tickets")


def _render_403(detail: dict[str, object]) -> str:
    page = build_app_403_view(
        app_name="Contact Manager",
        message=str(detail.get("message") or ""),
        forbidden_detail=detail,  # type: ignore[arg-type]
    )
    return FragmentRenderer().render(page)


def test_support_sla_waiver_forbidden_noun_is_live() -> None:
    spec = load_project(SUPPORT)
    waiver = next(e for e in spec.domain.entities if e.name == "SlaWaiver")
    assert waiver.title == "SLA Waiver"
    detail = _forbidden_detail(
        entity_name="SlaWaiver",
        operation="read",
        cedar_access_spec=None,
        entity=waiver,
    )
    assert detail["entity"] == "SlaWaiver"
    assert detail["entity_label"] == "SLA Waiver"
    assert detail["message"] == "You don't have permission to read sla waiver."


def test_pascal_split_without_catalog() -> None:
    detail = _forbidden_detail(
        entity_name="EngagementLetter",
        operation="create",
        cedar_access_spec=None,
    )
    assert detail["entity"] == "EngagementLetter"
    assert detail["entity_label"] == "Engagement Letter"
    assert "EngagementLetter" not in detail["message"]
    assert "engagement letter" in detail["message"]


def test_403_page_legacy_entity_payload_still_humanizes() -> None:
    html = _render_403(
        {
            "message": "Insufficient role",
            "entity": "EngagementLetter",
            "operation": "delete",
            "permitted_personas": ["admin"],
            "current_roles": ["viewer"],
        }
    )
    assert "Entity: Engagement Letter" in html
    assert "Entity: EngagementLetter" not in html
