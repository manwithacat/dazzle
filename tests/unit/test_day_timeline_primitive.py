"""Issue #1016 (v0.67.3): regression tests for the `day_timeline`
region primitive — second AegisMark Day-One demo region primitive,
follows the discriminated `region_config` IR pattern landed by #1018.

Coverage:
  - IR: DayTimelineConfig construction + validation, DisplayMode.DAY_TIMELINE
    enum value, WorkspaceRegion typed config slot.
  - Primitives: DayTimelineSlot + DayTimelineRegion validation invariants
    (non-empty slot_id, at most one active slot).
  - Renderer: slot markup with position class + data attr, active-slot
    highlight, drill-down anchor, empty-state path, escape safety.
"""

from __future__ import annotations

import pytest

from dazzle.core.ir.workspaces import (
    DayTimelineConfig,
    DisplayMode,
    WorkspaceRegion,
)
from dazzle.render.fragment import (
    DayTimelineRegion,
    DayTimelineSlot,
    FragmentRenderer,
)

# ── IR ──


def test_display_mode_includes_day_timeline() -> None:
    assert DisplayMode.DAY_TIMELINE == "day_timeline"
    assert DisplayMode("day_timeline") is DisplayMode.DAY_TIMELINE


def test_day_timeline_config_constructs_with_required_fields() -> None:
    cfg = DayTimelineConfig(starts_at="period_start", ends_at="period_end")
    assert cfg.starts_at == "period_start"
    assert cfg.ends_at == "period_end"
    assert cfg.card == ""


def test_day_timeline_config_carries_card_template_name() -> None:
    cfg = DayTimelineConfig(starts_at="t0", ends_at="t1", card="lesson_card")
    assert cfg.card == "lesson_card"


def test_workspace_region_carries_typed_config_slot() -> None:
    cfg = DayTimelineConfig(starts_at="starts_at", ends_at="ends_at")
    region = WorkspaceRegion(
        name="today",
        source="TimetableSlot",
        display=DisplayMode.DAY_TIMELINE,
        day_timeline_config=cfg,
    )
    assert region.day_timeline_config is cfg
    assert region.cohort_strip_config is None


def test_workspace_region_typed_config_slot_defaults_to_none() -> None:
    region = WorkspaceRegion(name="r", display=DisplayMode.LIST)
    assert region.day_timeline_config is None


# ── Primitive invariants ──


def test_slot_rejects_empty_id() -> None:
    with pytest.raises(ValueError, match="slot_id"):
        DayTimelineSlot(slot_id="", label="P1")


def test_slot_position_defaults_to_after() -> None:
    slot = DayTimelineSlot(slot_id="s", label="L")
    assert slot.position == "after"


def test_region_rejects_empty_region_name() -> None:
    with pytest.raises(ValueError, match="region_name"):
        DayTimelineRegion(region_name="", slots=())


def test_region_permits_zero_active_slots() -> None:
    """Before-school / after-school / weekend → no slot active."""
    region = DayTimelineRegion(
        region_name="day",
        slots=(
            DayTimelineSlot(slot_id="s1", label="P1", position="before"),
            DayTimelineSlot(slot_id="s2", label="P2", position="after"),
        ),
    )
    assert sum(1 for s in region.slots if s.position == "active") == 0


def test_region_rejects_multiple_active_slots() -> None:
    with pytest.raises(ValueError, match="active slot"):
        DayTimelineRegion(
            region_name="day",
            slots=(
                DayTimelineSlot(slot_id="s1", label="P1", position="active"),
                DayTimelineSlot(slot_id="s2", label="P2", position="active"),
            ),
        )


def test_region_accepts_exactly_one_active_slot() -> None:
    region = DayTimelineRegion(
        region_name="day",
        slots=(
            DayTimelineSlot(slot_id="s1", label="P1", position="before"),
            DayTimelineSlot(slot_id="s2", label="P2", position="active"),
            DayTimelineSlot(slot_id="s3", label="P3", position="after"),
        ),
    )
    assert sum(1 for s in region.slots if s.position == "active") == 1


# ── Renderer ──


def _render(fragment: object) -> str:
    return FragmentRenderer().render(fragment)  # type: ignore[arg-type]


def test_renderer_emits_region_wrapper_with_data_attr() -> None:
    region = DayTimelineRegion(region_name="day", slots=())
    html = _render(region)
    assert 'class="dz-day-timeline-region"' in html
    assert 'data-dz-region-name="day"' in html


