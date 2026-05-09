"""Phase 4B.5.c (v0.66.125): full `_content.html` byte-equivalence
assembly tests.

This is the gate test for the typed-Fragment chrome port: compose
WorkspaceShell with the inner primitives (WorkspaceContextSelector?,
WorkspaceToolbar, DashboardGrid, AddCardRow) plus a sibling
WorkspaceDrawer, render via FragmentRenderer, and assert byte-
equivalence against rendering `_content.html` directly.

Once this test holds across the relevant fixture matrix, 4B.6
(decommission DISPLAY_TEMPLATE_MAP + 32 Jinja region templates) is
unblocked — the typed substrate IS the canonical Dazzle rendering
method for workspaces."""

from __future__ import annotations

import json

from dazzle.render.fragment import (
    AddCardRow,
    CardPicker,
    CardPickerEntry,
    DashboardCard,
    DashboardGrid,
    DashboardNotice,
    FragmentRenderer,
    Sequence,
    WorkspaceContextSelector,
    WorkspaceDrawer,
    WorkspacePrimaryAction,
    WorkspaceShell,
    WorkspaceToolbar,
)
from dazzle_back.runtime.renderers.dual_path import diff_summary
from dazzle_ui.runtime.template_renderer import create_jinja_env


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
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


def _legacy_render(workspace, catalog, primary_actions=None, fold_count=0):
    env = create_jinja_env()
    return env.get_template("workspace/_content.html").render(
        workspace=workspace,
        catalog=catalog,
        primary_actions=primary_actions or [],
        fold_count=fold_count,
    )


def _typed_render(shell: WorkspaceShell) -> str:
    """Compose the WorkspaceShell + sibling WorkspaceDrawer (matches
    the legacy `_content.html` shape — drawer is a top-level sibling
    of the workspace div, not nested)."""
    r = FragmentRenderer()
    return r.render(shell) + r.render(WorkspaceDrawer())


def test_content_html_basic_byte_equivalence() -> None:
    """Two-card grid with primary actions, mixed eager/lazy, with
    eyebrow + notice band on one card. No context selector, no SSE."""
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
    catalog = [
        {"name": "tasks", "title": "Tasks", "entity": "Task", "display": "LIST"},
        {"name": "metrics", "title": "Metrics", "entity": "Metric", "display": "METRICS"},
    ]
    ws = _LegacyWorkspace(
        name="dashboard",
        title="My Dashboard",
        regions=regions,
        sse_url="",
        context_options_url="",
        context_selector_label="",
        context_selector_entity="",
    )
    legacy = _legacy_render(
        ws,
        catalog,
        primary_actions=[{"label": "New ticket", "route": "/api/tickets/new"}],
        fold_count=1,
    )

    typed_cards = (
        DashboardCard(
            card_id="card-0",
            name="tasks",
            title="My Tasks",
            display="LIST",
            col_span=6,
            row_order=0,
            eager=True,
            hx_endpoint="/api/workspaces/dashboard/regions/tasks",
        ),
        DashboardCard(
            card_id="card-1",
            name="kanban",
            title="Board",
            display="KANBAN",
            col_span=12,
            row_order=1,
            eager=False,
            eyebrow="Active",
            hx_endpoint="/api/workspaces/dashboard/regions/kanban",
            notice=DashboardNotice(title="Beta", body="still rolling out", tone="warning"),
        ),
    )
    picker = CardPicker(
        entries=tuple(
            CardPickerEntry(
                name=c["name"],
                title=c["title"],
                entity=c["entity"],
                display=c["display"],
            )
            for c in catalog
        ),
        catalog_json=json.dumps(catalog, sort_keys=True),
    )
    shell = WorkspaceShell(
        workspace_name="dashboard",
        title="My Dashboard",
        primary_actions=(WorkspacePrimaryAction(label="New ticket", route="/api/tickets/new"),),
        fold_count=1,
        body=Sequence(
            children=(
                WorkspaceToolbar(),
                DashboardGrid(cards=typed_cards),
                AddCardRow(picker=picker),
            )
        ),
    )
    assert diff_summary(legacy, _typed_render(shell)) is None


def test_content_html_with_context_selector_and_sse_byte_equivalence() -> None:
    """Workspace with a context selector + SSE-enabled grid + lazy-only
    cards. Tests that WorkspaceContextSelector composes cleanly inside
    the WorkspaceShell.body Sequence and that the per-card SSE
    triggers compose with the grid-level sse-connect attr."""
    regions = [_LegacyRegion("alerts", "Alerts", "LIST", 12)]
    catalog: list[dict[str, str]] = []
    ws = _LegacyWorkspace(
        name="ops_dash",
        title="Ops",
        regions=regions,
        sse_url="/api/sse/ops",
        context_options_url="/api/contexts/tenant",
        context_selector_label="Tenant",
        context_selector_entity="tenant",
    )
    legacy = _legacy_render(ws, catalog, fold_count=0)

    typed_cards = (
        DashboardCard(
            card_id="card-0",
            name="alerts",
            title="Alerts",
            display="LIST",
            col_span=12,
            row_order=0,
            eager=False,
            sse_enabled=True,
            hx_endpoint="/api/workspaces/ops_dash/regions/alerts",
        ),
    )
    picker = CardPicker(entries=(), catalog_json=json.dumps(catalog, sort_keys=True))
    shell = WorkspaceShell(
        workspace_name="ops_dash",
        title="Ops",
        fold_count=0,
        body=Sequence(
            children=(
                WorkspaceContextSelector(
                    workspace_name="ops_dash",
                    options_url="/api/contexts/tenant",
                    label="Tenant",
                ),
                WorkspaceToolbar(),
                DashboardGrid(cards=typed_cards, sse_url="/api/sse/ops"),
                AddCardRow(picker=picker),
            )
        ),
    )
    assert diff_summary(legacy, _typed_render(shell)) is None


def test_content_html_empty_workspace_byte_equivalence() -> None:
    """Empty-regions workspace — no cards in the grid, empty catalog
    in the picker. The chrome (heading, toolbar, empty grid, add-card
    row, drawer) all still emit."""
    catalog: list[dict[str, str]] = []
    ws = _LegacyWorkspace(
        name="blank",
        title="Blank",
        regions=[],
        sse_url="",
        context_options_url="",
        context_selector_label="",
        context_selector_entity="",
    )
    legacy = _legacy_render(ws, catalog)

    picker = CardPicker(entries=(), catalog_json="[]")
    shell = WorkspaceShell(
        workspace_name="blank",
        title="Blank",
        fold_count=0,
        body=Sequence(
            children=(
                WorkspaceToolbar(),
                DashboardGrid(cards=()),
                AddCardRow(picker=picker),
            )
        ),
    )
    assert diff_summary(legacy, _typed_render(shell)) is None


def test_sequence_primitive_emits_no_wrapper() -> None:
    """The Sequence primitive concatenates rendered children with no
    surrounding markup — distinct from Stack/Row/Grid which all wrap
    in a `<div>`. Smoke test: rendering a Sequence of two Texts
    should equal concatenation of their individual renders."""
    from dazzle.render.fragment import Text

    r = FragmentRenderer()
    children = (Text("hello"), Text("world"))
    seq = Sequence(children=children)
    expected = "".join(r.render(c) for c in children)
    assert r.render(seq) == expected
    assert "<div" not in r.render(seq).split(">", 1)[0]
