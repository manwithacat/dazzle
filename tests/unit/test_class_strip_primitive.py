"""Issue #1018 (v0.67.2): regression tests for the `class_strip`
region primitive — first AegisMark Day-One demo region primitive,
architectural pilot for the discriminated `region_config` IR pattern.

Coverage:
  - IR: ClassStripLens + ClassStripConfig construction, validation,
    DisplayMode.CLASS_STRIP enum value, WorkspaceRegion typed config slot.
  - Primitives: ClassStripCell + ClassStripLensTab + ClassStripRegion
    validation invariants (non-empty ids, exactly-one-active-lens).
  - Renderer: lens-tab markup with HTMX swap, active-lens highlight,
    cell halo + tone, drill-down anchor, empty-state path.
"""

from __future__ import annotations

import pytest

from dazzle.core.ir.workspaces import (
    ClassStripConfig,
    ClassStripLens,
    DisplayMode,
    WorkspaceRegion,
)
from dazzle.render.fragment import (
    URL,
    ClassStripCell,
    ClassStripLensTab,
    ClassStripRegion,
    FragmentRenderer,
)

# ── IR ──


def test_display_mode_includes_class_strip() -> None:
    """`DisplayMode.CLASS_STRIP` is registered in the workspace
    region display enum so DSL authors can declare
    `display: class_strip` and the parser will accept it."""
    assert DisplayMode.CLASS_STRIP == "class_strip"
    assert DisplayMode("class_strip") is DisplayMode.CLASS_STRIP


def test_class_strip_lens_constructs_with_required_fields() -> None:
    """Minimal lens needs id + label + primary."""
    lens = ClassStripLens(id="attainment", label="Attainment", primary="latest_pct")
    assert lens.id == "attainment"
    assert lens.threshold is None


def test_class_strip_lens_threshold_optional_float() -> None:
    """RAG threshold drives the renderer's tone tint per lens."""
    lens = ClassStripLens(
        id="attendance",
        label="Attendance",
        primary="attendance_pct",
        threshold=90.0,
    )
    assert lens.threshold == 90.0


def test_class_strip_config_carries_lenses_and_default() -> None:
    """ClassStripConfig is the typed config block on WorkspaceRegion
    when display == CLASS_STRIP."""
    cfg = ClassStripConfig(
        pupil_via="student_profile",
        lenses=[
            ClassStripLens(id="attainment", label="Attainment", primary="latest_pct"),
            ClassStripLens(id="attendance", label="Attendance", primary="att_pct"),
        ],
        default_lens="attainment",
    )
    assert cfg.pupil_via == "student_profile"
    assert len(cfg.lenses) == 2
    assert cfg.default_lens == "attainment"


def test_workspace_region_carries_class_strip_config_slot() -> None:
    """Establishes the discriminated-config pattern — when display is
    CLASS_STRIP, `class_strip_config` is populated; otherwise it stays
    None and the region behaves as a generic `WorkspaceRegion`."""
    cfg = ClassStripConfig(
        pupil_via="student_profile",
        lenses=[ClassStripLens(id="x", label="X", primary="p")],
    )
    region = WorkspaceRegion(
        name="cohort",
        display=DisplayMode.CLASS_STRIP,
        class_strip_config=cfg,
    )
    assert region.class_strip_config is cfg
    assert region.display is DisplayMode.CLASS_STRIP


def test_workspace_region_default_class_strip_config_is_none() -> None:
    """Generic regions (display != CLASS_STRIP) leave the slot None
    — no schema cost for non-class-strip regions."""
    region = WorkspaceRegion(name="x", display=DisplayMode.LIST)
    assert region.class_strip_config is None


# ── Primitive validation ──


def test_class_strip_cell_validates_non_empty_pupil_id() -> None:
    with pytest.raises(ValueError, match="pupil_id"):
        ClassStripCell(pupil_id="", pupil_name="A", primary_value="0")


def test_class_strip_lens_tab_validates_non_empty_id() -> None:
    with pytest.raises(ValueError, match="non-empty id"):
        ClassStripLensTab(id="", label="X", is_active=True)


def test_class_strip_region_requires_non_empty_region_name() -> None:
    with pytest.raises(ValueError, match="region_name"):
        ClassStripRegion(
            region_name="",
            endpoint=URL("/x"),
            lenses=(ClassStripLensTab(id="a", label="A", is_active=True),),
            cells=(),
        )


