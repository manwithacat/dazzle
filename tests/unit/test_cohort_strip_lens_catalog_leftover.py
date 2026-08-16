"""Cohort-strip leftover-honest lens catalog (cycle 2184).

``?lens=ghost`` / ``zzz`` used to invent the first declared lens even
when ``default_lens`` was a later sibling — highlight + cells silently
became Attainment while rest was Attendance. Valid declared ids ride.
Absent or leftover junk restores rest (default, else first).

New invent class (oral #68). Not leftover temporal echo (oral #67).
"""

from __future__ import annotations

import re
from pathlib import Path

from dazzle.http.runtime.workspace_card_data import _build_cohort_cells
from dazzle.render.fragment.region import WorkspaceRegionAdapter
from dazzle.render.fragment.renderer._render_interactive import leftover_honest_catalog_id
from tests.unit.test_region_adapter import _cohort_region, _render

_HELPER = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "render"
    / "fragment"
    / "renderer"
    / "_render_interactive.py"
)
_BUILDERS = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "render"
    / "fragment"
    / "region"
    / "_builders_cards.py"
)
_ADAPTER = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "http"
    / "runtime"
    / "workspace_region_render.py"
)
_CELLS = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "http"
    / "runtime"
    / "workspace_card_data.py"
)
_CONTRACT = (
    Path(__file__).resolve().parents[2]
    / "packages"
    / "hatchi-maxchi"
    / "contracts"
    / "cohort_strip.py"
)


def test_leftover_honest_catalog_id_helper() -> None:
    known = ("attainment", "attendance")
    assert leftover_honest_catalog_id("attendance", known, "attendance") == "attendance"
    assert leftover_honest_catalog_id("attainment", known, "attendance") == "attainment"
    assert leftover_honest_catalog_id("ghost-lens", known, "attendance") == "attendance"
    assert leftover_honest_catalog_id("zzz", known, "attendance") == "attendance"
    assert leftover_honest_catalog_id("", known, "attendance") == "attendance"
    assert leftover_honest_catalog_id("ghost-lens", known, "") == "attainment"
    assert leftover_honest_catalog_id("  ", known, "") == "attainment"


def test_unknown_lens_restores_default_not_first() -> None:
    """Junk ?lens= must not invent the first declared id."""
    adapter = WorkspaceRegionAdapter()
    region = _cohort_region(default_lens="attendance")
    surface = adapter.build(
        region,
        {
            "cohort_cells": [],
            "cohort_endpoint": "/r/cohort",
            "cohort_active_lens": "ghost-lens",
        },
    )
    html = _render(surface)
    match = re.search(r'aria-pressed="true"[^>]*>([^<]+)</button>', html)
    assert match is not None
    assert "Attendance" in match.group(1)


def test_unknown_lens_cells_use_default_primary() -> None:
    from dazzle.core.ir.workspaces import CohortStripConfig, CohortStripLens

    cfg = CohortStripConfig(
        member_via="profile",
        default_lens="att",
        lenses=[
            CohortStripLens(id="score", label="Score", primary="score"),
            CohortStripLens(id="att", label="Attendance", primary="att_pct"),
        ],
    )
    cells = _build_cohort_cells(
        items=[{"id": "p1", "score": 50, "att_pct": 90}],
        config=cfg,
        active_lens_id="ghost-lens",
    )
    assert cells[0]["primary_value"] == "90"


def test_valid_lens_still_rides() -> None:
    adapter = WorkspaceRegionAdapter()
    region = _cohort_region(default_lens="attendance")
    surface = adapter.build(
        region,
        {
            "cohort_cells": [],
            "cohort_endpoint": "/r/cohort",
            "cohort_active_lens": "attainment",
        },
    )
    html = _render(surface)
    match = re.search(r'aria-pressed="true"[^>]*>([^<]+)</button>', html)
    assert match is not None
    assert "Attainment" in match.group(1)


def test_helper_source_pin() -> None:
    src = _HELPER.read_text(encoding="utf-8")
    assert "def leftover_honest_catalog_id(" in src
    assert "must not invent the first declared id" in src


def test_builder_source_pin() -> None:
    src = _BUILDERS.read_text(encoding="utf-8")
    assert "leftover_honest_catalog_id" in src


def test_adapter_source_pin() -> None:
    src = _ADAPTER.read_text(encoding="utf-8")
    assert "leftover_honest_catalog_id" in src
    src_cells = _CELLS.read_text(encoding="utf-8")
    assert "leftover_honest_catalog_id" in src_cells


def test_contract_pins_catalog_leftover() -> None:
    src = _CONTRACT.read_text(encoding="utf-8")
    assert "leftover-honest lens catalog" in src.lower() or "ghost" in src.lower()
