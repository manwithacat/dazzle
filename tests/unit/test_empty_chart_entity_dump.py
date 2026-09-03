"""Chart empty must not dump generic 'No data' for Issue Report (oral #219)."""

from __future__ import annotations

from pathlib import Path

from dazzle.core.project import load_project
from dazzle.render.breadcrumbs import (
    clerk_empty_chart_title,
    clerk_entity_confirm_noun,
    clerk_entity_noun,
    entity_path_labels_from_spec,
)
from dazzle.render.fragment import FragmentRenderer
from dazzle.render.fragment.region._builders_charts import _BuildersChartsMixin

FIELDTEST = Path("examples/fieldtest_hub")
CONTACT = Path("examples/contact_manager")
FIELDTEST_DSL = FIELDTEST / "dsl" / "app.dsl"


class _A(_BuildersChartsMixin):
    pass


def _region(**overrides: object) -> object:
    base: dict[str, object] = {
        "name": "severity_mix",
        "title": "Severity mix",
        "empty_message": "No open reports",
        "source": "IssueReport",
    }
    base.update(overrides)
    return type("R", (), base)()


def _render_bar(region: object, ctx: dict[str, object] | None = None) -> str:
    return FragmentRenderer().render(_A()._build_bar_chart(region, ctx or {}))


def test_fieldtest_severity_mix_bar_chart_is_live() -> None:
    block = FIELDTEST_DSL.read_text()
    region = block.split("  severity_mix:", 1)[1].split("  device_board:", 1)[0]
    assert "display: bar_chart" in region
    assert "source: IssueReport" in region
    assert 'empty: "No open reports"' in region


def test_clerk_empty_chart_title_splits_pascal_and_catalog() -> None:
    spec = load_project(FIELDTEST)
    issue = next(e for e in spec.domain.entities if e.name == "IssueReport")
    assert issue.title == "Issue Report"
    labels = entity_path_labels_from_spec(spec)
    assert clerk_entity_noun("IssueReport", labels) == "Issue Report"
    assert clerk_entity_confirm_noun("IssueReport", labels) == "issue report"
    assert clerk_empty_chart_title("IssueReport", labels) == "No issue reports to chart"
    assert clerk_empty_chart_title("IssueReport") == "No issue reports to chart"


def test_clerk_empty_chart_title_leftover_invents_no_collection() -> None:
    for junk in ("zzz", "ghost", "2abc"):
        assert clerk_empty_chart_title(junk) == "No data"


def test_contact_engagement_letter_chart_title_is_live() -> None:
    spec = load_project(CONTACT)
    letter = next(e for e in spec.domain.entities if e.name == "EngagementLetter")
    assert letter.title == "Engagement Letter"
    labels = entity_path_labels_from_spec(spec)
    assert clerk_empty_chart_title("EngagementLetter", labels) == "No engagement letters to chart"


def test_bar_chart_empty_is_issue_reports_not_no_data() -> None:
    html = _render_bar(_region())
    assert "No issue reports to chart" in html
    assert ">No data<" not in html
    assert "No issuereport" not in html.lower()
    assert "No open reports" in html


def test_bar_chart_empty_bare_pascal_source_still_splits() -> None:
    html = _render_bar(_region(), {"source_entity": "IssueReport"})
    assert "No issue reports to chart" in html
    assert ">No data<" not in html


def test_bar_chart_empty_missing_entity_stays_no_data() -> None:
    html = _render_bar(_region(source=""))
    assert "No data" in html
    assert "No issue reports to chart" not in html


def test_bar_chart_empty_leftover_invents_no_collection() -> None:
    html = _render_bar(_region(source="zzz"))
    assert "No data" in html
    assert "No zzz" not in html
    assert "to chart" not in html