def test_class_strip_region_requires_at_least_one_lens() -> None:
    with pytest.raises(ValueError, match="at least one lens"):
        ClassStripRegion(
            region_name="r",
            endpoint=URL("/x"),
            lenses=(),
            cells=(),
        )


def test_class_strip_region_requires_exactly_one_active_lens() -> None:
    """Defensive: zero or two-active-lens states would render an
    inconsistent UI. Constructor catches it."""
    with pytest.raises(ValueError, match="exactly one active lens"):
        # zero active
        ClassStripRegion(
            region_name="r",
            endpoint=URL("/x"),
            lenses=(ClassStripLensTab(id="a", label="A", is_active=False),),
            cells=(),
        )
    with pytest.raises(ValueError, match="exactly one active lens"):
        # two active
        ClassStripRegion(
            region_name="r",
            endpoint=URL("/x"),
            lenses=(
                ClassStripLensTab(id="a", label="A", is_active=True),
                ClassStripLensTab(id="b", label="B", is_active=True),
            ),
            cells=(),
        )


# ── Renderer ──


def _render(strip: ClassStripRegion) -> str:
    return FragmentRenderer().render(strip)


def _strip(**overrides) -> ClassStripRegion:
    base: dict = {
        "region_name": "cohort",
        "endpoint": URL("/api/regions/cohort"),
        "lenses": (
            ClassStripLensTab(id="attainment", label="Attainment", is_active=True),
            ClassStripLensTab(id="attendance", label="Attendance"),
        ),
        "cells": (
            ClassStripCell(
                pupil_id="p1",
                pupil_name="Alice Wong",
                year_form="9G",
                primary_value="78%",
                tone="good",
                drill_url="/pupils/p1",
            ),
        ),
    }
    base.update(overrides)
    return ClassStripRegion(**base)


def test_render_emits_lens_toggle_with_tablist_role() -> None:
    """Lens toggle is a `<div role="tablist">` of buttons — a11y
    contract that the cohort skim's primary nav is a set of tabs."""
    html = _render(_strip())
    assert 'class="dz-class-strip-lenses" role="tablist"' in html
    assert 'aria-label="Lens toggle"' in html


def test_render_active_lens_button_carries_aria_pressed_true() -> None:
    """The active lens button gets `is-active` + `aria-pressed="true"`;
    others get `aria-pressed="false"`. Drives the visual highlight + a11y."""
    html = _render(_strip())
    # The active lens (attainment).
    assert ">Attainment</button>" in html
    assert html.count('aria-pressed="true"') == 1
    assert html.count('aria-pressed="false"') == 1


def test_render_lens_button_emits_hx_get_with_lens_id() -> None:
    """Each lens button fires `hx-get="<endpoint>?lens=<id>"` +
    `hx-target="#region-<name>-body"` — same-region swap."""
    html = _render(_strip())
    assert 'hx-get="/api/regions/cohort?lens=attainment"' in html
    assert 'hx-get="/api/regions/cohort?lens=attendance"' in html
    assert 'hx-target="#region-cohort-body"' in html
    assert 'hx-swap="innerHTML"' in html


def test_render_emits_one_cell_per_pupil() -> None:
    cells = (
        ClassStripCell(pupil_id="p1", pupil_name="Alice", primary_value="78"),
        ClassStripCell(pupil_id="p2", pupil_name="Bob", primary_value="62"),
        ClassStripCell(pupil_id="p3", pupil_name="Carol", primary_value="45"),
    )
    html = _render(_strip(cells=cells))
    # Three cells.
    assert html.count('data-pupil-id="p1"') == 1
    assert html.count('data-pupil-id="p2"') == 1
    assert html.count('data-pupil-id="p3"') == 1
    assert "Alice" in html and "Bob" in html and "Carol" in html


def test_render_cell_with_drill_url_wraps_in_anchor() -> None:
    """Cells with drill_url become `<a href="...">` so the cell is
    keyboard-navigable + clickable for drill-down to pupil_card."""
    html = _render(_strip())
    assert '<a class="dz-class-strip-cell" href="/pupils/p1"' in html


