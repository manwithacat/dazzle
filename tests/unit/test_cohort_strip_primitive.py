"""Issue #1018 (v0.67.2): regression tests for the `cohort_strip`
region primitive — first AegisMark Day-One demo region primitive,
architectural pilot for the discriminated `region_config` IR pattern.

The primitive is deliberately domain-agnostic: school class
(pupils + grades), sales team (reps + quota), engineering team
(engineers + commits), customer cohort (customers + MRR), field crew
(technicians + SLA) all reuse the same shape. The DSL keyword is
`cohort_strip`; the AegisMark spec called it `class_strip` originally
— renamed in v0.67.6 alongside the field generalisation
(pupil_id → member_id, year_form → subtitle, pupil_via → member_via)
so the framework vocabulary stays domain-neutral.

Coverage:
  - IR: CohortStripLens + CohortStripConfig construction, validation,
    DisplayMode.COHORT_STRIP enum value, WorkspaceRegion typed config slot.
  - Primitives: CohortStripCell + CohortStripLensTab + CohortStripRegion
    validation invariants (non-empty ids, exactly-one-active-lens).
  - Renderer: lens-tab markup with HTMX swap, active-lens highlight,
    cell halo + tone, drill-down anchor, empty-state path.
"""

from __future__ import annotations

import pytest

from dazzle.core.ir.workspaces import (
    CohortStripConfig,
    CohortStripLens,
    DisplayMode,
    WorkspaceRegion,
)
from dazzle.render.fragment import (
    URL,
    CohortStripCell,
    CohortStripLensTab,
    CohortStripRegion,
    FragmentRenderer,
)

# ── IR ──


def test_display_mode_includes_cohort_strip() -> None:
    """`DisplayMode.COHORT_STRIP` is registered in the workspace
    region display enum so DSL authors can declare
    `display: cohort_strip` and the parser will accept it."""
    assert DisplayMode.COHORT_STRIP == "cohort_strip"
    assert DisplayMode("cohort_strip") is DisplayMode.COHORT_STRIP


def test_cohort_strip_lens_constructs_with_required_fields() -> None:
    """Minimal lens needs id + label + primary."""
    lens = CohortStripLens(id="attainment", label="Attainment", primary="latest_pct")
    assert lens.id == "attainment"
    assert lens.threshold is None


def test_cohort_strip_lens_threshold_optional_float() -> None:
    """RAG threshold drives the renderer's tone tint per lens."""
    lens = CohortStripLens(
        id="attendance",
        label="Attendance",
        primary="attendance_pct",
        threshold=90.0,
    )
    assert lens.threshold == 90.0


def test_cohort_strip_config_carries_lenses_and_default() -> None:
    """CohortStripConfig is the typed config block on WorkspaceRegion
    when display == COHORT_STRIP."""
    cfg = CohortStripConfig(
        member_via="profile",
        lenses=[
            CohortStripLens(id="attainment", label="Attainment", primary="latest_pct"),
            CohortStripLens(id="attendance", label="Attendance", primary="att_pct"),
        ],
        default_lens="attainment",
    )
    assert cfg.member_via == "profile"
    assert len(cfg.lenses) == 2
    assert cfg.default_lens == "attainment"


def test_workspace_region_carries_cohort_strip_config_slot() -> None:
    """Establishes the discriminated-config pattern — when display is
    COHORT_STRIP, `cohort_strip_config` is populated; otherwise it stays
    None and the region behaves as a generic `WorkspaceRegion`."""
    cfg = CohortStripConfig(
        member_via="profile",
        lenses=[CohortStripLens(id="x", label="X", primary="p")],
    )
    region = WorkspaceRegion(
        name="cohort",
        display=DisplayMode.COHORT_STRIP,
        cohort_strip_config=cfg,
    )
    assert region.cohort_strip_config is cfg
    assert region.display is DisplayMode.COHORT_STRIP