def test_renderer_emits_empty_state_for_empty_slots() -> None:
    region = DayTimelineRegion(region_name="day", slots=(), empty_message="Nothing today")
    html = _render(region)
    assert 'class="dz-day-timeline-empty"' in html
    assert "Nothing today" in html
    assert "<ol" not in html


def test_renderer_wraps_slots_in_ordered_list() -> None:
    region = DayTimelineRegion(
        region_name="day",
        slots=(DayTimelineSlot(slot_id="s1", label="P1"),),
    )
    html = _render(region)
    assert '<ol class="dz-day-timeline-slots">' in html


def test_renderer_marks_position_via_class_and_data_attr() -> None:
    region = DayTimelineRegion(
        region_name="day",
        slots=(
            DayTimelineSlot(slot_id="s1", label="P1", position="before"),
            DayTimelineSlot(slot_id="s2", label="P2", position="active"),
            DayTimelineSlot(slot_id="s3", label="P3", position="after"),
        ),
    )
    html = _render(region)
    assert "is-before" in html
    assert "is-active" in html
    assert "is-after" in html
    assert 'data-dz-position="active"' in html


def test_renderer_includes_slot_id_data_attr() -> None:
    region = DayTimelineRegion(
        region_name="day",
        slots=(DayTimelineSlot(slot_id="period-3", label="P3"),),
    )
    html = _render(region)
    assert 'data-slot-id="period-3"' in html


def test_renderer_renders_slot_label() -> None:
    region = DayTimelineRegion(
        region_name="day",
        slots=(DayTimelineSlot(slot_id="s", label="Period 3 — 11:30"),),
    )
    html = _render(region)
    assert "Period 3" in html


def test_renderer_drill_url_wraps_slot_in_anchor() -> None:
    region = DayTimelineRegion(
        region_name="day",
        slots=(DayTimelineSlot(slot_id="s", label="P1", drill_url="/lesson/123"),),
    )
    html = _render(region)
    assert '<a class="dz-day-timeline-slot is-after"' in html
    assert 'href="/lesson/123"' in html


def test_renderer_omits_anchor_when_no_drill_url() -> None:
    region = DayTimelineRegion(
        region_name="day",
        slots=(DayTimelineSlot(slot_id="s", label="P1"),),
    )
    html = _render(region)
    assert '<div class="dz-day-timeline-slot is-after"' in html
    assert 'href="' not in html


def test_renderer_passes_through_pre_rendered_body() -> None:
    """The adapter is responsible for body HTML safety; the
    primitive does not double-escape pre-rendered fragments."""
    body_html = '<span class="lesson-card">Y8 Maths · Room B12</span>'
    region = DayTimelineRegion(
        region_name="day",
        slots=(DayTimelineSlot(slot_id="s", label="P1", body=body_html),),
    )
    html = _render(region)
    assert body_html in html


def test_renderer_escapes_label() -> None:
    region = DayTimelineRegion(
        region_name="day",
        slots=(DayTimelineSlot(slot_id="s", label="<script>x</script>"),),
    )
    html = _render(region)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_renderer_escapes_drill_url() -> None:
    region = DayTimelineRegion(
        region_name="day",
        slots=(DayTimelineSlot(slot_id="s", label="P1", drill_url='/x"><script>'),),
    )
    html = _render(region)
    assert '"><script>' not in html
    assert "&quot;" in html or "&#34;" in html


def test_renderer_escapes_region_name() -> None:
    region = DayTimelineRegion(region_name='x"><svg', slots=())
    html = _render(region)
    assert '"><svg' not in html


def test_renderer_escapes_empty_message() -> None:
    region = DayTimelineRegion(region_name="day", slots=(), empty_message="<b>none</b>")
    html = _render(region)
    assert "<b>none</b>" not in html
    assert "&lt;b&gt;" in html


def test_renderer_unknown_position_falls_through_to_after() -> None:
    """Defensive: if a non-Literal value sneaks in, the renderer
    treats it as `after` so the page still emits valid HTML."""
    slot = DayTimelineSlot.__new__(DayTimelineSlot)
    object.__setattr__(slot, "slot_id", "s")
    object.__setattr__(slot, "label", "P1")
    object.__setattr__(slot, "position", "weird")
    object.__setattr__(slot, "body", "")
    object.__setattr__(slot, "drill_url", "")
    region = DayTimelineRegion(region_name="day", slots=(slot,))
    html = _render(region)
    assert "is-after" in html
    assert 'data-dz-position="after"' in html
