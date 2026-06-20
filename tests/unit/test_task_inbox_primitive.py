"""Issue #1015 (v0.67.4): regression tests for the `task_inbox`
region primitive — third AegisMark Day-One demo region primitive,
follows the discriminated `region_config` IR pattern from #1018.

Coverage:
  - IR: TaskSourceTemplate + TaskSource + TaskInboxConfig
    construction and defaults, DisplayMode.TASK_INBOX enum,
    WorkspaceRegion typed config slot.
  - Primitives: TaskInboxItem + TaskInboxSummaryChip + TaskInboxRegion
    validation invariants.
  - Renderer: items list, summary-chips row, urgency tone, drill
    anchors, empty-state path, escape safety.
"""

from __future__ import annotations

import pytest

from dazzle.core.ir.workspaces import (
    DisplayMode,
    TaskInboxConfig,
    TaskSource,
    TaskSourceTemplate,
    WorkspaceRegion,
)
from dazzle.render.fragment import (
    FragmentRenderer,
    TaskInboxItem,
    TaskInboxRegion,
    TaskInboxSummaryChip,
)

# ── IR ──


def test_display_mode_includes_task_inbox() -> None:
    assert DisplayMode.TASK_INBOX == "task_inbox"
    assert DisplayMode("task_inbox") is DisplayMode.TASK_INBOX


def test_task_source_template_constructs_with_required_fields() -> None:
    tpl = TaskSourceTemplate(icon="register", title="Register {class.name}")
    assert tpl.icon == "register"
    assert tpl.meta == ""


def test_task_source_carries_optional_filter_and_template() -> None:
    tpl = TaskSourceTemplate(icon="pupil", title="Follow up: {pupil}")
    src = TaskSource(source="BehaviourIncident", as_task=tpl)
    assert src.source == "BehaviourIncident"
    assert src.as_task is tpl
    assert src.count_as == ""
    assert src.filter is None


def test_task_source_count_as_alternative() -> None:
    src = TaskSource(source="ManuscriptFeedback", count_as="manuscripts ready to review")
    assert src.count_as == "manuscripts ready to review"
    assert src.as_task is None


def test_task_inbox_config_default_order_and_empty_state() -> None:
    cfg = TaskInboxConfig(sources=[])
    assert cfg.order == ["urgency", "deadline"]
    assert cfg.empty_state == "All caught up."
    assert cfg.sources == []


def test_task_inbox_config_carries_sources() -> None:
    cfg = TaskInboxConfig(
        sources=[
            TaskSource(
                source="AssessmentEvent",
                as_task=TaskSourceTemplate(icon="register", title="Register {class}"),
            ),
            TaskSource(source="ManuscriptFeedback", count_as="manuscripts ready"),
        ],
        order=["deadline"],
        empty_state="Nothing to do.",
    )
    assert len(cfg.sources) == 2
    assert cfg.order == ["deadline"]


def test_workspace_region_typed_config_slot() -> None:
    cfg = TaskInboxConfig(sources=[])
    region = WorkspaceRegion(name="today", display=DisplayMode.TASK_INBOX, task_inbox_config=cfg)
    assert region.task_inbox_config is cfg
    assert region.day_timeline_config is None
    assert region.cohort_strip_config is None


def test_workspace_region_typed_config_slot_defaults_to_none() -> None:
    region = WorkspaceRegion(name="r", display=DisplayMode.LIST)
    assert region.task_inbox_config is None


# ── Primitive invariants ──


def test_item_rejects_empty_id() -> None:
    with pytest.raises(ValueError, match="item_id"):
        TaskInboxItem(item_id="", icon="x", title="x")


def test_item_urgency_defaults_to_later() -> None:
    item = TaskInboxItem(item_id="i", icon="x", title="t")
    assert item.urgency == "later"


def test_summary_chip_rejects_empty_id() -> None:
    with pytest.raises(ValueError, match="chip_id"):
        TaskInboxSummaryChip(chip_id="", count=3, label="x")


def test_summary_chip_rejects_negative_count() -> None:
    with pytest.raises(ValueError, match="count"):
        TaskInboxSummaryChip(chip_id="c", count=-1, label="x")


