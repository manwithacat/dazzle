"""Phase 4B.5.b.2.ii (v0.66.122): byte-equivalence + structural tests
for the typed `DashboardGrid` + `DashboardCard` + `DashboardNotice`
primitives.

Five dual-path tests pin byte-equivalence vs the literal `_content.html`
card-grid block: basic two-card / SSE-enabled / empty grid / notice-
without-body / css_class. Plus structural assertions on every
contract attribute the dashboard JS, idiomorph, contract checker,
and harness key off."""

from __future__ import annotations

import pytest

from dazzle.render.fragment import (
    DashboardCard,
    DashboardGrid,
    DashboardNotice,
    FragmentRenderer,
)
from dazzle_back.runtime.renderers.dual_path import diff_summary
from dazzle_ui.runtime.template_renderer import create_jinja_env

# Legacy `_content.html` card-grid block (lines 149-211) extracted
# verbatim. Pinned here so any drift between the typed primitives
# and the legacy template is caught immediately.
_LEGACY_GRID_TEMPLATE = """<div class="dz-dashboard-grid"
       data-grid-container
       role="application"
       aria-label="Dashboard card grid"
       {% if workspace.sse_url %}hx-ext="sse" sse-connect="{{ workspace.sse_url }}"{% endif %}>
    {%- for r in workspace.regions %}
    {%- set _card_id = 'card-' ~ loop.index0 %}
    {%- set _eager = loop.index0 < (fold_count or 0) %}
    {%- set _trigger = 'load' if _eager else 'intersect once' %}
    {%- if workspace.sse_url %}
    {%- set _trigger = _trigger ~ ', sse:entity.created, sse:entity.updated, sse:entity.deleted' %}
    {%- endif %}
    <div data-card-id="{{ _card_id }}" data-card-region="{{ r.name }}" data-card-col-span="{{ r.col_span }}" data-card-row-order="{{ loop.index0 }}" class="dz-card-wrapper{% if r.css_class %} {{ r.css_class }}{% endif %} is-animating" style="grid-column: span {{ r.col_span }} / span {{ r.col_span }};" tabindex="0">
      <article class="dz-card" role="article" aria-labelledby="card-title-{{ _card_id }}">
        <div class="dz-card-header" data-test-id="dz-card-drag-handle">
          <div class="dz-card-titles">
            {%- if r.eyebrow %}<span class="dz-card-eyebrow">{{ r.eyebrow }}</span>{% endif %}
            <h3 id="card-title-{{ _card_id }}" class="dz-card-title">{{ r.title or r.name.replace('_', ' ').title() }}</h3>
          </div>
          <div class="dz-card-actions">
            <button data-test-id="dz-card-remove" class="dz-card-action-button" aria-label="Remove card">
              <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
              <span class="visually-hidden">Remove card</span>
            </button>
          </div>
        </div>
        {%- if r.notice and r.notice.title %}
        <div class="dz-notice-band dz-card-notice" data-dz-notice-tone="{{ r.notice.tone or 'neutral' }}" role="note">
          <div class="dz-card-notice-title">{{ r.notice.title }}</div>
          {%- if r.notice.body %}<div class="dz-card-notice-body">{{ r.notice.body }}</div>{% endif %}
        </div>
        {%- endif %}
        <div class="dz-card-body" id="region-{{ r.name }}-{{ _card_id }}" data-display="{{ r.display | lower }}" hx-get="/api/workspaces/{{ workspace.name }}/regions/{{ r.name }}" hx-trigger="{{ _trigger }}" hx-swap="innerHTML">
          <div class="dz-card-skeleton">
            <div class="dz-card-skeleton-line w-3-4"></div>
            <div class="dz-card-skeleton-line is-thin"></div>
            <div class="dz-card-skeleton-line is-thin w-5-6"></div>
          </div>
        </div>
      </article>
      <div class="dz-card-resize" aria-hidden="true"></div>
    </div>
    {%- endfor %}
  </div>"""


class _LegacyRegion:
    def __init__(self, name, title, display, col_span, eyebrow="", css_class="", notice=None):
        self.name = name
        self.title = title
        self.display = display
        self.col_span = col_span
        self.eyebrow = eyebrow
        self.css_class = css_class
        self.notice = notice


class _LegacyNotice:
    def __init__(self, title, body="", tone="neutral"):
        self.title = title
        self.body = body
        self.tone = tone


class _LegacyWorkspace:
    def __init__(self, name, regions, sse_url=""):
        self.name = name
        self.regions = regions
        self.sse_url = sse_url