def test_workspace_region_default_cohort_strip_config_is_none() -> None:
    """Generic regions (display != COHORT_STRIP) leave the slot None
    — no schema cost for non-cohort-strip regions."""
    region = WorkspaceRegion(name="x", display=DisplayMode.LIST)
    assert region.cohort_strip_config is None


# ── Primitive validation ──


def test_cohort_strip_cell_validates_non_empty_member_id() -> None:
    with pytest.raises(ValueError, match="member_id"):
        CohortStripCell(member_id="", member_name="A", primary_value="0")


def test_cohort_strip_lens_tab_validates_non_empty_id() -> None:
    with pytest.raises(ValueError, match="non-empty id"):
        CohortStripLensTab(id="", label="X", is_active=True)


def test_cohort_strip_region_requires_non_empty_region_name() -> None:
    with pytest.raises(ValueError, match="region_name"):
        CohortStripRegion(
            region_name="",
            endpoint=URL("/x"),
            lenses=(CohortStripLensTab(id="a", label="A", is_active=True),),
            cells=(),
        )


def test_cohort_strip_region_requires_at_least_one_lens() -> None:
    with pytest.raises(ValueError, match="at least one lens"):
        CohortStripRegion(
            region_name="r",
            endpoint=URL("/x"),
            lenses=(),
            cells=(),
        )


def test_cohort_strip_region_requires_exactly_one_active_lens() -> None:
    """Defensive: zero or two-active-lens states would render an
    inconsistent UI. Constructor catches it."""
    with pytest.raises(ValueError, match="exactly one active lens"):
        # zero active
        CohortStripRegion(
            region_name="r",
            endpoint=URL("/x"),
            lenses=(CohortStripLensTab(id="a", label="A", is_active=False),),
            cells=(),
        )
    with pytest.raises(ValueError, match="exactly one active lens"):
        # two active
        CohortStripRegion(
            region_name="r",
            endpoint=URL("/x"),
            lenses=(
                CohortStripLensTab(id="a", label="A", is_active=True),
                CohortStripLensTab(id="b", label="B", is_active=True),
            ),
            cells=(),
        )


# ── Renderer ──


def _render(strip: CohortStripRegion) -> str:
    return FragmentRenderer().render(strip)


def _strip(**overrides) -> CohortStripRegion:
    base: dict = {
        "region_name": "cohort",
        "endpoint": URL("/api/regions/cohort"),
        "lenses": (
            CohortStripLensTab(id="attainment", label="Attainment", is_active=True),
            CohortStripLensTab(id="attendance", label="Attendance"),
        ),
        "cells": (
            CohortStripCell(
                member_id="p1",
                member_name="Alice Wong",
                subtitle="9G",
                primary_value="78%",
                tone="good",
                drill_url="/members/p1",
            ),
        ),
    }
    base.update(overrides)
    return CohortStripRegion(**base)


def test_render_emits_lens_toggle_with_tablist_role() -> None:
    """Lens toggle is a `<div role="tablist">` of buttons — a11y
    contract that the cohort skim's primary nav is a set of tabs."""
    html = _render(_strip())
    assert 'class="dz-cohort-strip-lenses" role="tablist"' in html
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


def test_render_emits_one_cell_per_member() -> None:
    cells = (
        CohortStripCell(member_id="p1", member_name="Alice", primary_value="78"),
        CohortStripCell(member_id="p2", member_name="Bob", primary_value="62"),
        CohortStripCell(member_id="p3", member_name="Carol", primary_value="45"),
    )
    html = _render(_strip(cells=cells))
    # Three cells.
    assert html.count('data-member-id="p1"') == 1
    assert html.count('data-member-id="p2"') == 1
    assert html.count('data-member-id="p3"') == 1
    assert "Alice" in html and "Bob" in html and "Carol" in html


def test_render_cell_with_drill_url_wraps_in_anchor() -> None:
    """Cells with drill_url become `<a href="...">` so the cell is
    keyboard-navigable + clickable for drill-down to entity_card."""
    html = _render(_strip())
    assert '<a class="dz-cohort-strip-cell" href="/members/p1"' in html


