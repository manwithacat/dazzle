"""Mutation toast / fallback detail must not dump IssueReport (oral #192)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from dazzle.core.project import load_project
from dazzle.core.strings import entity_slug
from dazzle.http.runtime.htmx import htmx_trigger_headers
from dazzle.http.runtime.htmx_render import _render_detail_html, _with_htmx_triggers
from dazzle.render.breadcrumbs import clerk_entity_noun, entity_path_labels_from_spec

FIELDTEST = Path("examples/fieldtest_hub")
CONTACT = Path("examples/contact_manager")


def _toast(headers: dict[str, str]) -> dict:
    raw = headers.get("HX-Trigger") or headers.get("hx-trigger")
    assert raw, f"missing HX-Trigger in {headers!r}"
    return json.loads(raw)["showToast"]


def test_fieldtest_issue_report_title_is_live() -> None:
    spec = load_project(FIELDTEST)
    issue = next(e for e in spec.domain.entities if e.name == "IssueReport")
    assert issue.title == "Issue Report"
    assert entity_slug("IssueReport") == "issuereport"
    labels = entity_path_labels_from_spec(spec)
    assert labels["issuereport"] == "Issue Report"
    assert clerk_entity_noun("IssueReport", labels) == "Issue Report"
    assert clerk_entity_noun("IssueReport") == "Issue Report"


def test_contact_engagement_letter_title_is_live() -> None:
    spec = load_project(CONTACT)
    letter = next(e for e in spec.domain.entities if e.name == "EngagementLetter")
    assert letter.title == "Engagement Letter"
    labels = entity_path_labels_from_spec(spec)
    assert clerk_entity_noun("EngagementLetter", labels) == "Engagement Letter"


def test_toast_issue_report_not_issuereport() -> None:
    spec = load_project(FIELDTEST)
    labels = entity_path_labels_from_spec(spec)
    toast = _toast(htmx_trigger_headers("IssueReport", "created", entity_labels=labels))
    assert toast["message"] == "Issue Report was created"
    assert "IssueReport was created" not in toast["message"]
    split = _toast(htmx_trigger_headers("IssueReport", "created"))
    assert split["message"] == "Issue Report was created"


def test_htmx_create_wrapper_uses_clerk_noun() -> None:
    request = MagicMock()
    request.headers = {"HX-Request": "true"}
    spec = load_project(FIELDTEST)
    labels = entity_path_labels_from_spec(spec)
    resp = _with_htmx_triggers(
        request,
        {"id": "c3000000-0000-4000-8000-000000000001"},
        "IssueReport",
        "created",
        entity_labels=labels,
    )
    toast = _toast(dict(resp.headers))
    assert toast["message"] == "Issue Report was created"
    payload = json.loads(resp.headers["HX-Trigger"])
    assert payload["entityCreated"] == {"entity": "IssueReport"}


def test_fallback_detail_heading_not_issuereport() -> None:
    request = SimpleNamespace(headers={"HX-Request": "true"}, method="GET")
    html = _render_detail_html(
        request,
        {"id": "c3000000-0000-4000-8000-000000000001", "title": "Login loop"},
        "IssueReport",
    )
    body = html.body.decode() if hasattr(html.body, "decode") else str(html.body)
    assert ">Issue Report</h2>" in body
    assert ">IssueReport</h2>" not in body
    assert "Login loop" in body


def test_leftover_zzz_invents_no_entity() -> None:
    spec = load_project(FIELDTEST)
    labels = entity_path_labels_from_spec(spec)
    toast = _toast(htmx_trigger_headers("zzz", "created", entity_labels=labels))
    assert toast["message"] == "zzz was created"
    assert "Issue Report" not in toast["message"]
    assert clerk_entity_noun("zzz", labels) == "zzz"
    assert clerk_entity_noun("ghost", labels) == "ghost"
    html = _render_detail_html(
        SimpleNamespace(headers={"HX-Request": "true"}, method="GET"),
        {"id": "1", "title": "x"},
        "zzz",
    )
    body = html.body.decode() if hasattr(html.body, "decode") else str(html.body)
    assert ">zzz</h2>" in body
    assert ">Issue Report</h2>" not in body
