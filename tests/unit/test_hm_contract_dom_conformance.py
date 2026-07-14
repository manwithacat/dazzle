"""Cross-boundary lock: the REAL Dazzle pipeline's emitted DOM must satisfy
the HM DOM contract. This is the gate that would have caught #1573 at the
contract layer: a hydrated badge row with producer-shaped filter_options is
rendered through build_data_table → render_data_table_rows and validated
against contracts/grid_edit.py's DOM_CONTRACT (fragment mode — the grid
root is page furniture, validated in HM's own exemplar tests)."""

import uuid
from pathlib import Path

import pytest

from dazzle.http.runtime.handlers.list_handlers import build_data_table
from dazzle.render.fragment.renderer._data_row import render_data_table_rows
from tests.unit.hm_contract_registry import (
    DOM_ONLY_CONTRACTS,
    DOM_ONLY_DEFERRED,
    REPO_ROOT,
    load_hm_module,
)

pytestmark = pytest.mark.gate

_KIT = load_hm_module("contracts/_kit.py")

PRODUCER_SHAPES = [
    [{"value": "open", "label": "Open"}, {"value": "closed", "label": "Closed"}],
    [("open", "Open"), ("closed", "Closed")],
    ["open", "closed"],  # the #1573 crash shape
]


@pytest.mark.parametrize("options", PRODUCER_SHAPES)
def test_hydrated_badge_row_conforms_to_grid_edit_contract(options) -> None:
    pytest.importorskip("fastapi")
    grid_edit = load_hm_module("contracts/grid_edit.py")
    table = {
        "columns": [
            {"key": "title", "label": "Title", "type": "text"},
            {"key": "status", "label": "Status", "type": "badge", "filter_options": options},
        ],
        "entity_name": "Ticket",
        "api_endpoint": "/tickets",
        "table_id": "t-conformance",
        "detail_url_template": "/app/ticket/{id}",
        "inline_editable": ["title", "status"],
    }
    row = {"id": str(uuid.uuid4()), "title": "x", "status": "open"}
    html = render_data_table_rows(build_data_table(table, [row]))
    violations = _KIT.validate_dom(html, grid_edit.DOM_CONTRACT, require_root=False)
    assert not violations, violations
    assert "data-dz-grid-edit=" in html  # the seam actually rendered


def test_typed_path_is_sole_emitter() -> None:
    """HM contract attribute *assembly* is allowed ONLY under ``ingest/``.

    Families (#1577): ``data-dz-edit-``, ``data-dz-tags``, ``data-dz-combobox``,
    ``data-dz-money``, ``data-dz-action-card``, ``data-dz-status-entry``,
    ``data-dz-queue-row``, ``data-dz-widget="search_select"`` (+ search-select
    timing knobs and workspace dual-lock roots). Docstrings and runtime
    readers (has_attr) are ignored; HTML f-string / quoted assembly outside
    the ``fragment/ingest`` package fails.
    """
    import re

    # Quoted/f-string assembly of contract markers (not bare identifier reads).
    # search_select: only the typeahead widget marker + its timing knobs
    # (not every data-dz-widget — file-upload/pdf-viewer use the same attr).
    assembly = re.compile(
        r"""(?x)
        (?:f['\"].{0,80}data-dz-(?:edit-|tags|combobox|money|action-card|status-entry|queue-row|metric-key|kanban-card|activity-row|timeline-item|profile-card|sparkline|funnel|bar-chart|heatmap|bullet|bar-track|histogram|pivot|box-plot|progress-region|radar|time-series|pagination|grid-pagination|grid-total|search-box|date-range|list-region|empty-state|skeleton|diagram|task-inbox|tree|calendar|dashboard-card|cohort-strip|day-timeline|entity-card|grid-region|pipeline|blur-grace-ms|confirm-hold-ms))
        | (?:['\"]data-dz-(?:edit-|tags|combobox|money|action-card|status-entry|queue-row|metric-key|kanban-card|activity-row|timeline-item|profile-card|sparkline|funnel|bar-chart|heatmap|bullet|bar-track|histogram|pivot|box-plot|progress-region|radar|time-series|pagination|grid-pagination|grid-total|search-box|date-range|list-region|empty-state|skeleton|diagram|task-inbox|tree|calendar|dashboard-card|cohort-strip|day-timeline|entity-card|grid-region|pipeline|blur-grace-ms|confirm-hold-ms))
        | (?:data-dz-widget\s*=\s*[\"']search_select[\"'])
        """
    )
    # Readers / docs that mention the attr without assembling HTML.
    allow_name = {
        "fidelity_scorer.py",  # has_attr reader
        "forms.py",  # primitive docstrings
        "form_field.py",  # routing comments
    }
    offenders: list[str] = []
    ingest_pkg = REPO_ROOT / "src" / "dazzle" / "render" / "fragment" / "ingest"
    for p in (REPO_ROOT / "src" / "dazzle").rglob("*.py"):
        # Sole-emitters live in the ingest package (models are pure data).
        try:
            p.relative_to(ingest_pkg)
            continue
        except ValueError:
            pass
        if p.name in allow_name:
            continue
        text = p.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), 1):
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            if assembly.search(line):
                # has_attr / get_attr are readers, not emitters
                if "has_attr" in line or "get_attr" in line:
                    continue
                offenders.append(f"{p.relative_to(REPO_ROOT)}:{i}")
    assert not offenders, (
        f"HM contract attrs assembled outside ingest.py: {offenders} — "
        f"use the typed seam model + attr helper."
    )


def test_widget_combobox_conforms_to_combobox_contract() -> None:
    """Real Dazzle WidgetCombobox emission must satisfy contracts/combobox.py."""
    pytest.importorskip("fastapi")
    from dazzle.render.fragment.primitives.forms import WidgetCombobox
    from dazzle.render.fragment.renderer import FragmentRenderer

    combobox = load_hm_module("contracts/combobox.py")
    kit = load_hm_module("contracts/_kit.py")
    frag = WidgetCombobox(
        name="priority",
        label="Priority",
        options=(("low", "Low"), ("medium", "Medium"), ("high", "High")),
        placeholder="Select…",
        initial_value="medium",
    )
    html = FragmentRenderer().render(frag)
    violations = kit.validate_dom(html, combobox.DOM_CONTRACT, require_root=False)
    assert not violations, violations
    assert "data-dz-combobox" in html
    assert 'name="priority"' in html


def test_tags_field_conforms_to_tags_contract() -> None:
    """Real Dazzle TagsField form primitive emission must satisfy contracts/tags.py."""
    pytest.importorskip("fastapi")
    from dazzle.render.fragment.primitives.forms import TagsField as FormTagsField
    from dazzle.render.fragment.renderer import FragmentRenderer

    tags_mod = load_hm_module("contracts/tags.py")
    kit = load_hm_module("contracts/_kit.py")
    frag = FormTagsField(
        name="labels",
        label="Labels",
        placeholder="Add a label…",
        initial_value="urgent,backend",
    )
    html = FragmentRenderer().render(frag)
    violations = kit.validate_dom(html, tags_mod.DOM_CONTRACT, require_root=False)
    assert not violations, violations
    assert "data-dz-tags" in html
    assert 'name="labels"' in html


def test_money_field_fixed_conforms_to_money_contract() -> None:
    """Fixed-currency MoneyField emission must satisfy contracts/money.py."""
    pytest.importorskip("fastapi")
    from dazzle.render.fragment.primitives.forms import MoneyField as FormMoneyField
    from dazzle.render.fragment.renderer import FragmentRenderer

    money_mod = load_hm_module("contracts/money.py")
    kit = load_hm_module("contracts/_kit.py")
    frag = FormMoneyField(
        name="amount",
        label="Amount",
        currency_code="GBP",
        scale="2",
        symbol="£",
        currency_fixed=True,
        minor_initial="1250",
    )
    html = FragmentRenderer().render(frag)
    violations = kit.validate_dom(html, money_mod.DOM_CONTRACT, require_root=False)
    assert not violations, violations
    assert "data-dz-money" in html
    assert 'data-dz-currency="GBP"' in html
    assert 'data-dz-scale="2"' in html


def test_money_field_selector_conforms_to_money_contract() -> None:
    """Selector-mode MoneyField root must still carry data-dz-currency (DOM_CONTRACT)."""
    pytest.importorskip("fastapi")
    from dazzle.render.fragment.primitives.forms import MoneyField as FormMoneyField
    from dazzle.render.fragment.renderer import FragmentRenderer

    money_mod = load_hm_module("contracts/money.py")
    kit = load_hm_module("contracts/_kit.py")
    frag = FormMoneyField(
        name="fee",
        label="Fee",
        currency_code="USD",
        scale="2",
        symbol="$",
        currency_fixed=False,
        currency_options=(("USD", "2", "$"), ("GBP", "2", "£")),
        minor_initial="99",
    )
    html = FragmentRenderer().render(frag)
    violations = kit.validate_dom(html, money_mod.DOM_CONTRACT, require_root=False)
    assert not violations, violations
    assert "data-dz-money" in html
    assert 'data-dz-currency="USD"' in html
    assert 'data-dz-scale="2"' in html
    assert 'name="fee_currency"' in html


def test_search_select_conforms_to_shell_contract() -> None:
    """Real Dazzle SearchSelect emission must satisfy contracts/search_select.py."""
    pytest.importorskip("fastapi")
    from dazzle.render.fragment.htmx import URL
    from dazzle.render.fragment.primitives.forms import SearchSelect
    from dazzle.render.fragment.renderer import FragmentRenderer

    ss_mod = load_hm_module("contracts/search_select.py")
    kit = load_hm_module("contracts/_kit.py")
    frag = SearchSelect(
        name="owner",
        label="Owner",
        endpoint=URL("/api/owners"),
        min_chars=1,
        placeholder="Find an owner…",
    )
    html = FragmentRenderer().render(frag)
    violations = kit.validate_dom(html, ss_mod.DOM_CONTRACT, require_root=True)
    assert not violations, violations
    assert 'data-dz-widget="search_select"' in html
    assert "data-dz-blur-grace-ms=" in html
    assert "data-dz-confirm-hold-ms=" in html
    assert 'id="search-input-owner"' in html
    assert 'id="search-results-owner"' in html


