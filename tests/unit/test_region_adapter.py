"""WorkspaceRegionAdapter tests (Phase 4A).

Most adapter behaviour is "this region config + this ctx renders HTML that
contains / omits these substrings"; that shape lives in ONE table-driven test
(`test_region_renders`) whose case ids name the behaviour — and carry the issue
number when a case is a regression pin. Tests that pin structure (fragment
types, card buckets, active-lens selection) stay as their own tests.
"""

import re

import pytest

from dazzle.core.ir import AggregateRef, DerivedMetricExpr
from dazzle.render.fragment import Region, Surface
from dazzle.render.fragment.region import WorkspaceRegionAdapter
from dazzle.render.fragment.renderer import FragmentRenderer


class _FakeRegion:
    """Lightweight WorkspaceRegion stub — we only consult `display`,
    `title`, `name`, and `empty_message`. The real WorkspaceRegion
    has ~20 fields; for unit tests we duck-type."""

    def __init__(
        self,
        name: str,
        display: str = "",
        title: str | None = None,
        empty_message: str | None = None,
    ) -> None:
        self.name = name
        self.title = title
        self.display = display
        self.empty_message = empty_message


def _render(node: object) -> str:
    return FragmentRenderer().render(node)


def _cohort_region(
    *,
    member_via: str = "profile",
    lenses: list[dict] | None = None,
    default_lens: str = "",
    empty_message: str | None = None,
) -> object:
    """Region exposing a CohortStripConfig (#1018) — duck-typed."""
    from dazzle.core.ir.workspaces import CohortStripConfig, CohortStripLens

    lens_data = (
        lenses
        if lenses is not None
        else [
            {"id": "attainment", "label": "Attainment", "primary": "score"},
            {"id": "attendance", "label": "Attendance", "primary": "att_pct"},
        ]
    )
    cfg = CohortStripConfig(
        member_via=member_via,
        lenses=[CohortStripLens(**spec) for spec in lens_data],
        default_lens=default_lens,
    )

    class _Region:
        name = "cohort"
        title = None
        display = "cohort_strip"
        cohort_strip_config = cfg

    r = _Region()
    r.empty_message = empty_message  # type: ignore[attr-defined]
    return r


def _day_timeline_region(*, empty_message: str | None = None) -> object:
    """Region exposing a DayTimelineConfig (#1016) — duck-typed."""
    from dazzle.core.ir.workspaces import DayTimelineConfig

    class _Region:
        name = "today"
        title = None
        display = "day_timeline"
        cohort_strip_config = None

    r = _Region()
    r.empty_message = empty_message  # type: ignore[attr-defined]
    r.day_timeline_config = DayTimelineConfig(  # type: ignore[attr-defined]
        starts_at="period_start", ends_at="period_end", card="lesson_card"
    )
    return r


def _task_inbox_region(*, empty_state: str = "All caught up.") -> object:
    """Region exposing a TaskInboxConfig (#1015) — duck-typed."""
    from dazzle.core.ir.workspaces import TaskInboxConfig

    class _Region:
        name = "today"
        title = None
        display = "task_inbox"
        empty_message = None

    r = _Region()
    r.task_inbox_config = TaskInboxConfig(sources=[], empty_state=empty_state)  # type: ignore[attr-defined]
    return r


def _entity_card_region() -> object:
    """Region exposing an EntityCardConfig (#1017) — duck-typed."""
    from dazzle.core.ir.workspaces import EntityCardConfig

    class _Region:
        name = "card"
        title = None
        display = "entity_card"
        empty_message = None

    r = _Region()
    r.entity_card_config = EntityCardConfig(sections=[])  # type: ignore[attr-defined]
    return r


# ───────────────── Structural pins ────────────────────────


def test_unsupported_display_raises_with_actionable_hint() -> None:
    """Pin NotImplementedError + actionable hint for a substrate-deferred
    display. Id is taken from coverage `_DEFERRED_DISPLAYS` so graduating
    a former deferred (e.g. `map` → Marker board 2026-08-09) cannot
    leave a hard-coded canary that expects raise forever."""
    from dazzle.render.fragment.coverage import _DEFERRED_DISPLAYS

    assert _DEFERRED_DISPLAYS, "expected at least one deferred display for canary"
    deferred = sorted(_DEFERRED_DISPLAYS)[0]
    adapter = WorkspaceRegionAdapter()
    with pytest.raises(NotImplementedError, match=deferred):
        adapter.build(_FakeRegion("r", display=deferred), {})


@pytest.mark.parametrize("display", ["", "list"], ids=["default-empty", "explicit-list"])
def test_list_display_routes_to_list_region(display: str) -> None:
    """Default display (empty string) and `display: list` are the list view."""
    fragment = WorkspaceRegionAdapter().build(
        _FakeRegion("task_list", display=display, title="Tasks"),
        {"items": [], "columns": []},
    )
    assert isinstance(fragment, Surface)
    assert isinstance(fragment.body, Region)
    assert fragment.body.kind == "list"


def test_timeline_renders_rich_event_shape() -> None:
    """Phase 4B.4 wave 2 (v0.66.108): Timeline uses rich `TimelineEvent`
    instances with title + date_label (timeago-formatted) + secondary
    fields. Adapter consumes columns + display_key (production ctx)."""
    from dazzle.render.fragment import Timeline, TimelineEvent

    ctx = {
        "items": [
            {"title": "Login", "created_at": "2026-05-08T12:00:00", "actor": "Alice"},
        ],
        "columns": [
            {"key": "title", "label": "Action"},
            {"key": "created_at", "label": "When", "type": "date"},
            {"key": "actor", "label": "Actor"},
        ],
        "display_key": "title",
    }
    fragment = WorkspaceRegionAdapter().build(_FakeRegion("activity", display="timeline"), ctx)
    timeline = fragment.body.body
    assert isinstance(timeline, Timeline)
    assert len(timeline.events) == 1
    evt = timeline.events[0]
    assert isinstance(evt, TimelineEvent)
    assert evt.title == "Login"
    assert evt.date_label  # timeago — exact value depends on the clock
    # Actor appears as a secondary field; the date column does NOT.
    assert any(label == "Actor" for label, _ in evt.fields)
    assert not any(label == "When" for label, _ in evt.fields)


@pytest.mark.parametrize(
    ("statuses", "kanban_columns", "expected_cards"),
    [
        pytest.param(
            ["todo", "doing", "todo", "done"],
            ["todo", "doing", "done"],
            {"todo": 2, "doing": 1, "done": 1},
            id="items-bucket-by-group_by-in-declared-order",
        ),
        # Items under a key not in `kanban_columns` drop (legacy template
        # `selectattr equalto` excluded off-board items; no Other column).
        pytest.param(
            ["blocked", "todo"],
            ["todo", "doing"],
            {"todo": 1, "doing": 0},
            id="unknown-group-key-dropped",
        ),
        # A declared key with zero items still renders as an empty column.
        pytest.param(
            ["todo"],
            ["todo", "doing", "done"],
            {"todo": 1, "doing": 0, "done": 0},
            id="empty-declared-columns-still-render",
        ),
    ],
)
def test_kanban_buckets_cards_into_declared_columns(
    statuses: list[str], kanban_columns: list[str], expected_cards: dict[str, int]
) -> None:
    """v0.66.112: KANBAN uses KanbanRegion with KanbanColumn instances."""
    from dazzle.render.fragment import KanbanRegion

    ctx = {
        "items": [{"id": str(i), "title": f"T{i}", "status": s} for i, s in enumerate(statuses)],
        "kanban_columns": kanban_columns,
        "group_by": "status",
        "display_key": "title",
    }
    fragment = WorkspaceRegionAdapter().build(_FakeRegion("b", display="kanban"), ctx)
    assert fragment.body.kind == "kanban"
    board = fragment.body.body
    assert isinstance(board, KanbanRegion)
    assert [c.label for c in board.columns] == kanban_columns
    assert {c.label: len(c.cards) for c in board.columns} == expected_cards


