"""Dashboard-card leftover include_closed / as_of (cycle 2183).

``_emit_dashboard_card`` hx-get used to be the bare
``{hx_endpoint}``. Valid ``include_closed`` / ``as_of`` were
dropped, so SSE / poll / lazy-load invented open-only / current.
Leftover junk (zzz / 2abc / maybe / not-a-date) must not invent.
Valid true / YYYY-MM-DD must ride hx-get. Rest-state gallery
unchanged (oral #33). Not leftover cohort-strip lens / kanban
Load all / DateRangePicker / FilterBar / search chrome / sentinel
/ pagination / CSV / sort-header echo, not leftover list
include_closed clone, not related-tab as_of, not DETAIL as_of
onto the edit form.
"""

from __future__ import annotations

from pathlib import Path

from dazzle.page.runtime.workspace_renderer import (
    WorkspaceContext,
    render_workspace_content_typed,
)
from dazzle.render.fragment import DashboardCard, FragmentRenderer
from dazzle.render.fragment.renderer._render_interactive import leftover_honest_temporal_query

_PAGE_ROUTES = (
    Path(__file__).resolve().parents[2] / "src" / "dazzle" / "http" / "runtime" / "page_routes.py"
)
_RENDERER = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "page"
    / "runtime"
    / "workspace_renderer.py"
)
_EMIT = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "render"
    / "fragment"
    / "renderer"
    / "_render_dashboard.py"
)
_CONTRACT = (
    Path(__file__).resolve().parents[2]
    / "packages"
    / "hatchi-maxchi"
    / "contracts"
    / "dashboard_card.py"
)
_DUAL_PANE = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "page"
    / "runtime"
    / "dual_pane_master_detail.py"
)


def _render(include_closed: str = "", as_of: str = "") -> str:
    return FragmentRenderer().render(
        DashboardCard(
            card_id="card-0",
            name="recent",
            title="Recent",
            display="LIST",
            col_span=6,
            row_order=0,
            hx_endpoint="/api/workspaces/dash/regions/recent",
            eager=True,
            include_closed=include_closed,
            as_of=as_of,
        )
    )


def _card_hx_get(html: str) -> str:
    marker = 'id="region-recent-card-0"'
    assert marker in html
    chunk = html.split(marker, 1)[1]
    assert "hx-get=" in chunk
    return chunk.split("hx-get=", 1)[1].split(" ", 1)[0].strip("\"'")


def test_dashboard_card_echoes_leftover_honest_include_closed() -> None:
    href = _card_hx_get(_render(include_closed="true"))
    assert "include_closed=true" in href
    assert "include_closed=true" in _card_hx_get(_render(include_closed="1"))
    assert "include_closed=true" in _card_hx_get(_render(include_closed="YES"))


def test_dashboard_card_echoes_leftover_honest_as_of() -> None:
    href = _card_hx_get(_render(as_of="2026-01-15"))
    assert "as_of=2026-01-15" in href


def test_dashboard_card_leftover_junk_does_not_invent() -> None:
    junk_ic = _card_hx_get(_render(include_closed="zzz"))
    assert "include_closed" not in junk_ic
    assert junk_ic == "/api/workspaces/dash/regions/recent"
    assert "include_closed" not in _card_hx_get(_render(include_closed="2abc"))
    assert "include_closed" not in _card_hx_get(_render(include_closed="maybe"))
    assert "include_closed" not in _card_hx_get(_render(include_closed="false"))
    junk_ao = _card_hx_get(_render(as_of="not-a-date"))
    assert "as_of" not in junk_ao
    assert "as_of" not in _card_hx_get(_render(as_of="2abc"))
    assert "as_of" not in _card_hx_get(_render(as_of="zzz"))
    assert "as_of" not in _card_hx_get(_render(as_of="2026-13-40"))


def test_dashboard_card_empty_temporal_omits() -> None:
    href = _card_hx_get(_render())
    assert "include_closed" not in href
    assert "as_of" not in href
    assert href == "/api/workspaces/dash/regions/recent"