def test_search_result_row_conforms_to_result_contract() -> None:
    """Ingest SearchResultRow renderer satisfies DOM_CONTRACT_RESULT_ROW."""
    pytest.importorskip("fastapi")
    from dazzle.render.fragment.ingest import SearchResultRow, render_search_result_row

    ss_mod = load_hm_module("contracts/search_select.py")
    kit = load_hm_module("contracts/_kit.py")
    row = SearchResultRow(
        id="co-aurora",
        name="Aurora Energy Ltd",
        secondary="Company no. 09182736",
        select_url="/_dazzle/fragments/select?source=companies&id=co-aurora",
        results_target="#search-results-company",
    )
    html = render_search_result_row(row)
    violations = kit.validate_dom(html, ss_mod.DOM_CONTRACT_RESULT_ROW, require_root=True)
    assert not violations, violations
    assert 'data-dz-result-id="co-aurora"' in html
    assert "dz-search-result-body" in html
    assert "Aurora Energy Ltd" in html


def test_action_card_emission_conforms_to_action_grid_contract() -> None:
    """Real FragmentRenderer ActionCard path satisfies contracts/action_grid.py."""
    pytest.importorskip("fastapi")
    from dazzle.render.fragment.primitives.data import ActionCard as ActionCardFrag
    from dazzle.render.fragment.primitives.data import ActionGrid
    from dazzle.render.fragment.renderer import FragmentRenderer

    ag_mod = load_hm_module("contracts/action_grid.py")
    kit = load_hm_module("contracts/_kit.py")
    html = FragmentRenderer().render(
        ActionGrid(
            cards=(
                ActionCardFrag(
                    label="Overdue invoices",
                    tone="warning",
                    url="/app/invoices?status=overdue",
                    count=3,
                    icon="triangle-alert",
                ),
                ActionCardFrag(label="Nothing else today", tone="neutral"),
            )
        )
    )
    # Grid furniture wraps cards — validate each card root in fragment mode
    # and assert the dual-lock marker is present on every card.
    violations = kit.validate_dom(html, ag_mod.DOM_CONTRACT, require_root=True)
    assert not violations, violations
    assert html.count("data-dz-action-card") == 2
    assert 'data-dz-tone="warning"' in html
    assert 'data-dz-tone="neutral"' in html
    assert "dz-action-card-icon-spacer" in html
    assert "Overdue invoices" in html


def test_status_list_emission_conforms_to_status_list_contract() -> None:
    """Real FragmentRenderer StatusList path satisfies contracts/status_list.py."""
    pytest.importorskip("fastapi")
    from dazzle.render.fragment.primitives.data import StatusList
    from dazzle.render.fragment.primitives.data import StatusListEntry as EntryFrag
    from dazzle.render.fragment.renderer import FragmentRenderer

    sl_mod = load_hm_module("contracts/status_list.py")
    kit = load_hm_module("contracts/_kit.py")
    html = FragmentRenderer().render(
        StatusList(
            entries=(
                EntryFrag(
                    title="Payments API",
                    state="positive",
                    caption="Operational",
                    icon="circle-check",
                ),
                EntryFrag(title="Nightly export", state="neutral", caption="02:00"),
            )
        )
    )
    violations = kit.validate_dom(html, sl_mod.DOM_CONTRACT, require_root=True)
    assert not violations, violations
    assert html.count("data-dz-status-entry") == 2
    assert 'data-dz-state="positive"' in html
    assert "dz-status-list-icon-spacer" in html
    assert "Payments API" in html


def test_queue_region_emission_conforms_to_queue_contract() -> None:
    """Real FragmentRenderer QueueRegion path satisfies contracts/queue.py."""
    pytest.importorskip("fastapi")
    from dazzle.render.fragment.primitives.data import QueueRegion
    from dazzle.render.fragment.primitives.data import QueueRow as RowFrag
    from dazzle.render.fragment.renderer import FragmentRenderer

    q_mod = load_hm_module("contracts/queue.py")
    kit = load_hm_module("contracts/_kit.py")
    html = FragmentRenderer().render(
        QueueRegion(
            total=2,
            rows=(
                RowFrag(
                    row_id="1",
                    title="Refund request — Acme",
                    attention_level="critical",
                    attention_message="SLA breaches at 16:00",
                ),
                RowFrag(row_id="2", title="KYC review — Globex"),
            ),
        )
    )
    violations = kit.validate_dom(html, q_mod.DOM_CONTRACT, require_root=True)
    assert not violations, violations
    assert html.count("data-dz-queue-row") == 2
    assert 'data-dz-attn="critical"' in html
    assert "Refund request" in html


def test_metric_tile_emission_conforms_to_metrics_contract() -> None:
    """Real FragmentRenderer MetricsGrid path satisfies contracts/metrics.py."""
    pytest.importorskip("fastapi")
    from dazzle.render.fragment.primitives.data import MetricsGrid
    from dazzle.render.fragment.primitives.data import MetricTile as TileFrag
    from dazzle.render.fragment.renderer import FragmentRenderer

    m_mod = load_hm_module("contracts/metrics.py")
    kit = load_hm_module("contracts/_kit.py")
    html = FragmentRenderer().render(
        MetricsGrid(
            tiles=(
                TileFrag(label="Outstanding", value="£12,450"),
                TileFrag(
                    label="Paid this month",
                    value="£48,900",
                    tone="positive",
                    delta_direction="up",
                    delta_sentiment="positive_up",
                    delta_value="12%",
                    delta_pct=12.0,
                    delta_period_label="last month",
                ),
            )
        )
    )
    violations = kit.validate_dom(html, m_mod.DOM_CONTRACT, require_root=True)
    assert not violations, violations
    assert 'data-dz-metric-key="outstanding"' in html
    assert 'data-dz-tone="positive"' in html
    assert "data-dz-delta-direction=" in html


def test_kanban_region_emission_conforms_to_kanban_contract() -> None:
    """Real FragmentRenderer KanbanRegion path satisfies contracts/kanban.py."""
    pytest.importorskip("fastapi")
    from dazzle.render.fragment.primitives.data import KanbanCard as CardFrag
    from dazzle.render.fragment.primitives.data import KanbanColumn, KanbanRegion
    from dazzle.render.fragment.renderer import FragmentRenderer

    k_mod = load_hm_module("contracts/kanban.py")
    kit = load_hm_module("contracts/_kit.py")
    html = FragmentRenderer().render(
        KanbanRegion(
            columns=(
                KanbanColumn(
                    label="Open",
                    cards=(
                        CardFrag(
                            title="Refund request — Acme",
                            fields=(("Amount", "£1,250"),),
                            attention_level="critical",
                            attention_message="SLA breaches at 16:00",
                        ),
                        CardFrag(title="KYC review — Globex"),
                    ),
                ),
            )
        )
    )
    violations = kit.validate_dom(html, k_mod.DOM_CONTRACT, require_root=True)
    assert not violations, violations
    assert html.count("data-dz-kanban-card") == 2
    assert 'data-dz-attn="critical"' in html
    assert "Refund request" in html


def test_activity_feed_emission_conforms_to_activity_feed_contract() -> None:
    """Real FragmentRenderer ActivityFeed path satisfies contracts/activity_feed.py."""
    pytest.importorskip("fastapi")
    from dazzle.render.fragment.primitives.data import ActivityFeed
    from dazzle.render.fragment.renderer import FragmentRenderer

    af_mod = load_hm_module("contracts/activity_feed.py")
    kit = load_hm_module("contracts/_kit.py")
    html = FragmentRenderer().render(
        ActivityFeed(
            items=(
                ("09:41", "Ada", "approved the refund."),
                ("09:12", "System", "flagged the account for review."),
            )
        )
    )
    violations = kit.validate_dom(html, af_mod.DOM_CONTRACT, require_root=True)
    assert not violations, violations
    assert html.count("data-dz-activity-row") == 2
    assert "dz-activity-actor" in html
    assert "approved the refund" in html


def test_timeline_emission_conforms_to_timeline_contract() -> None:
    """Real FragmentRenderer Timeline path satisfies contracts/timeline.py."""
    pytest.importorskip("fastapi")
    from dazzle.render.fragment.primitives.data import Timeline
    from dazzle.render.fragment.primitives.data import TimelineEvent as EvtFrag
    from dazzle.render.fragment.renderer import FragmentRenderer

    tl_mod = load_hm_module("contracts/timeline.py")
    kit = load_hm_module("contracts/_kit.py")
    html = FragmentRenderer().render(
        Timeline(
            events=(
                EvtFrag(
                    title="Payment failed",
                    date_label="Today",
                    fields=(("Reason", "Card declined"),),
                ),
                EvtFrag(title="Invoice sent", date_label="Mon"),
            )
        )
    )
    violations = kit.validate_dom(html, tl_mod.DOM_CONTRACT, require_root=True)
    assert not violations, violations
    assert html.count("data-dz-timeline-item") == 2
    assert "Payment failed" in html
    assert "dz-timeline-field" in html


def test_profile_card_emission_conforms_to_profile_card_contract() -> None:
    """Real FragmentRenderer ProfileCard path satisfies contracts/profile_card.py."""
    pytest.importorskip("fastapi")
    from dazzle.render.fragment.primitives.data import ProfileCard as CardFrag
    from dazzle.render.fragment.renderer import FragmentRenderer

    pc_mod = load_hm_module("contracts/profile_card.py")
    kit = load_hm_module("contracts/_kit.py")
    html = FragmentRenderer().render(
        CardFrag(
            primary="Maya Reyes",
            secondary="Operations lead",
            initials="MR",
            stats=(("Open work orders", "7"), ("On call", "")),
            facts=("Certified for HV switching",),
        )
    )
    violations = kit.validate_dom(html, pc_mod.DOM_CONTRACT, require_root=True)
    assert not violations, violations
    assert "data-dz-profile-card" in html
    assert "Maya Reyes" in html
    assert "dz-profile-stat-value" in html