def test_summary_chip_accepts_zero_count() -> None:
    """Zero is permitted so adapters can emit empty chips when a
    `count_as` source resolves zero rows; the renderer's empty-state
    path is keyed on items+chips both being empty."""
    chip = TaskInboxSummaryChip(chip_id="c", count=0, label="manuscripts ready")
    assert chip.count == 0


def test_region_rejects_empty_region_name() -> None:
    with pytest.raises(ValueError, match="region_name"):
        TaskInboxRegion(region_name="", items=())


# ── Renderer ──


def _render(fragment: object) -> str:
    return FragmentRenderer().render(fragment)  # type: ignore[arg-type]


def test_renderer_emits_region_wrapper_with_data_attr() -> None:
    region = TaskInboxRegion(region_name="today", items=())
    html = _render(region)
    assert 'class="dz-task-inbox-region"' in html
    assert 'data-dz-region-name="today"' in html


def test_renderer_emits_empty_state_when_no_items_and_no_chips() -> None:
    region = TaskInboxRegion(region_name="today", items=(), empty_message="All caught up.")
    html = _render(region)
    assert 'class="dz-task-inbox-empty"' in html
    assert "All caught up." in html
    assert "<ul" not in html


def test_renderer_omits_empty_state_when_only_chips_present() -> None:
    """Chips-only region renders just the chip row; no empty-state
    paragraph and no items list (the chips ARE the content)."""
    region = TaskInboxRegion(
        region_name="today",
        items=(),
        summary_chips=(TaskInboxSummaryChip(chip_id="c1", count=3, label="manuscripts ready"),),
    )
    html = _render(region)
    assert "dz-task-inbox-empty" not in html
    assert "dz-task-inbox-chip" in html
    assert "<ul" not in html


def test_renderer_renders_items_list() -> None:
    region = TaskInboxRegion(
        region_name="today",
        items=(
            TaskInboxItem(item_id="i1", icon="register", title="Register 8X"),
            TaskInboxItem(item_id="i2", icon="message", title="Reply to parent"),
        ),
    )
    html = _render(region)
    assert '<ul class="dz-task-inbox-items">' in html
    assert "Register 8X" in html
    assert "Reply to parent" in html


def test_renderer_includes_urgency_tone_data_attr() -> None:
    region = TaskInboxRegion(
        region_name="today",
        items=(
            TaskInboxItem(item_id="i1", icon="x", title="t1", urgency="overdue"),
            TaskInboxItem(item_id="i2", icon="x", title="t2", urgency="due"),
            TaskInboxItem(item_id="i3", icon="x", title="t3", urgency="soon"),
            TaskInboxItem(item_id="i4", icon="x", title="t4", urgency="later"),
        ),
    )
    html = _render(region)
    assert 'data-dz-urgency="overdue"' in html
    assert 'data-dz-urgency="due"' in html
    assert 'data-dz-urgency="soon"' in html
    assert 'data-dz-urgency="later"' in html


def test_renderer_includes_icon_token() -> None:
    region = TaskInboxRegion(
        region_name="today",
        items=(TaskInboxItem(item_id="i", icon="register", title="t"),),
    )
    html = _render(region)
    assert 'data-icon="register"' in html


def test_renderer_renders_optional_meta_only_when_present() -> None:
    region = TaskInboxRegion(
        region_name="today",
        items=(
            TaskInboxItem(item_id="a", icon="x", title="t1"),  # no meta
            TaskInboxItem(item_id="b", icon="x", title="t2", meta="Period 3"),
        ),
    )
    html = _render(region)
    assert "Period 3" in html
    # First item should not contain a meta div
    first_li_end = html.index("dz-task-inbox-item-meta")
    first_li_start = html.index('data-item-id="a"')
    # meta div for second item must appear AFTER first item's </li>
    assert first_li_end > first_li_start + 100  # comfortable buffer past first item


def test_renderer_drill_url_wraps_item_in_anchor() -> None:
    region = TaskInboxRegion(
        region_name="today",
        items=(TaskInboxItem(item_id="i", icon="x", title="t", drill_url="/s/123"),),
    )
    html = _render(region)
    assert '<a class="dz-task-inbox-item-link" href="/s/123">' in html


