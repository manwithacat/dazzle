"""display: map must not dump empty pins while devices exist (oral #167)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from dazzle.core.project import load_project
from dazzle.http.runtime.workspace_region_render import (
    _LIST_FAMILY,
    _TYPED_REGION_DISPLAYS,
    RegionRenderInputs,
    RenderEnv,
    _build_list_adapter_ctx,
)
from dazzle.render.fragment.region import WorkspaceRegionAdapter
from dazzle.render.fragment.region._builders_metrics import _map_markers_from_items
from dazzle.render.fragment.renderer import FragmentRenderer


class _FakeMap:
    name = "device_map"
    title = "Device map"
    display = "map"
    empty_message = "No devices registered"


def _fieldtest_device_map():
    spec = load_project(Path("examples/fieldtest_hub"))
    for ws in spec.workspaces:
        for region in ws.regions:
            if region.name == "device_map":
                return spec, region
    raise AssertionError("fieldtest_hub device_map missing")


def test_fieldtest_device_map_is_map() -> None:
    _spec, region = _fieldtest_device_map()
    assert str(getattr(region.display, "value", region.display)) == "map"
    assert region.source == "Device"


def test_map_is_on_typed_http_whitelist() -> None:
    assert "MAP" in _LIST_FAMILY
    assert "MAP" in _TYPED_REGION_DISPLAYS


def test_device_items_emit_status_pins() -> None:
    items = [
        {"id": "d1", "name": "Probe-01", "status": "active"},
        {"id": "d2", "name": "Gateway-07", "status": "recalled"},
        {"id": "d99", "name": "zzz", "status": "prototype"},
    ]
    markers = _map_markers_from_items(items)
    labels = [m.label for m in markers]
    assert labels == ["Probe-01", "Gateway-07", "zzz"]
    assert [m.tone for m in markers] == ["success", "danger", "warning"]


def test_empty_items_do_not_invent_leftover_pins() -> None:
    assert _map_markers_from_items([]) == []
    assert _map_markers_from_items([{"id": "ghost", "status": "active"}]) == []


def test_map_html_renders_pins_not_empty() -> None:
    items = [
        {"id": "d1", "name": "Probe-01", "status": "active"},
        {"id": "d2", "name": "Gateway-07", "status": "recalled"},
        {"id": "d99", "name": "zzz", "status": "prototype"},
    ]
    html = FragmentRenderer().render(
        WorkspaceRegionAdapter().build(  # type: ignore[arg-type]
            _FakeMap(),
            {"items": items, "empty_message": "No devices registered"},
        )
    )
    assert 'class="dz-map"' in html
    assert "data-dz-marker" in html
    assert "Probe-01" in html
    assert "Gateway-07" in html
    assert "zzz" in html
    assert "No devices registered" not in html
    assert "No locations." not in html


def test_list_adapter_ctx_forwards_map_items() -> None:
    items = [{"id": "d1", "name": "Probe-01", "status": "active"}]
    ctx_region = SimpleNamespace(
        name="device_map",
        empty_message="No devices registered",
        status_entries=[],
        endpoint="/api/workspaces/engineering_dashboard/regions/device_map",
    )
    ctx = SimpleNamespace(
        ctx_region=ctx_region,
        source="Device",
        surface_empty_message=None,
        ir_region=None,
        detail_url_template="",
        entity_detail_urls={},
    )
    env = RenderEnv(
        ctx=ctx,  # type: ignore[arg-type]
        ir_region=None,
        inputs=RegionRenderInputs(items=items),
        request=SimpleNamespace(query_params={}),
        user_ctx=SimpleNamespace(auth_ctx_for_filters=None, user_id=None),  # type: ignore[arg-type]
        sort=None,
        sort_dir="asc",
    )
    out = _build_list_adapter_ctx("MAP", env, {})
    assert out["items"] == items
    assert out["empty_message"] == "No devices registered"
    assert "zzz" not in str(out["items"])