def test_sparkline_emission_conforms_to_sparkline_contract() -> None:
    """Real FragmentRenderer Sparkline path satisfies contracts/sparkline.py."""
    pytest.importorskip("fastapi")
    from dazzle.render.fragment.primitives.data import Sparkline as SparkFrag
    from dazzle.render.fragment.renderer import FragmentRenderer

    sp_mod = load_hm_module("contracts/sparkline.py")
    kit = load_hm_module("contracts/_kit.py")
    html = FragmentRenderer().render(SparkFrag(points=(("a", 10.0), ("b", 20.0), ("c", 15.0))))
    violations = kit.validate_dom(html, sp_mod.DOM_CONTRACT, require_root=True)
    assert not violations, violations
    assert "data-dz-sparkline" in html
    assert "dz-sparkline-svg" in html
    assert "dz-sparkline-value" in html


def test_funnel_emission_conforms_to_funnel_contract() -> None:
    """Real FragmentRenderer Funnel path satisfies contracts/funnel.py."""
    pytest.importorskip("fastapi")
    from dazzle.render.fragment.primitives.data import Funnel as FunnelFrag
    from dazzle.render.fragment.primitives.data import FunnelStage as StageFrag
    from dazzle.render.fragment.renderer import FragmentRenderer

    fn_mod = load_hm_module("contracts/funnel.py")
    kit = load_hm_module("contracts/_kit.py")
    html = FragmentRenderer().render(
        FunnelFrag(
            stages=(
                StageFrag(label="Visited", count=100),
                StageFrag(label="Signed up", count=40),
            ),
            total=100,
        )
    )
    violations = kit.validate_dom(html, fn_mod.DOM_CONTRACT, require_root=True)
    assert not violations, violations
    assert "data-dz-funnel" in html
    assert 'data-dz-funnel-step="0"' in html
    assert "Visited" in html


def test_bar_chart_emission_conforms_to_bar_chart_contract() -> None:
    """Real FragmentRenderer BarChart path satisfies contracts/bar_chart.py."""
    pytest.importorskip("fastapi")
    from dazzle.render.fragment.primitives.data import BarChart as BarFrag
    from dazzle.render.fragment.renderer import FragmentRenderer

    bc_mod = load_hm_module("contracts/bar_chart.py")
    kit = load_hm_module("contracts/_kit.py")
    html = FragmentRenderer().render(
        BarFrag(label="Traffic", buckets=(("API", 126), ("Dashboard", 84)))
    )
    violations = kit.validate_dom(html, bc_mod.DOM_CONTRACT, require_root=True)
    assert not violations, violations
    assert "data-dz-bar-chart" in html
    assert "dz-bar-chart-fill" in html
    assert "126" in html


def test_heatmap_emission_conforms_to_heatmap_contract() -> None:
    """Real FragmentRenderer Heatmap path satisfies contracts/heatmap.py."""
    pytest.importorskip("fastapi")
    from dazzle.render.fragment.primitives.data import Heatmap as HeatFrag
    from dazzle.render.fragment.primitives.data import HeatmapRow as RowFrag
    from dazzle.render.fragment.renderer import FragmentRenderer

    hm_mod = load_hm_module("contracts/heatmap.py")
    kit = load_hm_module("contracts/_kit.py")
    html = FragmentRenderer().render(
        HeatFrag(
            columns=("Mon", "Tue"),
            rows=(RowFrag(label="API", cells=(99.9, 97.2)),),
            thresholds=(90.0, 98.0),
        )
    )
    violations = kit.validate_dom(html, hm_mod.DOM_CONTRACT, require_root=True)
    assert not violations, violations
    assert "data-dz-heatmap" in html
    assert "data-dz-heatmap-tone=" in html
    assert "API" in html


def test_bullet_emission_conforms_to_bullet_contract() -> None:
    """Real FragmentRenderer Bullet path satisfies contracts/bullet.py."""
    pytest.importorskip("fastapi")
    from dazzle.render.fragment.primitives.data import Bullet as BulletFrag
    from dazzle.render.fragment.primitives.data import BulletRow as RowFrag
    from dazzle.render.fragment.primitives.data import ReferenceBand
    from dazzle.render.fragment.renderer import FragmentRenderer

    bl_mod = load_hm_module("contracts/bullet.py")
    kit = load_hm_module("contracts/_kit.py")
    html = FragmentRenderer().render(
        BulletFrag(
            max_value=100.0,
            rows=(RowFrag(label="Revenue", actual=72.0, target=80.0),),
            reference_bands=(
                ReferenceBand(from_value=0, to_value=60, label="Poor", color="destructive"),
            ),
        )
    )
    violations = kit.validate_dom(html, bl_mod.DOM_CONTRACT, require_root=True)
    assert not violations, violations
    assert "data-dz-bullet" in html
    assert "Revenue" in html
    assert "dz-bullet-actual" in html


def test_bar_track_emission_conforms_to_bar_track_contract() -> None:
    """Real FragmentRenderer BarTrack path satisfies contracts/bar_track.py."""
    pytest.importorskip("fastapi")
    from dazzle.render.fragment.primitives.data import BarTrack as TrackFrag
    from dazzle.render.fragment.renderer import FragmentRenderer

    bt_mod = load_hm_module("contracts/bar_track.py")
    kit = load_hm_module("contracts/_kit.py")
    html = FragmentRenderer().render(
        TrackFrag(
            max_value=100.0,
            rows=(("Storage", 62.0, "62%", 62.0), ("Compute", 38.0, "38%", 38.0)),
        )
    )
    violations = kit.validate_dom(html, bt_mod.DOM_CONTRACT, require_root=True)
    assert not violations, violations
    assert "data-dz-bar-track" in html
    assert 'role="progressbar"' in html
    assert "Storage" in html


def test_histogram_emission_conforms_to_histogram_contract() -> None:
    """Real FragmentRenderer Histogram path satisfies contracts/histogram.py."""
    pytest.importorskip("fastapi")
    from dazzle.render.fragment.primitives.data import Histogram as HistFrag
    from dazzle.render.fragment.primitives.data import HistogramBin as BinFrag
    from dazzle.render.fragment.renderer import FragmentRenderer

    hist_mod = load_hm_module("contracts/histogram.py")
    kit = load_hm_module("contracts/_kit.py")
    html = FragmentRenderer().render(
        HistFrag(
            label="Latency",
            bins=(
                BinFrag(label="0-10", count=12, low=0.0, high=10.0),
                BinFrag(label="10-20", count=30, low=10.0, high=20.0),
                BinFrag(label="20-30", count=42, low=20.0, high=30.0),
            ),
        )
    )
    violations = kit.validate_dom(html, hist_mod.DOM_CONTRACT, require_root=True)
    assert not violations, violations
    assert "data-dz-histogram" in html
    assert "dz-histogram-summary" in html
    assert "<svg" in html


def test_pivot_emission_conforms_to_pivot_contract() -> None:
    """Real FragmentRenderer PivotTableRegion path satisfies contracts/pivot.py."""
    pytest.importorskip("fastapi")
    from dazzle.render.fragment.primitives.data import PivotDimSpec
    from dazzle.render.fragment.primitives.data import PivotTableRegion as PivotFrag
    from dazzle.render.fragment.renderer import FragmentRenderer

    pivot_mod = load_hm_module("contracts/pivot.py")
    kit = load_hm_module("contracts/_kit.py")
    html = FragmentRenderer().render(
        PivotFrag(
            dim_specs=(
                PivotDimSpec(name="system", label="System"),
                PivotDimSpec(name="severity", label="Severity"),
            ),
            measure_keys=("count",),
            rows=(
                {"system": "API", "severity": "Critical", "count": 3},
                {"system": "Dashboard", "severity": None, "count": 9},
            ),
        )
    )
    violations = kit.validate_dom(html, pivot_mod.DOM_CONTRACT, require_root=True)
    assert not violations, violations
    assert "data-dz-pivot" in html
    assert "dz-pivot-grid" in html
    assert "System" in html  # dim header
    assert "Api" in html  # non-FK dim cell → status badge (humanized)
    assert "is-measure" in html


def test_box_plot_emission_conforms_to_box_plot_contract() -> None:
    """Real FragmentRenderer BoxPlot path satisfies contracts/box_plot.py."""
    pytest.importorskip("fastapi")
    from dazzle.render.fragment.primitives.data import BoxPlot as BoxFrag
    from dazzle.render.fragment.renderer import FragmentRenderer

    bp_mod = load_hm_module("contracts/box_plot.py")
    kit = load_hm_module("contracts/_kit.py")
    html = FragmentRenderer().render(
        BoxFrag(
            label="Latency",
            groups=(
                ("API", 10.0, 20.0, 30.0, 45.0, 80.0),
                ("Web", 5.0, 15.0, 25.0, 40.0, 70.0),
            ),
            samples=(40, 30),
        )
    )
    violations = kit.validate_dom(html, bp_mod.DOM_CONTRACT, require_root=True)
    assert not violations, violations
    assert "data-dz-box-plot" in html
    assert "dz-box-plot-summary" in html
    assert "<svg" in html
    assert "2 groups · 70 samples" in html


