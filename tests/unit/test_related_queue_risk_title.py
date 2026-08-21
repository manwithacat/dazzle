"""Related queue must title the walk, not severity/environment (oral #145)."""

from __future__ import annotations

from pathlib import Path

from dazzle.core.project import load_project
from dazzle.http.runtime.renderers.fragment_adapter import FragmentSurfaceAdapter
from dazzle.page.converters.template_compiler import compile_appspec_to_templates
from dazzle.render.cell_chrome import (
    is_risk_title_key,
    related_queue_columns_omit_identity,
    related_queue_identity_from_record,
    related_queue_title_and_meta,
)
from dazzle.render.fragment.primitives.data import RelatedGroup, RelatedTab
from dazzle.render.fragment.renderer import FragmentRenderer


def test_risk_title_keys() -> None:
    assert is_risk_title_key("severity")
    assert is_risk_title_key("Severity")
    assert is_risk_title_key("environment")
    assert is_risk_title_key("quality_score")
    assert not is_risk_title_key("description")
    assert not is_risk_title_key("zzz")


def test_related_queue_prefers_description_not_severity() -> None:
    title, metas = related_queue_title_and_meta(
        ("Battery drained after 20 minutes", "critical", "open", "battery", "12 May 2026"),
        ("Title", "Severity", "Status", "Category", "Reported At"),
    )
    assert title == "Battery drained after 20 minutes"
    assert ("Severity", "critical") in metas
    assert "critical" != title


def test_related_queue_leftover_description_stays_put() -> None:
    title, metas = related_queue_title_and_meta(
        ("zzz", "critical", "ghost"),
        ("Title", "Severity", "Status"),
    )
    assert title == "zzz"
    assert ("Severity", "critical") in metas
    assert "ghost" in {raw for _, raw in metas}


def test_related_queue_html_titles_description() -> None:
    html = FragmentRenderer().render(
        RelatedGroup(
            group_id="issues",
            label="Issue reports",
            display="queue",
            tabs=(
                RelatedTab(
                    tab_id="issues",
                    label="Issue reports",
                    headers=("Title", "Severity", "Status", "Category", "Reported At"),
                    rows=(
                        (
                            "Battery drained after 20 minutes",
                            "critical",
                            "open",
                            "battery",
                            "12 May 2026",
                        ),
                    ),
                    row_drill=("/app/issuereport/a-1",),
                ),
            ),
        )
    )
    assert "Battery drained after 20 minutes" in html
    assert "dz-queue-row-title" in html
    assert "Severity: critical" in html
    assert ">Battery drained after 20 minutes<" in html


def test_related_queue_leftover_html_stays_put() -> None:
    html = FragmentRenderer().render(
        RelatedGroup(
            group_id="issues",
            label="Issue reports",
            display="queue",
            tabs=(
                RelatedTab(
                    tab_id="issues",
                    label="Issue reports",
                    headers=("Title", "Severity"),
                    rows=(("zzz", "critical"),),
                ),
            ),
        )
    )
    assert ">zzz<" in html or "zzz" in html
    assert "Severity: critical" in html


def test_fieldtest_device_issues_columns_omit_description() -> None:
    spec = load_project(Path("examples/fieldtest_hub"))
    ctxs = compile_appspec_to_templates(spec)
    detail = ctxs["/device/{id}"].detail
    assert detail is not None
    group = next(g for g in detail.related_groups if g.group_id == "group-issues")
    assert group.display == "queue"
    keys = [c.key for c in group.tabs[0].columns]
    assert keys[0] == "severity"
    assert "description" not in keys
    assert related_queue_columns_omit_identity(keys)


def test_fieldtest_issue_report_identity_is_description() -> None:
    spec = load_project(Path("examples/fieldtest_hub"))
    issue = spec.get_entity("IssueReport")
    assert issue is not None
    assert issue.display_field == "description"


def test_related_queue_identity_from_record_prefers_description() -> None:
    assert (
        related_queue_identity_from_record(
            {
                "severity": "critical",
                "status": "open",
                "category": "battery",
                "description": "Battery drained after 20 minutes",
            }
        )
        == "Battery drained after 20 minutes"
    )
    assert (
        related_queue_identity_from_record({"severity": "critical", "description": "zzz"}) == "zzz"
    )
    assert related_queue_identity_from_record({"severity": "critical"}) == ""


def test_adapter_injects_description_not_severity() -> None:
    frag = FragmentSurfaceAdapter()._build_related_group(
        {
            "group_id": "issues",
            "label": "Issue reports",
            "display": "queue",
            "tabs": [
                {
                    "tab_id": "issues",
                    "label": "Issue reports",
                    "columns": [
                        {"key": "severity", "label": "Severity", "type": "badge"},
                        {"key": "status", "label": "Status", "type": "badge"},
                        {"key": "category", "label": "Category", "type": "badge"},
                        {"key": "reported_at", "label": "Reported At", "type": "datetime"},
                    ],
                    "rows": [
                        {
                            "id": "a-1",
                            "severity": "critical",
                            "status": "open",
                            "category": "battery",
                            "reported_at": "2026-05-12",
                            "description": "Battery drained after 20 minutes",
                        }
                    ],
                    "detail_url_template": "/app/issuereport/{id}",
                }
            ],
        },
        "device-1",
    )
    html = FragmentRenderer().render(frag)
    assert ">Battery drained after 20 minutes<" in html
    assert "Severity:" in html
    assert html.index(">Battery drained after 20 minutes<") < html.index("Severity:")


def test_adapter_leftover_identity_stays_put() -> None:
    frag = FragmentSurfaceAdapter()._build_related_group(
        {
            "group_id": "issues",
            "label": "Issue reports",
            "display": "queue",
            "tabs": [
                {
                    "tab_id": "issues",
                    "label": "Issue reports",
                    "columns": [
                        {"key": "severity", "label": "Severity", "type": "badge"},
                    ],
                    "rows": [{"id": "a-1", "severity": "critical", "description": "zzz"}],
                }
            ],
        },
        "device-1",
    )
    html = FragmentRenderer().render(frag)
    assert ">zzz<" in html