def test_render_cell_without_drill_url_is_plain_div() -> None:
    """Cells without drill_url become plain `<div>` — no hover-link
    state, no keyboard target. Used when the cohort view is the
    terminal node (no pupil_card surface to drill into)."""
    html = _render(
        _strip(cells=(ClassStripCell(pupil_id="p1", pupil_name="Alice", primary_value="78"),))
    )
    assert '<div class="dz-class-strip-cell" data-pupil-id="p1">' in html
    assert "<a " not in html.split("dz-class-strip-cells")[1]


def test_render_cell_emits_dz_tone_data_attribute() -> None:
    """The primary value carries `data-dz-tone="<good|warn|bad|neutral>"`
    so the dz-tones.css CSS rules apply the RAG colouring. Adapter
    sets the tone based on the lens threshold (per-lens semantics)."""
    cells = (
        ClassStripCell(pupil_id="p1", pupil_name="Alice", primary_value="78", tone="good"),
        ClassStripCell(pupil_id="p2", pupil_name="Bob", primary_value="62", tone="warn"),
        ClassStripCell(pupil_id="p3", pupil_name="Carol", primary_value="45", tone="bad"),
        ClassStripCell(pupil_id="p4", pupil_name="Dan", primary_value="55"),
    )
    html = _render(_strip(cells=cells))
    assert html.count('data-dz-tone="good"') == 1
    assert html.count('data-dz-tone="warn"') == 1
    assert html.count('data-dz-tone="bad"') == 1
    # Default tone is "neutral".
    assert html.count('data-dz-tone="neutral"') == 1


def test_render_unknown_tone_falls_back_to_neutral() -> None:
    """Defensive: an adapter that produces an out-of-allowlist tone
    string gets coerced to neutral rather than appearing verbatim."""
    cells = (ClassStripCell(pupil_id="p1", pupil_name="A", primary_value="0", tone="rainbow"),)
    html = _render(_strip(cells=cells))
    assert 'data-dz-tone="neutral"' in html
    assert 'data-dz-tone="rainbow"' not in html


def test_render_uses_avatar_initials_when_provided() -> None:
    cells = (
        ClassStripCell(
            pupil_id="p1",
            pupil_name="Alice Wong",
            primary_value="78",
            avatar_initials="AW",
        ),
    )
    html = _render(_strip(cells=cells))
    assert ">AW</div>" in html


def test_render_synthesises_initials_from_pupil_name() -> None:
    """Empty `avatar_initials` → renderer uses the first two letters
    of `pupil_name`, uppercased. Defensive default for adapters that
    don't compute initials upstream."""
    cells = (ClassStripCell(pupil_id="p1", pupil_name="alice", primary_value="78"),)
    html = _render(_strip(cells=cells))
    assert ">AL</div>" in html


def test_render_year_form_appears_when_set() -> None:
    cells = (ClassStripCell(pupil_id="p1", pupil_name="A", primary_value="0", year_form="9G"),)
    html = _render(_strip(cells=cells))
    assert '<div class="dz-class-strip-cell-year">9G</div>' in html


def test_render_year_form_omitted_when_blank() -> None:
    cells = (ClassStripCell(pupil_id="p1", pupil_name="A", primary_value="0"),)
    html = _render(_strip(cells=cells))
    assert "dz-class-strip-cell-year" not in html


def test_render_empty_cells_emits_empty_message() -> None:
    """Empty cohort renders the configured empty_message (or
    framework default). The lens toggle is still emitted — switching
    lenses might populate the strip."""
    html = _render(_strip(cells=(), empty_message="No pupils to show."))
    assert 'class="dz-class-strip-empty"' in html
    assert "No pupils to show." in html
    # Lens toggle still present.
    assert 'role="tablist"' in html


def test_render_outer_carries_data_dz_region_name() -> None:
    """`data-dz-region-name` lets the lens-toggle HTMX target find the
    right region wrapper — same convention as DashboardCard."""
    html = _render(_strip())
    assert 'data-dz-region-name="cohort"' in html
    assert 'id="region-cohort-body"' in html


def test_render_escapes_pupil_name_and_lens_label() -> None:
    """User-supplied display strings escape attribute-context chars."""
    cells = (
        ClassStripCell(
            pupil_id="p1",
            pupil_name="<script>alert(1)</script>",
            primary_value="0",
        ),
    )
    lenses = (ClassStripLensTab(id="x", label="<script>", is_active=True),)
    html = _render(_strip(cells=cells, lenses=lenses))
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