def test_progress_emission_conforms_to_progress_contract() -> None:
    """Real FragmentRenderer StageBar path satisfies contracts/progress.py."""
    pytest.importorskip("fastapi")
    from dazzle.render.fragment.primitives.data import StageBar
    from dazzle.render.fragment.renderer import FragmentRenderer

    prog_mod = load_hm_module("contracts/progress.py")
    kit = load_hm_module("contracts/_kit.py")
    html = FragmentRenderer().render(
        StageBar(
            stages=(
                ("Draft", 4, True),
                ("Review", 2, False),
                ("Published", 0, False),
            ),
            complete_pct=33.0,
            complete_count=1,
            total=3,
        )
    )
    violations = kit.validate_dom(html, prog_mod.DOM_CONTRACT, require_root=True)
    assert not violations, violations
    assert "data-dz-progress-region" in html
    assert 'data-dz-progress value="33"' in html
    assert 'data-dz-stage-tone="complete"' in html
    assert 'data-dz-stage-tone="active"' in html
    assert 'data-dz-stage-tone="empty"' in html
    assert "1 of 3 complete" in html


def test_pagination_emission_conforms_to_pagination_contract() -> None:
    """Real FragmentRenderer Pagination path satisfies contracts/pagination.py."""
    pytest.importorskip("fastapi")
    from dazzle.render.fragment.htmx import URL
    from dazzle.render.fragment.primitives.data import Pagination as PagFrag
    from dazzle.render.fragment.renderer import FragmentRenderer

    pag_mod = load_hm_module("contracts/pagination.py")
    kit = load_hm_module("contracts/_kit.py")
    html = FragmentRenderer().render(
        PagFrag(
            region_name="tickets",
            endpoint=URL("/api/tickets"),
            total=42,
            page=1,
            page_size=10,
        )
    )
    violations = kit.validate_dom(html, pag_mod.DOM_CONTRACT, require_root=True)
    assert not violations, violations
    assert "data-dz-pagination" in html
    assert "data-dz-grid-pagination" in html
    assert 'data-dz-grid-total="42"' in html
    assert "dz-pagination-page" in html
    assert "42 rows" in html


def test_search_box_emission_conforms_to_search_box_contract() -> None:
    """Real FragmentRenderer SearchBox path satisfies contracts/search_box.py."""
    pytest.importorskip("fastapi")
    from dazzle.render.fragment.htmx import URL
    from dazzle.render.fragment.primitives.data import SearchBox as SearchFrag
    from dazzle.render.fragment.renderer import FragmentRenderer

    sb_mod = load_hm_module("contracts/search_box.py")
    kit = load_hm_module("contracts/_kit.py")
    html = FragmentRenderer().render(
        SearchFrag(
            name="records",
            fts_endpoint=URL("/mock/search"),
            placeholder="Search records…",
            coaching_message="Type a title or keyword",
            label="Search records",
        )
    )
    violations = kit.validate_dom(html, sb_mod.DOM_CONTRACT, require_root=True)
    assert not violations, violations
    assert "data-dz-search-box" in html
    assert "dz-search-box-input" in html
    assert 'aria-live="polite"' in html
    assert "Type a title or keyword" in html


def test_date_range_emission_conforms_to_date_range_contract() -> None:
    """Real FragmentRenderer DateRangePicker path satisfies contracts/date_range.py."""
    pytest.importorskip("fastapi")
    from dazzle.render.fragment.htmx import URL
    from dazzle.render.fragment.primitives.data import DateRangePicker
    from dazzle.render.fragment.renderer import FragmentRenderer

    dr_mod = load_hm_module("contracts/date_range.py")
    kit = load_hm_module("contracts/_kit.py")
    html = FragmentRenderer().render(
        DateRangePicker(
            region_name="invoices",
            endpoint=URL("/api/region"),
            date_from="2026-06-01",
            date_to="2026-06-30",
        )
    )
    violations = kit.validate_dom(html, dr_mod.DOM_CONTRACT, require_root=True)
    assert not violations, violations
    assert "data-dz-date-range" in html
    assert 'name="date_from"' in html
    assert 'name="date_to"' in html
    assert "date-range-bar" in html
    assert "2026-06-01" in html


def test_list_region_emission_conforms_to_list_region_contract() -> None:
    """Real FragmentRenderer ListRegion path satisfies contracts/list_region.py."""
    pytest.importorskip("fastapi")
    from dazzle.render.fragment.primitives.data import ListColumn, ListRegion
    from dazzle.render.fragment.renderer import FragmentRenderer

    lr_mod = load_hm_module("contracts/list_region.py")
    kit = load_hm_module("contracts/_kit.py")
    html = FragmentRenderer().render(
        ListRegion(
            columns=(ListColumn(key="name", label="Name"),),
            rows=(("Quarterly audit",),),
            csv_endpoint="/api/export",
            csv_filename="rows.csv",
            total=14,
        )
    )
    violations = kit.validate_dom(html, lr_mod.DOM_CONTRACT, require_root=True)
    assert not violations, violations
    assert "data-dz-list-region" in html
    assert "dz-list-region" in html
    assert "Quarterly audit" in html
    assert "Showing 1 of 14" in html
    assert "dz-list-csv-button" in html


def test_empty_state_emission_conforms_to_empty_state_contract() -> None:
    """Real FragmentRenderer EmptyState path satisfies contracts/empty_state.py."""
    pytest.importorskip("fastapi")
    from dazzle.render.fragment.primitives.content import EmptyState
    from dazzle.render.fragment.renderer import FragmentRenderer

    es_mod = load_hm_module("contracts/empty_state.py")
    kit = load_hm_module("contracts/_kit.py")
    html = FragmentRenderer().render(
        EmptyState(
            title="No invoices yet",
            description="Create your first invoice to get started.",
            icon="inbox",
        )
    )
    violations = kit.validate_dom(html, es_mod.DOM_CONTRACT, require_root=True)
    assert not violations, violations
    assert "data-dz-empty-state" in html
    assert "No invoices yet" in html
    assert "dz-empty-state__title" in html


def test_skeleton_emission_conforms_to_skeleton_contract() -> None:
    """Real FragmentRenderer Skeleton path satisfies contracts/skeleton.py."""
    pytest.importorskip("fastapi")
    from dazzle.render.fragment.primitives.content import Skeleton
    from dazzle.render.fragment.renderer import FragmentRenderer

    sk_mod = load_hm_module("contracts/skeleton.py")
    kit = load_hm_module("contracts/_kit.py")
    html = FragmentRenderer().render(Skeleton(lines=3))
    violations = kit.validate_dom(html, sk_mod.DOM_CONTRACT, require_root=True)
    assert not violations, violations
    assert "data-dz-skeleton" in html
    assert "dz-skeleton-lines" in html
    assert html.count('data-dz-shape="text"') == 3


def test_diagram_emission_conforms_to_diagram_contract() -> None:
    """Real FragmentRenderer Diagram path satisfies contracts/diagram.py."""
    pytest.importorskip("fastapi")
    from dazzle.render.fragment.primitives.data import Diagram
    from dazzle.render.fragment.renderer import FragmentRenderer

    dg_mod = load_hm_module("contracts/diagram.py")
    kit = load_hm_module("contracts/_kit.py")
    html = FragmentRenderer().render(
        Diagram(nodes=("Customer", "Order"), edges=(("Customer", "Order"),))
    )
    violations = kit.validate_dom(html, dg_mod.DOM_CONTRACT, require_root=True)
    assert not violations, violations
    assert "data-dz-diagram" in html
    assert "Customer" in html
    assert "dz-diagram__edge" in html


def test_task_inbox_emission_conforms_to_task_inbox_contract() -> None:
    """Real FragmentRenderer TaskInboxRegion path satisfies contracts/task_inbox.py."""
    pytest.importorskip("fastapi")
    from dazzle.render.fragment.primitives.data import TaskInboxItem, TaskInboxRegion
    from dazzle.render.fragment.renderer import FragmentRenderer

    ti_mod = load_hm_module("contracts/task_inbox.py")
    kit = load_hm_module("contracts/_kit.py")
    html = FragmentRenderer().render(
        TaskInboxRegion(
            region_name="inbox",
            items=(
                TaskInboxItem(
                    item_id="t1",
                    icon="inbox",
                    title="Approve refund",
                    urgency="overdue",
                ),
            ),
        )
    )
    violations = kit.validate_dom(html, ti_mod.DOM_CONTRACT, require_root=True)
    assert not violations, violations
    assert "data-dz-task-inbox" in html
    assert "Approve refund" in html
    assert 'data-dz-urgency="overdue"' in html


def test_tree_emission_conforms_to_tree_contract() -> None:
    """Real FragmentRenderer Tree path satisfies contracts/tree.py."""
    pytest.importorskip("fastapi")
    from dazzle.render.fragment.primitives.data import Tree, TreeNode
    from dazzle.render.fragment.renderer import FragmentRenderer

    tr_mod = load_hm_module("contracts/tree.py")
    kit = load_hm_module("contracts/_kit.py")
    html = FragmentRenderer().render(
        Tree(
            nodes=(
                TreeNode(
                    label="Engineering",
                    children=(TreeNode(label="Platform"),),
                ),
            )
        )
    )
    violations = kit.validate_dom(html, tr_mod.DOM_CONTRACT, require_root=True)
    assert not violations, violations
    assert "data-dz-tree" in html
    assert "Engineering" in html
    assert "dz-tree-node" in html


def test_calendar_emission_conforms_to_calendar_contract() -> None:
    """Real FragmentRenderer CalendarGrid path satisfies contracts/calendar.py."""
    pytest.importorskip("fastapi")
    from dazzle.render.fragment.primitives.data import CalendarGrid
    from dazzle.render.fragment.renderer import FragmentRenderer

    cal_mod = load_hm_module("contracts/calendar.py")
    kit = load_hm_module("contracts/_kit.py")
    html = FragmentRenderer().render(
        CalendarGrid(view="month", events=(("Sprint review", "2026-07-15"),))
    )
    violations = kit.validate_dom(html, cal_mod.DOM_CONTRACT, require_root=True)
    assert not violations, violations
    assert "data-dz-calendar" in html
    assert "Sprint review" in html
    assert "dz-calendar--view-month" in html


