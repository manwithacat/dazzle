"""Chart empty must not dump generic 'No data' for Issue Report (oral #219)."""

from __future__ import annotations

from dazzle.render.breadcrumbs import (
    clerk_empty_chart_title,
)
from dazzle.render.fragment import FragmentRenderer
from dazzle.render.fragment.region._builders_charts import _BuildersChartsMixin


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


def test_clerk_empty_chart_title_leftover_invents_no_collection() -> None:
    for junk in ("zzz", "ghost", "2abc"):
        assert clerk_empty_chart_title(junk) == "No data"


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