def test_render_cell_without_drill_url_is_plain_div() -> None:
    """Cells without drill_url become plain `<div>` — no hover-link
    state, no keyboard target. Used when the cohort view is the
    terminal node (no entity_card surface to drill into)."""
    html = _render(
        _strip(cells=(CohortStripCell(member_id="p1", member_name="Alice", primary_value="78"),))
    )
    assert '<div class="dz-cohort-strip-cell" data-member-id="p1">' in html
    assert "<a " not in html.split("dz-cohort-strip-cells")[1]


def test_render_cell_emits_dz_tone_data_attribute() -> None:
    """The primary value carries `data-dz-tone="<good|warn|bad|neutral>"`
    so the dz-tones.css CSS rules apply the RAG colouring. Adapter
    sets the tone based on the lens threshold (per-lens semantics)."""
    cells = (
        CohortStripCell(member_id="p1", member_name="Alice", primary_value="78", tone="good"),
        CohortStripCell(member_id="p2", member_name="Bob", primary_value="62", tone="warn"),
        CohortStripCell(member_id="p3", member_name="Carol", primary_value="45", tone="bad"),
        CohortStripCell(member_id="p4", member_name="Dan", primary_value="55"),
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
    cells = (CohortStripCell(member_id="p1", member_name="A", primary_value="0", tone="rainbow"),)
    html = _render(_strip(cells=cells))
    assert 'data-dz-tone="neutral"' in html
    assert 'data-dz-tone="rainbow"' not in html


def test_render_uses_avatar_initials_when_provided() -> None:
    cells = (
        CohortStripCell(
            member_id="p1",
            member_name="Alice Wong",
            primary_value="78",
            avatar_initials="AW",
        ),
    )
    html = _render(_strip(cells=cells))
    assert ">AW</div>" in html


def test_render_synthesises_initials_from_member_name() -> None:
    """Empty `avatar_initials` → renderer uses the first two letters
    of `member_name`, uppercased. Defensive default for adapters that
    don't compute initials upstream."""
    cells = (CohortStripCell(member_id="p1", member_name="alice", primary_value="78"),)
    html = _render(_strip(cells=cells))
    assert ">AL</div>" in html


def test_render_subtitle_appears_when_set() -> None:
    cells = (CohortStripCell(member_id="p1", member_name="A", primary_value="0", subtitle="9G"),)
    html = _render(_strip(cells=cells))
    assert '<div class="dz-cohort-strip-cell-subtitle">9G</div>' in html


def test_render_subtitle_omitted_when_blank() -> None:
    cells = (CohortStripCell(member_id="p1", member_name="A", primary_value="0"),)
    html = _render(_strip(cells=cells))
    assert "dz-cohort-strip-cell-subtitle" not in html


def test_render_empty_cells_emits_empty_message() -> None:
    """Empty cohort renders the configured empty_message (or
    framework default). The lens toggle is still emitted — switching
    lenses might populate the strip."""
    html = _render(_strip(cells=(), empty_message="No members to show."))
    assert 'class="dz-cohort-strip-empty"' in html
    assert "No members to show." in html
    # Lens toggle still present.
    assert 'role="tablist"' in html


def test_render_outer_carries_data_dz_region_name() -> None:
    """`data-dz-region-name` lets the lens-toggle HTMX target find the
    right region wrapper — same convention as DashboardCard."""
    html = _render(_strip())
    assert 'data-dz-region-name="cohort"' in html
    assert 'id="region-cohort-body"' in html


def test_render_escapes_member_name_and_lens_label() -> None:
    """User-supplied display strings escape attribute-context chars."""
    cells = (
        CohortStripCell(
            member_id="p1",
            member_name="<script>alert(1)</script>",
            primary_value="0",
        ),
    )
    lenses = (CohortStripLensTab(id="x", label="<script>", is_active=True),)
    html = _render(_strip(cells=cells, lenses=lenses))
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