@pytest.fixture
def legacy_render():
    env = create_jinja_env()
    tmpl = env.from_string(_LEGACY_GRID_TEMPLATE)

    def _render(workspace, fold_count=0):
        return tmpl.render(workspace=workspace, fold_count=fold_count)

    return _render


def _typed_render(grid: DashboardGrid) -> str:
    return FragmentRenderer().render(grid)


def test_dashboard_grid_basic_two_cards_byte_equivalence(legacy_render) -> None:
    """Two-card grid with mixed eager/lazy, no SSE, no notice."""
    regions = [
        _LegacyRegion("tasks", "My Tasks", "LIST", 6),
        _LegacyRegion(
            "kanban",
            "Board",
            "KANBAN",
            12,
            eyebrow="Active",
            notice=_LegacyNotice("Beta", "still rolling out", "warning"),
        ),
    ]
    ws = _LegacyWorkspace("dashboard", regions)
    legacy = legacy_render(ws, fold_count=1)

    cards = (
        DashboardCard(
            card_id="card-0",
            name="tasks",
            title="My Tasks",
            display="LIST",
            col_span=6,
            row_order=0,
            hx_endpoint="/api/workspaces/dashboard/regions/tasks",
            eager=True,
        ),
        DashboardCard(
            card_id="card-1",
            name="kanban",
            title="Board",
            display="KANBAN",
            col_span=12,
            row_order=1,
            hx_endpoint="/api/workspaces/dashboard/regions/kanban",
            eager=False,
            eyebrow="Active",
            notice=DashboardNotice(title="Beta", body="still rolling out", tone="warning"),
        ),
    )
    assert diff_summary(legacy, _typed_render(DashboardGrid(cards=cards))) is None


def test_dashboard_grid_with_sse_byte_equivalence(legacy_render) -> None:
    """Workspace with `sse_url` adds `hx-ext="sse" sse-connect=...` on
    the grid container and three entity events to per-card hx-trigger."""
    ws = _LegacyWorkspace("ops", [_LegacyRegion("tasks", "T", "LIST", 6)], sse_url="/api/sse/ops")
    legacy = legacy_render(ws, fold_count=0)

    cards = (
        DashboardCard(
            card_id="card-0",
            name="tasks",
            title="T",
            display="LIST",
            col_span=6,
            row_order=0,
            hx_endpoint="/api/workspaces/ops/regions/tasks",
            eager=False,
            sse_enabled=True,
        ),
    )
    typed = _typed_render(DashboardGrid(cards=cards, sse_url="/api/sse/ops"))
    assert diff_summary(legacy, typed) is None


def test_dashboard_grid_empty_byte_equivalence(legacy_render) -> None:
    """Empty grid (no regions) renders an empty `dz-dashboard-grid`
    wrapper with no inner cards."""
    ws = _LegacyWorkspace("blank", [])
    legacy = legacy_render(ws, fold_count=0)
    typed = _typed_render(DashboardGrid(cards=()))
    assert diff_summary(legacy, typed) is None


def test_dashboard_card_notice_without_body_byte_equivalence(legacy_render) -> None:
    """Notice band with no body — `<div class="dz-card-notice-body">` is
    omitted entirely, not emitted as empty."""
    regions = [
        _LegacyRegion("tasks", "T", "LIST", 6, notice=_LegacyNotice("Heads up")),
    ]
    ws = _LegacyWorkspace("d", regions)
    legacy = legacy_render(ws, fold_count=1)

    cards = (
        DashboardCard(
            card_id="card-0",
            name="tasks",
            title="T",
            display="LIST",
            col_span=6,
            row_order=0,
            hx_endpoint="/api/workspaces/d/regions/tasks",
            eager=True,
            notice=DashboardNotice(title="Heads up"),
        ),
    )
    assert diff_summary(legacy, _typed_render(DashboardGrid(cards=cards))) is None


def test_dashboard_card_with_css_class_byte_equivalence(legacy_render) -> None:
    """Caller-supplied `css_class` is appended to the wrapper class
    list before `is-animating`."""
    regions = [_LegacyRegion("tasks", "T", "LIST", 6, css_class="is-priority")]
    ws = _LegacyWorkspace("d", regions)
    legacy = legacy_render(ws, fold_count=1)

    cards = (
        DashboardCard(
            card_id="card-0",
            name="tasks",
            title="T",
            display="LIST",
            col_span=6,
            row_order=0,
            hx_endpoint="/api/workspaces/d/regions/tasks",
            eager=True,
            css_class="is-priority",
        ),
    )
    assert diff_summary(legacy, _typed_render(DashboardGrid(cards=cards))) is None