def test_dashboard_card_emission_conforms_to_dashboard_card_contract() -> None:
    """Real FragmentRenderer DashboardCard path satisfies contracts/dashboard_card.py."""
    pytest.importorskip("fastapi")
    from dazzle.render.fragment.primitives.data import DashboardCard
    from dazzle.render.fragment.renderer import FragmentRenderer

    dc_mod = load_hm_module("contracts/dashboard_card.py")
    kit = load_hm_module("contracts/_kit.py")
    html = FragmentRenderer().render(
        DashboardCard(
            card_id="card-0",
            name="tasks",
            title="Tasks",
            display="list",
            col_span=1,
            row_order=0,
            hx_endpoint="/api/regions/tasks",
        )
    )
    violations = kit.validate_dom(html, dc_mod.DOM_CONTRACT, require_root=True)
    assert not violations, violations
    assert "data-dz-dashboard-card" in html
    assert "Tasks" in html
    assert "dz-card-wrapper" in html


def test_cohort_strip_emission_conforms_to_cohort_strip_contract() -> None:
    """Real FragmentRenderer CohortStripRegion path satisfies contracts/cohort_strip.py."""
    pytest.importorskip("fastapi")
    from dazzle.render.fragment.htmx import URL
    from dazzle.render.fragment.primitives.data import (
        CohortStripCell,
        CohortStripLensTab,
        CohortStripRegion,
    )
    from dazzle.render.fragment.renderer import FragmentRenderer

    cs_mod = load_hm_module("contracts/cohort_strip.py")
    kit = load_hm_module("contracts/_kit.py")
    html = FragmentRenderer().render(
        CohortStripRegion(
            region_name="class_roll",
            endpoint=URL("/api/region"),
            lenses=(CohortStripLensTab(id="grade", label="Grade", is_active=True),),
            cells=(
                CohortStripCell(
                    member_id="m1",
                    member_name="Ada",
                    primary_value="A",
                ),
            ),
        )
    )
    violations = kit.validate_dom(html, cs_mod.DOM_CONTRACT, require_root=True)
    assert not violations, violations
    assert "data-dz-cohort-strip" in html
    assert "Ada" in html
    assert "dz-cohort-strip-lens" in html


def test_day_timeline_emission_conforms_to_day_timeline_contract() -> None:
    """Real FragmentRenderer DayTimelineRegion path satisfies contracts/day_timeline.py."""
    pytest.importorskip("fastapi")
    from dazzle.render.fragment.primitives.data import DayTimelineRegion, DayTimelineSlot
    from dazzle.render.fragment.renderer import FragmentRenderer

    dt_mod = load_hm_module("contracts/day_timeline.py")
    kit = load_hm_module("contracts/_kit.py")
    html = FragmentRenderer().render(
        DayTimelineRegion(
            region_name="today",
            slots=(
                DayTimelineSlot(
                    slot_id="p3",
                    label="Period 3",
                    position="active",
                    body="Maths",
                ),
            ),
        )
    )
    violations = kit.validate_dom(html, dt_mod.DOM_CONTRACT, require_root=True)
    assert not violations, violations
    assert "data-dz-day-timeline" in html
    assert "Period 3" in html
    assert 'data-dz-position="active"' in html


def test_entity_card_emission_conforms_to_entity_card_contract() -> None:
    """Real FragmentRenderer EntityCardRegion path satisfies contracts/entity_card.py."""
    pytest.importorskip("fastapi")
    from dazzle.render.fragment.primitives.data import EntityCardRegion, EntityCardSection
    from dazzle.render.fragment.renderer import FragmentRenderer

    ec_mod = load_hm_module("contracts/entity_card.py")
    kit = load_hm_module("contracts/_kit.py")
    html = FragmentRenderer().render(
        EntityCardRegion(
            region_name="customer_360",
            record_label="Acme Corp",
            sections=(
                EntityCardSection(
                    section_id="halo",
                    label="Profile",
                    mode="halo",
                    body="Hello",
                    column="main",
                ),
            ),
        )
    )
    violations = kit.validate_dom(html, ec_mod.DOM_CONTRACT, require_root=True)
    assert not violations, violations
    assert "data-dz-entity-card" in html
    assert "Acme Corp" in html
    assert "dz-entity-card-section" in html


def test_grid_region_emission_conforms_to_grid_region_contract() -> None:
    """Real FragmentRenderer GridRegion path satisfies contracts/grid_region.py."""
    pytest.importorskip("fastapi")
    from dazzle.render.fragment.primitives.data import GridCell, GridRegion
    from dazzle.render.fragment.renderer import FragmentRenderer

    gr_mod = load_hm_module("contracts/grid_region.py")
    kit = load_hm_module("contracts/_kit.py")
    html = FragmentRenderer().render(
        GridRegion(cells=(GridCell(title="Alpha", fields=(("Owner", "Ada"),)),))
    )
    violations = kit.validate_dom(html, gr_mod.DOM_CONTRACT, require_root=True)
    assert not violations, violations
    assert "data-dz-grid-region" in html
    assert "Alpha" in html
    assert "dz-grid-list" in html


def test_pipeline_emission_conforms_to_pipeline_contract() -> None:
    """Real FragmentRenderer PipelineSteps path satisfies contracts/pipeline.py."""
    pytest.importorskip("fastapi")
    from dazzle.render.fragment.primitives.data import PipelineStage, PipelineSteps
    from dazzle.render.fragment.renderer import FragmentRenderer

    pl_mod = load_hm_module("contracts/pipeline.py")
    kit = load_hm_module("contracts/_kit.py")
    html = FragmentRenderer().render(PipelineSteps(stages=(PipelineStage(label="Lead", value=12),)))
    violations = kit.validate_dom(html, pl_mod.DOM_CONTRACT, require_root=True)
    assert not violations, violations
    assert "data-dz-pipeline" in html
    assert "Lead" in html
    assert "dz-pipeline-stages" in html


def test_radar_emission_conforms_to_radar_contract() -> None:
    """Real FragmentRenderer Radar path satisfies contracts/radar.py."""
    pytest.importorskip("fastapi")
    from dazzle.render.fragment.primitives.data import Radar as RadarFrag
    from dazzle.render.fragment.renderer import FragmentRenderer

    radar_mod = load_hm_module("contracts/radar.py")
    kit = load_hm_module("contracts/_kit.py")
    html = FragmentRenderer().render(
        RadarFrag(
            label="Coverage",
            axes=(("Auth", 80.0), ("API", 65.0), ("UI", 90.0)),
        )
    )
    violations = kit.validate_dom(html, radar_mod.DOM_CONTRACT, require_root=True)
    assert not violations, violations
    assert "data-dz-radar" in html
    assert "dz-chart-summary" in html
    assert "<svg" in html
    assert "3 spokes" in html


def test_time_series_emission_conforms_to_time_series_contract() -> None:
    """Real FragmentRenderer TimeSeries path satisfies contracts/time_series.py."""
    pytest.importorskip("fastapi")
    from dazzle.render.fragment.primitives.data import TimeSeries as TsFrag
    from dazzle.render.fragment.renderer import FragmentRenderer

    ts_mod = load_hm_module("contracts/time_series.py")
    kit = load_hm_module("contracts/_kit.py")
    html = FragmentRenderer().render(
        TsFrag(
            label="Traffic",
            points=(("Mon", 12.0), ("Tue", 18.0), ("Wed", 9.0)),
            view="line",
        )
    )
    violations = kit.validate_dom(html, ts_mod.DOM_CONTRACT, require_root=True)
    assert not violations, violations
    assert "data-dz-time-series" in html
    assert "dz-line-chart-region" in html
    assert "dz-chart-summary" in html
    assert "<svg" in html
    assert "3 buckets" in html


# ── Root-only Hyperpart DOM conformance (#1578) ──────────────────────
# No Pydantic models — validate real Dazzle emission against DOM_CONTRACT
# with require_root=True so empty-attr nodes can't soft-pass.