def test_renderer_omits_anchor_when_no_drill_url() -> None:
    region = TaskInboxRegion(
        region_name="today",
        items=(TaskInboxItem(item_id="i", icon="x", title="t"),),
    )
    html = _render(region)
    assert "dz-task-inbox-item-link" not in html


def test_renderer_summary_chips_above_items() -> None:
    region = TaskInboxRegion(
        region_name="today",
        items=(TaskInboxItem(item_id="i", icon="x", title="t"),),
        summary_chips=(TaskInboxSummaryChip(chip_id="c", count=3, label="manuscripts"),),
    )
    html = _render(region)
    chip_pos = html.index("dz-task-inbox-chips")
    items_pos = html.index("dz-task-inbox-items")
    assert chip_pos < items_pos


def test_renderer_summary_chip_count_and_label() -> None:
    region = TaskInboxRegion(
        region_name="today",
        items=(),
        summary_chips=(TaskInboxSummaryChip(chip_id="c1", count=7, label="manuscripts ready"),),
    )
    html = _render(region)
    assert ">7<" in html
    assert "manuscripts ready" in html


def test_renderer_summary_chip_drill_wraps_in_anchor() -> None:
    region = TaskInboxRegion(
        region_name="today",
        items=(),
        summary_chips=(TaskInboxSummaryChip(chip_id="c", count=3, label="x", drill_url="/list"),),
    )
    html = _render(region)
    assert '<a class="dz-task-inbox-chip" href="/list"' in html


def test_renderer_unknown_urgency_falls_through_to_later() -> None:
    item = TaskInboxItem.__new__(TaskInboxItem)
    object.__setattr__(item, "item_id", "i")
    object.__setattr__(item, "icon", "x")
    object.__setattr__(item, "title", "t")
    object.__setattr__(item, "meta", "")
    object.__setattr__(item, "urgency", "weird")
    object.__setattr__(item, "drill_url", "")
    region = TaskInboxRegion(region_name="today", items=(item,))
    html = _render(region)
    assert 'data-dz-urgency="later"' in html


def test_renderer_escapes_title_meta_label() -> None:
    region = TaskInboxRegion(
        region_name="today",
        items=(TaskInboxItem(item_id="i", icon="x", title="<x>", meta="<m>", urgency="due"),),
        summary_chips=(TaskInboxSummaryChip(chip_id="c", count=1, label="<l>"),),
    )
    html = _render(region)
    assert "<x>" not in html
    assert "<m>" not in html
    assert "<l>" not in html
    assert "&lt;x&gt;" in html


def test_renderer_escapes_drill_urls_and_region_name() -> None:
    region = TaskInboxRegion(
        region_name='r"><script>',
        items=(TaskInboxItem(item_id="i", icon="x", title="t", drill_url='"><svg'),),
        summary_chips=(TaskInboxSummaryChip(chip_id="c", count=1, label="x", drill_url='"><img>'),),
    )
    html = _render(region)
    assert '"><script>' not in html
    assert '"><svg' not in html
    assert '"><img>' not in html


# ── CSS (#1326) ──


def _regions_css() -> str:
    from pathlib import Path

    import dazzle.page as dazzle_page

    css_path = (
        Path(dazzle_page.__file__).parent
        / "runtime"
        / "static"
        / "css"
        / "components"
        / "regions.css"
    )
    return css_path.read_text(encoding="utf-8")


def test_task_inbox_chip_has_count_label_separator_css() -> None:
    """#1326: the chip rendered count + label glued together ("0manuscripts")
    because the `.dz-task-inbox-chip*` family had NO css. The chip must now
    style a separator (inline-flex + gap) between the count and label spans."""
    css = _regions_css()
    # The chip rule exists and is an inline-flex pill with a gap (the gap is
    # what separates the count span from the label span).
    chip_idx = css.find(".dz-task-inbox-chip {")
    assert chip_idx != -1, ".dz-task-inbox-chip rule missing"
    rule = css[chip_idx : css.find("}", chip_idx)]
    assert "inline-flex" in rule
    assert "gap:" in rule


def test_task_inbox_chip_count_and_label_styled() -> None:
    """The count and label spans each have a rule, so the chip reads as a
    proper pill rather than unstyled glued text."""
    css = _regions_css()
    assert ".dz-task-inbox-chip-count {" in css
    assert ".dz-task-inbox-chip-label {" in css