# ── Structural unit tests pinning contract attributes ──


def test_dashboard_grid_carries_contract_attributes() -> None:
    """`data-grid-container`, `role="application"`, `aria-label`
    pinned — the dashboard JS keys off the data-attr."""
    html = _typed_render(DashboardGrid(cards=()))
    assert 'class="dz-dashboard-grid"' in html
    assert "data-grid-container" in html
    assert 'role="application"' in html
    assert 'aria-label="Dashboard card grid"' in html


def test_dashboard_card_carries_drag_handle_test_id() -> None:
    """`data-test-id="dz-card-drag-handle"` anchors INTERACTION_WALK
    (#948 invariant). Must round-trip exactly."""
    card = DashboardCard(
        card_id="card-0",
        name="x",
        title="X",
        display="LIST",
        col_span=6,
        row_order=0,
        hx_endpoint="/x",
    )
    html = FragmentRenderer().render(card)
    assert 'data-test-id="dz-card-drag-handle"' in html
    assert 'data-test-id="dz-card-remove"' in html


def test_dashboard_card_body_id_links_to_aria_labelledby() -> None:
    """`card-title-{card_id}` is shared between the `<h3>` id and the
    `<article>` aria-labelledby — accessibility contract."""
    card = DashboardCard(
        card_id="card-7",
        name="x",
        title="X",
        display="LIST",
        col_span=6,
        row_order=7,
        hx_endpoint="/x",
    )
    html = FragmentRenderer().render(card)
    assert 'aria-labelledby="card-title-card-7"' in html
    assert 'id="card-title-card-7"' in html


def test_dashboard_card_eager_uses_load_trigger() -> None:
    """`eager=True` → `hx-trigger="load"` (above-the-fold; #864)."""
    card = DashboardCard(
        card_id="card-0",
        name="x",
        title="X",
        display="LIST",
        col_span=6,
        row_order=0,
        hx_endpoint="/x",
        eager=True,
    )
    html = FragmentRenderer().render(card)
    assert 'hx-trigger="load"' in html


def test_dashboard_card_lazy_uses_intersect_once_trigger() -> None:
    """`eager=False` → `hx-trigger="intersect once"` (defer until
    scrolled into view)."""
    card = DashboardCard(
        card_id="card-0",
        name="x",
        title="X",
        display="LIST",
        col_span=6,
        row_order=0,
        hx_endpoint="/x",
        eager=False,
    )
    html = FragmentRenderer().render(card)
    assert 'hx-trigger="intersect once"' in html


def test_dashboard_card_resize_handle_is_aria_hidden() -> None:
    """The resize handle must carry `aria-hidden="true"` — it's a
    pointer affordance only, not a tab stop."""
    card = DashboardCard(
        card_id="card-0",
        name="x",
        title="X",
        display="LIST",
        col_span=6,
        row_order=0,
        hx_endpoint="/x",
    )
    html = FragmentRenderer().render(card)
    assert '<div class="dz-card-resize" aria-hidden="true"></div>' in html


def test_dashboard_card_validates_required_fields() -> None:
    """Empty card_id / region name / col_span < 1 all raise."""
    with pytest.raises(ValueError, match="card_id"):
        DashboardCard(
            card_id="",
            name="x",
            title="X",
            display="LIST",
            col_span=6,
            row_order=0,
            hx_endpoint="/x",
        )
    with pytest.raises(ValueError, match="region name"):
        DashboardCard(
            card_id="c",
            name="",
            title="X",
            display="LIST",
            col_span=6,
            row_order=0,
            hx_endpoint="/x",
        )
    with pytest.raises(ValueError, match="col_span"):
        DashboardCard(
            card_id="c",
            name="x",
            title="X",
            display="LIST",
            col_span=0,
            row_order=0,
            hx_endpoint="/x",
        )


def test_dashboard_notice_tone_drives_data_attribute() -> None:
    """`data-dz-notice-tone` (#906) keys into dz-tones.css for the
    visual band colour."""
    card = DashboardCard(
        card_id="c",
        name="x",
        title="X",
        display="LIST",
        col_span=6,
        row_order=0,
        hx_endpoint="/x",
        notice=DashboardNotice(title="Watch out", tone="warning"),
    )
    html = FragmentRenderer().render(card)
    assert 'data-dz-notice-tone="warning"' in html
