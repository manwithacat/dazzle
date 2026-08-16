"""dual_pane_flow → master-detail Hyperpart emission + pair detection."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from dazzle.page.runtime.dual_pane_master_detail import (
    detect_dual_pane_master_detail_pair,
    master_detail_item_endpoint,
    master_detail_pane_id,
    render_master_detail_shell,
)
from dazzle.page.runtime.workspace_renderer import (
    RegionContext,
    WorkspaceContext,
    render_workspace_content_typed,
)
from dazzle.render.fragment.renderer._data_row import drill_row_attrs

pytestmark = pytest.mark.gate


def test_detect_same_source_list_detail() -> None:
    regions = [
        SimpleNamespace(name="search", display="SEARCH_BOX", source="Contact"),
        SimpleNamespace(name="contact_list", display="LIST", source="Contact"),
        SimpleNamespace(name="contact_detail", display="DETAIL", source="Contact"),
    ]
    pair = detect_dual_pane_master_detail_pair("dual_pane_flow", regions)
    assert pair is not None
    assert pair.list_region == "contact_list"
    assert pair.detail_region == "contact_detail"
    assert pair.source == "Contact"


def test_detect_ignores_non_dual_pane_stage() -> None:
    regions = [
        SimpleNamespace(name="a", display="LIST", source="X"),
        SimpleNamespace(name="b", display="DETAIL", source="X"),
    ]
    assert detect_dual_pane_master_detail_pair("monitor_wall", regions) is None


def test_detect_requires_both_list_and_detail() -> None:
    regions = [
        SimpleNamespace(name="a", display="LIST", source="X"),
        SimpleNamespace(name="b", display="LIST", source="X"),
    ]
    assert detect_dual_pane_master_detail_pair("dual_pane_flow", regions) is None


def test_master_detail_item_endpoint_template() -> None:
    ep = master_detail_item_endpoint("contacts", "contact_detail")
    assert ep == "/api/workspaces/contacts/regions/contact_detail?id={id}"
    assert ep.format(id="abc-1") == "/api/workspaces/contacts/regions/contact_detail?id=abc-1"


def test_render_master_detail_shell_has_contract_markers() -> None:
    html = render_master_detail_shell(
        list_region="contact_list",
        list_title="Contacts",
        list_endpoint="/api/workspaces/contacts/regions/contact_list",
        detail_region="contact_detail",
        detail_title="Detail",
        detail_endpoint_base="/api/workspaces/contacts/regions/contact_detail",
    )
    assert "data-dz-master-detail" in html
    assert "data-dz-master-detail-list-body" in html
    assert "data-dz-master-detail-detail-body" in html
    # List body is the swap root for region HTMX chrome (list-search q= filter).
    assert "data-dz-region" in html
    assert 'data-dz-region-name="contact_list"' in html
    assert 'id="region-contact_list-md-list"' in html or 'id="region-contact_list-' in html
    assert f'id="{master_detail_pane_id("contact_detail")}"' in html
    assert "hx-get=" in html
    assert "Select an item" in html
    assert "include_closed" not in html
    assert "as_of" not in html


def _list_pane_hx_get(html: str) -> str:
    marker = 'data-dz-master-detail-list-body="true"'
    assert marker in html
    chunk = html.split(marker, 1)[1]
    assert "hx-get=" in chunk
    return chunk.split("hx-get=", 1)[1].split(" ", 1)[0].strip("\"'")


def test_master_detail_list_echoes_leftover_honest_temporal() -> None:
    """Cycle 2183 class-close: list pane load rides valid pair; junk omits."""
    honest = render_master_detail_shell(
        list_region="contact_list",
        list_title="Contacts",
        list_endpoint="/api/workspaces/contacts/regions/contact_list",
        detail_region="contact_detail",
        detail_title="Detail",
        detail_endpoint_base="/api/workspaces/contacts/regions/contact_detail",
        include_closed="true",
        as_of="2026-01-15",
    )
    href = _list_pane_hx_get(honest)
    assert href.startswith("/api/workspaces/contacts/regions/contact_list?")
    assert "include_closed=true" in href
    assert "as_of=2026-01-15" in href

    junk = render_master_detail_shell(
        list_region="contact_list",
        list_title="Contacts",
        list_endpoint="/api/workspaces/contacts/regions/contact_list",
        detail_region="contact_detail",
        detail_title="Detail",
        detail_endpoint_base="/api/workspaces/contacts/regions/contact_detail",
        include_closed="zzz",
        as_of="not-a-date",
    )
    junk_href = _list_pane_hx_get(junk)
    assert junk_href == "/api/workspaces/contacts/regions/contact_list"
    assert "include_closed" not in junk_href
    assert "as_of" not in junk_href


def test_workspace_typed_threads_temporal_onto_master_detail() -> None:
    pytest.importorskip("fastapi")
    ws = WorkspaceContext(
        name="contacts",
        title="Contacts",
        stage="dual_pane_flow",
        regions=[
            RegionContext(
                name="contact_list",
                title="Contact list",
                source="Contact",
                display="LIST",
                col_span=6,
            ),
            RegionContext(
                name="contact_detail",
                title="Contact detail",
                source="Contact",
                display="DETAIL",
                col_span=6,
            ),
        ],
    )
    html = render_workspace_content_typed(
        ws,
        catalog=[],
        fold_count=4,
        primary_actions=[],
        include_closed="true",
        as_of="2026-01-15",
    )
    href = _list_pane_hx_get(html)
    assert "include_closed=true" in href
    assert "as_of=2026-01-15" in href


def test_pane_drill_row_attrs_target_detail_pane() -> None:
    full = drill_row_attrs("/app/contact/1")
    assert 'hx-target="#main-content"' in full
    assert "hx-push-url" in full

    pane = drill_row_attrs(
        "/api/workspaces/c/regions/d?id=1",
        pane=True,
        pane_target="#dz-md-detail-contact_detail",
    )
    assert 'hx-target="#dz-md-detail-contact_detail"' in pane
    assert "closest" not in pane  # cousin pane is not reachable via closest
    assert "hx-push-url" not in pane
    assert 'hx-target="#main-content"' not in pane
    assert "load once" not in pane
    assert "aria-current" not in pane

    auto = drill_row_attrs(
        "/api/workspaces/c/regions/d?id=1",
        pane=True,
        auto_load=True,
        pane_target="#dz-md-detail-contact_detail",
    )
    assert "load once" in auto
    assert 'aria-current="true"' in auto


def test_workspace_typed_render_emits_master_detail_for_dual_pane() -> None:
    pytest.importorskip("fastapi")
    ws = WorkspaceContext(
        name="contacts",
        title="Contacts",
        stage="dual_pane_flow",
        regions=[
            RegionContext(
                name="contact_list",
                title="Contact list",
                source="Contact",
                display="LIST",
                col_span=6,
            ),
            RegionContext(
                name="contact_detail",
                title="Contact detail",
                source="Contact",
                display="DETAIL",
                col_span=6,
            ),
        ],
    )
    html = render_workspace_content_typed(
        ws,
        catalog=[],
        fold_count=4,
        primary_actions=[],
    )
    assert "data-dz-master-detail" in html
    assert "data-dz-master-detail-list-body" in html
    assert "data-dz-master-detail-detail-body" in html
    # Pair is not also emitted as free dashboard cards for those regions.
    assert 'data-card-region="contact_list"' not in html or "md-list" in html
    assert "contact_list" in html
    assert "contact_detail" in html


def test_workspace_typed_render_no_master_detail_without_pair() -> None:
    pytest.importorskip("fastapi")
    ws = WorkspaceContext(
        name="ops",
        title="Ops",
        stage="dual_pane_flow",
        regions=[
            RegionContext(name="a", title="A", source="Ticket", display="LIST", col_span=6),
            RegionContext(name="b", title="B", source="Comment", display="LIST", col_span=6),
        ],
    )
    html = render_workspace_content_typed(ws, catalog=[], fold_count=4, primary_actions=[])
    assert "data-dz-master-detail" not in html
