"""#1677: command_center first paint SSRs the fold, not skeleton-only."""

from __future__ import annotations

from types import SimpleNamespace

from dazzle.page.runtime.workspace_renderer import (
    RegionContext,
    WorkspaceContext,
    render_workspace_content_typed,
)
from dazzle.render.fragment import DashboardCard, FragmentRenderer


def _card(**kw: object) -> DashboardCard:
    base: dict[str, object] = {
        "card_id": "card-0",
        "name": "week_energy",
        "title": "Week energy",
        "display": "metrics",
        "col_span": 1,
        "row_order": 0,
        "hx_endpoint": "/api/workspaces/daily_board/regions/week_energy",
        "eager": True,
    }
    base.update(kw)
    return DashboardCard(**base)  # type: ignore[arg-type]


def test_ssr_html_skips_skeleton_and_load_trigger() -> None:
    html = FragmentRenderer().render(_card(ssr_html="<div data-dz-metric>Avg Kw 360.1</div>"))
    assert "Avg Kw 360.1" in html
    assert "dz-card-skeleton" not in html
    assert 'hx-trigger="load"' not in html
    assert 'hx-get="/api/workspaces/daily_board/regions/week_energy"' in html


def test_eager_without_ssr_still_skeleton_plus_load() -> None:
    html = FragmentRenderer().render(_card())
    assert "dz-card-skeleton" in html
    assert 'hx-trigger="load"' in html


def test_ssr_keeps_poll_refresh() -> None:
    html = FragmentRenderer().render(_card(ssr_html="<p>ok</p>", refresh_interval=30))
    assert 'hx-trigger="every 30s"' in html
    assert "load" not in html.split("hx-trigger")[1].split(">")[0]


def test_workspace_fold_ssr_bodies_land_in_first_cards() -> None:
    ws = WorkspaceContext(
        name="daily_board",
        title="Daily board",
        stage="command_center",
        regions=[
            RegionContext(name="board_pulse", title="Pulse", display="metrics", source="Finding"),
            RegionContext(name="week_energy", title="Week", display="metrics", source="Reading"),
            RegionContext(
                name="export_trend", title="Trend", display="line_chart", source="Reading"
            ),
            RegionContext(name="suspect_days", title="Suspect", display="queue", source="Finding"),
        ],
    )
    html = render_workspace_content_typed(
        workspace=ws,
        catalog=[],
        fold_count=3,
        primary_actions=[],
        ssr_bodies={
            "board_pulse": "<span>open findings</span>",
            "week_energy": "<span>Avg Kw 360.1</span>",
            "export_trend": "<span>trend-ssr</span>",
        },
    )
    assert "open findings" in html
    assert "Avg Kw 360.1" in html
    assert "trend-ssr" in html
    # Below-the-fold card is still a skeleton + intersect.
    assert "dz-card-skeleton" in html
    assert 'hx-trigger="intersect once"' in html
    # SSR cards must not fire load (would refetch first paint).
    assert html.count('hx-trigger="load"') == 0


def test_region_ctxs_for_names_preserves_order() -> None:
    from dazzle.http.runtime.workspace_context import (
        region_ctxs_for_names,
        register_workspace_region_ctxs,
    )

    app = SimpleNamespace(state=SimpleNamespace())
    a = SimpleNamespace(ctx_region=SimpleNamespace(name="a"))
    b = SimpleNamespace(ctx_region=SimpleNamespace(name="b"))
    register_workspace_region_ctxs(app, "daily_board", [a, b])  # type: ignore[arg-type]
    out = region_ctxs_for_names(app, "daily_board", ["b", "a"])
    assert [c.ctx_region.name for c in out] == ["b", "a"]