def test_dashboard_card_endpoint_still_rides_with_temporal() -> None:
    html = _render(include_closed="true", as_of="2026-01-15")
    href = _card_hx_get(html)
    assert href.startswith("/api/workspaces/dash/regions/recent?")
    assert "include_closed=true" in href
    assert "as_of=2026-01-15" in href
    assert 'hx-trigger="load"' in html


def test_workspace_typed_threads_leftover_honest_pair() -> None:
    ws = WorkspaceContext(
        name="dash",
        title="Dashboard",
        regions=[
            {
                "name": "recent",
                "title": "Recent",
                "display": "list",
                "source": "Task",
                "col_span": 6,
                "eyebrow": "",
                "notice": {},
            }
        ],
        fold_count=1,
    )
    html = render_workspace_content_typed(
        workspace=ws,
        catalog=[],
        fold_count=1,
        primary_actions=[],
        include_closed="true",
        as_of="2026-01-15",
    )
    href = _card_hx_get(html)
    assert "include_closed=true" in href
    assert "as_of=2026-01-15" in href
    empty = render_workspace_content_typed(
        workspace=ws,
        catalog=[],
        fold_count=1,
        primary_actions=[],
    )
    assert "include_closed" not in _card_hx_get(empty)
    assert "as_of" not in _card_hx_get(empty)


def test_leftover_honest_query_helper() -> None:
    assert leftover_honest_temporal_query("true", "2026-01-15") == (
        "include_closed=true&amp;as_of=2026-01-15"
    )
    assert leftover_honest_temporal_query("zzz", "not-a-date") == ""
    assert leftover_honest_temporal_query("", "") == ""


def test_emit_source_pins_leftover_honest_echo() -> None:
    src = _EMIT.read_text(encoding="utf-8")
    emit = src.split("def _emit_dashboard_card")[1].split("def ", 1)[0]
    assert "_with_leftover_honest_temporal" in emit
    assert "include_closed" in emit
    assert "as_of" in emit
    assert "cycle 2183" in emit
    assert "must not invent" in emit


def test_renderer_source_pins_leftover_honest_echo() -> None:
    src = _RENDERER.read_text(encoding="utf-8")
    block = src.split("def render_workspace_content_typed")[1].split("def ", 1)[0]
    assert "include_closed=include_closed" in block
    assert "as_of=as_of" in block
    assert "cycle 2183" in block


def test_page_route_source_pins_leftover_honest_echo() -> None:
    src = _PAGE_ROUTES.read_text(encoding="utf-8")
    block = src.split("workspace_inner = render_workspace_content_typed")[1].split(
        "# Fragment targeting", 1
    )[0]
    assert 'query_params.get("include_closed"' in block
    assert 'query_params.get("as_of"' in block
    assert "cycle 2183" in block


def test_dashboard_card_contract_pins_temporal_leftover_honesty() -> None:
    src = _CONTRACT.read_text(encoding="utf-8")
    assert "include_closed" in src
    assert "as_of" in src
    assert "2183" in src


def test_edit_form_still_does_not_time_travel_or_include_closed() -> None:
    """Do not clone leftover list include_closed / related-tab as_of onto edit."""
    src = _PAGE_ROUTES.read_text(encoding="utf-8")
    edit = src.split("async def _handle_edit_form")[1].split("async def ")[0]
    assert "_detail_as_of" not in edit
    assert "_related_tab_as_of_raw" not in edit
    assert "as_of=" not in edit
    assert "as_of_raw=" not in edit
    assert "include_closed" not in edit


def test_dual_pane_list_hx_get_now_echoes_temporal() -> None:
    """Class-close (oral #67): dual-pane list pane rides the same
    leftover-honest pair. Do not seed another hx-get sibling."""
    src = _DUAL_PANE.read_text(encoding="utf-8")
    assert "_with_leftover_honest_temporal" in src
    assert "include_closed" in src
    assert "as_of" in src
    emit = src.split("def render_master_detail_shell")[1].split("return (", 1)[1]
    assert "list_hx" in emit
    assert 'hx-get="{list_hx}"' in emit