@pytest.mark.parametrize(
    ("default_lens", "active_lens", "expected_active"),
    [
        pytest.param("attendance", None, "Attendance", id="config-default-lens"),
        # Explicit ctx lens (the `?lens=<id>` URL-param flow) wins.
        pytest.param("attendance", "attainment", "Attainment", id="ctx-lens-wins-over-default"),
        # Junk `?lens=ghost` with no default restores the first declared lens.
        pytest.param("", "ghost-lens", "Attainment", id="unknown-lens-falls-back-to-first"),
    ],
)
def test_cohort_strip_active_lens(
    default_lens: str, active_lens: str | None, expected_active: str
) -> None:
    ctx: dict = {"cohort_cells": [], "cohort_endpoint": "/r/cohort"}
    if active_lens is not None:
        ctx["cohort_active_lens"] = active_lens
    html = _render(WorkspaceRegionAdapter().build(_cohort_region(default_lens=default_lens), ctx))
    assert html.count('aria-pressed="true"') == 1
    assert html.count('aria-pressed="false"') == 1
    match = re.search(r'aria-pressed="true"[^>]*>([^<]+)</button>', html)
    assert match is not None
    assert expected_active in match.group(1)


# ───────────────── Render table ────────────────────────


def _case(
    case_id: str,
    region: object,
    ctx: dict,
    present: tuple[str, ...] = (),
    absent: tuple[str, ...] = (),
    counts: dict[str, int] | None = None,
) -> object:
    return pytest.param(region, ctx, present, absent, counts or {}, id=case_id)


def _r(display: str, name: str = "r", title: str | None = None, empty: str | None = None):
    return _FakeRegion(name, display=display, title=title, empty_message=empty)


_PERSON_REF_COLUMNS = [
    {"key": "title", "label": "Title", "type": "text"},
    {"key": "assigned_to", "label": "Assigned To", "type": "ref", "ref_entity": "User"},
]

