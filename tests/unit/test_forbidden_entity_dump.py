"""403 permission speech must not dump EngagementLetter (oral #197)."""

from __future__ import annotations

from pathlib import Path

from dazzle.core.ir import EntitySpec
from dazzle.core.project import load_project
from dazzle.core.strings import entity_slug
from dazzle.http.runtime.app_error_views import build_app_403_view
from dazzle.render.access_messages import _forbidden_detail
from dazzle.render.fragment.renderer import FragmentRenderer

CONTACT = Path("examples/contact_manager")
SUPPORT = Path("examples/support_tickets")


def _letter() -> EntitySpec:
    spec = load_project(CONTACT)
    return next(e for e in spec.domain.entities if e.name == "EngagementLetter")


def _render_403(detail: dict[str, object]) -> str:
    page = build_app_403_view(
        app_name="Contact Manager",
        message=str(detail.get("message") or ""),
        forbidden_detail=detail,  # type: ignore[arg-type]
    )
    return FragmentRenderer().render(page)


def test_contact_engagement_letter_forbidden_noun_is_live() -> None:
    letter = _letter()
    assert letter.title == "Engagement Letter"
    assert entity_slug("EngagementLetter") == "engagementletter"
    detail = _forbidden_detail(
        entity_name="EngagementLetter",
        operation="create",
        cedar_access_spec=None,
        current_roles=["viewer"],
        entity=letter,
    )
    assert detail["entity"] == "EngagementLetter"
    assert detail["entity_label"] == "Engagement Letter"
    assert detail["message"] == "You don't have permission to create engagement letter."


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


def test_403_page_entity_panel_not_pascal() -> None:
    letter = _letter()
    detail = _forbidden_detail(
        entity_name="EngagementLetter",
        operation="create",
        cedar_access_spec=None,
        entity=letter,
    )
    html = _render_403(detail)
    assert "create engagement letter." in html
    assert "Entity: Engagement Letter" in html
    assert "Entity: EngagementLetter" not in html
    assert "EngagementLetter" not in html


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


def test_leftover_zzz_invents_no_entity() -> None:
    letter = _letter()
    detail = _forbidden_detail(
        entity_name="zzz",
        operation="create",
        cedar_access_spec=None,
        entity=letter,
    )
    assert detail["entity"] == "zzz"
    assert detail["entity_label"] == "zzz"
    assert detail["message"] == "You don't have permission to create zzz."
    assert "engagement letter" not in detail["message"].lower()
    html = _render_403(detail)
    assert "Entity: zzz" in html
    assert "Engagement Letter" not in html
