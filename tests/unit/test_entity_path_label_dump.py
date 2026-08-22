"""Shell breadcrumbs must not dump Issuereport for Issue Report (oral #191)."""

from __future__ import annotations

from pathlib import Path

from dazzle.core.project import load_project
from dazzle.core.strings import entity_slug
from dazzle.page.converters.template_compiler import compile_appspec_to_templates
from dazzle.render.breadcrumbs import (
    build_breadcrumb_trail,
    build_shell_breadcrumb,
    clerk_entity_path_label,
    crumbs_to_breadcrumb,
    entity_path_labels_from_spec,
)
from dazzle.render.context import PageContext
from dazzle.render.fragment import FragmentRenderer

FIELDTEST = Path("examples/fieldtest_hub")
CONTACT = Path("examples/contact_manager")
_ISSUE_ID = "c3000000-0000-4000-8000-000000000001"


def _html(trail) -> str:
    return FragmentRenderer().render(crumbs_to_breadcrumb(trail))


def test_fieldtest_issue_report_slug_is_live() -> None:
    spec = load_project(FIELDTEST)
    issue = next(e for e in spec.domain.entities if e.name == "IssueReport")
    assert issue.title == "Issue Report"
    assert entity_slug("IssueReport") == "issuereport"
    labels = entity_path_labels_from_spec(spec)
    assert labels["issuereport"] == "Issue Report"


def test_contact_engagement_letter_slug_is_live() -> None:
    spec = load_project(CONTACT)
    letter = next(e for e in spec.domain.entities if e.name == "EngagementLetter")
    assert letter.title == "Engagement Letter"
    assert entity_slug("EngagementLetter") == "engagementletter"
    labels = entity_path_labels_from_spec(spec)
    assert labels["engagementletter"] == "Engagement Letter"


def test_breadcrumb_issue_report_not_issuereport() -> None:
    spec = load_project(FIELDTEST)
    labels = entity_path_labels_from_spec(spec)
    trail = build_breadcrumb_trail(f"/app/issuereport/{_ISSUE_ID}", entity_labels=labels)
    assert [c.label for c in trail] == [
        "Home",
        "App",
        "Issue Report",
        _ISSUE_ID,
    ]
    html = _html(trail)
    assert ">Issue Report</a>" in html
    assert ">Issuereport</a>" not in html
    assert ">Issuereport</li>" not in html
    assert _ISSUE_ID in html


def test_compiled_page_context_stamps_entity_path_labels() -> None:
    spec = load_project(FIELDTEST)
    contexts = compile_appspec_to_templates(spec, app_prefix="/app")
    detail = contexts["/app/issuereport/{id}"]
    assert detail.entity_path_labels["issuereport"] == "Issue Report"
    detail.current_route = f"/app/issuereport/{_ISSUE_ID}"
    html = FragmentRenderer().render(build_shell_breadcrumb(detail))
    assert ">Issue Report</a>" in html
    assert ">Issuereport</a>" not in html
    assert ">Issuereport</li>" not in html


def test_page_title_override_still_wins_on_leaf() -> None:
    labels = {"issuereport": "Issue Report"}
    ctx = PageContext(
        page_title="Login loop on Probe-01",
        current_route=f"/app/issuereport/{_ISSUE_ID}",
        entity_path_labels=labels,
    )
    html = FragmentRenderer().render(build_shell_breadcrumb(ctx))
    assert ">Login loop on Probe-01</li>" in html
    assert ">Issue Report</a>" in html
    assert ">Issuereport</a>" not in html
    assert ">Issuereport</li>" not in html


def test_leftover_zzz_invents_no_entity() -> None:
    spec = load_project(FIELDTEST)
    labels = entity_path_labels_from_spec(spec)
    trail = build_breadcrumb_trail("/app/zzz", entity_labels=labels)
    assert [c.label for c in trail] == ["Home", "App", "Zzz"]
    html = _html(trail)
    assert ">Issue Report</a>" not in html
    assert ">Issuereport</a>" not in html
    assert ">Zzz</li>" in html or ">Zzz</a>" in html
    assert clerk_entity_path_label("zzz", labels) == "Zzz"
    assert clerk_entity_path_label("issuereport", labels) == "Issue Report"
    assert clerk_entity_path_label(_ISSUE_ID, labels) == _ISSUE_ID
