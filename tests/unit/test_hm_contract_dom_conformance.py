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
    """HM contract attribute *assembly* is allowed ONLY in ingest.py.

    Families (#1577): ``data-dz-edit-``, ``data-dz-tags``, ``data-dz-combobox``,
    ``data-dz-money``, ``data-dz-action-card``, ``data-dz-status-entry``,
    ``data-dz-queue-row``, ``data-dz-widget="search_select"`` (+ search-select
    timing knobs). Docstrings and runtime readers (has_attr) are ignored;
    HTML f-string / quoted assembly outside ingest fails.
    """
    import re

    # Quoted/f-string assembly of contract markers (not bare identifier reads).
    # search_select: only the typeahead widget marker + its timing knobs
    # (not every data-dz-widget — file-upload/pdf-viewer use the same attr).
    assembly = re.compile(
        r"""(?x)
        (?:f['\"].{0,80}data-dz-(?:edit-|tags|combobox|money|action-card|status-entry|queue-row|metric-key|kanban-card|activity-row|timeline-item|profile-card|sparkline|blur-grace-ms|confirm-hold-ms))
        | (?:['\"]data-dz-(?:edit-|tags|combobox|money|action-card|status-entry|queue-row|metric-key|kanban-card|activity-row|timeline-item|profile-card|sparkline|blur-grace-ms|confirm-hold-ms))
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
    for p in (REPO_ROOT / "src" / "dazzle").rglob("*.py"):
        if p.name == "ingest.py" and p.parent.name == "fragment":
            continue
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
