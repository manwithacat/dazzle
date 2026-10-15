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


@pytest.mark.parametrize(
    ("kwargs", "expected_card"),
    [
        pytest.param({}, "", id="card-defaults-empty"),
        pytest.param({"card": "lesson_card"}, "lesson_card", id="card-template-name"),
    ],
)
def test_day_timeline_config_fields(kwargs: dict[str, str], expected_card: str) -> None:
    cfg = DayTimelineConfig(starts_at="period_start", ends_at="period_end", **kwargs)
    assert (cfg.starts_at, cfg.ends_at, cfg.card) == ("period_start", "period_end", expected_card)


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


@pytest.mark.parametrize(
    ("positions", "expected_active"),
    [
        # Before-school / after-school / weekend -> no slot active.
        pytest.param(("before", "after"), [], id="zero-active"),
        pytest.param(("before", "active", "after"), ["s2"], id="exactly-one-active"),
    ],
)
def test_region_accepts_at_most_one_active_slot(
    positions: tuple[str, ...], expected_active: list[str]
) -> None:
    region = DayTimelineRegion(
        region_name="day",
        slots=tuple(
            DayTimelineSlot(slot_id=f"s{i}", label=f"P{i}", position=pos)  # type: ignore[arg-type]
            for i, pos in enumerate(positions, start=1)
        ),
    )
    assert [s.slot_id for s in region.slots if s.position == "active"] == expected_active


def test_region_rejects_multiple_active_slots() -> None:
    with pytest.raises(ValueError, match="active slot"):
        DayTimelineRegion(
            region_name="day",
            slots=(
                DayTimelineSlot(slot_id="s1", label="P1", position="active"),
                DayTimelineSlot(slot_id="s2", label="P2", position="active"),
            ),
        )


# ── Renderer ──


def _one_slot(**slot_kwargs: str) -> DayTimelineRegion:
    slot_kwargs.setdefault("slot_id", "s")
    slot_kwargs.setdefault("label", "P1")
    return DayTimelineRegion(region_name="day", slots=(DayTimelineSlot(**slot_kwargs),))  # type: ignore[arg-type]


def _unknown_position_region() -> DayTimelineRegion:
    """Defensive: if a non-Literal position sneaks past validation, the
    renderer treats it as `after` so the page still emits valid HTML."""
    slot = DayTimelineSlot.__new__(DayTimelineSlot)
    object.__setattr__(slot, "slot_id", "s")
    object.__setattr__(slot, "label", "P1")
    object.__setattr__(slot, "position", "weird")
    object.__setattr__(slot, "body", "")
    object.__setattr__(slot, "drill_url", "")
    object.__setattr__(slot, "action_html", "")
    return DayTimelineRegion(region_name="day", slots=(slot,))


_BODY_HTML = '<span class="lesson-card">Y8 Maths · Room B12</span>'


@pytest.mark.parametrize(
    ("region", "present", "absent"),
    [
        pytest.param(
            DayTimelineRegion(region_name="day", slots=()),
            ['class="dz-day-timeline-region"', 'data-dz-region-name="day"'],
            [],
            id="region-wrapper-with-data-attr",
        ),
        pytest.param(
            DayTimelineRegion(region_name="day", slots=(), empty_message="Nothing today"),
            ['class="dz-day-timeline-empty"', "Nothing today"],
            ["<ol"],
            id="empty-state-for-empty-slots",
        ),
        pytest.param(
            _one_slot(slot_id="s1"),
            ['<ol class="dz-day-timeline-slots">'],
            [],
            id="slots-in-ordered-list",
        ),
        pytest.param(
            DayTimelineRegion(
                region_name="day",
                slots=(
                    DayTimelineSlot(slot_id="s1", label="P1", position="before"),
                    DayTimelineSlot(slot_id="s2", label="P2", position="active"),
                    DayTimelineSlot(slot_id="s3", label="P3", position="after"),
                ),
            ),
            ["is-before", "is-active", "is-after", 'data-dz-position="active"'],
            [],
            id="position-via-class-and-data-attr",
        ),
        pytest.param(
            _one_slot(slot_id="period-3", label="P3"),
            ['data-slot-id="period-3"'],
            [],
            id="slot-id-data-attr",
        ),
        pytest.param(
            _one_slot(label="Period 3 — 11:30"),
            ["Period 3 — 11:30"],
            [],
            id="slot-label",
        ),
        pytest.param(
            _one_slot(drill_url="/lesson/123"),
            ['<a class="dz-day-timeline-slot is-after"', 'href="/lesson/123"'],
            [],
            id="drill-url-wraps-slot-in-anchor",
        ),
        pytest.param(
            _one_slot(),
            ['<div class="dz-day-timeline-slot is-after"'],
            ['href="'],
            id="no-drill-url-no-anchor",
        ),
        # The adapter owns body HTML safety; the primitive does not double-escape.
        pytest.param(
            _one_slot(body=_BODY_HTML), [_BODY_HTML], [], id="pre-rendered-body-passthrough"
        ),
        pytest.param(
            _one_slot(label="<script>x</script>"),
            ["&lt;script&gt;"],
            ["<script>"],
            id="escapes-label",
        ),
        pytest.param(
            _one_slot(drill_url='/x"><script>'),
            ['href="/x&quot;&gt;&lt;script&gt;"'],
            ['"><script>'],
            id="escapes-drill-url",
        ),
        pytest.param(
            DayTimelineRegion(region_name='x"><svg', slots=()),
            ['data-dz-region-name="x&quot;&gt;&lt;svg"'],
            ['"><svg'],
            id="escapes-region-name",
        ),
        pytest.param(
            DayTimelineRegion(region_name="day", slots=(), empty_message="<b>none</b>"),
            ["&lt;b&gt;"],
            ["<b>none</b>"],
            id="escapes-empty-message",
        ),
        pytest.param(
            _unknown_position_region(),
            ["is-after", 'data-dz-position="after"'],
            ["weird"],
            id="unknown-position-falls-through-to-after",
        ),
    ],
)
def test_renderer_markup(region: DayTimelineRegion, present: list[str], absent: list[str]) -> None:
    html = FragmentRenderer().render(region)
    for needle in present:
        assert needle in html
    for needle in absent:
        assert needle not in html