def _emit_root_only_html(part_id: str) -> str:
    """Build HTML for a root-only part via the real Dazzle emission path."""
    from dazzle.render.fragment import AppShell, Surface, Tabs, Text
    from dazzle.render.fragment.primitives.data import ConfirmCheckItem, ConfirmGate
    from dazzle.render.fragment.primitives.forms import (
        ColorField,
        SliderField,
    )
    from dazzle.render.fragment.renderer import FragmentRenderer

    r = FragmentRenderer()
    if part_id == "slider":
        return r.render(SliderField(name="vol", label="Volume", initial_value="40"))
    if part_id == "color":
        return r.render(ColorField(name="accent", label="Accent", initial_value="#3b82f6"))
    if part_id == "app_shell":
        return r.render(AppShell(body=Surface(header=Text("h"), body=Text("b"))))  # type: ignore[arg-type]
    if part_id == "command":
        return r.render(
            AppShell(
                body=Surface(header=Text("h"), body=Text("b")),
                command_endpoint="/app/command",
            )
        )  # type: ignore[arg-type]
    if part_id == "confirm_panel":
        return r.render(
            ConfirmGate(
                state="off",
                confirmations=(ConfirmCheckItem(title="I understand", required=True),),
                primary_action_url="/confirm",
            )
        )
    if part_id == "tabs":
        return r.render(Tabs(tabs=(("one", Text("One")), ("two", Text("Two")))))
    if part_id in ("grid", "grid_cols", "grid_resize"):
        from dazzle.render.fragment.primitives.containers import DzTableMount, Region
        from dazzle.render.fragment.primitives.data import (
            ColumnVisibilityMenu,
            Sequence,
            Table,
        )

        table = Table(
            columns=("Title", "Status"),
            rows=(),
            skeleton=True,
            tbody_id="grid-fixture-body",
            hx_endpoint="/api/tickets",
            caption="Tickets",
            has_actions=True,
            column_keys=("title", "status"),
            sortable_keys=("title",),
            sort_field="title",
            sort_dir="asc",
        )
        menu = ColumnVisibilityMenu(columns=(("title", "Title"), ("status", "Status")))
        return r.render(
            Region(
                kind="list",
                body=Sequence(children=(menu, table)),
                data_table="Ticket",
                mount=DzTableMount(
                    table_id="grid-fixture",
                    endpoint="/api/tickets",
                    entity_name="Ticket",
                ),
            )
        )
    if part_id == "dialog":
        # Real list-row peek:slide_over path emits data-dz-dialog-open on the chevron.
        table = {
            "columns": [{"key": "title", "label": "Title", "type": "text"}],
            "entity_name": "Ticket",
            "api_endpoint": "/tickets",
            "table_id": "t-dialog",
            "detail_url_template": "/app/ticket/{id}",
            "peek_mode": "slide_over",
        }
        row = {"id": str(uuid.uuid4()), "title": "x"}
        return render_data_table_rows(build_data_table(table, [row]))
    if part_id == "confirm":
        # Real list-row delete affordance emits hx-confirm (contracts/confirm.py root).
        table = {
            "columns": [{"key": "title", "label": "Title", "type": "text"}],
            "entity_name": "Ticket",
            "api_endpoint": "/tickets",
            "table_id": "t-confirm",
            "detail_url_template": "/app/ticket/{id}",
        }
        row = {"id": str(uuid.uuid4()), "title": "x"}
        return render_data_table_rows(build_data_table(table, [row]))
    if part_id == "pdf":
        from dazzle.page.runtime.pdf_viewer_renderer import render_pdf_viewer_component

        return render_pdf_viewer_component(
            src="/files/fixture.pdf",
            back_url="/app",
            title="Fixture PDF",
        )
    if part_id == "wizard":
        from types import SimpleNamespace

        from dazzle.page.runtime.experience_renderer import _render_form_step_body

        form = SimpleNamespace(
            sections=[
                {"title": "Basics", "fields": []},
                {"title": "Details", "fields": []},
            ],
            initial_values={},
            fields=[],
            entity_name="Ticket",
            mode="create",
            method="post",
            action_url="/api/tickets",
        )
        return _render_form_step_body(SimpleNamespace(transitions=[]), SimpleNamespace(form=form))
    if part_id == "menu":
        # Workspace heading overflow (#1491) emits details.dz-menu (HM menu Hyperpart).
        from dazzle.render.fragment.primitives.data import (
            WorkspacePrimaryAction,
            WorkspaceShell,
        )

        return r.render(
            WorkspaceShell(
                workspace_name="ops",
                title="Command center",
                body=Text(""),
                overflow_actions=(
                    WorkspacePrimaryAction(label="Export", route="/app/export"),
                    WorkspacePrimaryAction(label="Settings", route="/app/settings"),
                ),
            )
        )
    if part_id == "badge":
        from dazzle.render.fragment.primitives.content import Badge

        return r.render(Badge(label="Approved", variant="success"))
    if part_id == "button":
        from dazzle.render.fragment.primitives.interactive import Button

        return r.render(Button(label="Save changes", variant="primary"))
    if part_id == "card":
        from dazzle.render.fragment.primitives.containers import Card

        return r.render(Card(body=Text("Card body")))
    if part_id == "drawer":
        from dazzle.render.fragment.primitives.containers import Drawer

        return r.render(Drawer(body=Text("Drawer body"), side="right"))
    if part_id == "toolbar":
        from dazzle.render.fragment.primitives.containers import Toolbar
        from dazzle.render.fragment.primitives.interactive import Button

        return r.render(
            Toolbar(
                label="Editor actions",
                actions=(Button(label="New", variant="primary"),),
            )
        )
    if part_id == "card_picker":
        from dazzle.render.fragment.primitives.data import CardPicker, CardPickerEntry

        return r.render(
            CardPicker(
                catalog_json="[]",
                entries=(
                    CardPickerEntry(
                        name="metrics",
                        title="Metrics",
                        entity="Ticket",
                        display="KPI",
                    ),
                ),
            )
        )
    if part_id == "add_card_row":
        from dazzle.render.fragment.primitives.data import (
            AddCardRow,
            CardPicker,
            CardPickerEntry,
        )

        return r.render(
            AddCardRow(
                picker=CardPicker(
                    catalog_json="[]",
                    entries=(
                        CardPickerEntry(
                            name="metrics",
                            title="Metrics",
                            entity="Ticket",
                            display="KPI",
                        ),
                    ),
                )
            )
        )
    if part_id == "bulk_actions":
        from dazzle.render.fragment.primitives.data import BulkActionToolbar

        return r.render(BulkActionToolbar(endpoint="/api/tickets"))
    if part_id == "workspace_toolbar":
        from dazzle.render.fragment.primitives.data import WorkspaceToolbar

        return r.render(WorkspaceToolbar())
    if part_id == "filter_bar":
        from dazzle.render.fragment.htmx import URL
        from dazzle.render.fragment.primitives.data import FilterColumn, ListFilterBar

        return r.render(
            ListFilterBar(
                tbody_id="list-body",
                endpoint=URL("/api/tickets"),
                columns=(
                    FilterColumn(
                        key="status",
                        label="Status",
                        options=(("open", "Open"), ("closed", "Closed")),
                    ),
                ),
            )
        )
    if part_id == "skip_link":
        from dazzle.render.fragment.primitives.navigation import SkipLink

        return r.render(SkipLink(target="#main", text="Skip to content"))
    if part_id == "topbar":
        from dazzle.render.fragment.primitives.navigation import Topbar

        return r.render(Topbar(title="App", show_sidebar_toggle=False))
    if part_id == "sidebar":
        from dazzle.render.fragment.htmx import URL
        from dazzle.render.fragment.primitives.navigation import NavItem, Sidebar

        return r.render(
            Sidebar(
                items=(NavItem(label="Home", href=URL("/app"), active=True),),
            )
        )
    if part_id == "related_group":
        from dazzle.render.fragment.primitives.data import RelatedGroup, RelatedTab

        return r.render(
            RelatedGroup(
                group_id="invoices",
                label="Invoices",
                display="status_cards",
                tabs=(
                    RelatedTab(
                        tab_id="open",
                        label="Open",
                        headers=("Number", "Total", "Status"),
                        rows=(("INV-1", "£100", "Open"),),
                    ),
                ),
            )
        )
    if part_id == "surface":
        from dazzle.render.fragment.primitives.containers import Surface

        return r.render(Surface(header=Text("Header"), body=Text("Body")))
    if part_id == "stack":
        from dazzle.render.fragment.primitives.layout import Stack

        return r.render(Stack(children=(Text("A"), Text("B")), gap="md"))
    if part_id == "cluster":
        from dazzle.render.fragment.primitives.layout import Row

        return r.render(Row(children=(Text("A"), Text("B")), gap="md"))
    if part_id == "heading":
        from dazzle.render.fragment.primitives.content import Heading

        return r.render(Heading(body="Section title", level=2))
    if part_id == "split":
        from dazzle.render.fragment.primitives.layout import Split

        return r.render(Split(start=Text("Start"), end=Text("End")))
    if part_id == "text":
        return r.render(Text("Hello"))
    if part_id == "icon":
        from dazzle.render.fragment.primitives.content import Icon

        return r.render(Icon(name="check", size="md"))
    if part_id == "link":
        from dazzle.render.fragment.htmx import URL
        from dazzle.render.fragment.primitives.interactive import Link

        return r.render(Link(label="Home", href=URL("/app")))
    if part_id == "inline_edit":
        from dazzle.render.fragment.primitives.interactive import InlineEdit

        return r.render(InlineEdit(field_name="title", value="Hello", placeholder="Enter title"))
    if part_id == "layout_grid":
        from dazzle.render.fragment.primitives.layout import Grid

        return r.render(Grid(children=(Text("A"), Text("B"), Text("C")), columns=3))
    if part_id == "region":
        from dazzle.render.fragment.primitives.containers import Region

        return r.render(Region(kind="list", body=Text("Region body")))
    if part_id == "interactive":
        from dazzle.render.fragment.primitives.interactive import Interactive

        return r.render(Interactive(child=Text("Click me")))
    if part_id == "form_field":
        from dazzle.render.fragment.primitives.forms import Field

        return r.render(Field(name="title", label="Title", kind="text"))
    if part_id == "form_stack":
        from dazzle.render.fragment.htmx import URL
        from dazzle.render.fragment.primitives.forms import Field, FormStack, Submit

        return r.render(
            FormStack(
                action=URL("/api/tickets"),
                method="POST",
                fields=(Field(name="title", label="Title", kind="text"),),
                submit=Submit(label="Save"),
                entity_name="Ticket",
                mode="create",
            )
        )
    if part_id == "submit":
        from dazzle.render.fragment.primitives.forms import Submit

        return r.render(Submit(label="Save"))
    if part_id == "form_section":
        from dazzle.render.fragment.primitives.forms import Field, FormSection

        return r.render(
            FormSection(
                title="Details",
                fields=(Field(name="title", label="Title", kind="text"),),
                note="Optional note",
            )
        )
    if part_id == "form_stepper":
        from dazzle.render.fragment.primitives.forms import FormStepper

        return r.render(FormStepper(sections=("Details", "Review", "Confirm")))
    if part_id == "kpi":
        from dazzle.render.fragment.primitives.data import KPI

        return r.render(KPI(label="Open", value="12", trend="up", delta="+2"))
    if part_id == "file_upload":
        from dazzle.render.fragment.htmx import URL
        from dazzle.render.fragment.primitives.forms import FileUpload

        return r.render(
            FileUpload(name="attach", label="Attachment", upload_url=URL("/api/upload"))
        )
    if part_id == "ref_picker":
        from dazzle.render.fragment.htmx import URL
        from dazzle.render.fragment.primitives.forms import RefPicker

        return r.render(RefPicker(name="owner", label="Owner", ref_api=URL("/api/users")))
    if part_id == "rich_text":
        from dazzle.render.fragment.primitives.forms import RichTextField

        return r.render(RichTextField(name="body", label="Body"))
    if part_id == "csv_export_button":
        from dazzle.render.fragment.htmx import URL
        from dazzle.render.fragment.primitives.data import CsvExportButton

        return r.render(
            CsvExportButton(
                endpoint=URL("/api/export"),
                filename="rows.csv",
                label="Export CSV",
            )
        )
    if part_id == "sort_header":
        from dazzle.render.fragment.htmx import URL
        from dazzle.render.fragment.primitives.data import SortHeader

        return r.render(
            SortHeader(
                label="Title",
                column_key="title",
                endpoint=URL("/api/list"),
                region_name="tickets",
            )
        )
    if part_id == "column_visibility_menu":
        from dazzle.render.fragment.primitives.data import ColumnVisibilityMenu

        return r.render(ColumnVisibilityMenu(columns=(("title", "Title"), ("status", "Status"))))
    if part_id == "metrics_grid":
        from dazzle.render.fragment.primitives.data import MetricsGrid, MetricTile

        return r.render(MetricsGrid(tiles=(MetricTile(label="Open", value="12"),)))
    if part_id == "nav_item":
        from dazzle.render.fragment.htmx import URL
        from dazzle.render.fragment.primitives.navigation import NavItem

        return r.render(NavItem(label="Home", href=URL("/app/home"), active=True))
    if part_id == "nav_group":
        from dazzle.render.fragment.htmx import URL
        from dazzle.render.fragment.primitives.navigation import NavGroup, NavItem

        return r.render(
            NavGroup(
                label="Ops",
                items=(NavItem(label="Home", href=URL("/app/home")),),
                collapsed=False,
            )
        )
    if part_id == "workspace_context":
        from dazzle.render.fragment.primitives.data import WorkspaceContextSelector

        return r.render(
            WorkspaceContextSelector(
                label="Tenant",
                workspace_name="main",
                options_url="/api/ctx",
            )
        )
    if part_id == "detail_grid":
        from dazzle.render.fragment.primitives.content import Text
        from dazzle.render.fragment.primitives.data import DetailGrid

        return r.render(
            DetailGrid(
                rows=(
                    ("Name", Text(body="Ada")),
                    ("Status", Text(body="Open")),
                )
            )
        )
    if part_id == "action_grid_region":
        from dazzle.render.fragment.primitives.data import ActionCard, ActionGrid

        return r.render(
            ActionGrid(
                cards=(ActionCard(label="New", url="/create", tone="neutral", icon="plus"),),
                empty_message="No actions",
            )
        )
    if part_id == "pivot_table":
        from dazzle.render.fragment.primitives.data import PivotTable

        return r.render(
            PivotTable(
                label="By status",
                columns=("A", "B"),
                rows=("r1",),
                cells={("r1", "A"): 1, ("r1", "B"): 2},
            )
        )
    if part_id == "dashboard_grid":
        from dazzle.render.fragment.primitives.data import DashboardGrid

        return r.render(DashboardGrid(cards=(), edit_enabled=False))
    if part_id == "workspace_shell":
        from dazzle.render.fragment.primitives.content import Text
        from dazzle.render.fragment.primitives.data import WorkspaceShell

        return r.render(
            WorkspaceShell(
                workspace_name="main",
                title="Home",
                body=Text(body="Body"),
                primary_actions=(),
                overflow_actions=(),
                fold_count=0,
            )
        )
    if part_id == "queue_region":
        from dazzle.render.fragment.primitives.data import QueueRegion

        return r.render(
            QueueRegion(
                rows=(),
                total=0,
                metrics=(),
                transitions=(),
                queue_status_field="status",
                queue_api_endpoint="/api/q",
                region_name="review",
                empty_message="empty",
            )
        )
    if part_id == "activity_feed_list":
        from dazzle.render.fragment.primitives.data import ActivityFeed

        return r.render(
            ActivityFeed(
                items=(("10:00", "Ada", "opened"),),
                empty_message="none",
            )
        )
    if part_id == "kanban_board":
        from dazzle.render.fragment.primitives.content import Text
        from dazzle.render.fragment.primitives.data import KanbanBoard

        return r.render(KanbanBoard(columns=(("todo", (Text(body="A"),)),)))
    if part_id == "status_list_region":
        from dazzle.render.fragment.primitives.data import StatusList, StatusListEntry

        return r.render(
            StatusList(
                entries=(StatusListEntry(title="OK", state="positive"),),
                empty_message="none",
            )
        )
    if part_id == "kanban_region":
        from dazzle.render.fragment.primitives.data import (
            KanbanCard,
            KanbanColumn,
            KanbanRegion,
        )

        return r.render(
            KanbanRegion(
                columns=(
                    KanbanColumn(
                        label="Todo",
                        cards=(KanbanCard(title="A", fields=()),),
                    ),
                ),
                empty_message="No items",
            )
        )
    if part_id == "data_list_scroll":
        from dazzle.render.fragment.primitives.data import DataListScroll, Table

        return r.render(
            DataListScroll(
                table=Table(columns=("A",), rows=()),
                table_id="t1",
                page_size=10,
                aria_label="Items",
                empty_title="Empty",
                empty_description="None",
                empty_action_href="",
                empty_action_label="",
                paginated=False,
            )
        )
    if part_id == "queue_filters":
        from dazzle.render.fragment.htmx import URL
        from dazzle.render.fragment.primitives.data import FilterBar, FilterColumn

        return r.render(
            FilterBar(
                endpoint=URL("/api/list"),
                region_name="tickets",
                columns=(
                    FilterColumn(
                        key="status",
                        label="Status",
                        options=(("open", "Open"),),
                        selected="",
                    ),
                ),
            )
        )
    if part_id == "carousel":
        # Gallery substrate fixture — no FragmentRenderer emit yet (HMC-125).
        return (
            '<div class="dz-carousel" data-dz-carousel data-dz-carousel-index="0" '
            'data-dz-carousel-wrap="none" data-dz-carousel-interval="0" '
            'aria-roledescription="carousel" aria-label="Fixture">'
            '<button type="button" data-dz-carousel-prev aria-label="Previous"></button>'
            '<div class="dz-carousel__slide" data-dz-active></div>'
            '<button type="button" data-dz-carousel-next aria-label="Next"></button>'
            '<p data-dz-carousel-status aria-live="polite">Slide 1 of 1</p>'
            "</div>"
        )
    if part_id == "menubar":
        # Gallery substrate fixture — no FragmentRenderer emit yet (HMC-126).
        return (
            '<div class="dz-menubar" data-dz-menubar role="navigation" aria-label="App">'
            '<details class="dz-menubar__item">'
            '<summary class="dz-menubar__trigger">File</summary>'
            '<div class="dz-menubar__panel" role="menu" aria-label="File">'
            '<a href="#" role="menuitem">New</a>'
            "</div></details></div>"
        )
    if part_id == "navigation_menu":
        # Gallery substrate fixture — no FragmentRenderer emit yet (HMC-127).
        return (
            '<nav class="dz-navigation-menu" data-dz-navigation-menu aria-label="Product">'
            '<ul class="dz-navigation-menu__list">'
            '<li class="dz-navigation-menu__item"><a href="#">Home</a></li>'
            "</ul></nav>"
        )
    if part_id == "popover":
        # Gallery substrate fixture — no FragmentRenderer emit yet (HMC-128).
        return (
            '<details class="dz-popover">'
            '<summary class="dz-button" data-dz-variant="secondary">Open</summary>'
            '<div class="dz-popover__content">Popover body</div>'
            "</details>"
        )
    if part_id == "switch":
        # Gallery substrate fixture — no FragmentRenderer emit yet (HMC-129).
        return (
            '<label class="dz-switch">'
            '<input type="checkbox" name="notify" data-dz-switch checked>'
            '<span class="dz-switch__track" aria-hidden="true"></span>'
            "<span>Email notifications</span></label>"
        )
    if part_id == "toggle":
        # Gallery substrate fixture — no FragmentRenderer emit yet (HMC-130).
        return (
            '<button type="button" class="dz-toggle" data-dz-toggle '
            'aria-pressed="true"><strong>B</strong> Bold</button>'
        )
    if part_id == "accordion":
        # Gallery substrate fixture — no FragmentRenderer emit yet (HMC-131).
        return (
            '<div class="dz-accordion">'
            '<details class="dz-accordion__item" name="fixture-acc" open>'
            '<summary class="dz-accordion__trigger">Section</summary>'
            '<div class="dz-accordion__panel">Body</div></details>'
            "</div>"
        )
    if part_id == "aspect_ratio":
        # Gallery substrate fixture — no FragmentRenderer emit yet (HMC-132).
        return (
            '<div class="dz-aspect-ratio" data-dz-ratio="16/9" '
            'aria-label="16:9 frame"><span>16:9</span></div>'
        )
    if part_id == "hover_card":
        # Gallery substrate fixture — no FragmentRenderer emit yet (HMC-133).
        return (
            '<div class="dz-hover-card" data-dz-hover-card>'
            '<button type="button" class="dz-hover-card__trigger">@maya</button>'
            '<div class="dz-hover-card__content" role="tooltip">'
            '<p class="dz-hover-card__title">Maya Reyes</p>'
            '<p class="dz-hover-card__description">Operations lead</p>'
            "</div></div>"
        )
    if part_id == "message":
        # Gallery substrate fixture — no FragmentRenderer emit yet (HMC-134).
        return (
            '<div class="dz-message" data-dz-message data-dz-from="in">'
            '<span class="dz-message__media" aria-hidden="true">MR</span>'
            '<div class="dz-message__body">'
            '<div class="dz-message__meta">'
            '<span class="dz-message__author">Maya Reyes</span>'
            '<time class="dz-message__time" datetime="2026-07-12T10:02">10:02</time>'
            "</div>"
            '<div class="dz-bubble" data-dz-bubble data-dz-from="in">'
            "<p>Hello</p></div></div></div>"
        )
    if part_id == "breadcrumb":
        # Gallery substrate fixture — no FragmentRenderer emit yet (HMC-135).
        return (
            '<nav class="dz-breadcrumb" aria-label="Breadcrumb"><ol>'
            '<li><a href="#">Home</a></li><li><a href="#">Invoices</a></li>'
            '<li aria-current="page">INV-0042</li></ol></nav>'
        )
    if part_id == "auto_grid":
        # Gallery substrate fixture — no FragmentRenderer emit yet (HMC-136).
        return (
            '<div class="dz-auto-grid" style="--dz-grid-min: 9rem">'
            '<div class="hm-demo-box">A</div><div class="hm-demo-box">B</div>'
            '<div class="hm-demo-box">C</div><div class="hm-demo-box">D</div>'
            '<div class="hm-demo-box">E</div>'
            "</div>"
        )
    if part_id == "center":
        # Gallery substrate fixture — no FragmentRenderer emit yet (HMC-137).
        return (
            '<div class="dz-center" data-dz-measure="prose">'
            '<p class="hm-demo-muted">A comfortable reading measure tops out '
            "around 65 characters; this block centres itself and caps its width "
            "so lines stay scannable on any screen.</p>"
            "</div>"
        )
    if part_id == "separator":
        # Gallery substrate fixture — no FragmentRenderer emit yet (HMC-138).
        return (
            '<div class="hm-stack hm-measure">'
            '<p class="hm-demo-muted">Account details</p>'
            '<hr class="dz-separator">'
            '<p class="hm-demo-muted">Billing and invoices</p>'
            '<div class="hm-demo-row">'
            '<span class="hm-demo-muted">Draft</span>'
            '<div class="dz-separator--vertical" role="separator" '
            'aria-orientation="vertical"></div>'
            '<span class="hm-demo-muted">Published</span>'
            "</div></div>"
        )
    if part_id == "alert":
        # Gallery substrate fixture — no FragmentRenderer emit yet (HMC-140).
        return (
            '<div class="dz-alert" data-dz-tone="warning" role="alert">'
            '<span class="dz-alert__icon" aria-hidden="true">!</span>'
            '<div class="dz-alert__body">'
            '<div class="dz-alert__title">Payment method expiring</div>'
            '<div class="dz-alert__description">'
            "Your card ending 4242 expires next month.</div></div></div>"
        )
    if part_id == "bubble":
        # Gallery substrate fixture — no FragmentRenderer emit yet (HMC-141).
        return (
            '<div class="dz-bubble" data-dz-bubble data-dz-from="in">'
            "<p>Can we reschedule the walkthrough to Thursday?</p></div>"
        )
    if part_id == "chart_legend":
        # Gallery substrate fixture — no FragmentRenderer emit yet (HMC-142).
        return (
            '<ul class="dz-chart-legend">'
            '<li class="dz-chart-legend-item">'
            '<span class="dz-chart-legend-swatch" '
            'style="background:var(--colour-brand)"></span>'
            '<span class="dz-chart-legend-name">Revenue</span></li>'
            '<li class="dz-chart-legend-item">'
            '<span class="dz-chart-legend-swatch" '
            'style="background:var(--colour-success)"></span>'
            '<span class="dz-chart-legend-name">Costs</span></li>'
            "</ul>"
        )
    if part_id == "form_errors":
        # Gallery substrate fixture — no FragmentRenderer emit yet (HMC-143).
        return (
            '<div class="dz-form-errors" role="alert">'
            '<div class="dz-form-errors-body">'
            '<h3 class="dz-form-errors-title">Validation Error</h3>'
            '<ul class="dz-form-errors-list" role="list">'
            "<li>Name is required</li>"
            "<li>Start date must be before end date</li>"
            "</ul></div></div>"
        )
    if part_id == "grid_list":
        # Gallery substrate fixture — no FragmentRenderer emit yet (HMC-144).
        return (
            '<div class="dz-grid-list">'
            '<div class="dz-grid-cell">'
            '<h4 class="dz-grid-cell-title">Aurora Substation</h4>'
            '<p class="dz-grid-cell-field">'
            '<span class="dz-grid-cell-field-label">Region:</span> North</p>'
            "</div></div>"
        )
    if part_id == "item":
        # Gallery substrate fixture — no FragmentRenderer emit yet (HMC-145).
        return (
            '<div class="dz-item" data-dz-item data-dz-variant="outline">'
            '<span class="dz-item__media" aria-hidden="true">MR</span>'
            '<div class="dz-item__content">'
            '<div class="dz-item__title">Maya Reyes</div>'
            '<div class="dz-item__description">Operations · North grid</div>'
            "</div></div>"
        )
    if part_id == "marker":
        # Gallery substrate fixture — no FragmentRenderer emit yet (HMC-146).
        return (
            '<span class="dz-marker" data-dz-marker>'
            '<span class="dz-marker__pin" aria-hidden="true"></span>'
            '<span class="dz-marker__label">HQ</span></span>'
        )
    if part_id == "message_scroller":
        # Gallery substrate fixture — no FragmentRenderer emit yet (HMC-147).
        return (
            '<div class="dz-message-scroller" data-dz-message-scroller '
            'role="log" aria-label="Conversation" aria-live="polite" tabindex="0">'
            '<div class="dz-message" data-dz-message data-dz-from="in">'
            '<span class="dz-message__media" aria-hidden="true">MR</span>'
            '<div class="dz-message__body">'
            '<div class="dz-message__meta">'
            '<span class="dz-message__author">Maya Reyes</span>'
            '<time class="dz-message__time" datetime="2026-07-12T10:02">10:02</time>'
            "</div>"
            '<div class="dz-bubble" data-dz-bubble data-dz-from="in">'
            "<p>Hello</p></div></div></div></div>"
        )
    if part_id == "two_factor":
        # Gallery substrate fixture — no FragmentRenderer emit yet (HMC-148).
        return (
            '<div class="dz-auth-card">'
            '<h1 class="dz-auth-card-title">Set Up 2FA</h1>'
            '<p class="dz-auth-card-subtitle">Aurora Ops</p>'
            '<form class="dz-auth-form">'
            '<div class="dz-auth-field">'
            '<label for="hm-2fa-code" class="dz-auth-label">Enter code from app</label>'
            '<input type="text" id="hm-2fa-code" inputmode="numeric" '
            'class="dz-auth-input-code" maxlength="6" placeholder="000000">'
            "</div></form></div>"
        )
    if part_id == "avatar":
        # Gallery substrate fixture — no FragmentRenderer emit yet (HMC-149).
        return '<span class="dz-avatar" data-dz-size="lg">HM</span>'
    if part_id == "controls":
        # Gallery substrate fixture — no FragmentRenderer emit yet (HMC-150).
        # Multi-root contract matches any of checkbox/radio/switch classes.
        return (
            '<label class="hm-inline">'
            '<input type="checkbox" class="dz-checkbox" checked> Checkbox</label>'
        )
    if part_id == "kbd":
        # Gallery substrate fixture — no FragmentRenderer emit yet (HMC-151).
        return '<kbd class="dz-kbd">⌘K</kbd>'
    if part_id == "sidebar_layout":
        # Gallery substrate fixture — no FragmentRenderer emit yet (HMC-152).
        return (
            '<div class="dz-sidebar-layout" style="--dz-sidebar-width: 12rem">'
            '<div class="hm-demo-box">Side (12rem)</div>'
            '<div class="hm-demo-box">Content</div>'
            "</div>"
        )
    if part_id == "master_detail":
        # dual_pane_flow LIST+DETAIL pair → HM master-detail shell
        from dazzle.page.runtime.dual_pane_master_detail import render_master_detail_shell

        return render_master_detail_shell(
            list_region="contact_list",
            list_title="Contacts",
            list_endpoint="/api/workspaces/contacts/regions/contact_list",
            detail_region="contact_detail",
            detail_title="Contact detail",
            detail_endpoint_base="/api/workspaces/contacts/regions/contact_detail",
            card_id="fixture",
            eager=True,
        )
    raise AssertionError(f"no fixture builder for root-only part {part_id!r}")


