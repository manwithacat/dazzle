"""Cycle 1617 — dashboard drill open discovery (task-inbox / cohort / day-timeline)."""

from __future__ import annotations

from dazzle.render.fragment.ingest.emit import drill_open_discovery_attrs
from dazzle.render.fragment.primitives.data import (
    CohortStripCell,
    CohortStripLensTab,
    CohortStripRegion,
    DayTimelineRegion,
    DayTimelineSlot,
    TaskInboxItem,
    TaskInboxRegion,
    TaskInboxSummaryChip,
)
from dazzle.render.fragment.renderer import FragmentRenderer


def test_drill_open_discovery_attrs_single_anchor() -> None:
    attrs = drill_open_discovery_attrs("/app/ticket/t-9")
    assert 'data-dz-open-entity="Ticket"' in attrs
    assert 'data-dz-open-via="id"' in attrs
    assert 'data-dz-open-chain="/app/ticket/t-9"' in attrs
    assert 'data-dz-open-hops="1"' in attrs
    assert "Open Ticket" in attrs


def test_task_inbox_item_drill_stamps_open_discovery() -> None:
    html = FragmentRenderer().render(
        TaskInboxRegion(
            region_name="inbox",
            items=(
                TaskInboxItem(
                    item_id="i1",
                    icon="check",
                    title="Review refund",
                    drill_url="/app/ticket/t-1",
                ),
            ),
            summary_chips=(
                TaskInboxSummaryChip(
                    chip_id="overdue",
                    count=2,
                    label="overdue",
                    drill_url="/app/ticket",
                ),
            ),
        )
    )
    assert "data-dz-task-inbox-drill" in html
    assert 'data-dz-open-entity="Ticket"' in html
    assert 'data-dz-open-chain="/app/ticket/t-1"' in html
    assert 'href="/app/ticket/t-1"' in html
    # Chip also stamped (list-ish drill still gets attrs)
    assert html.count("data-dz-task-inbox-drill") >= 2


def test_cohort_strip_cell_drill_stamps_open_discovery() -> None:
    html = FragmentRenderer().render(
        CohortStripRegion(
            region_name="cohort",
            endpoint="/app/regions/cohort",
            lenses=(CohortStripLensTab(id="score", label="Score", is_active=True),),
            cells=(
                CohortStripCell(
                    member_id="m1",
                    member_name="Ada",
                    primary_value="92",
                    drill_url="/app/person/p-1",
                ),
            ),
        )
    )
    assert "data-dz-cohort-drill" in html
    assert 'data-dz-open-entity="Person"' in html
    assert 'data-dz-open-chain="/app/person/p-1"' in html


def test_day_timeline_slot_drill_stamps_open_discovery() -> None:
    html = FragmentRenderer().render(
        DayTimelineRegion(
            region_name="day",
            slots=(
                DayTimelineSlot(
                    slot_id="s1",
                    label="Period 1",
                    position="active",
                    body="<p>Maths</p>",
                    drill_url="/app/timetable-slot/ts-1",
                ),
            ),
        )
    )
    assert "data-dz-day-timeline-drill" in html
    assert 'data-dz-open-entity="Timetable slot"' in html or "Timetable" in html
    assert 'data-dz-open-chain="/app/timetable-slot/ts-1"' in html
