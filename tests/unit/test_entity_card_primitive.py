"""Issue #1017 (v0.67.5): regression tests for the `entity_card`
region primitive — fourth AegisMark Day-One demo region primitive,
follows the discriminated `region_config` IR pattern from #1018.

The primitive is deliberately domain-agnostic: pupil-360 in MIS,
customer-360 in CRM, asset-360 in field-ops, patient-360 in healthcare
all reuse the same shape. The DSL keyword is `entity_card`; the AegisMark
spec called it `pupil_card` originally — generalised before ship per
review feedback ("might be worth pondering ways to generalise them to
items").

Coverage:
  - IR: EntityCardSectionMode + EntityCardSection + EntityCardConfig
    construction and defaults, DisplayMode.ENTITY_CARD enum,
    WorkspaceRegion typed config slot.
  - Primitives: EntityCardSection + EntityCardRegion validation
    invariants.
  - Renderer: section composition, mode + column data attrs,
    is_omitted skip, drill anchors via section bodies (adapter-owned),
    empty-state path, escape safety.
"""

from __future__ import annotations

import pytest

from dazzle.core.ir.workspaces import (
    DisplayMode,
    EntityCardConfig,
    EntityCardSectionMode,
    WorkspaceRegion,
)
from dazzle.core.ir.workspaces import (
    EntityCardSection as IREntityCardSection,
)
from dazzle.render.fragment import (
    EntityCardRegion,
    EntityCardSection,
    FragmentRenderer,
)

# ── IR ──


def test_display_mode_includes_entity_card() -> None:
    assert DisplayMode.ENTITY_CARD == "entity_card"
    assert DisplayMode("entity_card") is DisplayMode.ENTITY_CARD


def test_section_mode_enum_values() -> None:
    assert EntityCardSectionMode.HALO == "halo"
    assert EntityCardSectionMode.FLAGS == "flags"
    assert EntityCardSectionMode.MINI_BARS == "mini_bars"
    assert EntityCardSectionMode.STAMPS == "stamps"
    assert EntityCardSectionMode.THREAD_SUMMARY == "thread_summary"
    assert EntityCardSectionMode.QUICK_ACTIONS == "quick_actions"


def test_ir_section_constructs_with_required_fields() -> None:
    s = IREntityCardSection(name="halo", mode=EntityCardSectionMode.HALO)
    assert s.name == "halo"
    assert s.source is None
    assert s.filter is None
    assert s.fields == []
    assert s.actions == []


def test_ir_section_carries_source_filter_limit_fields() -> None:
    s = IREntityCardSection(
        name="recent_marks",
        mode=EntityCardSectionMode.MINI_BARS,
        source="ManuscriptFeedback",
        limit=5,
        fields=["score", "date"],
    )
    assert s.source == "ManuscriptFeedback"
    assert s.limit == 5
    assert s.fields == ["score", "date"]


def test_ir_section_quick_actions_carries_action_list() -> None:
    s = IREntityCardSection(
        name="quick_actions",
        mode=EntityCardSectionMode.QUICK_ACTIONS,
        actions=["log_behaviour", "message_parent", "open_in_fastmark"],
    )
    assert len(s.actions) == 3


def test_config_default_scope_param_is_generic() -> None:
    """Default `scope_param` is `id` — domain-agnostic. Per-domain
    DSL authors override to `pupil_id`, `customer_id`, etc."""
    cfg = EntityCardConfig(sections=[])
    assert cfg.scope_param == "id"


def test_config_carries_sections_and_custom_scope_param() -> None:
    cfg = EntityCardConfig(
        scope_param="pupil_id",
        sections=[
            IREntityCardSection(name="halo", mode=EntityCardSectionMode.HALO),
            IREntityCardSection(name="flags", mode=EntityCardSectionMode.FLAGS),
        ],
    )
    assert cfg.scope_param == "pupil_id"
    assert len(cfg.sections) == 2


def test_workspace_region_typed_config_slot() -> None:
    cfg = EntityCardConfig(sections=[])
    region = WorkspaceRegion(
        name="pupil",
        display=DisplayMode.ENTITY_CARD,
        entity_card_config=cfg,
    )
    assert region.entity_card_config is cfg
    assert region.task_inbox_config is None
    assert region.day_timeline_config is None
    assert region.class_strip_config is None


def test_workspace_region_typed_config_slot_defaults_to_none() -> None:
    region = WorkspaceRegion(name="r", display=DisplayMode.LIST)
    assert region.entity_card_config is None


# ── Primitive invariants ──


def test_section_rejects_empty_id() -> None:
    with pytest.raises(ValueError, match="section_id"):
        EntityCardSection(section_id="", label="L")


