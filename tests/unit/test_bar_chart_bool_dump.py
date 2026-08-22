"""Bar-chart bool group_by must emit Yes/No, not Python True (oral #185)."""

from __future__ import annotations

from pathlib import Path

from dazzle.render.filters import clerk_stage_label
from dazzle.render.fragment import BarChart, FragmentRenderer
from dazzle.render.fragment.region._builders_charts import _BuildersChartsMixin

SUPPORT = Path("examples/support_tickets/dsl")
ACME = Path("examples/acme_billing/dsl")


class _A(_BuildersChartsMixin):
    pass


def _render_buckets(buckets: list[object]) -> str:
    region = type(
        "R", (), {"name": "agent_comment_chart", "title": "Comments", "empty_message": None}
    )()
    ctx = {"buckets": buckets, "chart_label": "Comments"}
    return FragmentRenderer().render(_A()._build_bar_chart(region, ctx))


def test_support_tickets_agent_comment_chart_is_live() -> None:
    block = (SUPPORT / "app.dsl").read_text()
    region = block.split("  agent_comment_chart:", 1)[1].split("  agent_priority_queue:", 1)[0]
    assert "display: bar_chart" in region
    assert "group_by: is_internal" in region
    comment = block.split('entity Comment "Comment":', 1)[1].split("entity ", 1)[0]
    assert "is_internal: bool" in comment


def test_acme_sensitive_share_is_live() -> None:
    block = (ACME / "surfaces.dsl").read_text()
    region = block.split("  sensitive_share:", 1)[1].split("\n\n", 1)[0]
    assert "display: bar_chart" in region
    assert "group_by: sensitive" in region


def test_clerk_stage_label_bool_strings() -> None:
    assert clerk_stage_label(True) == "Yes"
    assert clerk_stage_label("True") == "Yes"
    assert clerk_stage_label("false") == "No"
    assert clerk_stage_label("zzz") == "zzz"
    assert clerk_stage_label("ghost") == "ghost"
    assert clerk_stage_label("in_progress") == "In Progress"


def test_bar_chart_bool_is_yes_no_not_true() -> None:
    html = _render_buckets([(True, 3), (False, 5)])
    assert ">Yes<" in html
    assert ">No<" in html
    assert ">True<" not in html
    assert ">False<" not in html
    stringified = _render_buckets([("True", 2), ("false", 4)])
    assert ">Yes<" in stringified
    assert ">No<" in stringified
    assert ">True<" not in stringified
    leftover = _render_buckets([("zzz", 1), ("ghost", 1)])
    assert ">zzz<" in leftover
    assert ">ghost<" in leftover
    assert ">Zzz<" not in leftover


def test_bar_chart_direct_emit_bool_string() -> None:
    html = FragmentRenderer().render(
        BarChart(label="Internal", buckets=(("True", 3), ("False", 1)))
    )
    assert ">Yes<" in html
    assert ">No<" in html
    assert ">True<" not in html