@pytest.mark.parametrize(
    ("hm_path", "part_id", "require_root"),
    DOM_ONLY_CONTRACTS,
    ids=[row[1] for row in DOM_ONLY_CONTRACTS],
)
def test_root_only_dazzle_emission_conforms(hm_path: str, part_id: str, require_root: bool) -> None:
    """#1578: stable Dazzle emitters must satisfy root-only HM DOM_CONTRACTs."""
    pytest.importorskip("fastapi")
    mod = load_hm_module(hm_path)
    html = _emit_root_only_html(part_id)
    violations = _KIT.validate_dom(html, mod.DOM_CONTRACT, require_root=require_root)
    assert not violations, violations


def test_root_only_deferred_inventory_is_documented() -> None:
    """Deferred root-only modules stay inventored (not silently forgotten).

    Empty deferred is success: every root-only contract has a DOM fixture.
    """
    # Every deferred path must exist on disk under packages/hatchi-maxchi/
    for rel, _why in DOM_ONLY_DEFERRED:
        assert (REPO_ROOT / "packages" / "hatchi-maxchi" / rel).is_file(), rel
    # Covered and deferred sets are disjoint by part stem
    covered = {Path(p).stem for p, _, _ in DOM_ONLY_CONTRACTS}
    deferred = {Path(p).stem for p, _ in DOM_ONLY_DEFERRED}
    assert covered.isdisjoint(deferred), covered & deferred
