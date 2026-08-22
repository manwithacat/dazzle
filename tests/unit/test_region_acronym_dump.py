"""Kanban / badge / FilterBar region tokens must emit EMEA, not Emea (oral #187)."""

from __future__ import annotations

from pathlib import Path

from dazzle.http.runtime.workspace_columns import enum_filter_options
from dazzle.render.filters import _humanize_filter, clerk_stage_label
from dazzle.render.fragment import FragmentRenderer, KanbanColumn, KanbanRegion
from dazzle.render.fragment.region import _render_status_badge_html

INVOICE = Path("examples/invoice_ops/dsl")


def test_invoice_ops_by_region_is_live() -> None:
    block = (INVOICE / "surfaces.dsl").read_text()
    region = block.split("  by_region:", 1)[1].split("\n\n", 1)[0]
    assert "display: kanban" in region
    assert "group_by: region" in region
    entities = (INVOICE / "entities.dsl").read_text()
    supplier = entities.split("entity Supplier", 1)[1].split("entity ", 1)[0]
    assert "region: enum[emea,amer,apac]=emea" in supplier


def test_clerk_stage_label_region_acronyms() -> None:
    assert clerk_stage_label("emea") == "EMEA"
    assert clerk_stage_label("EMEA") == "EMEA"
    assert clerk_stage_label("Emea") == "EMEA"
    assert clerk_stage_label("amer") == "AMER"
    assert clerk_stage_label("apac") == "APAC"
    assert clerk_stage_label("latam") == "LATAM"
    assert clerk_stage_label("in_progress") == "In Progress"
    assert clerk_stage_label("ic1") == "IC1"
    assert clerk_stage_label(True) == "Yes"
    assert clerk_stage_label("zzz") == "zzz"
    assert clerk_stage_label("ghost") == "ghost"
    assert clerk_stage_label("2abc") == "2abc"


def test_humanize_filter_region_acronyms() -> None:
    assert _humanize_filter("emea") == "EMEA"
    assert _humanize_filter("AMER") == "AMER"
    assert _humanize_filter("apac") == "APAC"
    assert _humanize_filter("in_progress") == "In Progress"
    assert _humanize_filter("zzz") == "Zzz"


def test_status_badge_region_is_emea_not_title() -> None:
    html = _render_status_badge_html("emea")
    assert ">EMEA<" in html
    assert ">Emea<" not in html
    leftover = _render_status_badge_html("zzz")
    assert ">Zzz<" in leftover
    assert ">ZZZ<" not in leftover


def test_kanban_column_region_is_emea_not_title() -> None:
    html = FragmentRenderer().render(
        KanbanRegion(
            columns=(
                KanbanColumn(label="emea", cards=()),
                KanbanColumn(label="amer", cards=()),
            )
        )
    )
    assert ">EMEA<" in html
    assert ">AMER<" in html
    assert ">Emea<" not in html
    leftover = FragmentRenderer().render(
        KanbanRegion(columns=(KanbanColumn(label="zzz", cards=()),))
    )
    assert ">Zzz<" in leftover
    assert ">ZZZ<" not in leftover


def test_enum_filter_options_region_is_emea_not_title() -> None:
    opts = dict(enum_filter_options(["emea", "amer", "apac", "zzz"]))
    assert opts["emea"] == "EMEA"
    assert opts["amer"] == "AMER"
    assert opts["apac"] == "APAC"
    assert opts["zzz"] == "zzz"
