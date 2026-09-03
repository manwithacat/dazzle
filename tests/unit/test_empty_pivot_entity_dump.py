"""Pivot empty must not dump generic 'No data to pivot.' (oral #230)."""

from __future__ import annotations

from pathlib import Path

from dazzle.core.project import load_project
from dazzle.render.breadcrumbs import (
    clerk_empty_pivot_title,
    clerk_entity_confirm_noun,
    clerk_entity_noun,
    entity_path_labels_from_spec,
)
from dazzle.render.fragment import FragmentRenderer
from dazzle.render.fragment.region._builders_tables import _BuildersTablesMixin

OPS = Path("examples/ops_dashboard")
FIELDTEST = Path("examples/fieldtest_hub")
OPS_DSL = OPS / "dsl" / "app.dsl"


class _A(_BuildersTablesMixin):
    pass


def _region(**overrides: object) -> object:
    base: dict[str, object] = {
        "name": "alert_pivot",
        "title": "Alert pivot",
        "empty_message": None,
        "source": "Alert",
    }
    base.update(overrides)
    return type("R", (), base)()


def _render_pivot(region: object, ctx: dict[str, object] | None = None) -> str:
    payload: dict[str, object] = {
        "pivot_buckets": [],
        "pivot_dim_specs": [
            {"name": "system", "label": "System", "is_fk": True},
            {"name": "severity", "label": "Severity", "is_fk": False},
        ],
    }
    payload.update(ctx or {})
    return FragmentRenderer().render(_A()._build_pivot_table(region, payload))


def test_ops_alert_pivot_is_live() -> None:
    block = OPS_DSL.read_text()
    region = block.split("  alert_pivot:", 1)[1].split("  alert_heatmap:", 1)[0]
    assert "display: pivot_table" in region
    assert "source: Alert" in region
    assert 'empty: "No alerts to pivot"' in region


def test_clerk_empty_pivot_title_splits_pascal_and_catalog() -> None:
    spec = load_project(OPS)
    alert = next(e for e in spec.domain.entities if e.name == "Alert")
    assert alert.title == "Alert"
    labels = entity_path_labels_from_spec(spec)
    assert clerk_entity_noun("Alert", labels) == "Alert"
    assert clerk_entity_confirm_noun("Alert", labels) == "alert"
    assert clerk_empty_pivot_title("Alert", labels) == "No alerts to pivot."
    assert clerk_empty_pivot_title("Alert") == "No alerts to pivot."


def test_clerk_empty_pivot_title_leftover_invents_no_collection() -> None:
    for junk in ("zzz", "ghost", "2abc"):
        assert clerk_empty_pivot_title(junk) == "No data to pivot."


def test_fieldtest_issue_report_pivot_is_issue_reports() -> None:
    spec = load_project(FIELDTEST)
    issue = next(e for e in spec.domain.entities if e.name == "IssueReport")
    assert issue.title == "Issue Report"
    labels = entity_path_labels_from_spec(spec)
    assert clerk_empty_pivot_title("IssueReport", labels) == "No issue reports to pivot."


def test_pivot_empty_is_alerts_not_no_data_to_pivot() -> None:
    html = _render_pivot(_region())
    assert "dz-empty-dense" in html
    assert "No alerts to pivot." in html
    assert "No data to pivot." not in html
    assert "No alertss" not in html


def test_pivot_empty_ctx_source_entity_still_splits() -> None:
    html = _render_pivot(_region(source=""), {"source_entity": "Alert"})
    assert "No alerts to pivot." in html
    assert "No data to pivot." not in html


def test_pivot_empty_missing_entity_stays_no_data_to_pivot() -> None:
    html = _render_pivot(_region(source=""))
    assert "No data to pivot." in html
    assert "No alerts" not in html


def test_pivot_empty_leftover_invents_no_collection() -> None:
    html = _render_pivot(_region(source="zzz"))
    assert "No data to pivot." in html
    assert "No zzz" not in html


def test_pivot_empty_card_title_item_fallback_does_not_invent() -> None:
    html = _render_pivot(_region(source="Alert"), {"entity_name": "Item"})
    assert "No alerts to pivot." in html
    assert "No data to pivot." not in html


def test_pivot_authored_empty_still_wins() -> None:
    html = _render_pivot(_region(empty_message="No alerts to pivot"))
    assert "No alerts to pivot" in html
    assert "No data to pivot." not in html
    assert "No alerts to pivot." not in html


def test_pivot_populated_still_renders_cells() -> None:
    html = _render_pivot(
        _region(),
        {
            "pivot_buckets": [
                {
                    "system": "s1",
                    "system_label": "API",
                    "severity": "critical",
                    "count": 3,
                }
            ],
            "pivot_dim_specs": [
                {"name": "system", "label": "System", "is_fk": True},
                {"name": "severity", "label": "Severity", "is_fk": False},
            ],
        },
    )
    assert "API" in html
    assert "No data to pivot." not in html
    assert "No alerts to pivot." not in html