_RENDER_CASES = [
    # ── empty data + region.empty_message → generic EmptyState arm (#1530) ──
    *(
        _case(f"empty-state-{display}", _r(display, empty=message), ctx, (message,))
        for display, ctx, message in [
            ("timeline", {}, "No events yet."),
            ("list", {"items": [], "columns": []}, "No users."),
            ("grid", {"items": []}, "Nothing here."),
            ("metrics", {}, "None yet."),
            ("bar_chart", {"buckets": []}, "None."),
            ("pivot_table", {"rows": [], "columns": ["x"]}, "No data."),
            ("tabbed_list", {}, "No tabs."),
            ("pipeline_steps", {"pipeline_stage_data": []}, "No steps."),
            ("status_list", {"items": []}, "All clear."),
            ("queue", {"items": []}, "Queue is empty."),
            ("kanban", {}, "No tasks yet."),
            # Bar chart: a bucket missing a usable key/value drops; pure garbage → empty.
            ("bar_chart", {"buckets": [None, 42, "string"]}, "No data."),
            # Radar's __post_init__ raises on <3 axes; the adapter degrades instead.
            ("radar", {"axes": [("A", 1), ("B", 2)]}, "Need 3+ axes."),
            # Uncoercible time-series points drop; pure garbage → empty.
            ("line_chart", {"points": [None, 42, "string"]}, "No points."),
        ]
    ),
    # ── timeline / activity feed ──
    _case(
        "timeline-overflow-line-when-total-exceeds-items",
        _r("timeline"),
        {
            "items": [{"title": "X", "created_at": "2026-05-08T12:00:00"}],
            "columns": [
                {"key": "title", "label": "T"},
                {"key": "created_at", "label": "W", "type": "date"},
            ],
            "display_key": "title",
            "total": 5,
        },
        ("Showing 1 of 5", "dz-timeline-overflow"),
    ),
    _case(
        "activity-feed-dispatches-through-timeline",
        _r("activity_feed"),
        {
            "items": [
                {"title": "Logged in", "created_at": "2026-05-07T09:00:00"},
                {"title": "Saved record", "created_at": "2026-05-07T09:01:00"},
            ]
        },
        ("Logged in", "Saved record"),
    ),
    # TR-8 / #852: Comment rows use `content`/`body`; a blank row is skipped
    # rather than soft-failing the region. Scalar actor stays text (oral #43).
    _case(
        "activity-feed-comment-content-field-852",
        _r("activity_feed", name="comment_activity"),
        {
            "items": [
                {
                    "content": "Customer asked about SLA credit",
                    "created_at": "2026-05-07T09:00:00",
                    "author": {"name": "Alex Agent"},
                },
                {"content": "  ", "created_at": "2026-05-07T09:05:00"},
                {
                    "body": "Internal note only",
                    "created_at": "2026-05-07T09:10:00",
                    "user": "Sam Manager",
                },
            ]
        },
        (
            "Customer asked about SLA credit",
            "Internal note only",
            "Alex Agent",
            "dz-avatar",
            'class="dz-activity-actor">Sam Manager<',
        ),
        ("Typed primitive render failed",),
    ),
    _case(
        "activity-feed-detail-url-template-drill-1303",
        _r("activity_feed"),
        {
            "items": [
                {
                    "id": "evt-1",
                    "title": "Ticket reopened",
                    "created_at": "2026-05-07T09:00:00",
                    "actor": "Ada",
                },
                {
                    "id": "evt-2",
                    "description": "Status changed",
                    "created_at": "2026-05-07T09:01:00",
                },
            ],
            "detail_url_template": "/app/ticket/{id}",
        },
        (
            'href="/app/ticket/evt-1"',
            'href="/app/ticket/evt-2"',
            "data-dz-activity-drill",
            "Ticket reopened",
            "Status changed",
        ),
    ),
    # Empty detail_url_template stays byte-stable: no anchors, scalar actor as text.
    _case(
        "activity-feed-without-drill-stays-plain-text",
        _r("activity_feed"),
        {"items": [{"title": "Logged in", "created_at": "2026-05-07T09:00:00", "actor": "Ada"}]},
        ("Logged in", 'class="dz-activity-actor">Ada<'),
        ("data-dz-activity-drill", "dz-avatar"),
    ),
    # ── kanban ──
    _case(
        "kanban-person-ref-dict-emits-avatar",
        _r("kanban", name="board"),
        {
            "items": [
                {
                    "id": "1",
                    "title": "Triage login",
                    "status": "todo",
                    "assigned_to": {
                        "id": "u1",
                        "name": "Alex Agent",
                        "email": "alex@demo.dazzle.local",
                    },
                }
            ],
            "kanban_columns": ["todo"],
            "group_by": "status",
            "display_key": "title",
            "columns": _PERSON_REF_COLUMNS,
        },
        ("Triage login", "dz-avatar", "Alex Agent"),
        ("{'id':",),
    ),
    # Bare scalar leftover (`Ada` / `System`) stays field text — no chip is
    # minted from a string (oral #43, cycle 2161).
    _case(
        "kanban-scalar-leftover-does-not-invent-chip",
        _r("kanban", name="board"),
        {
            "items": [
                {"id": "1", "title": "Triage login", "status": "todo", "assigned_to": "Ada"},
                {"id": "2", "title": "Nightly sweep", "status": "todo", "assigned_to": "System"},
            ],
            "kanban_columns": ["todo"],
            "group_by": "status",
            "display_key": "title",
            "columns": _PERSON_REF_COLUMNS,
        },
        ("Triage login", "Nightly sweep", "Ada", "System"),
        ("dz-avatar", "dz-user-chip"),
    ),
    # Resolved `{key}_display` sibling + id is honest — still an Avatar.
    _case(
        "kanban-display-sibling-emits-avatar",
        _r("kanban", name="board"),
        {
            "items": [
                {
                    "id": "1",
                    "title": "Triage login",
                    "status": "todo",
                    "assigned_to": "u1",
                    "assigned_to_display": "Alex Agent",
                }
            ],
            "kanban_columns": ["todo"],
            "group_by": "status",
            "display_key": "title",
            "columns": _PERSON_REF_COLUMNS,
        },
        ("dz-avatar", "Alex Agent"),
    ),
    # `dz-kanban` CSS hook + title + card content (legacy ctx key spelling).
    _case(
        "kanban-render-smoke",
        _r("kanban", title="Tasks"),
        {
            "items": [{"id": "1", "title": "Buy milk", "status": "todo"}],
            "group_keys": ["todo", "doing", "done"],
            "group_by_field": "status",
        },
        ("dz-kanban", "Tasks", "Buy milk"),
    ),
    # ── list ──
    _case(
        "list-renders-table",
        _r("list", name="users"),
        {
            "items": [{"name": "Alice"}, {"name": "Bob"}],
            "columns": [{"key": "name", "label": "Name"}],
        },
        ("<table", "Alice", "Bob"),
    ),
    # Phase 4B.1.e: endpoint + filter_columns compose a FilterBar above the table.
    _case(
        "list-filter-columns-render-filter-bar",
        _r("list"),
        {
            "items": [{"name": "X"}],
            "columns": [{"key": "name", "label": "Name"}],
            "endpoint": "/api/regions/r",
            "region_name": "r",
            "filter_columns": [
                {
                    "key": "status",
                    "label": "Status",
                    "options": [("open", "Open"), ("closed", "Closed")],
                },
            ],
            "active_filters": {"status": "open"},
        },
        ("filter-bar", 'name="filter_status"', 'value="open" selected>', "<table"),
    ),
    # Workspace list free-text search filters via ?q= (not the FTS results
    # panel): dual_pane directories scored find-by-name broken when the A–Z
    # list never shrank. Swap target is the closest region chrome.
    _case(
        "list-search-fields-render-q-input",
        _r("list", name="contact_list"),
        {
            "items": [{"name": "Ruth Griffiths"}, {"name": "Ada Lovelace"}],
            "columns": [{"key": "name", "label": "Name"}],
            "endpoint": "/api/workspaces/contacts/regions/contact_list",
            "region_name": "contact_list",
            "search_fields": ["first_name", "last_name", "email", "company"],
            "active_search": "Griff",
        },
        (
            'name="q"',
            "dz-list-q-contact_list",
            'value="Griff"',
            "data-dz-list-search",
            'hx-get="/api/workspaces/contacts/regions/contact_list"',
            "Find by First Name",
            "dz-list-search-label",
            "filter-label",
            'hx-target="closest [data-dz-region]"',
        ),
        ("dz-search-results-contact_list",),
    ),
    _case(
        "list-date-range-renders-picker",
        _r("list"),
        {
            "items": [],
            "endpoint": "/api/x",
            "region_name": "r",
            "date_range": True,
            "date_from": "2026-01-01",
            "date_to": "2026-12-31",
        },
        ("date-range-bar", 'value="2026-01-01"', 'value="2026-12-31"'),
    ),
    _case(
        "list-csv-export-default-filename-is-region-name",
        _r("list"),
        {
            "items": [{"name": "X"}],
            "columns": [{"key": "name", "label": "Name"}],
            "endpoint": "/api/x",
            "region_name": "tickets",
            "csv_export": True,
        },
        ("dz-list-csv-button", 'data-dz-csv-filename="tickets.csv"'),
    ),
    _case(
        "list-csv-export-filename-override",
        _r("list"),
        {
            "items": [],
            "endpoint": "/api/x",
            "region_name": "r",
            "csv_export": True,
            "csv_filename": "custom-export.csv",
        },
        ('data-dz-csv-filename="custom-export.csv"',),
    ),
    # Without `endpoint`, FilterBar / DateRangePicker chrome is skipped (both
    # need an HTMX URL); the CSV button is always emitted with an empty endpoint.
    _case(
        "list-without-endpoint-skips-filter-chrome",
        _r("list"),
        {
            "items": [{"name": "X"}],
            "columns": [{"key": "name", "label": "Name"}],
            "filter_columns": [{"key": "k", "label": "K", "options": []}],
            "csv_export": True,
            "date_range": True,
        },
        ("<table", "dz-list-csv-button", 'data-dz-csv-endpoint=""'),
        ("filter-bar", "date-range-bar"),
    ),
    # Missing key, non-dict and duplicate filter columns drop rather than
    # tripping FilterBar's strict invariants.
    _case(
        "list-drops-malformed-filter-columns",
        _r("list"),
        {
            "items": [],
            "endpoint": "/api/x",
            "region_name": "r",
            "filter_columns": [
                None,
                42,
                {"label": "no key"},
                {"key": "valid", "label": "Valid", "options": []},
                {"key": "valid", "label": "Dup"},
            ],
        },
        ("filter-bar", ">All Valid<"),
        ("Dup",),
    ),
    # ── grid ──
    _case(
        "grid-renders-one-card-per-item",
        _r("grid", name="cards", title="Cards"),
        {"items": [{"title": "Alpha"}, {"title": "Beta"}, {"title": "Gamma"}], "columns": 2},
        ("Alpha", "Beta", "Gamma", "Cards"),
    ),
    _case(
        "grid-label-field-override",
        _r("grid"),
        {"items": [{"label": "Custom", "title": "Ignored"}], "label_field": "label"},
        ("Custom",),
        ("Ignored",),
    ),
    # columns=999 is clamped to the Grid primitive's range instead of raising.
    _case(
        "grid-clamps-column-count",
        _r("grid"),
        {"items": [{"title": "Clamp me"}], "columns": 999},
        ("Clamp me",),
    ),
    _case(
        "grid-person-ref-emits-card-meta-avatar",
        _r("grid", name="cards"),
        {
            "items": [
                {
                    "title": "Storefront refresh",
                    "owner": {"id": "u1", "name": "Ada Owner", "email": "ada@demo.dazzle.local"},
                }
            ],
            "display_key": "title",
            "columns": [
                {"key": "title", "label": "Title", "type": "text"},
                {"key": "owner", "label": "Owner", "type": "ref", "ref_entity": "User"},
            ],
        },
        ("Storefront refresh", "dz-avatar", "Ada Owner"),
        ("{'id':", "UUID("),
    ),
    # Dashboard grid cells open VIEW hubs at /app/<slug>/{id}; without the
    # template trial agents invented /brands/{id} and hit 404s.
    _case(
        "grid-drills-to-app-shell-hub-not-api-plural",
        _r("grid", name="brands"),
        {
            "items": [{"id": "a267b2db-ada2-4314-9172-c2c293207acb", "name": "Palmer Group"}],
            "columns": [{"key": "name", "label": "Name", "type": "text"}],
            "display_key": "name",
            "detail_url_template": "/app/brand/{id}",
        },
        ("/app/brand/a267b2db-ada2-4314-9172-c2c293207acb", "data-dz-grid-drill", "Palmer Group"),
        ("/brands/",),
    ),
    # ── metrics ──
    _case(
        "metrics-renders-pre-computed-kpi-tiles",
        _r("metrics", name="kpis"),
        {
            "metrics": [
                {"label": "Open", "value": "42", "trend": "up", "delta": "+5"},
                {"label": "Closed", "value": "18", "trend": "flat"},
            ]
        },
        ("Open", "42", "Closed", "18"),
    ),
    # Legacy shape: ctx['aggregates'] maps to KPIs label-cased from the keys.
    _case(
        "metrics-falls-back-to-aggregates-dict",
        _r("metrics", name="kpis"),
        {"aggregates": {"total_open": 7, "total_closed": 3}},
        ("Total Open", "7"),
    ),
    # `display: summary` reuses the metrics adapter.
    _case(
        "metrics-summary-alias",
        _r("summary"),
        {"metrics": [{"label": "Revenue", "value": "1"}]},
        ("Revenue", "dz-metric"),
    ),
    _case(
        "metrics-invalid-tone-stripped",
        _r("metrics"),
        {"metrics": [{"label": "X", "value": "1", "tone": "garbage"}]},
        ("X",),
        ('data-dz-tone="garbage"',),
    ),
    # Phase 4B.1.a: MetricTile keeps the legacy delta block; up + positive_down = bad.
    _case(
        "metrics-extended-deltas-render-full-block",
        _r("metrics"),
        {
            "metrics": [
                {
                    "label": "Open Tickets",
                    "value": 1234,
                    "tone": "warning",
                    "delta_direction": "up",
                    "delta_sentiment": "positive_down",
                    "delta": "42",
                    "delta_pct": 12.5,
                    "delta_period_label": "last week",
                }
            ]
        },
        (
            'data-dz-metric-key="open_tickets"',
            'data-dz-tone="warning"',
            'data-dz-delta-tone="destructive"',
            "1,234",
            "↑",
            "+42",
            "(12.5%)",
            "vs last week",
        ),
    ),
    _case(
        "metrics-delta-up-positive_up-renders-good",
        _r("metrics"),
        {
            "metrics": [
                {
                    "label": "Revenue",
                    "value": 50000,
                    "delta_direction": "up",
                    "delta_sentiment": "positive_up",
                    "delta": "5000",
                    "delta_period_label": "last month",
                }
            ]
        },
        ('data-dz-delta-tone="positive"',),
    ),
    _case(
        "metrics-no-delta-omits-delta-block",
        _r("metrics"),
        {"metrics": [{"label": "Total", "value": 42}]},
        (">42<",),
        ("dz-metric-delta",),
    ),
    # metric_number: thousands separators, bools → Yes/No, None → "0".
    _case(
        "metrics-value-through-metric-number-filter",
        _r("metrics"),
        {
            "metrics": [
                {"label": "Big", "value": 1500000},
                {"label": "Bool", "value": True},
                {"label": "Null", "value": None},
            ]
        },
        ("1,500,000", ">Yes<", ">0<"),
    ),
    _case(
        "metrics-sub-one-float-rounds-to-2dp-1479",
        _r("metrics"),
        {"metrics": [{"label": "Avg Confidence", "value": 0.8850441412520064}]},
        ("0.89",),
        ("0.8850441412520064",),
    ),
    # On scope-denial ctx['aggregates'] still holds raw IR; the fallback drops
    # it instead of stringifying a repr that leaks the where-clause.
    _case(
        "metrics-scope-denied-raw-ir-not-leaked-1425",
        _r("metrics", name="kpis", empty="No access."),
        {
            "aggregates": {
                "total_secret": AggregateRef(func="count", entity="SecretEntity"),
                "ratio": DerivedMetricExpr(metric_name="ratio"),
            }
        },
        ("No access.",),
        ("func=", "entity=", "SecretEntity", "metric_name="),
    ),
    # A person dict on a KPI tile is refused — no str(dict) / name prose.
    _case(
        "metrics-person-value-refused-not-invented",
        _r("metrics"),
        {
            "metrics": [
                {"label": "Open", "value": 12},
                {
                    "label": "Assignee",
                    "key": "assigned_to",
                    "type": "ref",
                    "ref_entity": "User",
                    "value": {
                        "id": "u1",
                        "name": "Support Agent",
                        "email": "agent@demo.dazzle.local",
                    },
                },
            ]
        },
        ("Open", ">12<"),
        ("Support Agent", "Assignee", "{'id':", "dz-avatar"),
    ),
    # ── bar chart ──
    # v0.66.110: bucket labels humanized via render_status_badge.
    _case(
        "bar-chart-renders-humanized-buckets",
        _r("bar_chart", name="severity"),
        {"buckets": [("low", 3), ("medium", 7), ("high", 2)]},
        ("Low", "Medium", "High"),
    ),
    # Reference overlays are ignored in the bucketed bar chart (legacy parity).
    _case(
        "bar-chart-ignores-reference-overlays",
        _r("bar_chart"),
        {
            "buckets": [("low", 3), ("high", 9)],
            "reference_lines": [{"value": 10, "label": "SLA", "style": "dashed"}],
            "reference_bands": [{"from": 0, "to": 5, "label": "Healthy", "color": "positive"}],
        },
        ("Low", "High", "dz-bar-chart-region"),
    ),
    _case(
        "bar-chart-alt-dict-bucket-shapes",
        _r("bar_chart"),
        {"buckets": [{"label": "open", "value": 5}, {"key": "closed", "count": 9}]},
        ("Open", "Closed"),
    ),
    # ── pivot table ──
    _case(
        "pivot-table-renders-rows-and-columns",
        _r("pivot_table"),
        {
            "rows": ["low", "high"],
            "columns": ["open", "closed"],
            "cells": {("low", "open"): 3, ("high", "closed"): 7},
        },
        ("low", "high", "open", "closed", ">3<", ">7<"),
    ),
    # Cells naming an undeclared row/column drop (PivotTable would raise).
    _case(
        "pivot-table-drops-cells-with-unknown-dimensions",
        _r("pivot_table"),
        {"rows": ["a"], "columns": ["x"], "cells": {("a", "x"): 1, ("z", "x"): 99}},
        (">1<",),
        ("99",),
    ),
    # ── tabbed list ──
    # Eager `{tabs: [...]}` shape renders content inline — no hx-get.
    _case(
        "tabbed-list-eager-tabs-render-inline",
        _r("tabbed_list"),
        {
            "tabs": [
                {
                    "key": "open",
                    "label": "Open",
                    "items": [{"name": "Alpha"}],
                    "columns": [{"key": "name", "label": "Name"}],
                },
                {
                    "key": "closed",
                    "label": "Closed",
                    "items": [{"name": "Beta"}],
                    "columns": [{"key": "name", "label": "Name"}],
                },
            ]
        },
        ('class="dz-tabs"', "Alpha", "Beta"),
        ("hx-get",),
    ),
    _case(
        "tabbed-list-legacy-slices-alias",
        _r("tabbed_list"),
        {
            "slices": [
                {
                    "key": "k",
                    "items": [{"x": "SliceValue"}],
                    "columns": [{"key": "x", "label": "X"}],
                }
            ]
        },
        ("SliceValue",),
    ),
    # Tabs raises on duplicate keys; the adapter dedups (first wins).
    _case(
        "tabbed-list-dedupes-duplicate-tab-keys",
        _r("tabbed_list"),
        {
            "tabs": [
                {
                    "key": "k",
                    "items": [{"x": "FirstValue"}],
                    "columns": [{"key": "x", "label": "X"}],
                },
                {
                    "key": "k",
                    "items": [{"x": "SecondValue"}],
                    "columns": [{"key": "x", "label": "X"}],
                },
            ]
        },
        ("FirstValue",),
        ("SecondValue",),
    ),
    # Phase 4B.1.d: source_tabs build a lazy panel; honest HM link-strip (no
    # role=tablist it can't back); first tab loads, the rest on intersect.
    _case(
        "tabbed-list-source-tabs-lazy-panel",
        _r("tabbed_list", name="t"),
        {
            "region_name": "ticket_tabs",
            "source_tabs": [
                {
                    "key": "github",
                    "label": "GitHub",
                    "endpoint": "/api/workspaces/admin/regions/ticket_tabs/github",
                },
                {
                    "key": "slack",
                    "label": "Slack",
                    "endpoint": "/api/workspaces/admin/regions/ticket_tabs/slack",
                },
            ],
        },
        (
            'class="dz-tabs"',
            'id="tabs-ticket_tabs"',
            'class="dz-tabs__tab"',
            'aria-current="true"',
            'data-dz-tab-target="tab-ticket_tabs-github"',
            'hx-get="/api/workspaces/admin/regions/ticket_tabs/github"',
            'hx-trigger="load"',
            'hx-trigger="intersect once"',
        ),
        ('role="tablist"',),
    ),
    _case(
        "tabbed-list-source-tabs-drop-malformed-entries",
        _r("tabbed_list"),
        {
            "region_name": "r",
            "source_tabs": [
                None,
                {"key": "valid", "label": "Valid", "endpoint": "/api/valid"},
                {"label": "Missing key", "endpoint": "/api/x"},
                {"key": "missing-endpoint"},
                {"key": "valid", "label": "Dup", "endpoint": "/api/other"},
            ],
        },
        (">Valid<",),
        ("Missing key", "Dup"),
    ),
    # Without ctx region_name, DOM ids are namespaced by the region's name.
    _case(
        "tabbed-list-source-tabs-dom-ids-fall-back-to-region-name",
        _r("tabbed_list", name="my_region"),
        {"source_tabs": [{"key": "x", "label": "X", "endpoint": "/api/x"}]},
        ("tabs-my_region",),
    ),
    # tab.eager fires hx-trigger=load even off the first position.
    _case(
        "tabbed-list-eager-flag-overrides-position-default",
        _r("tabbed_list"),
        {
            "region_name": "r",
            "source_tabs": [
                {"key": "a", "label": "A", "endpoint": "/a"},
                {"key": "b", "label": "B", "endpoint": "/b", "eager": True},
                {"key": "c", "label": "C", "endpoint": "/c"},
            ],
        },
        counts={'hx-trigger="load"': 2, 'hx-trigger="intersect once"': 1},
    ),
    # ── radar / line chart / diagram ──
    _case(
        "radar-render-smoke",
        _r("radar"),
        {"axes": [("Python", 9), ("Go", 7), ("Rust", 5), ("JavaScript", 6)]},
        ("dz-radar", "Python", "Go", "Rust"),
    ),
    _case(
        "radar-alt-dict-axis-shapes",
        _r("radar"),
        {
            "axes": [
                {"axis": "Xaxis", "value": 1},
                {"label": "Yaxis", "value": 2},
                {"axis": "Zaxis", "value": 3},
            ]
        },
        ("Xaxis", "Yaxis", "Zaxis"),
    ),
    # v0.66.110: legacy region wrapper class is dz-line-chart-region.
    _case(
        "line-chart-render-smoke",
        _r("line_chart"),
        {"points": [("Jan", 5), ("Feb", 8), ("Mar", 12)]},
        ("dz-line-chart-region", "Jan", "Feb", "Mar"),
        ("dz-timeseries__references",),
    ),
    _case(
        "line-chart-alt-dict-point-shapes",
        _r("line_chart"),
        {"points": [{"x": "Jan", "y": 10}, {"label": "Feb", "value": 20}]},
        ("Jan", "Feb"),
    ),
    # v0.66.110: reference lines render as SVG overlays; unknown style → solid.
    _case(
        "line-chart-carries-reference-lines",
        _r("line_chart"),
        {
            "points": [("Jan", 50), ("Feb", 75)],
            "reference_lines": [
                {"value": 100, "label": "Target", "style": "dashed"},
                {"value": 50, "label": "Min", "style": "wavy"},
            ],
        },
        ('stroke-dasharray="4,3"', "<title>Target: 100", "<title>Min: 50"),
    ),
    # Bands accept from/to and from_value/to_value; from > to drops.
    _case(
        "line-chart-carries-reference-bands-with-alt-keys",
        _r("line_chart"),
        {
            "points": [("a", 1), ("b", 2)],
            "reference_bands": [
                {"from": 80, "to": 120, "label": "Healthy", "color": "positive"},
                {"from": 200, "to": 100, "label": "Bad order"},
                {"from_value": 0, "to_value": 30, "label": "Danger", "color": "destructive"},
            ],
        },
        ("<title>Healthy:", "hsl(145, 55%, 45%)", "<title>Danger:", "var(--colour-danger)"),
        ("Bad order",),
    ),
    _case(
        "diagram-render-smoke",
        _r("diagram"),
        {
            "nodes": ["Device", "Tester", "IssueReport"],
            "edges": [("Device", "Tester"), ("Device", "IssueReport")],
        },
        ("dz-diagram", "Device", "Tester", "IssueReport", "→"),
    ),
    _case(
        "diagram-alt-dict-edge-shape",
        _r("diagram"),
        {"nodes": ["Aa", "Bb"], "edges": [{"from": "Aa", "to": "Bb"}]},
        ('dz-diagram__edge-from">Aa', 'dz-diagram__edge-to">Bb'),
    ),
    # Edges with unknown endpoints drop (Diagram would raise); self-loops stay.
    _case(
        "diagram-drops-edges-with-unknown-endpoints",
        _r("diagram"),
        {"nodes": ["Alpha"], "edges": [("Alpha", "ZZZ"), ("Alpha", "Alpha")]},
        ('dz-diagram__edge-from">Alpha', 'dz-diagram__edge-to">Alpha'),
        ("ZZZ",),
    ),
    # v0.66.118: empty diagram uses the legacy hardcoded copy; empty_message is ignored.
    _case(
        "diagram-empty-renders-legacy-hardcoded-message",
        _r("diagram", empty="ignored"),
        {"nodes": []},
        ("dz-diagram-empty", "No entity relationships to display."),
        ("ignored",),
    ),
    # ── confirm action panel ──
    # Phase 4A fallback: prompt + action_label become a synthetic single-item gate.
    _case(
        "confirm-panel-legacy-prompt-ctx-synthetic-checklist",
        _r("confirm_action_panel", title="Confirm Delete"),
        {"prompt": "This will permanently delete 5 items.", "action_label": "Delete"},
        ("Confirm Delete", "permanently delete 5 items", "dz-confirm-panel"),
        ("&quot;",),
    ),
    # HM data-dz-confirm-gate checklist: required-count, primary parked in
    # data-dz-confirm-href + aria-disabled until armed (Alpine island retired).
    _case(
        "confirm-panel-off-state-hm-gated-checklist",
        _r("confirm_action_panel"),
        {
            "state_value": "off",
            "confirmations": [
                {
                    "title": "I have reviewed the data",
                    "caption": "All records will be synced",
                    "required": True,
                },
                {"title": "I have legal authority", "required": True},
                {"title": "Optional: notify the team"},
            ],
            "primary_action_url": "/admin/sync/confirm",
            "secondary_action_url": "/admin/sync/draft",
            "audit_enabled": True,
        },
        (
            'data-dz-state-value="off"',
            "data-dz-confirm-gate",
            'data-dz-required-count="2"',
            "I have reviewed the data",
            "All records will be synced",
            'data-dz-confirm-href="/admin/sync/confirm"',
            'aria-disabled="true"',
            "/admin/sync/draft",
            "dz-confirm-audit",
        ),
        # Leading space: a bare href= would substring-match data-dz-confirm-href.
        ("x-data", ' href="/admin/sync/confirm"'),
    ),
    _case(
        "confirm-panel-live-state-summary-and-revoke",
        _r("confirm_action_panel"),
        {"state_value": "live", "revoke_url": "/admin/sync/revoke"},
        ("Currently live", "/admin/sync/revoke", "dz-confirm-revoke"),
        ("dz-confirm-checklist",),
    ),
    _case(
        "confirm-panel-revoked-state-offers-re-enable",
        _r("confirm_action_panel"),
        {"state_value": "revoked", "primary_action_url": "/admin/sync/reenable"},
        ("revoked", "Re-enable", "/admin/sync/reenable"),
    ),
    _case(
        "confirm-panel-drops-malformed-confirmations",
        _r("confirm_action_panel"),
        {
            "state_value": "off",
            "confirmations": [None, 42, {"title": ""}, {"title": "Valid item", "required": True}],
            "primary_action_url": "/x",
        },
        ("Valid item", 'data-dz-required-count="1"', "data-dz-confirm-gate"),
    ),
    # ── search box ──
    # Phase 4B.1.d: typed SearchBox — FTS input + lazy results + CSS-only
    # coaching toggle (Alpine q-island retired in Tier F3).
    _case(
        "search-box-typed-primitive",
        _r("search_box", name="manuscript_search"),
        {
            "source_entity": "Manuscript",
            "placeholder": "Find a manuscript",
            "coaching_message": "Type a title or keyword",
        },
        (
            "dz-search-box-region",
            'hx-get="/_dazzle/fts/Manuscript?html=1"',
            "this.value.trim().length>0",
            'aria-live="polite"',
            "dz-search-box-empty",
            "Type a title or keyword",
        ),
        ("x-show", "x-data", "x-model"),
    ),
    _case(
        "search-box-endpoint-falls-back-to-region-name",
        _r("search_box", name="ticket_search"),
        {"placeholder": "Find tickets…"},
        ('hx-get="/_dazzle/fts/ticket_search?html=1"', "Find tickets"),
    ),
    _case(
        "search-box-default-coaching-message",
        _r("search_box", name="s"),
        {"source_entity": "Item"},
        ("Type to search",),
    ),
    # Visible chrome surfaces the author title so FTS isn't mistaken for a list filter.
    _case(
        "search-box-placeholder-uses-author-title",
        _r(
            "search_box",
            name="contact_search",
            title="Find a contact — results appear below",
            empty="Results appear below as you type. The A–Z list is not filtered.",
        ),
        {"source_entity": "Contact"},
        ('placeholder="Find a contact — results appear below"', "Results appear below as you type"),
    ),
    _case(
        "search-box-placeholder-falls-back-to-empty-clause",
        _r(
            "search_box",
            name="find_contact",
            empty="Results appear below as you type (name, company, or email).",
        ),
        {"source_entity": "Contact"},
        ('placeholder="Results appear below as you type (name, company, or email)"',),
    ),
    # Several SearchBoxes on one page need distinct result panels (ctx `name`).
    *(
        _case(
            f"search-box-results-panel-id-{name}",
            _r("search_box"),
            {"source_entity": entity, "name": name},
            (f"dz-search-results-{name}",),
        )
        for entity, name in [("A", "search_a"), ("B", "search_b")]
    ),
    # ── pipeline steps / status list ──
    # v0.66.106: authored pipeline_stage_data; None value → "—"; last stage has no connector.
    _case(
        "pipeline-steps-render-stages-with-connectors",
        _r("pipeline_steps"),
        {
            "pipeline_stage_data": [
                {"label": "Plan", "value": 1, "caption": "Scope locked"},
                {"label": "Build", "value": 2},
                {"label": "Ship", "value": None, "caption": "Pending"},
            ]
        },
        ("Plan", "Build", "Ship", "Scope locked", "Pending", "—"),
        counts={'class="dz-pipeline-connector"': 2},
    ),
    # v0.66.104: authored status_entries emit the legacy dz-status-list structure.
    _case(
        "status-list-renders-authored-entries",
        _r("status_list"),
        {
            "status_entries": [
                {"title": "Service A", "state": "positive", "caption": "All systems normal"},
                {"title": "Service B", "state": "destructive", "icon": "alert-triangle"},
            ]
        },
        (
            "Service A",
            "Service B",
            'data-dz-state="positive"',
            'data-dz-state="destructive"',
            "All systems normal",
            'data-lucide="alert-triangle"',
        ),
    ),
    # Unknown state coerces to neutral (legacy `state | default('neutral')`).
    _case(
        "status-list-unknown-state-falls-back-to-neutral",
        _r("status_list"),
        {"status_entries": [{"title": "Mystery", "state": "purple"}]},
        ('data-dz-state="neutral"',),
        ("dz-status-list-pill",),
    ),
    # ── queue ──
    # v0.66.117: dedicated QueueRegion; title via display+_display → display → id.
    _case(
        "queue-renders-minimal-items",
        _r("queue"),
        {
            "items": [
                {"id": 1, "title": "Item One", "title_display": "Item One", "status": "open"},
                {"id": 2, "title": "Item Two", "title_display": "Item Two", "status": "open"},
            ],
            "columns": [{"key": "title", "label": "Title"}],
            "display_key": "title",
        },
        ("Item One", "Item Two", "dz-queue-region"),
    ),
    # Queue titles drill to /app/ticket/{id} with dual-open discovery (cycle 1606).
    _case(
        "queue-drills-to-app-shell-hub",
        _r("queue", name="open_queue"),
        {
            "items": [
                {
                    "id": "5f122722-3193-476c-8f98-34b41f792d4d",
                    "subject": "Double charged on monthly invoice",
                    "status": "open",
                }
            ],
            "columns": [{"key": "subject", "type": "text"}, {"key": "status", "type": "badge"}],
            "display_key": "subject",
            "detail_url_template": "/app/ticket/{id}",
        },
        (
            "/app/ticket/5f122722-3193-476c-8f98-34b41f792d4d",
            "data-dz-queue-drill",
            "Double charged",
            'data-dz-open-entity="Ticket"',
            'data-dz-open-role="primary"',
            'data-dz-open-chain="/app/ticket/5f122722-3193-476c-8f98-34b41f792d4d"',
        ),
        ("/tickets/",),
    ),
    # A non-FK display_field has no `*_display`; fall through to the field, not the UUID.
    _case(
        "queue-title-uses-display-field-without-fk-display-suffix",
        _r("queue", name="open_queue"),
        {
            "items": [
                {
                    "id": "70193944-6955-4d6d-9a6a-4d076a6e033f",
                    "subject": "Cannot login to my account",
                    "customer_email": "user@example.com",
                    "status": "open",
                }
            ],
            "columns": [
                {"key": "subject", "label": "Subject", "type": "text"},
                {"key": "status", "label": "Status", "type": "badge"},
            ],
            "display_key": "subject",
        },
        ("Cannot login to my account",),
        ("70193944-6955-4d6d-9a6a-4d076a6e033f",),
    ),
    _case(
        "queue-title-falls-back-to-id-without-display-key",
        _r("queue"),
        {
            "items": [
                {
                    "id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                    "subject": "Hidden subject",
                    "status": "open",
                }
            ],
            "columns": [{"key": "status", "label": "Status", "type": "badge"}],
        },
        ("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",),
    ),
    # Phase 4B.1.d: per-row hx-put transition buttons; the transition to the
    # current state is skipped (legacy "don't offer your current state" UX).
    _case(
        "queue-transition-buttons-skip-current-state",
        _r("queue"),
        {
            "items": [{"id": 42, "title": "Bug A", "status": "open"}],
            "endpoint": "/api/regions/tickets",
            "region_name": "tickets",
            "queue_transitions": [
                {"label": "Resolve", "to_state": "resolved"},
                {"label": "Close", "to_state": "closed"},
                {"label": "Reopen", "to_state": "open"},
            ],
            "queue_status_field": "status",
            "queue_api_endpoint": "/api/tickets",
        },
        ('hx-put="/api/tickets/42"', "Resolve", "Close"),
        ("Reopen",),
    ),
    # Missing queue_api_endpoint skips the buttons; the row still renders.
    _case(
        "queue-skips-transitions-without-required-ctx",
        _r("queue"),
        {
            "items": [{"id": 1, "title": "Row X", "title_display": "Row X", "status": "open"}],
            "display_key": "title",
            "queue_transitions": [{"label": "Close", "to_state": "closed"}],
            "queue_status_field": "status",
        },
        ("Row X",),
        ("hx-put",),
    ),
    _case(
        "queue-count-metrics-overflow",
        _r("queue"),
        {
            "items": [{"id": 1, "title": "X", "status": "open"}],
            "metrics": [{"label": "Open", "value": 12}, {"label": "Closed", "value": 88}],
            "endpoint": "/api/regions/r",
            "region_name": "r",
            "total": 100,
        },
        ("dz-queue-count", "100", "dz-queue-metric", "Showing 1 of 100"),
    ),
    _case(
        "queue-omits-redundant-count-when-all-rows-visible",
        _r("queue"),
        {
            "items": [{"id": 1, "title": "First"}, {"id": 2, "title": "Second"}],
            "endpoint": "/api/regions/r",
            "region_name": "r",
            "total": 2,
            "columns": [{"key": "title", "label": "Title", "type": "text"}],
            "display_key": "title",
        },
        ("First", "Second"),
        ("dz-queue-count-row",),
    ),
    # ── cohort strip (#1018) ──
    _case(
        "cohort-strip-dispatches-to-builder",
        _cohort_region(),
        {"cohort_cells": [], "cohort_endpoint": "/r/cohort"},
        ('class="dz-cohort-strip-region"',),
    ),
    # Zero cells render the empty message; the lens toggle stays so users can swap.
    _case(
        "cohort-strip-empty-cells-keep-lens-toggle",
        _cohort_region(empty_message="Nobody here yet."),
        {"cohort_endpoint": "/r/cohort"},
        ("Nobody here yet.", 'class="dz-cohort-strip-empty"', 'role="tablist"'),
    ),
    _case(
        "cohort-strip-builds-cells-from-ctx-dicts",
        _cohort_region(),
        {
            "cohort_cells": [
                {
                    "member_id": "p1",
                    "member_name": "Alice",
                    "primary_value": "78",
                    "subtitle": "9G",
                    "tone": "good",
                    "drill_url": "/m/p1",
                },
                {
                    "member_id": "p2",
                    "member_name": "Bob",
                    "primary_value": "62",
                    "subtitle": "9G",
                    "tone": "warn",
                },
            ],
            "cohort_endpoint": "/r/cohort",
        },
        (
            'data-member-id="p1"',
            'data-member-id="p2"',
            "Alice",
            "Bob",
            'data-dz-tone="good"',
            'data-dz-tone="warn"',
        ),
    ),
    _case(
        "cohort-strip-skips-cells-with-missing-member-id",
        _cohort_region(),
        {
            "cohort_cells": [
                {"member_id": "p1", "member_name": "OK", "primary_value": "1"},
                {"member_id": "", "member_name": "Bad", "primary_value": "?"},
                {"member_name": "Missing key", "primary_value": "?"},
            ],
            "cohort_endpoint": "/r/cohort",
        },
        ('data-member-id="p1"',),
        ("Bad", "Missing key"),
    ),
    # Zero lenses degrade to an EmptyState instead of the at-least-one-lens raise.
    _case(
        "cohort-strip-no-lenses-renders-not-configured",
        _cohort_region(member_via="x", lenses=[]),
        {},
        ("Cohort strip not configured",),
    ),
    _case(
        "cohort-strip-unknown-tone-coerces-to-neutral",
        _cohort_region(),
        {
            "cohort_cells": [
                {"member_id": "p1", "member_name": "A", "primary_value": "1", "tone": "rainbow"}
            ],
            "cohort_endpoint": "/r/cohort",
        },
        ('data-dz-tone="neutral"',),
        ("rainbow",),
    ),
    _case(
        "cohort-strip-endpoint-falls-back-to-region-url",
        _cohort_region(),
        {"cohort_cells": [], "region_url": "/api/regions/cohort"},
        ('hx-get="/api/regions/cohort?lens=',),
    ),
    # ── day timeline (#1016) ──
    _case(
        "day-timeline-dispatches-to-builder",
        _day_timeline_region(),
        {},
        ('class="dz-day-timeline-region"',),
    ),
    _case(
        "day-timeline-empty-slots-render-empty-state",
        _day_timeline_region(empty_message="No periods today."),
        {"day_timeline_slots": []},
        ('class="dz-day-timeline-empty"', "No periods today."),
    ),
    _case(
        "day-timeline-builds-slots-with-positions",
        _day_timeline_region(),
        {
            "day_timeline_slots": [
                {"slot_id": "p1", "label": "Period 1 — 09:00", "position": "before"},
                {"slot_id": "p2", "label": "Period 2 — 10:00", "position": "active"},
                {"slot_id": "p3", "label": "Period 3 — 11:00", "position": "after"},
            ]
        },
        ('data-slot-id="p1"', "is-before", "is-active", "is-after"),
        counts={'data-dz-position="active"': 1},
    ),
    _case(
        "day-timeline-unknown-position-falls-through-to-after",
        _day_timeline_region(),
        {"day_timeline_slots": [{"slot_id": "p1", "label": "P1", "position": "weird"}]},
        ("is-after",),
    ),
    # A resolver that mis-classifies several slots as active keeps the first.
    _case(
        "day-timeline-collapses-multiple-active-slots",
        _day_timeline_region(),
        {
            "day_timeline_slots": [
                {"slot_id": f"p{i}", "label": f"P{i}", "position": "active"} for i in (1, 2, 3)
            ]
        },
        counts={'data-dz-position="active"': 1},
    ),
    _case(
        "day-timeline-skips-slots-with-missing-id",
        _day_timeline_region(),
        {
            "day_timeline_slots": [
                {"slot_id": "p1", "label": "OK"},
                {"slot_id": "", "label": "Bad"},
                {"label": "Missing key"},
            ]
        },
        ('data-slot-id="p1"',),
        ("Bad", "Missing key"),
    ),
    _case(
        "day-timeline-drill-url-wraps-slot-in-anchor",
        _day_timeline_region(),
        {"day_timeline_slots": [{"slot_id": "p1", "label": "P1", "drill_url": "/lessons/123"}]},
        ('href="/lessons/123"',),
    ),
    # `body` is pre-rendered HTML from data resolution; passed through as-is.
    _case(
        "day-timeline-passes-through-pre-rendered-body",
        _day_timeline_region(),
        {
            "day_timeline_slots": [
                {
                    "slot_id": "p1",
                    "label": "P1",
                    "body": '<span class="lesson-card">Year 8 Maths — Room B12</span>',
                }
            ]
        },
        ('<span class="lesson-card">Year 8 Maths — Room B12</span>',),
    ),
    # ── task inbox (#1015) ──
    _case(
        "task-inbox-dispatches-to-builder",
        _task_inbox_region(),
        {},
        ('class="dz-task-inbox-region"',),
    ),
    _case(
        "task-inbox-uses-config-empty-state",
        _task_inbox_region(empty_state="Nothing to do."),
        {},
        ("Nothing to do.",),
    ),
    # Unknown icon names keep the authored value for client hydration.
    _case(
        "task-inbox-builds-items-with-urgency",
        _task_inbox_region(),
        {
            "task_inbox_items": [
                {
                    "item_id": "i1",
                    "icon": "register",
                    "title": "Register 8X",
                    "meta": "Period 1",
                    "urgency": "due",
                    "drill_url": "/r/i1",
                },
                {"item_id": "i2", "icon": "message", "title": "Reply", "urgency": "overdue"},
            ]
        },
        (
            'data-dz-item-id="i1"',
            'data-dz-urgency="due"',
            'data-dz-urgency="overdue"',
            'data-lucide="register"',
            'href="/r/i1"',
        ),
    ),
    _case(
        "task-inbox-builds-summary-chips",
        _task_inbox_region(),
        {
            "task_inbox_chips": [
                {"chip_id": "c1", "count": 7, "label": "manuscripts ready", "drill_url": "/m"},
                {"chip_id": "c2", "count": 3, "label": "drafts in review"},
            ]
        },
        ('class="dz-task-inbox-chips"', ">7<", "manuscripts ready", 'href="/m"'),
    ),
    _case(
        "task-inbox-skips-items-with-missing-id",
        _task_inbox_region(),
        {
            "task_inbox_items": [
                {"item_id": "i1", "icon": "x", "title": "ok"},
                {"item_id": "", "icon": "x", "title": "bad"},
            ]
        },
        ('data-dz-item-id="i1"',),
        ("bad",),
    ),
    _case(
        "task-inbox-unknown-urgency-falls-through-to-later",
        _task_inbox_region(),
        {"task_inbox_items": [{"item_id": "i", "icon": "x", "title": "t", "urgency": "weird"}]},
        ('data-dz-urgency="later"',),
    ),
    # A buggy resolver's negative / non-int chip count clamps to 0.
    *(
        _case(
            f"task-inbox-{label}-chip-count-coerces-to-zero",
            _task_inbox_region(),
            {"task_inbox_chips": [{"chip_id": "c", "count": count, "label": "x"}]},
            (">0<",),
        )
        for label, count in [("negative", -5), ("non-int", "??")]
    ),
    # ── entity card (#1017) ──
    _case(
        "entity-card-dispatches-to-builder",
        _entity_card_region(),
        {},
        ('class="dz-entity-card-region"',),
    ),
    _case(
        "entity-card-renders-record-label",
        _entity_card_region(),
        {
            "entity_card_record_label": "Alice Wong · Year 9",
            "entity_card_sections": [{"section_id": "s", "label": "Halo", "body": "<p>x</p>"}],
        },
        ("Alice Wong",),
    ),
    _case(
        "entity-card-omits-record-label-heading-when-empty",
        _entity_card_region(),
        {"entity_card_sections": [{"section_id": "s", "label": "L"}]},
        absent=("dz-entity-card-heading",),
    ),
    _case(
        "entity-card-builds-sections-with-modes",
        _entity_card_region(),
        {
            "entity_card_sections": [
                {
                    "section_id": "halo",
                    "label": "Halo",
                    "mode": "halo",
                    "column": "main",
                    "body": "<div>halo body</div>",
                },
                {"section_id": "flags", "label": "Flags", "mode": "flags", "column": "sidebar"},
                {"section_id": "marks", "label": "Marks", "mode": "mini_bars", "column": "main"},
            ]
        },
        (
            'data-section-id="halo"',
            'data-dz-mode="flags"',
            'data-dz-mode="mini_bars"',
            'data-dz-column="sidebar"',
        ),
    ),
    _case(
        "entity-card-skips-omitted-sections",
        _entity_card_region(),
        {
            "entity_card_sections": [
                {"section_id": "shown", "label": "Shown"},
                {"section_id": "hidden", "label": "Hidden", "is_omitted": True},
            ]
        },
        ('data-section-id="shown"',),
        ('data-section-id="hidden"',),
    ),
    _case(
        "entity-card-unknown-mode-falls-through-to-halo",
        _entity_card_region(),
        {"entity_card_sections": [{"section_id": "s", "label": "L", "mode": "weird"}]},
        ('data-dz-mode="halo"',),
    ),
    _case(
        "entity-card-unknown-column-falls-through-to-main",
        _entity_card_region(),
        {"entity_card_sections": [{"section_id": "s", "label": "L", "column": "weird"}]},
        ('data-dz-column="main"',),
    ),
    _case(
        "entity-card-skips-sections-with-missing-id",
        _entity_card_region(),
        {
            "entity_card_sections": [
                {"section_id": "ok", "label": "OK"},
                {"section_id": "", "label": "Bad"},
            ]
        },
        ('data-section-id="ok"',),
        ("Bad",),
    ),
]


@pytest.mark.parametrize(("region", "ctx", "present", "absent", "counts"), _RENDER_CASES)
def test_region_renders(
    region: object,
    ctx: dict,
    present: tuple[str, ...],
    absent: tuple[str, ...],
    counts: dict[str, int],
) -> None:
    fragment = WorkspaceRegionAdapter().build(region, ctx)
    assert isinstance(fragment, Surface)
    html = _render(fragment)
    missing = [s for s in present if s not in html]
    leaked = [s for s in absent if s in html]
    miscounted = {s: html.count(s) for s, n in counts.items() if html.count(s) != n}
    assert not (missing or leaked or miscounted), (
        f"missing={missing} leaked={leaked} miscounted={miscounted}"
    )