def test_section_defaults_to_main_column_and_halo_mode() -> None:
    s = EntityCardSection(section_id="s", label="L")
    assert s.column == "main"
    assert s.mode == "halo"
    assert s.is_omitted is False


def test_region_rejects_empty_region_name() -> None:
    with pytest.raises(ValueError, match="region_name"):
        EntityCardRegion(region_name="", sections=())


# ── Renderer ──


def _render(fragment: object) -> str:
    return FragmentRenderer().render(fragment)  # type: ignore[arg-type]


def test_renderer_emits_region_wrapper_with_data_attr() -> None:
    region = EntityCardRegion(region_name="pupil", sections=())
    html = _render(region)
    assert 'class="dz-entity-card-region"' in html
    assert 'data-dz-region-name="pupil"' in html


def test_renderer_emits_empty_state_when_no_sections() -> None:
    region = EntityCardRegion(region_name="card", sections=())
    html = _render(region)
    assert 'class="dz-entity-card-empty"' in html
    assert "No record context" in html


def test_renderer_emits_optional_record_label_heading() -> None:
    region = EntityCardRegion(
        region_name="card",
        sections=(EntityCardSection(section_id="s", label="L"),),
        record_label="Alice Bayard · Year 8",
    )
    html = _render(region)
    assert 'class="dz-entity-card-heading"' in html
    assert "Alice Bayard" in html


def test_renderer_omits_heading_when_record_label_empty() -> None:
    region = EntityCardRegion(
        region_name="card",
        sections=(EntityCardSection(section_id="s", label="L"),),
    )
    html = _render(region)
    assert "dz-entity-card-heading" not in html


def test_renderer_emits_one_section_per_non_omitted() -> None:
    region = EntityCardRegion(
        region_name="card",
        sections=(
            EntityCardSection(section_id="halo", label="Halo"),
            EntityCardSection(section_id="flags", label="Flags", mode="flags"),
            EntityCardSection(section_id="opt", label="Optional", is_omitted=True),
        ),
    )
    html = _render(region)
    assert 'data-section-id="halo"' in html
    assert 'data-section-id="flags"' in html
    assert 'data-section-id="opt"' not in html


def test_renderer_includes_mode_and_column_data_attrs() -> None:
    region = EntityCardRegion(
        region_name="card",
        sections=(
            EntityCardSection(section_id="m", label="Marks", mode="mini_bars", column="main"),
            EntityCardSection(section_id="s", label="Stamps", mode="stamps", column="sidebar"),
        ),
    )
    html = _render(region)
    assert 'data-dz-mode="mini_bars"' in html
    assert 'data-dz-column="main"' in html
    assert 'data-dz-mode="stamps"' in html
    assert 'data-dz-column="sidebar"' in html


def test_renderer_passes_through_pre_rendered_section_body() -> None:
    body_html = '<ul class="marks"><li>78%</li></ul>'
    region = EntityCardRegion(
        region_name="card",
        sections=(EntityCardSection(section_id="m", label="Marks", body=body_html),),
    )
    html = _render(region)
    assert body_html in html


def test_renderer_unknown_mode_falls_through_to_halo() -> None:
    section = EntityCardSection.__new__(EntityCardSection)
    object.__setattr__(section, "section_id", "x")
    object.__setattr__(section, "label", "X")
    object.__setattr__(section, "mode", "weird")
    object.__setattr__(section, "body", "")
    object.__setattr__(section, "column", "main")
    object.__setattr__(section, "is_omitted", False)
    region = EntityCardRegion(region_name="card", sections=(section,))
    html = _render(region)
    assert 'data-dz-mode="halo"' in html


def test_renderer_unknown_column_falls_through_to_main() -> None:
    section = EntityCardSection.__new__(EntityCardSection)
    object.__setattr__(section, "section_id", "x")
    object.__setattr__(section, "label", "X")
    object.__setattr__(section, "mode", "halo")
    object.__setattr__(section, "body", "")
    object.__setattr__(section, "column", "weird")
    object.__setattr__(section, "is_omitted", False)
    region = EntityCardRegion(region_name="card", sections=(section,))
    html = _render(region)
    assert 'data-dz-column="main"' in html


def test_renderer_escapes_label_and_record_label_and_region_name() -> None:
    region = EntityCardRegion(
        region_name='r"><script>',
        sections=(EntityCardSection(section_id="s", label="<x>"),),
        record_label="<rec>",
    )
    html = _render(region)
    assert '"><script>' not in html
    assert "<x>" not in html  # but <x> as text not as tag
    assert "&lt;x&gt;" in html
    assert "<rec>" not in html
