"""Bar-chart / badge level tokens must emit IC1, not title-cased Ic1 (oral #186)."""

from __future__ import annotations

from pathlib import Path

from dazzle.render.filters import _humanize_filter, clerk_stage_label
from dazzle.render.fragment import BarChart, FragmentRenderer
from dazzle.render.fragment.region import _render_status_badge_html
from dazzle.render.fragment.region._builders_charts import _BuildersChartsMixin

HR = Path("examples/hr_records/dsl")


class _A(_BuildersChartsMixin):
    pass


def _render_buckets(buckets: list[object]) -> str:
    region = type(
        "R", (), {"name": "role_level_mix", "title": "Role levels", "empty_message": None}
    )()
    ctx = {"buckets": buckets, "chart_label": "Role levels"}
    return FragmentRenderer().render(_A()._build_bar_chart(region, ctx))


def test_hr_records_role_level_mix_is_live() -> None:
    block = (HR / "app.dsl").read_text()
    region = block.split("  role_level_mix:", 1)[1].split("\n\n", 1)[0]
    assert "display: bar_chart" in region
    assert "group_by: level" in region
    role = block.split('entity Role "Role":', 1)[1].split("entity ", 1)[0]
    assert "level: enum[ic1, ic2, ic3, ic4, ic5, ic6, m1, m2, m3, m4]" in role


def test_hr_records_by_level_kanban_is_live() -> None:
    block = (HR / "app.dsl").read_text()
    region = block.split("  by_level:", 1)[1].split("\n\n", 1)[0]
    assert "display: kanban" in region
    assert "group_by: level" in region


def test_clerk_stage_label_level_acronyms() -> None:
    assert clerk_stage_label("ic1") == "IC1"
    assert clerk_stage_label("IC1") == "IC1"
    assert clerk_stage_label("Ic1") == "IC1"
    assert clerk_stage_label("m2") == "M2"
    assert clerk_stage_label("p0") == "P0"
    assert clerk_stage_label("in_progress") == "In Progress"
    assert clerk_stage_label(True) == "Yes"
    assert clerk_stage_label("zzz") == "zzz"
    assert clerk_stage_label("ghost") == "ghost"
    assert clerk_stage_label("2abc") == "2abc"


def test_humanize_filter_level_acronyms() -> None:
    assert _humanize_filter("ic1") == "IC1"
    assert _humanize_filter("IC1") == "IC1"
    assert _humanize_filter("m4") == "M4"
    assert _humanize_filter("in_progress") == "In Progress"
    assert _humanize_filter("zzz") == "Zzz"


def test_bar_chart_level_is_ic1_not_ic_title() -> None:
    html = _render_buckets([("ic1", 3), ("m2", 2)])
    assert ">IC1<" in html
    assert ">M2<" in html
    assert ">Ic1<" not in html
    leftover = _render_buckets([("zzz", 1), ("ghost", 1)])
    assert ">zzz<" in leftover
    assert ">ghost<" in leftover
    assert ">Zzz<" not in leftover


def test_bar_chart_direct_emit_level_acronym() -> None:
    html = FragmentRenderer().render(BarChart(label="Levels", buckets=(("ic1", 3), ("m2", 1))))
    assert ">IC1<" in html
    assert ">M2<" in html
    assert ">Ic1<" not in html


def test_status_badge_level_is_ic1_not_ic_title() -> None:
    html = _render_status_badge_html("ic1", size="sm")
    assert ">IC1<" in html
    assert ">Ic1<" not in html
    leftover = _render_status_badge_html("zzz", size="sm")
    assert ">Zzz<" in leftover
